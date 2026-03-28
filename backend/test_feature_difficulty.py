"""特征分析难度评估测试（v3: 难度预测模型）。"""
import pytest
from rule_scorer import compute_difficulty, score_to_label


class TestComputeDifficulty:
    """compute_difficulty v3 评分测试。"""

    def _base(self, **overrides):
        f = {"working_memory": 1, "reasoning_steps": 1, "chain_coupling": 1,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1,
             "bloom": 1, "info_density": 1, "representation_complexity": 1}
        f.update(overrides)
        return f

    def test_easiest(self):
        score = compute_difficulty(self._base())
        assert 2.0 <= score <= 3.5, f"全最低应在 2.0-3.5，实际 {score}"

    def test_hardest(self):
        score = compute_difficulty(self._base(
            working_memory=5, reasoning_steps=10, chain_coupling=3,
            trap_density=3, novelty=3, knowledge_breadth=3))
        assert 9.0 <= score <= 10.0, f"全最高应在 9.0-10.0，实际 {score}"

    def test_medium(self):
        score = compute_difficulty(self._base(
            working_memory=3, reasoning_steps=4, chain_coupling=2,
            trap_density=2, novelty=2, knowledge_breadth=2))
        assert 4.0 <= score <= 7.0, f"中等题应在 4.0-7.0，实际 {score}"

    def test_coupling_impact(self):
        """同样步数，耦合度高 → 更难。"""
        indep = compute_difficulty(self._base(reasoning_steps=5, chain_coupling=1))
        chained = compute_difficulty(self._base(reasoning_steps=5, chain_coupling=3))
        assert chained > indep, f"全链依赖应更难: {chained} vs {indep}"

    def test_trap_density_impact(self):
        """陷阱密度高 → 更难。"""
        low = compute_difficulty(self._base(working_memory=3, reasoning_steps=3, trap_density=1))
        high = compute_difficulty(self._base(working_memory=3, reasoning_steps=3, trap_density=3))
        assert high - low >= 1.0, f"陷阱密度差应 ≥1.0: {high} - {low} = {high-low}"

    def test_working_memory_impact(self):
        """工作记忆负荷高 → 更难。"""
        low = compute_difficulty(self._base(working_memory=1, reasoning_steps=4))
        high = compute_difficulty(self._base(working_memory=5, reasoning_steps=4))
        assert high - low >= 1.5, f"wm 差应 ≥1.5: {high} - {low} = {high-low}"

    def test_coupling_multiplier_effect(self):
        """7步全链依赖 应比 7步独立 难很多。"""
        indep = compute_difficulty(self._base(reasoning_steps=7, chain_coupling=1))
        chained = compute_difficulty(self._base(reasoning_steps=7, chain_coupling=3))
        assert chained - indep >= 0.5, f"7步耦合差应 ≥0.5: {chained} - {indep}"

    def test_bloom_not_affect_score(self):
        """bloom 不参与 v3 评分。"""
        low_bloom = compute_difficulty(self._base(working_memory=3, reasoning_steps=3, bloom=1))
        high_bloom = compute_difficulty(self._base(working_memory=3, reasoning_steps=3, bloom=6))
        assert low_bloom == high_bloom, f"bloom 不应影响评分: {low_bloom} vs {high_bloom}"


class TestScoreToLabel:
    def test_labels(self):
        assert score_to_label(2.0) == "简单"
        assert score_to_label(3.5) == "简单"
        assert score_to_label(4.0) == "中等偏易"
        assert score_to_label(5.5) == "中等偏易"
        assert score_to_label(6.0) == "中等偏难"
        assert score_to_label(7.5) == "中等偏难"
        assert score_to_label(8.0) == "困难"


import json
from feature_extractor import parse_features, build_feature_prompt, DEFAULT_FEATURES


