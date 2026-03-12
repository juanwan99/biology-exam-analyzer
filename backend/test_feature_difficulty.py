"""特征分析难度评估测试。"""
import pytest
from rule_scorer import compute_difficulty, score_to_label


class TestComputeDifficulty:
    """compute_difficulty 加权公式测试。"""

    def test_easiest_question(self):
        """纯识记单选题 → 约 2.3 分。"""
        features = {
            "bloom": 1,
            "reasoning_steps": 1,
            "knowledge_breadth": 1,
            "info_density": 1,
            "novelty": 1,
            "question_type_factor": 1,
        }
        score = compute_difficulty(features)
        assert 2.0 <= score <= 3.0, f"最简单题应在 2-3 分，实际 {score}"

    def test_hardest_question(self):
        """跨模块实验设计题 → 约 9.6 分。"""
        features = {
            "bloom": 5,
            "reasoning_steps": 10,
            "knowledge_breadth": 3,
            "info_density": 3,
            "novelty": 3,
            "question_type_factor": 4,
        }
        score = compute_difficulty(features)
        assert 9.0 <= score <= 10.0, f"最难题应在 9-10 分，实际 {score}"

    def test_medium_question(self):
        """中等难度题 → 4-6 分。"""
        features = {
            "bloom": 3,
            "reasoning_steps": 3,
            "knowledge_breadth": 2,
            "info_density": 2,
            "novelty": 2,
            "question_type_factor": 1,
        }
        score = compute_difficulty(features)
        assert 4.0 <= score <= 6.0, f"中等题应在 4-6 分，实际 {score}"

    def test_steps_capped_at_8(self):
        """reasoning_steps 超过 8 应封顶。"""
        f8 = {"bloom": 3, "reasoning_steps": 8, "knowledge_breadth": 2,
              "info_density": 2, "novelty": 2, "question_type_factor": 1}
        f20 = dict(f8, reasoning_steps=20)
        assert compute_difficulty(f8) == compute_difficulty(f20)


class TestScoreToLabel:
    def test_labels(self):
        assert score_to_label(2.0) == "简单"
        assert score_to_label(4.0) == "中等偏易"
        assert score_to_label(6.0) == "中等偏难"
        assert score_to_label(8.0) == "困难"
