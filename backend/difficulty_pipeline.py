"""难度量化 Pipeline 主控 — 4 阶段编排。

Stage 1: 题目预处理（纯代码）
Stage 2: 模拟学生作答（Claude Sonnet 4.5）
Stage 3: IRT 拟合（scipy）
Stage 4: 校准映射（预留，Phase 2）

设计文档: docs/plans/2026-03-11-difficulty-pipeline-design.md §1
"""
import asyncio
import logging
from simulated_student import simulate_all_students
from irt_estimator import estimate_difficulty

logger = logging.getLogger(__name__)


class DifficultyPipeline:
    """难度量化 Pipeline。替代旧 DifficultyEngine。"""

    def __init__(self, **kwargs):
        """初始化。接受 kwargs 以兼容旧调用方 DifficultyEngine(gemini_analyzer=...) 签名。"""
        # 忽略旧参数（gemini_analyzer 不再需要）
        pass

    async def _evaluate_single(self, question: dict, **kwargs) -> dict:
        """评估单道题难度。

        Args:
            question: dict，需包含 content, question_type, correct_answer, total_score
            **kwargs: 兼容旧接口，忽略 mode/analysis_result

        Returns:
            dict: 兼容旧接口 + 新增 IRT 字段
        """
        # Stage 1: 预处理
        question_text = question.get("content", "")
        question_type = question.get("question_type", "")
        correct_answer = question.get("correct_answer", "")
        total_score = float(question.get("total_score", 1))
        image_base64 = question.get("image_base64", None)

        if not question_text:
            logger.warning("题目内容为空，跳过难度评估")
            return self._default_result()

        if not correct_answer:
            logger.warning("无标准答案，跳过难度评估（无法评判对错）")
            return self._default_result()

        # Stage 2: 模拟学生作答
        logger.info(f"开始模拟学生作答: {question_text[:50]}...")
        responses_raw = await simulate_all_students(
            question_text=question_text,
            question_type=question_type,
            correct_answer=correct_answer,
            total_score=total_score,
            image_base64=image_base64,
        )

        # 提取得分列表（0/0.5/1）
        scores = [r["score"] for r in responses_raw]
        logger.info(f"模拟作答完成: 正确率={sum(s >= 1.0 for s in scores)/len(scores):.0%}")

        # Stage 3: IRT 拟合
        irt_result = estimate_difficulty(scores)
        logger.info(
            f"IRT 拟合: score={irt_result['difficulty_score']}, "
            f"b={irt_result['irt_params']['b']}, "
            f"flags={irt_result['flags']}"
        )

        # Stage 4: 校准映射（预留，Phase 2 实现）
        predicted_score_rate = None

        # 组装输出（兼容旧字段名 + 新增字段）
        score = irt_result["difficulty_score"]
        return {
            # 旧字段（main.py / prediction_service.py 消费）
            "base_difficulty": score,
            "final_difficulty": score,
            "difficulty_label": irt_result["difficulty_label"],
            "score_distribution_by_difficulty": self._score_distribution(score, total_score),
            # 新字段
            "irt_difficulty": irt_result["irt_params"]["b"],
            "irt_params": irt_result["irt_params"],
            "confidence": irt_result["confidence"],
            "predicted_score_rate": predicted_score_rate,
            "flags": irt_result["flags"],
            "simulated_responses": responses_raw,
        }

    def _default_result(self):
        """无法评估时的默认返回。"""
        return {
            "base_difficulty": 5.0,
            "final_difficulty": 5.0,
            "difficulty_label": "未评估",
            "score_distribution_by_difficulty": {},
            "irt_difficulty": None,
            "irt_params": None,
            "confidence": 0.0,
            "predicted_score_rate": None,
            "flags": ["no_evaluation"],
            "simulated_responses": [],
        }

    def _score_distribution(self, difficulty_score: float, total_score: float) -> dict:
        """从难度分数推导预期得分分布（兼容旧 score_allocator 输出格式）。

        简化版：基于正态分布近似。
        """
        import numpy as np

        mean_rate = max(0, min(1, 1 - difficulty_score / 10))
        # 标准差与难度适中程度相关（中等题方差最大）
        std_rate = 0.15 + 0.1 * (1 - abs(difficulty_score - 5) / 5)

        distribution = {}
        for pct in [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
            rate = pct / 100
            # 预测该得分率的学生比例
            if rate <= 0:
                prob = max(0, 1 - mean_rate) * 0.3
            elif rate >= 1:
                prob = mean_rate * 0.3
            else:
                diff = abs(rate - mean_rate)
                prob = max(0, np.exp(-diff ** 2 / (2 * std_rate ** 2)))
            score_val = round(rate * total_score, 1)
            distribution[str(score_val)] = round(prob, 3)
        return distribution

    async def evaluate_with_refinement(self, question: dict, **kwargs) -> dict:
        """兼容旧接口名。直接调用 _evaluate_single。

        旧签名: evaluate_with_refinement(question, mode="fast", analysis_result=None)
        新实现忽略 mode 和 analysis_result。
        """
        return await self._evaluate_single(question, **kwargs)

    def evaluate_with_refinement_sync(self, question: dict, **kwargs) -> dict:
        """同步版本，供非 async 调用方使用。"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._evaluate_single(question, **kwargs))
        finally:
            loop.close()