class TestParseFeatures:
    """JSON 解析容错测试。"""

    def test_v3_fields_parsed(self):
        """v3 新增字段正确解析。"""
        raw = json.dumps({
            "working_memory": 4, "working_memory_reason": "需同时考虑基因型+表型+连锁",
            "reasoning_steps": 5, "steps_detail": "读图→判基因型→推概率→选答案→验证",
            "chain_coupling": 3, "coupling_reason": "全链依赖",
            "trap_density": 2, "trap_reason": "选项BC易混",
            "novelty": 2, "novelty_reason": "变式题",
            "knowledge_breadth": 2, "breadth_reason": "遗传+概率",
            "bloom": 4, "bloom_reason": "分析遗传图谱",
            "info_density": 2, "density_reason": "系谱图+文字",
            "representation_complexity": 3, "representation_reason": "复杂系谱图",
        })
        result = parse_features(raw)
        assert result["working_memory"] == 4
        assert result["chain_coupling"] == 3
        assert result["trap_density"] == 2
        assert result["bloom"] == 4
        assert "working_memory_reason" in result
        assert "coupling_reason" in result
        assert "trap_reason" in result

    def test_missing_v3_fields_use_default(self):
        """缺少 v3 新字段 → 用默认值。"""
        raw = json.dumps({
            "bloom": 3, "reasoning_steps": 2, "knowledge_breadth": 1,
            "info_density": 1, "novelty": 1, "representation_complexity": 1,
        })
        result = parse_features(raw)
        assert result["working_memory"] == DEFAULT_FEATURES["working_memory"]
        assert result["chain_coupling"] == DEFAULT_FEATURES["chain_coupling"]
        assert result["trap_density"] == DEFAULT_FEATURES["trap_density"]

    def test_all_reasons_preserved(self):
        """v3 所有 reason 字段保留。"""
        raw = json.dumps({
            "bloom": 3, "bloom_reason": "理解",
            "reasoning_steps": 2, "steps_detail": "两步",
            "knowledge_breadth": 1, "breadth_reason": "单点",
            "info_density": 1, "density_reason": "少",
            "novelty": 1, "novelty_reason": "教材",
            "representation_complexity": 1, "representation_reason": "无图",
            "working_memory": 2, "working_memory_reason": "两概念对比",
            "chain_coupling": 1, "coupling_reason": "独立",
            "trap_density": 1, "trap_reason": "无陷阱",
        })
        result = parse_features(raw)
        assert "bloom_reason" in result
        assert "working_memory_reason" in result
        assert "coupling_reason" in result
        assert "trap_reason" in result

    def test_valid_json(self):
        raw = '{"bloom": 3, "reasoning_steps": 4, "knowledge_breadth": 2, "info_density": 2, "novelty": 1}'
        result = parse_features(raw)
        assert result["bloom"] == 3
        assert result["reasoning_steps"] == 4

    def test_json_in_code_block(self):
        raw = '```json\n{"bloom": 2, "reasoning_steps": 1, "knowledge_breadth": 1}\n```'
        result = parse_features(raw)
        assert result["bloom"] == 2

    def test_out_of_range_clipped(self):
        raw = '{"bloom": 10, "reasoning_steps": -1, "knowledge_breadth": 5, "working_memory": 8, "chain_coupling": 0, "trap_density": 5}'
        result = parse_features(raw)
        assert result["bloom"] == 6
        assert result["reasoning_steps"] == 1
        assert result["knowledge_breadth"] == 3
        assert result["working_memory"] == 5
        assert result["chain_coupling"] == 1
        assert result["trap_density"] == 3

    def test_unparseable_returns_default(self):
        result = parse_features("这道题很难blahblah")
        assert result == DEFAULT_FEATURES

    def test_partial_json_extracts_what_it_can(self):
        raw = '{"bloom": 4, "reasoning_steps": 3}'
        result = parse_features(raw)
        assert result["bloom"] == 4
        assert result["reasoning_steps"] == 3
        assert result["working_memory"] == DEFAULT_FEATURES["working_memory"]


class TestBuildPrompt:
    def test_prompt_contains_question(self):
        prompt = build_feature_prompt("下列关于DNA的说法...", "A.xx B.xx", "A")
        assert "下列关于DNA的说法" in prompt
        assert "A.xx B.xx" in prompt

    def test_prompt_contains_v3_fields(self):
        """prompt 包含 v3 新增维度指令。"""
        prompt = build_feature_prompt("某题", question_type="选择题")
        assert "working_memory" in prompt
        assert "chain_coupling" in prompt
        assert "trap_density" in prompt
        assert "quality_sensitivity" in prompt


import asyncio
from unittest.mock import patch, AsyncMock
from difficulty_pipeline import DifficultyPipeline
from feature_extractor import DEFAULT_FEATURES


