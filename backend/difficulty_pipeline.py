"""难度量化 Pipeline 主控 — 特征分析评分。

v2: 特征提取 + 规则评分 + Gemini representation 合并 + 动态 confidence
v3.1: 大题结构化拆分评估（total_score >= 8 → 结构化提取 → 聚合 → 评分）
设计文档: docs/plans/2026-03-28-difficulty-v3.1-design.md
"""
import asyncio
from feature_extractor import extract_features, extract_big_question_features, DEFAULT_FEATURES
from rule_scorer import compute_difficulty, score_to_label, aggregate_big_question
from logger import get_logger

logger = get_logger()


class DifficultyPipeline:
    """难度量化 Pipeline。v3.1: 大题结构化拆分评估。"""

    def __init__(self, **kwargs):
        """初始化。接受 kwargs 以兼容旧调用方 DifficultyEngine(gemini_analyzer=...) 签名。"""
        pass

    async def _evaluate_single(self, question: dict, **kwargs) -> dict:
        """评估单道题难度。

        Args:
            question: dict，需包含 content, question_type, correct_answer, total_score
            **kwargs: analysis_result=Gemini 分析结果（含 representation 字段）

        Returns:
            dict: 兼容旧接口 + 新增 features/flags/confidence 字段
        """
        question_text = question.get("content", "")
        correct_answer = question.get("correct_answer", "")
        total_score = float(question.get("total_score", 1))
        options = question.get("options", "")
        question_type = question.get("question_type", "")

        if not question_text:
            logger.warning("题目内容为空，跳过难度评估")
            return self._default_result()

        # 拼接选项（options 可能是 dict 或字符串）
        options_text = ""
        if isinstance(options, dict):
            options_text = " ".join(f"{k}.{v}" for k, v in sorted(options.items()))
        elif isinstance(options, list):
            options_text = " ".join(str(o) for o in options)
        elif isinstance(options, str) and options:
            options_text = options

        full_text = question_text
        if options_text:
            full_text = f"{question_text}\n{options_text}"

        # ── v3.1 大题分流 ──
        is_big_question = total_score >= 8
        big_question_fallback = False

        if is_big_question:
            logger.info(f"[v3.1] 大题模式 (total_score={total_score}): {question_text[:50]}...")
            structured = await extract_big_question_features(
                full_text, "", correct_answer, question_type)

            if structured is not None:
                # A-003: points 总和校验
                sq_points_sum = sum(sq["points"] for sq in structured["subquestions"])
                if total_score > 0 and abs(sq_points_sum - total_score) / total_score > 0.2:
                    logger.warning(f"[v3.1] 小问分值和({sq_points_sum})与总分({total_score})偏差>20%，fallback")
                    structured = None
                    big_question_fallback = True

            if structured is not None:
                aggregated = aggregate_big_question(
                    structured["subquestions"],
                    structured["dependencies"],
                    structured["global_features"],
                )
                features = {
                    "working_memory": aggregated["working_memory"],
                    "reasoning_steps": round(aggregated["effective_steps"]),
                    "chain_coupling": aggregated["chain_coupling"],
                    "trap_density": aggregated["trap_density"],
                    "novelty": aggregated["novelty"],
                    "knowledge_breadth": aggregated["knowledge_breadth"],
                }
                features.update(structured.get("report", {}))
                features["_big_question"] = {
                    "subquestions": structured["subquestions"],
                    "dependencies": structured["dependencies"],
                    "global_features": structured["global_features"],
                    "effective_steps": aggregated["effective_steps"],
                }
            else:
                if not big_question_fallback:
                    big_question_fallback = True
                logger.warning("[v3.1] 结构化解析失败，fallback 到 v3 原路径")

        if not is_big_question or big_question_fallback:
            logger.info(f"开始特征提取: {question_text[:50]}...")
            features = await extract_features(full_text, "", correct_answer, question_type)
            logger.info(f"特征提取完成: {features}")

        # Stage 2.5: 合并 Gemini representation
        flags = []
        if big_question_fallback:
            flags.append("big_question_fallback")
        analysis_result = kwargs.get("analysis_result") or {}
        features, flags = self._merge_representation(features, analysis_result, flags)

        # Stage 3: 规则评分
        if is_big_question and not big_question_fallback:
            score_features = dict(features)
            score_features["reasoning_steps"] = features["_big_question"]["effective_steps"]
            score_features["chain_coupling"] = 1  # 不让 coupling 再乘一次
            raw_score = compute_difficulty(score_features)
        else:
            raw_score = compute_difficulty(features)

        from calibration import calibrate
        score = calibrate(raw_score)
        label = score_to_label(score)
        logger.info(f"规则评分: raw={raw_score} calibrated={score} ({label})"
                    + (" [v3.1 大题]" if is_big_question and not big_question_fallback else ""))

        confidence = self._compute_confidence(features, flags)
        if big_question_fallback:
            confidence = max(0.2, confidence - 0.15)

        # bloom 1-6 → cognitive_level 0-10（向后兼容旧前端/报告/预测）
        bloom = features.get("bloom", 3)
        cognitive_level = round(bloom / 6.0 * 10.0, 1)

        return {
            # 旧字段（main.py / prediction_service.py / 前端 消费）
            "base_difficulty": score,
            "final_difficulty": score,
            "difficulty_label": label,
            "cognitive_level": cognitive_level,
            "score_distribution_by_difficulty": self._score_distribution(score, total_score),
            # 新字段
            "features": features,
            "raw_score": raw_score,
            "confidence": confidence,
            "predicted_score_rate": None,
            "flags": flags,
        }

    def _merge_representation(self, features: dict, analysis_result: dict,
                              flags: list) -> tuple:
        """合并 Gemini 的 representation 数据到 Claude 特征中。

        只有当 Gemini 说 representation_is_core_to_solving=True 时才覆盖。
        """
        if not analysis_result:
            return features, flags

        gemini_repr = analysis_result.get("representation_complexity")
        gemini_core = analysis_result.get("representation_is_core_to_solving", False)

        if gemini_repr is None:
            return features, flags

        claude_repr = features.get("representation_complexity", 1)

        if gemini_core:
            # Gemini 确认表征参与核心推理 → 用 Gemini 值
            if abs(gemini_repr - claude_repr) > 1:
                flags.append("repr_divergence")
                logger.warning(
                    f"Gemini/Claude representation 分歧: Gemini={gemini_repr} Claude={claude_repr}")
            features["representation_complexity"] = gemini_repr
        else:
            # Gemini 说不参与核心推理 → 取两者较低值
            features["representation_complexity"] = min(claude_repr, gemini_repr)

        return features, flags

    def _compute_confidence(self, features: dict, flags: list) -> float:
        """动态 confidence 计算。"""
        conf = 0.85
        # 触发默认值 → 降低
        default_count = sum(1 for k in ["working_memory", "reasoning_steps", "knowledge_breadth"]
                            if features.get(k) == DEFAULT_FEATURES.get(k))
        conf -= default_count * 0.1
        # 缺少 reason → 降低
        reason_count = sum(1 for k in features if k.endswith("_reason") or k == "steps_detail")
        if reason_count < 5:
            conf -= 0.1
        # 有 flag → 降低
        conf -= len(flags) * 0.05
        return max(0.2, round(conf, 2))

    def _default_result(self):
        """无法评估时的默认返回。"""
        return {
            "base_difficulty": 5.0,
            "final_difficulty": 5.0,
            "difficulty_label": "未评估",
            "score_distribution_by_difficulty": {},
            "features": None,
            "confidence": 0.0,
            "predicted_score_rate": None,
            "flags": ["no_evaluation"],
        }

    def _score_distribution(self, difficulty_score: float, total_score: float) -> dict:
        """从难度分数推导按难度等级的分值分布（兼容旧格式：中文 key）。"""
        if difficulty_score <= 3:
            weights = {"简单": 0.7, "中等": 0.2, "困难": 0.1}
        elif difficulty_score <= 5:
            weights = {"简单": 0.3, "中等": 0.5, "困难": 0.2}
        elif difficulty_score <= 7:
            weights = {"简单": 0.1, "中等": 0.4, "困难": 0.5}
        else:
            weights = {"简单": 0.05, "中等": 0.25, "困难": 0.7}
        return {k: round(v * total_score, 1) for k, v in weights.items()}

    async def evaluate_with_refinement(self, question: dict, **kwargs) -> dict:
        """兼容旧接口名。直接调用 _evaluate_single。"""
        return await self._evaluate_single(question, **kwargs)

    def evaluate_with_refinement_sync(self, question: dict, **kwargs) -> dict:
        """同步版本，供非 async 调用方使用。"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._evaluate_single(question, **kwargs))
        finally:
            loop.close()
