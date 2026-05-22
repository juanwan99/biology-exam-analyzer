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


def _score_record(question: dict) -> tuple[float, dict | None]:
    value = question.get("total_score")
    if isinstance(value, (int, float)):
        if value > 0:
            return float(value), None
        return 0.0, {
            "id": question.get("id"),
            "reason": "non_positive_score",
            "source": "total_score",
            "value": value,
        }
    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value)
        except ValueError:
            return 0.0, {
                "id": question.get("id"),
                "reason": "invalid_score",
                "source": "total_score",
                "value": value,
            }
        if parsed > 0:
            return parsed, None
        return 0.0, {
            "id": question.get("id"),
            "reason": "non_positive_score",
            "source": "total_score",
            "value": parsed,
        }
    return 0.0, {
        "id": question.get("id"),
        "reason": "missing_score",
        "source": "total_score",
        "value": None,
    }


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
        total_score, score_issue = _score_record(question)
        if score_issue:
            logger.error(f"[难度] 题目分值无效，阻断难度评估: Q{question.get('id')} {score_issue['reason']}")
            return self._failed_result(
                score_issue["reason"],
                flags=["score_invalid", score_issue["reason"]],
                features={"score_issue": score_issue},
            )
        options = question.get("options", "")
        question_type = question.get("question_type", "")
        subject = question.get("subject", "biology")

        if not question_text:
            logger.warning("题目内容为空，跳过难度评估")
            return self._default_result()

        media_integrity = question.get("media_integrity")
        if isinstance(media_integrity, dict) and media_integrity.get("status") == "failed":
            warnings = media_integrity.get("warnings") or []
            if not isinstance(warnings, list):
                warnings = []
            logger.error(f"[难度] 媒体证据链不完整，阻断难度评估: Q{question.get('id')}")
            return self._failed_result(
                "media_integrity_failed",
                flags=["media_integrity_failed", *warnings],
                features={"media_integrity": media_integrity},
            )

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
        structured = None

        if is_big_question:
            logger.info(f"[v3.1] 大题模式 (total_score={total_score}): {question_text[:50]}...")
            structured = await extract_big_question_features(
                full_text, "", correct_answer, question_type,
                subject=subject, total_score=total_score, return_failure=True)

            if isinstance(structured, dict) and structured.get("_big_question_failed"):
                failure_type = structured.get("failure_type") or "big_question_structure_failed"
                logger.error(f"[v3.1] 结构化解析失败: {failure_type}")

                # SEU fallback: use v2 analysis scoring_units if available
                analysis_result = kwargs.get("analysis_result") or {}
                fg = analysis_result.get("_fine_grained", {})
                seus = fg.get("scoring_units", []) if isinstance(fg, dict) else []
                if len(seus) >= 2:
                    logger.info(f"[v3.1] SEU fallback: {len(seus)} SEUs available")
                    seu_metrics = self._scoring_unit_metrics(seus)
                    if seu_metrics and seu_metrics["avg_confidence"] >= 0.5:
                        fallback_score = seu_metrics["score"]
                        fallback_score = max(2.0, min(10.0, round(fallback_score, 1)))
                        label = score_to_label(fallback_score)
                        logger.info(f"[v3.1] SEU fallback 评分: {fallback_score} ({label})")
                        return {
                            "base_difficulty": fallback_score,
                            "final_difficulty": fallback_score,
                            "difficulty_label": label,
                            "cognitive_level": round(fallback_score * 0.9, 1),
                            "cognitive_level_source": "linear_approximation",
                            "score_distribution_by_difficulty": self._score_distribution(fallback_score, total_score),
                            "features": {
                                "_feature_status": "seu_fallback",
                                "big_question_failure_type": failure_type,
                                "seu_count": len(seus),
                            },
                            "raw_score": fallback_score,
                            "source": "seu_fallback",
                            "difficulty_source": "seu_fallback",
                            "confidence": min(0.5, round(seu_metrics["avg_confidence"] * 0.5, 2)),
                            "predicted_score_rate": None,
                            "flags": ["seu_fallback", f"original_failure:{failure_type}"],
                            "calibration_status": "not_configured",
                            "calibration_error": None,
                        }
                    else:
                        logger.warning("[v3.1] SEU fallback 置信度不足，仍阻断")

                # No fallback available → hard block as before
                failed_features = dict(structured)
                failed_features["big_question_errors"] = structured.get("errors", [])
                return self._failed_result(
                    failure_type,
                    flags=["big_question_structure_failed", failure_type],
                    features=failed_features,
                )

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
                # 大题结构化成功 → 补充状态字段
                from feature_extractor import SCORING_RANGES
                features["_raw_core_count"] = len([k for k in SCORING_RANGES if k in features])
                features["_feature_status"] = "ok"
                if structured.get("_dropped_deps", 0) > 0:
                    logger.warning(f"[v3.1] {structured['_dropped_deps']} 条依赖因 ID 无效被丢弃")
                if structured.get("_llm_calls"):
                    features["_llm_calls"] = structured["_llm_calls"]
            else:
                logger.error("[v3.1] 结构化解析失败，阻断大题难度评估")
                return self._failed_result("big_question_structure_failed", flags=["big_question_structure_failed"])

        if not is_big_question:
            logger.info(f"开始特征提取: {question_text[:50]}...")
            features = await extract_features(full_text, "", correct_answer, question_type, subject=subject)
            logger.info(f"特征提取完成: {features}")

            # Bloom 优先级：LLM 分析的 bloom_level 优先于特征提取推断
            llm_bloom = kwargs.get("analysis_result", {}).get("bloom_level")
            if isinstance(llm_bloom, (int, float)) and 1 <= llm_bloom <= 6:
                features["bloom"] = int(llm_bloom)

        # Stage 2.5: 合并 Gemini representation
        flags = []
        if is_big_question and structured and structured.get("_dropped_deps", 0) > 0:
            flags.append("dep_partial_invalid")
        analysis_result = kwargs.get("analysis_result") or {}
        features, flags = self._merge_representation(features, analysis_result, flags)
        features, flags = self._merge_media_representation(features, question, is_big_question, flags)

        # Stage 3: 规则评分（消费 _feature_status 四态）
        feature_status = features.get("_feature_status", "ok")
        difficulty_source = "rule_scorer"

        if feature_status == "failed":
            logger.error("[难度] 特征提取失败，阻断难度评估")
            return self._failed_result(
                "feature_extraction_failed",
                flags=["feature_extraction_failed"],
                features=features,
            )
        elif is_big_question:
            score_features = dict(features)
            score_features["reasoning_steps"] = features["_big_question"]["effective_steps"]
            score_features["chain_coupling"] = features.get("chain_coupling", 1)
            raw_score = compute_difficulty(score_features)
        else:
            raw_score = compute_difficulty(features)

        raw_score, fg_flags = self._apply_fine_grained_adjustments(
            raw_score,
            features,
            analysis_result,
            is_big_question=is_big_question,
            total_score=total_score,
        )
        flags.extend(fg_flags)

        score = raw_score
        calibration_status = "not_configured"
        calibration_error = None

        # 校准修正
        try:
            from calibration_service import get_correction
            correction = get_correction(score)
            calibration_status = "checked"
            if correction != 0:
                score = max(0, min(10, score + correction))
                calibration_status = "applied"
                logger.debug(f"[校准] 难度修正 {correction:+.2f} -> {score:.2f}")
        except ModuleNotFoundError as exc:
            calibration_error = str(exc)
            calibration_status = "not_configured"
        except Exception as exc:
            calibration_error = str(exc)
            calibration_status = "failed"
            flags.append("calibration_failed")
            logger.error(f"[校准] 难度校准失败: {exc}", exc_info=True)

        label = score_to_label(score)
        logger.info(f"规则评分: raw={raw_score} calibrated={score} ({label})"
                    + (" [v3.1 大题]" if is_big_question else ""))

        # P4: LLM 难度信号一致性检查
        consistency = self._check_llm_difficulty_consistency(score, analysis_result)
        flags.extend(consistency.get("flags", []))

        confidence = self._compute_confidence(features, flags)
        confidence -= consistency.get("confidence_penalty", 0)
        if feature_status == "partial":
            confidence *= 0.7
        elif difficulty_source == "seu_fallback":
            confidence *= 0.5
        elif difficulty_source == "default":
            confidence = 0.2
        confidence = max(0.1, round(confidence, 2))

        # bloom 1-6 → cognitive_level 0-10（非线性，Anderson & Krathwohl 2001）
        bloom = features.get("bloom", 3)
        _BLOOM_COGNITIVE = {1: 1.0, 2: 2.5, 3: 4.5, 4: 6.5, 5: 8.0, 6: 9.5}
        cognitive_level = _BLOOM_COGNITIVE.get(bloom, round(bloom / 6.0 * 10.0, 1))

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
            "source": difficulty_source,
            "difficulty_source": difficulty_source,
            "confidence": confidence,
            "predicted_score_rate": None,
            "flags": flags,
            "calibration_status": calibration_status,
            "calibration_error": calibration_error,
        }

    def _apply_fine_grained_adjustments(self, score: float, features: dict,
                                        analysis_result: dict, *,
                                        is_big_question: bool,
                                        total_score: float) -> tuple:
        """Use SEU/DU evidence as a bounded cross-check for the rule score.

        The adjustment is deliberately generic: it uses scoring-unit demand,
        high-order score share, and diagnostic-unit burden, never question ids
        or real score-rate data.
        """
        fg = analysis_result.get("_fine_grained", {}) if analysis_result else {}
        flags = []
        adjusted = float(score)

        seu_metrics = self._scoring_unit_metrics(fg.get("scoring_units", []))
        if seu_metrics:
            seu_score = seu_metrics["score"]
            high_order_share = seu_metrics["high_order_share"]
            avg_confidence = seu_metrics["avg_confidence"]

            if is_big_question:
                target = 0.58 * adjusted + 0.42 * seu_score + high_order_share * 1.6
                if target > adjusted + 0.05:
                    adjusted = target
                    if high_order_share >= 0.20:
                        flags.append("seu_high_order_adjustment")
                    else:
                        flags.append("seu_crosscheck_adjustment")
            elif total_score <= 2 and avg_confidence >= 0.70:
                # Trap/novelty can be over-additive on bounded choice items.
                # A reliable SEU estimate prevents a single item from becoming
                # "hardest" only because many independent risk labels stacked.
                if adjusted - seu_score > 1.20 and high_order_share < 0.20:
                    adjusted -= 0.45 * (adjusted - seu_score - 1.0)
                    flags.append("seu_extreme_rule_moderation")

        diagnostic_units = fg.get("diagnostic_units", []) if isinstance(fg, dict) else []
        if len(diagnostic_units) >= 3 and adjusted < 6.0:
            adjusted += 1.00
            flags.append("diagnostic_burden_adjustment")

        return round(max(0.0, min(10.0, adjusted)), 1), flags

    def _scoring_unit_metrics(self, scoring_units: list) -> dict | None:
        if not scoring_units:
            return None

        shares = [float(s.get("score_share") or 0) for s in scoring_units]
        if sum(shares) > 0:
            weights = shares
            total_share = sum(shares)
        else:
            weights = [1.0 for _ in scoring_units]
            total_share = float(len(scoring_units))
        avg_confidence = sum(
            float(s.get("allocation_confidence") or 0.5) for s in scoring_units
        ) / len(scoring_units)

        def weighted(field: str, default: float) -> float:
            return sum(
                float(s.get(field) or default) * weight
                for s, weight in zip(scoring_units, weights)
            ) / total_share

        bloom_to_score = {1: 2.5, 2: 4.0, 3: 5.3, 4: 6.5, 5: 7.8, 6: 9.0}
        bloom_score = sum(
            bloom_to_score.get(int(round(float(s.get("bloom_level") or 3))), 5.3)
            * weight
            for s, weight in zip(scoring_units, weights)
        ) / total_share
        difficulty_score = weighted("difficulty_estimate", 5.0)
        high_order_share = sum(
            weight
            for s, weight in zip(scoring_units, weights)
            if float(s.get("difficulty_estimate") or 0) >= 8
            or float(s.get("bloom_level") or 0) >= 6
        ) / total_share

        return {
            "score": 0.62 * difficulty_score + 0.38 * bloom_score,
            "high_order_share": high_order_share,
            "avg_confidence": avg_confidence,
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

    def _merge_media_representation(self, features: dict, question: dict,
                                    is_big_question: bool, flags: list) -> tuple:
        if not is_big_question:
            return features, flags
        content = str(question.get("content") or "")
        has_media = bool(
            question.get("image_base64")
            or question.get("images")
            or question.get("_media_for_ai")
        )
        visual_cue = any(token in content for token in ("图", "表", "曲线", "电泳", "坐标"))
        if has_media and visual_cue and features.get("representation_complexity", 1) < 3:
            features = dict(features)
            features["representation_complexity"] = 3
            flags.append("media_representation_adjustment")
        return features, flags

    def _check_llm_difficulty_consistency(self, rule_score: float, analysis_result: dict) -> dict:
        """P4: 检查规则评分与 LLM 难度信号的一致性（HEURISTIC）。"""
        result = {"flags": [], "confidence_penalty": 0.0}
        if not analysis_result:
            return result

        # 4a: LLM 三级分类 vs rule_score 区间
        llm_diff = analysis_result.get("difficulty", "")
        llm_ranges = {"简单": (1, 4), "中等": (3.5, 7), "困难": (6, 10)}
        if llm_diff in llm_ranges:
            lo, hi = llm_ranges[llm_diff]
            if not (lo <= rule_score <= hi):
                result["flags"].append("rule_llm_mismatch")
                result["confidence_penalty"] += 0.1
                logger.info(f"[P4] rule={rule_score:.1f} vs LLM={llm_diff}({lo}-{hi}): 不一致")

        # 4b: 选项难度离散度 flag
        option_bd = analysis_result.get("option_difficulty_breakdown")
        if isinstance(option_bd, dict) and len(option_bd) >= 2:
            vals = [v for v in option_bd.values() if isinstance(v, (int, float))]
            if len(vals) >= 2:
                import statistics as stats_mod
                stdev = stats_mod.stdev(vals)
                if stdev > 3:
                    trap = analysis_result.get("trap_density", 2)
                    if isinstance(trap, (int, float)) and trap <= 1:
                        result["flags"].append("option_spread_high_trap_low")
                        result["confidence_penalty"] += 0.05

        return result

    def _compute_confidence(self, features: dict, flags: list) -> float:
        """分层 confidence 计算（P2 改造）。"""
        # L1: extraction_confidence（Schema 校验结果）
        ext_conf = features.get("_extraction_confidence", 0.85)
        # L2: consistency_confidence（特征内部一致性）
        cons_conf = features.get("_consistency_confidence", 1.0)

        # 基础 = L1 * L2 权重混合
        conf = ext_conf * 0.6 + cons_conf * 0.4

        # 触发默认值 → 降低
        default_count = sum(1 for k in ["working_memory", "reasoning_steps", "knowledge_breadth"]
                            if features.get(k) == DEFAULT_FEATURES.get(k))
        conf -= default_count * 0.08
        # 缺少 reason → 降低
        reason_count = sum(1 for k in features if k.endswith("_reason") or k == "steps_detail")
        if reason_count < 5:
            conf -= 0.08
        # 有 flag → 降低
        conf -= len(flags) * 0.04
        return max(0.1, round(conf, 2))

    def _default_result(self):
        """无法评估时的默认返回。"""
        return self._failed_result("no_evaluation", flags=["no_evaluation"])

    def _failed_result(self, reason: str, flags: list | None = None, features: dict | None = None) -> dict:
        """Return an explicit failure payload instead of a normal-looking fallback score."""
        failed_features = dict(features or {})
        failed_features["_feature_status"] = "failed"
        failed_features["analysis_failed_reason"] = reason
        return {
            "base_difficulty": None,
            "final_difficulty": None,
            "difficulty_label": "未评估",
            "score_distribution_by_difficulty": {},
            "features": failed_features,
            "raw_score": None,
            "source": "analysis_failed",
            "difficulty_source": "analysis_failed",
            "confidence": 0.0,
            "predicted_score_rate": None,
            "flags": flags or [reason],
            "analysis_failed": True,
            "failure_reason": reason,
        }

    def _score_distribution(self, difficulty_score: float, total_score: float) -> dict:
        """从难度分数推导按难度等级的分值分布。

        阈值与 score_to_label 对齐：≤3.5 简单 / ≤6.5 中等 / >6.5 困难。
        使用线性插值确保相邻区间过渡平滑。
        """
        if difficulty_score <= 2.0:
            weights = {"简单": 0.9, "中等": 0.08, "困难": 0.02}
        elif difficulty_score <= 3.5:
            weights = {"简单": 0.7, "中等": 0.23, "困难": 0.07}
        elif difficulty_score <= 5.0:
            weights = {"简单": 0.3, "中等": 0.6, "困难": 0.1}
        elif difficulty_score <= 6.5:
            t = (difficulty_score - 5.0) / 1.5
            weights = {
                "简单": round(0.2 * (1 - t) + 0.05 * t, 2),
                "中等": round(0.6 * (1 - t) + 0.4 * t, 2),
                "困难": round(0.2 * (1 - t) + 0.55 * t, 2),
            }
        else:
            weights = {"简单": 0.03, "中等": 0.22, "困难": 0.75}
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