class TestPipelineRepresentation:
    """Pipeline representation 合并测试。"""

    def _mock_v3_features(self, **overrides):
        f = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 2,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
        }
        f.update(overrides)
        return f

    def test_gemini_repr_merged_via_kwarg(self):
        """Gemini 的 representation_complexity 通过 analysis_result 传入。"""
        mock_features = self._mock_v3_features(representation_complexity=1)
        gemini_analysis = {
            "representation_complexity": 3,
            "representation_is_core_to_solving": True,
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement(
                    question={"content": "观察系谱图...", "question_type": "选择题",
                              "correct_answer": "A", "total_score": 2},
                    analysis_result=gemini_analysis,
                )
            )
        assert result["features"]["representation_complexity"] == 3

    def test_gemini_repr_ignored_when_not_core(self):
        mock_features = self._mock_v3_features(representation_complexity=2)
        gemini_analysis = {
            "representation_complexity": 1,
            "representation_is_core_to_solving": False,
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement(
                    question={"content": "某题...", "question_type": "选择题",
                              "correct_answer": "A", "total_score": 2},
                    analysis_result=gemini_analysis,
                )
            )
        assert result["features"]["representation_complexity"] <= 2

    def test_no_analysis_result_uses_claude_only(self):
        mock_features = self._mock_v3_features(representation_complexity=2)
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement(
                    question={"content": "某题...", "question_type": "选择题",
                              "correct_answer": "A", "total_score": 2},
                )
            )
        assert result["features"]["representation_complexity"] == 2

    def test_dynamic_confidence_default_features(self):
        """使用默认特征 → confidence 应低于基线 0.85。"""
        mock_features = dict(DEFAULT_FEATURES)
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement(
                    question={"content": "某题...", "question_type": "实验题",
                              "correct_answer": "", "total_score": 6},
                )
            )
        assert result["confidence"] < 0.7, f"默认特征应降低 confidence，实际 {result['confidence']}"


class TestPipelineIntegration:
    """Pipeline 集成测试（mock LLM 调用）。"""

    def test_evaluate_returns_expected_fields(self):
        mock_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 2,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
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
        assert "base_difficulty" in result
        assert "final_difficulty" in result
        assert "difficulty_label" in result
        assert "features" in result
        assert 0 <= result["base_difficulty"] <= 10

    def test_empty_content_returns_default(self):
        pipeline = DifficultyPipeline()
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.evaluate_with_refinement({"content": "", "question_type": "", "correct_answer": "", "total_score": 1})
        )
        assert result["difficulty_label"] == "未评估"


class TestExtendedFields:
    """质量审查 + 教师点评字段测试。"""

    def test_quality_review_parsed(self):
        raw = json.dumps({
            "bloom": 3, "reasoning_steps": 2, "knowledge_breadth": 1,
            "info_density": 1, "novelty": 1, "representation_complexity": 1,
            "working_memory": 2, "chain_coupling": 1, "trap_density": 1,
            "quality_scientific": "准确",
            "quality_normative": "选项格式规范",
            "quality_language": "表述简洁",
            "quality_context": "情境合理",
            "teacher_comment": "本题考查光合作用基本概念，难度适中。",
        })
        result = parse_features(raw)
        assert result["quality_scientific"] == "准确"
        assert result["teacher_comment"] == "本题考查光合作用基本概念，难度适中。"

    def test_quality_fields_missing_use_empty(self):
        raw = json.dumps({
            "bloom": 3, "reasoning_steps": 2, "knowledge_breadth": 1,
        })
        result = parse_features(raw)
        assert result.get("quality_scientific", "") == ""

    def test_prompt_contains_quality_section(self):
        prompt = build_feature_prompt("下列关于DNA的说法正确的是", question_type="选择题")
        assert "quality_scientific" in prompt
        assert "quality_sensitivity" in prompt
        assert "teacher_comment" in prompt


class TestNoAnswerEvaluation:
    def test_no_answer_still_evaluates(self):
        mock_features = {
            "working_memory": 2, "reasoning_steps": 2, "chain_coupling": 1,
            "trap_density": 1, "novelty": 1, "knowledge_breadth": 1,
            "bloom": 2, "info_density": 1, "representation_complexity": 1,
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "描述光合作用的过程",
                    "question_type": "简答题",
                    "correct_answer": "",
                    "total_score": 6,
                })
            )
        assert result["difficulty_label"] != "未评估"
        assert result["features"] is not None
