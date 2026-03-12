"""难度量化 Pipeline 主控 — 特征分析评分。

v2: 特征提取 + 规则评分（替代模拟学生 + IRT）
设计文档: docs/plans/2026-03-12-feature-difficulty-design.md
"""
import asyncio
import logging
from feature_extractor import extract_features
from rule_scorer import compute_difficulty, score_to_label

logger = logging.getLogger(__name__)


class DifficultyPipeline:
    """难度量化 Pipeline。v2: 特征分析。"""

    def __init__(self, **kwargs):
        """初始化。接受 kwargs 以兼容旧调用方 DifficultyEngine(gemini_analyzer=...) 签名。"""
        pass

    async def _evaluate_single(self, question: dict, **kwargs) -> dict:
        """评估单道题难度。

        Args:
            question: dict，需包含 content, question_type, correct_answer, total_score
            **kwargs: 兼容旧接口，忽略 mode/analysis_result

        Returns:
            dict: 兼容旧接口 + 新增 features 字段
        """
        question_text = question.get("content", "")
        correct_answer = question.get("correct_answer", "")
        total_score = float(question.get("total_score", 1))
        options = question.get("options", "")

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

        # Stage 2 (new): LLM 特征提取
        logger.info(f"开始特征提取: {question_text[:50]}...")
        features = await extract_features(full_text, "", correct_answer)
        logger.info(f"特征提取完成: {features}")

        # Stage 3 (new): 规则评分
        score = compute_difficulty(features)
        label = score_to_label(score)
        logger.info(f"规则评分: {score} ({label})")

        return {
            # 旧字段（main.py / prediction_service.py 消费）
            "base_difficulty": score,
            "final_difficulty": score,
            "difficulty_label": label,
            "score_distribution_by_difficulty": self._score_distribution(score, total_score),
            # 新字段
            "features": features,
            "confidence": 0.7,
            "predicted_score_rate": None,
            "flags": [],
        }

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
