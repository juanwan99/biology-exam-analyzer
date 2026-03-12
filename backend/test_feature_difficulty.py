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


import json
from feature_extractor import parse_features, build_feature_prompt, DEFAULT_FEATURES


class TestParseFeatures:
    """JSON 解析容错测试。"""

    def test_valid_json(self):
        raw = '{"bloom": 3, "reasoning_steps": 4, "knowledge_breadth": 2, "info_density": 2, "novelty": 1, "question_type_factor": 1}'
        result = parse_features(raw)
        assert result["bloom"] == 3
        assert result["reasoning_steps"] == 4

    def test_json_in_code_block(self):
        raw = '```json\n{"bloom": 2, "reasoning_steps": 1, "knowledge_breadth": 1, "info_density": 1, "novelty": 1, "question_type_factor": 1}\n```'
        result = parse_features(raw)
        assert result["bloom"] == 2

    def test_out_of_range_clipped(self):
        raw = '{"bloom": 10, "reasoning_steps": -1, "knowledge_breadth": 5, "info_density": 0, "novelty": 3, "question_type_factor": 1}'
        result = parse_features(raw)
        assert result["bloom"] == 6  # clipped to max
        assert result["reasoning_steps"] == 1  # clipped to min
        assert result["knowledge_breadth"] == 3  # clipped to max
        assert result["info_density"] == 1  # clipped to min

    def test_unparseable_returns_default(self):
        result = parse_features("这道题很难blahblah")
        assert result == DEFAULT_FEATURES

    def test_partial_json_extracts_what_it_can(self):
        """部分字段缺失 → 用默认值补全。"""
        raw = '{"bloom": 4, "reasoning_steps": 3}'
        result = parse_features(raw)
        assert result["bloom"] == 4
        assert result["reasoning_steps"] == 3
        assert result["knowledge_breadth"] == DEFAULT_FEATURES["knowledge_breadth"]


class TestBuildPrompt:
    def test_prompt_contains_question(self):
        prompt = build_feature_prompt("下列关于DNA的说法...", "A.xx B.xx", "A")
        assert "下列关于DNA的说法" in prompt
        assert "A.xx B.xx" in prompt


import asyncio
from unittest.mock import patch, AsyncMock
from difficulty_pipeline import DifficultyPipeline


class TestPipelineIntegration:
    """Pipeline 集成测试（mock LLM 调用）。"""

    def test_evaluate_returns_expected_fields(self):
        """验证返回字段兼容旧接口。"""
        mock_features = {
            "bloom": 3, "reasoning_steps": 4, "knowledge_breadth": 2,
            "info_density": 2, "novelty": 2, "question_type_factor": 1,
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "下列关于DNA的说法正确的是",
                    "question_type": "选择题",
                    "correct_answer": "A",
                    "total_score": 2,
                })
            )

        # 旧字段必须存在
        assert "base_difficulty" in result
        assert "final_difficulty" in result
        assert "difficulty_label" in result
        assert "score_distribution_by_difficulty" in result
        # 新字段
        assert "features" in result
        assert result["features"]["bloom"] == 3
        # 分数合理
        assert 0 <= result["base_difficulty"] <= 10

    def test_empty_content_returns_default(self):
        pipeline = DifficultyPipeline()
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.evaluate_with_refinement({"content": "", "question_type": "", "correct_answer": "", "total_score": 1})
        )
        assert result["difficulty_label"] == "未评估"
