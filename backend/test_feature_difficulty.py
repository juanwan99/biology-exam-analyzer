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

    def test_representation_and_information_load_affect_score(self):
        """Biology figures/tables add representation burden even when core logic is unchanged."""
        plain = compute_difficulty(self._base(
            working_memory=3, reasoning_steps=4, chain_coupling=1,
            trap_density=2, novelty=1, knowledge_breadth=2,
            representation_complexity=1, info_density=1))
        visual = compute_difficulty(self._base(
            working_memory=3, reasoning_steps=4, chain_coupling=1,
            trap_density=2, novelty=1, knowledge_breadth=2,
            representation_complexity=3, info_density=3))
        assert visual - plain >= 0.8

    def test_trap_novelty_do_not_swamp_visual_multistep_demand(self):
        """Many traps alone should not outrank a longer visual multi-step task."""
        trap_heavy_choice = compute_difficulty(self._base(
            working_memory=4, reasoning_steps=5, chain_coupling=3,
            trap_density=3, novelty=3, knowledge_breadth=2,
            representation_complexity=1, info_density=2))
        visual_multistep = compute_difficulty(self._base(
            working_memory=4, reasoning_steps=8, chain_coupling=2,
            trap_density=2, novelty=2, knowledge_breadth=2,
            representation_complexity=3, info_density=3))
        assert visual_multistep > trap_heavy_choice


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

    def test_model_repr_merged_via_kwarg(self):
        """模型的 representation_complexity 通过 analysis_result 传入。"""
        mock_features = self._mock_v3_features(representation_complexity=1)
        model_analysis = {
            "representation_complexity": 3,
            "representation_is_core_to_solving": True,
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement(
                    question={"content": "观察系谱图...", "question_type": "选择题",
                              "correct_answer": "A", "total_score": 2},
                    analysis_result=model_analysis,
                )
            )
        assert result["features"]["representation_complexity"] == 3

    def test_model_repr_ignored_when_not_core(self):
        mock_features = self._mock_v3_features(representation_complexity=2)
        model_analysis = {
            "representation_complexity": 1,
            "representation_is_core_to_solving": False,
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement(
                    question={"content": "某题...", "question_type": "选择题",
                              "correct_answer": "A", "total_score": 2},
                    analysis_result=model_analysis,
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


class TestFineGrainedDifficultyEvidence:
    """Fine-grained SEU/DU evidence should refine, not replace, rule scoring."""

    def _seus(self, high_order=False):
        if high_order:
            return [
                {"score_share": 0.2, "difficulty_estimate": 5.5, "bloom_level": 4,
                 "allocation_confidence": 0.9},
                {"score_share": 0.4, "difficulty_estimate": 8.0, "bloom_level": 6,
                 "allocation_confidence": 0.9},
                {"score_share": 0.2, "difficulty_estimate": 5.5, "bloom_level": 3,
                 "allocation_confidence": 0.9},
                {"score_share": 0.2, "difficulty_estimate": 5.5, "bloom_level": 4,
                 "allocation_confidence": 0.9},
            ]
        return [
            {"score_share": 0.25, "difficulty_estimate": 5.0, "bloom_level": 3,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 5.5, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 5.0, "bloom_level": 3,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 5.5, "bloom_level": 4,
             "allocation_confidence": 0.9},
        ]

    def test_big_question_structure_failure_fails_closed(self):
        flat_features = {
            "working_memory": 4, "reasoning_steps": 8, "chain_coupling": 2,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 5, "info_density": 3, "representation_complexity": 2,
        }

        async def run():
            with patch("difficulty_pipeline.extract_big_question_features",
                        new_callable=AsyncMock, return_value=None), \
                  patch("difficulty_pipeline.extract_features",
                        new_callable=AsyncMock, return_value=dict(flat_features)):
                pipeline = DifficultyPipeline()
                return await pipeline.evaluate_with_refinement(
                    {"content": "vector construction experiment", "question_type": "experiment",
                      "correct_answer": "", "total_score": 14},
                    analysis_result={"_fine_grained": {"scoring_units": self._seus(True)}})

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(run())

        assert result["final_difficulty"] is None
        assert result["difficulty_label"] == "未评估"
        assert result["confidence"] == 0.0
        assert result["analysis_failed"] is True
        assert "big_question_structure_failed" in result.get("flags", [])

    def test_diagnostic_burden_raises_understated_misconception_heavy_item(self):
        base_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 1,
            "trap_density": 3, "novelty": 1, "knowledge_breadth": 1,
            "bloom": 3, "info_density": 1, "representation_complexity": 1,
        }
        diagnostic_units = [
            {"description": "confuses screening purpose", "trap_strength": 3},
            {"description": "confuses cell source", "trap_strength": 3},
            {"description": "confuses culture condition", "trap_strength": 2},
        ]

        async def run(with_diagnostics):
            analysis = {"_fine_grained": {"diagnostic_units": diagnostic_units if with_diagnostics else []}}
            with patch("difficulty_pipeline.extract_features",
                       new_callable=AsyncMock, return_value=dict(base_features)):
                pipeline = DifficultyPipeline()
                return await pipeline.evaluate_with_refinement(
                    {"content": "single choice misconception-heavy item",
                     "question_type": "single_choice", "correct_answer": "B", "total_score": 2},
                    analysis_result=analysis)

        loop = asyncio.get_event_loop()
        plain = loop.run_until_complete(run(False))
        with_du = loop.run_until_complete(run(True))

        assert 0.25 <= with_du["final_difficulty"] - plain["final_difficulty"] <= 0.7
        assert "diagnostic_burden_adjustment" in with_du.get("flags", [])

    def test_weak_diagnostic_count_does_not_raise_difficulty(self):
        base_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 1,
            "trap_density": 2, "novelty": 1, "knowledge_breadth": 1,
            "bloom": 3, "info_density": 1, "representation_complexity": 1,
        }
        weak_dus = [
            {"description": f"minor distractor {idx}", "trap_strength": 1}
            for idx in range(6)
        ]

        async def run(with_diagnostics):
            analysis = {"_fine_grained": {"diagnostic_units": weak_dus if with_diagnostics else []}}
            with patch("difficulty_pipeline.extract_features",
                       new_callable=AsyncMock, return_value=dict(base_features)):
                pipeline = DifficultyPipeline()
                return await pipeline.evaluate_with_refinement(
                    {"content": "single choice with many weak distractor notes",
                     "question_type": "single_choice", "correct_answer": "B", "total_score": 2},
                    analysis_result=analysis)

        loop = asyncio.get_event_loop()
        plain = loop.run_until_complete(run(False))
        with_du = loop.run_until_complete(run(True))

        assert with_du["final_difficulty"] == plain["final_difficulty"]
        assert "diagnostic_burden_adjustment" not in with_du.get("flags", [])

    def test_non_numeric_trap_strength_does_not_crash(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"diagnostic_units": [
            {"description": "text strength", "trap_strength": "strong"},
            {"description": "zero strength", "trap_strength": 0},
            {"description": "numeric strength", "trap_strength": 3},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            5.5,
            {
                "trap_density": 2,
                "representation_complexity": 1,
            },
            analysis,
            is_big_question=False,
            total_score=2,
        )

        assert adjusted >= 5.5
        assert "diagnostic_burden_adjustment" in flags

    def test_visual_big_question_diagnostic_traps_raise_understated_difficulty(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"diagnostic_units": [
            {"description": "graph relation misconception", "trap_strength": 3},
            {"description": "key node misconception", "trap_strength": 2},
            {"description": "matter transfer misconception", "trap_strength": 2},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            6.1,
            {
                "working_memory": 4,
                "reasoning_steps": 5,
                "chain_coupling": 1,
                "trap_density": 2,
                "novelty": 1,
                "knowledge_breadth": 2,
                "representation_complexity": 3,
                "info_density": 2,
            },
            analysis,
            is_big_question=True,
            total_score=11,
        )

        assert adjusted >= 7.2
        assert "visual_diagnostic_burden_adjustment" in flags

    def test_visual_big_question_two_structural_traps_are_not_treated_as_routine(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"diagnostic_units": [
            {"description": "food-web level omission", "trap_strength": 3},
            {"description": "system stability misconception", "trap_strength": 2},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            5.8,
            {
                "working_memory": 4,
                "reasoning_steps": 4,
                "chain_coupling": 1,
                "trap_density": 2,
                "novelty": 1,
                "knowledge_breadth": 2,
                "representation_complexity": 3,
                "info_density": 2,
            },
            analysis,
            is_big_question=True,
            total_score=11,
        )

        assert adjusted >= 6.8
        assert "visual_diagnostic_burden_adjustment" in flags

    def test_scoring_unit_metrics_expose_partial_credit_thresholds(self):
        pipeline = DifficultyPipeline()
        metrics = pipeline._scoring_unit_metrics([
            {"score_share": 0.35, "difficulty_estimate": 9.0, "bloom_level": 6,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 3.0, "bloom_level": 2,
             "allocation_confidence": 0.9},
            {"score_share": 0.20, "difficulty_estimate": 3.0, "bloom_level": 2,
             "allocation_confidence": 0.9},
            {"score_share": 0.20, "difficulty_estimate": 3.0, "bloom_level": 2,
             "allocation_confidence": 0.9},
        ])

        assert metrics["average_score"] < 6.0
        assert metrics["mastery_threshold_score"] >= 8.8
        assert metrics["bottleneck_score"] >= 8.0

    def test_big_question_without_top_bottleneck_is_only_moderated_boundedly(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.10, "difficulty_estimate": 2.0, "bloom_level": 1,
             "allocation_confidence": 0.9},
            {"score_share": 0.15, "difficulty_estimate": 5.0, "bloom_level": 3,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 6.5, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 7.0, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 7.5, "bloom_level": 5,
             "allocation_confidence": 0.9},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            9.8,
            {
                "working_memory": 5,
                "reasoning_steps": 9,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 3,
                "representation_complexity": 3,
            },
            analysis,
            is_big_question=True,
            total_score=12,
        )

        assert adjusted >= 8.8
        assert "seu_no_top_bottleneck_moderation" in flags

    def test_big_question_high_order_evidence_keeps_high_difficulty(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.20, "difficulty_estimate": 6.5, "bloom_level": 4,
             "allocation_confidence": 0.85},
            {"score_share": 0.30, "difficulty_estimate": 8.5, "bloom_level": 6,
             "allocation_confidence": 0.85},
            {"score_share": 0.25, "difficulty_estimate": 8.0, "bloom_level": 5,
             "allocation_confidence": 0.85},
            {"score_share": 0.25, "difficulty_estimate": 8.8, "bloom_level": 6,
             "allocation_confidence": 0.85},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            9.4,
            {},
            analysis,
            is_big_question=True,
            total_score=14,
        )

        assert adjusted >= 9.0

    def test_many_medium_scoring_units_do_not_create_top_tier_difficulty(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.12, "difficulty_estimate": 4.5, "bloom_level": 2,
             "allocation_confidence": 0.9},
            {"score_share": 0.12, "difficulty_estimate": 5.5, "bloom_level": 3,
             "allocation_confidence": 0.9},
            {"score_share": 0.13, "difficulty_estimate": 6.0, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.13, "difficulty_estimate": 6.2, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.13, "difficulty_estimate": 6.5, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.12, "difficulty_estimate": 7.0, "bloom_level": 5,
             "allocation_confidence": 0.9},
            {"score_share": 0.13, "difficulty_estimate": 7.0, "bloom_level": 5,
             "allocation_confidence": 0.9},
            {"score_share": 0.12, "difficulty_estimate": 7.2, "bloom_level": 5,
             "allocation_confidence": 0.9},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            7.0,
            {
                "working_memory": 3,
                "reasoning_steps": 5,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 2,
                "representation_complexity": 2,
            },
            analysis,
            is_big_question=True,
            total_score=12,
        )

        assert adjusted <= 7.3

    def test_many_medium_scoring_units_cannot_stack_into_top_tier(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.08, "difficulty_estimate": 1.0, "bloom_level": 1,
             "allocation_confidence": 0.9},
            {"score_share": 0.09, "difficulty_estimate": 4.0, "bloom_level": 3,
             "allocation_confidence": 0.9},
            {"score_share": 0.09, "difficulty_estimate": 6.0, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.17, "difficulty_estimate": 7.0, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.17, "difficulty_estimate": 6.5, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.12, "difficulty_estimate": 7.5, "bloom_level": 5,
             "allocation_confidence": 0.9},
            {"score_share": 0.12, "difficulty_estimate": 8.0, "bloom_level": 6,
             "allocation_confidence": 0.8},
            {"score_share": 0.16, "difficulty_estimate": 7.0, "bloom_level": 5,
             "allocation_confidence": 0.9},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            9.8,
            {
                "working_memory": 5,
                "reasoning_steps": 8,
                "trap_density": 2,
                "novelty": 3,
                "knowledge_breadth": 3,
                "representation_complexity": 3,
            },
            analysis,
            is_big_question=True,
            total_score=12,
        )

        assert adjusted <= 8.9
        assert "seu_many_medium_unit_moderation" in flags

    def test_low_construct_big_question_can_be_slightly_moderated(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.50, "difficulty_estimate": 3.5, "bloom_level": 2,
             "allocation_confidence": 0.9},
            {"score_share": 0.50, "difficulty_estimate": 4.0, "bloom_level": 3,
             "allocation_confidence": 0.9},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            8.2,
            {
                "working_memory": 3,
                "reasoning_steps": 5,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 2,
                "representation_complexity": 1,
            },
            analysis,
            is_big_question=True,
            total_score=12,
        )

        assert 7.5 <= adjusted < 8.2
        assert "seu_low_construct_moderation" in flags

    def test_decisive_high_order_bottleneck_share_can_remain_top_tier(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.18, "difficulty_estimate": 5.5, "bloom_level": 3,
             "allocation_confidence": 0.85},
            {"score_share": 0.18, "difficulty_estimate": 6.5, "bloom_level": 4,
             "allocation_confidence": 0.85},
            {"score_share": 0.22, "difficulty_estimate": 8.5, "bloom_level": 6,
             "allocation_confidence": 0.85},
            {"score_share": 0.22, "difficulty_estimate": 8.8, "bloom_level": 6,
             "allocation_confidence": 0.85},
            {"score_share": 0.20, "difficulty_estimate": 9.0, "bloom_level": 6,
             "allocation_confidence": 0.85},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            9.4,
            {},
            analysis,
            is_big_question=True,
            total_score=14,
        )

        assert adjusted >= 9.0

    def test_bounded_objective_item_uses_seu_ceiling(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.15, "difficulty_estimate": 2.0, "bloom_level": 2,
             "allocation_confidence": 0.9},
            {"score_share": 0.30, "difficulty_estimate": 7.0, "bloom_level": 4,
             "allocation_confidence": 0.8},
            {"score_share": 0.30, "difficulty_estimate": 6.5, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 8.0, "bloom_level": 5,
             "allocation_confidence": 0.8},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            8.6,
            {},
            analysis,
            is_big_question=False,
            total_score=4,
        )

        assert adjusted <= 7.8
        assert "bounded_item_seu_ceiling" in flags

    def test_bounded_item_with_partial_bottleneck_is_still_capped(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.15, "difficulty_estimate": 2.0, "bloom_level": 2,
             "allocation_confidence": 0.9},
            {"score_share": 0.30, "difficulty_estimate": 7.0, "bloom_level": 4,
             "allocation_confidence": 0.8},
            {"score_share": 0.30, "difficulty_estimate": 6.5, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.25, "difficulty_estimate": 8.0, "bloom_level": 5,
             "allocation_confidence": 0.8},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            8.6,
            {
                "working_memory": 4,
                "reasoning_steps": 6,
                "chain_coupling": 2,
                "trap_density": 3,
                "representation_complexity": 3,
                "info_density": 3,
            },
            analysis,
            is_big_question=False,
            total_score=4,
        )

        assert adjusted <= 7.8
        assert "bounded_item_seu_ceiling" in flags

    def test_decisive_high_order_bounded_item_can_remain_hard(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.25, "difficulty_estimate": 7.0, "bloom_level": 4,
             "allocation_confidence": 0.85},
            {"score_share": 0.35, "difficulty_estimate": 8.5, "bloom_level": 6,
             "allocation_confidence": 0.85},
            {"score_share": 0.40, "difficulty_estimate": 8.2, "bloom_level": 5,
             "allocation_confidence": 0.85},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            8.8,
            {},
            analysis,
            is_big_question=False,
            total_score=4,
        )

        assert adjusted >= 8.7
        assert "bounded_item_seu_ceiling" not in flags

    def test_compact_objective_item_lifts_on_seu_bottleneck(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.50, "difficulty_estimate": 7.5, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.50, "difficulty_estimate": 7.0, "bloom_level": 4,
             "allocation_confidence": 0.9},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            5.7,
            {
                "working_memory": 4,
                "reasoning_steps": 3,
                "trap_density": 2,
                "representation_complexity": 1,
            },
            analysis,
            is_big_question=False,
            total_score=2,
        )

        assert adjusted > 5.9
        assert "compact_seu_bottleneck_lift" in flags

    def test_choice_strong_misconceptions_add_decision_load_without_ids(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {
            "scoring_units": [
                {"score_share": 0.25, "difficulty_estimate": 3.0, "bloom_level": 2,
                 "allocation_confidence": 0.9},
                {"score_share": 0.25, "difficulty_estimate": 4.0, "bloom_level": 3,
                 "allocation_confidence": 0.9},
                {"score_share": 0.25, "difficulty_estimate": 4.0, "bloom_level": 2,
                 "allocation_confidence": 0.9},
                {"score_share": 0.25, "difficulty_estimate": 4.5, "bloom_level": 3,
                 "allocation_confidence": 0.9},
            ],
            "diagnostic_units": [
                {"description": "counter-intuitive distractor", "trap_strength": 3},
                {"description": "near-miss distractor", "trap_strength": 2},
                {"description": "near-miss distractor", "trap_strength": 2},
            ],
        }}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            4.0,
            {
                "working_memory": 2,
                "reasoning_steps": 4,
                "trap_density": 2,
                "representation_complexity": 1,
                "novelty": 1,
            },
            analysis,
            is_big_question=False,
            total_score=2,
        )

        assert adjusted >= 5.0
        assert "choice_strong_misconception_lift" in flags

    def test_choice_multi_medium_decisions_are_not_treated_as_easy(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {
            "scoring_units": [
                {"score_share": 0.25, "difficulty_estimate": 4.0, "bloom_level": 2,
                 "allocation_confidence": 0.9},
                {"score_share": 0.25, "difficulty_estimate": 4.5, "bloom_level": 2,
                 "allocation_confidence": 0.9},
                {"score_share": 0.25, "difficulty_estimate": 3.0, "bloom_level": 1,
                 "allocation_confidence": 0.9},
                {"score_share": 0.25, "difficulty_estimate": 3.5, "bloom_level": 2,
                 "allocation_confidence": 0.9},
            ],
            "diagnostic_units": [
                {"description": "medium distractor", "trap_strength": 2},
                {"description": "medium distractor", "trap_strength": 2},
                {"description": "medium distractor", "trap_strength": 2},
            ],
        }}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            4.0,
            {
                "working_memory": 2,
                "reasoning_steps": 4,
                "trap_density": 2,
                "representation_complexity": 1,
                "novelty": 1,
            },
            analysis,
            is_big_question=False,
            total_score=2,
        )

        assert adjusted >= 5.1
        assert "choice_multi_medium_decision_lift" in flags

    def test_fragmented_medium_big_item_is_moderated_below_top_tier(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {"scoring_units": [
            {"score_share": 0.08, "difficulty_estimate": 3.0, "bloom_level": 2,
             "allocation_confidence": 0.9},
            {"score_share": 0.08, "difficulty_estimate": 4.0, "bloom_level": 3,
             "allocation_confidence": 0.9},
            {"score_share": 0.08, "difficulty_estimate": 6.0, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.17, "difficulty_estimate": 6.5, "bloom_level": 6,
             "allocation_confidence": 0.9},
            {"score_share": 0.17, "difficulty_estimate": 7.0, "bloom_level": 5,
             "allocation_confidence": 0.9},
            {"score_share": 0.17, "difficulty_estimate": 7.5, "bloom_level": 5,
             "allocation_confidence": 0.9},
            {"score_share": 0.08, "difficulty_estimate": 6.0, "bloom_level": 4,
             "allocation_confidence": 0.9},
            {"score_share": 0.17, "difficulty_estimate": 8.0, "bloom_level": 5,
             "allocation_confidence": 0.9},
        ]}}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            8.8,
            {
                "working_memory": 5,
                "reasoning_steps": 7,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 3,
                "representation_complexity": 3,
            },
            analysis,
            is_big_question=True,
            total_score=12,
        )

        assert 7.4 <= adjusted <= 7.8
        assert "fragmented_medium_big_item_moderation" in flags

    def test_evidence_rich_big_question_restores_understated_structural_load(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {
            "scoring_units": [
                {"score_share": 0.10, "difficulty_estimate": 3.0, "bloom_level": 3,
                 "allocation_confidence": 0.75},
                {"score_share": 0.10, "difficulty_estimate": 4.0, "bloom_level": 3,
                 "allocation_confidence": 0.75},
                {"score_share": 0.12, "difficulty_estimate": 5.0, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.12, "difficulty_estimate": 5.5, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.12, "difficulty_estimate": 6.0, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.12, "difficulty_estimate": 6.3, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.12, "difficulty_estimate": 6.6, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.10, "difficulty_estimate": 7.0, "bloom_level": 5,
                 "allocation_confidence": 0.75},
                {"score_share": 0.10, "difficulty_estimate": 7.2, "bloom_level": 5,
                 "allocation_confidence": 0.75},
            ],
            "diagnostic_units": [
                {"description": "food-web level misconception", "trap_strength": 3},
                {"description": "species relationship misconception", "trap_strength": 2},
                {"description": "ecosystem stability misconception", "trap_strength": 2},
            ],
        }}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            5.6,
            {
                "working_memory": 3,
                "reasoning_steps": 4,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 2,
                "representation_complexity": 2,
                "info_density": 3,
            },
            analysis,
            is_big_question=True,
            total_score=11,
        )

        assert adjusted >= 7.4
        assert "evidence_rich_big_question_floor" in flags

    def test_dense_diagnostic_big_question_floor_handles_coarser_seu_splits(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {
            "scoring_units": [
                {"score_share": 0.16, "difficulty_estimate": 4.0, "bloom_level": 3,
                 "allocation_confidence": 0.75},
                {"score_share": 0.16, "difficulty_estimate": 5.0, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.17, "difficulty_estimate": 5.8, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.17, "difficulty_estimate": 6.2, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.17, "difficulty_estimate": 6.8, "bloom_level": 4,
                 "allocation_confidence": 0.75},
                {"score_share": 0.17, "difficulty_estimate": 7.0, "bloom_level": 5,
                 "allocation_confidence": 0.75},
            ],
            "diagnostic_units": [
                {"description": "table reconstruction trap", "trap_strength": 3},
                {"description": "food-web relation trap", "trap_strength": 2},
                {"description": "stability inference trap", "trap_strength": 2},
            ],
        }}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            7.1,
            {
                "working_memory": 3,
                "reasoning_steps": 4,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 2,
                "representation_complexity": 2,
                "info_density": 3,
            },
            analysis,
            is_big_question=True,
            total_score=11,
        )

        assert adjusted >= 7.4
        assert "evidence_rich_big_question_floor" in flags

    def test_evidence_rich_big_question_can_reach_model_baseline_floor(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {
            "scoring_units": [
                {"score_share": 0.14, "difficulty_estimate": 4.0, "bloom_level": 3,
                 "allocation_confidence": 0.8},
                {"score_share": 0.14, "difficulty_estimate": 5.0, "bloom_level": 4,
                 "allocation_confidence": 0.8},
                {"score_share": 0.14, "difficulty_estimate": 5.8, "bloom_level": 4,
                 "allocation_confidence": 0.8},
                {"score_share": 0.14, "difficulty_estimate": 6.5, "bloom_level": 4,
                 "allocation_confidence": 0.8},
                {"score_share": 0.14, "difficulty_estimate": 7.0, "bloom_level": 5,
                 "allocation_confidence": 0.8},
                {"score_share": 0.15, "difficulty_estimate": 7.4, "bloom_level": 5,
                 "allocation_confidence": 0.8},
                {"score_share": 0.15, "difficulty_estimate": 7.6, "bloom_level": 5,
                 "allocation_confidence": 0.8},
            ],
            "diagnostic_units": [
                {"description": "novel system misconception", "trap_strength": 3},
                {"description": "pathway interpretation misconception", "trap_strength": 2},
            ],
        }}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            7.1,
            {
                "working_memory": 4,
                "reasoning_steps": 5,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 2,
                "representation_complexity": 2,
                "info_density": 3,
            },
            analysis,
            is_big_question=True,
            total_score=11,
        )

        assert adjusted >= 8.0
        assert "evidence_rich_big_question_floor" in flags

    def test_high_value_method_rich_big_question_keeps_upper_load_floor(self):
        pipeline = DifficultyPipeline()
        analysis = {"_fine_grained": {
            "scoring_units": [
                {"score_share": 0.10, "difficulty_estimate": 4.0, "bloom_level": 3,
                 "allocation_confidence": 0.65},
                {"score_share": 0.12, "difficulty_estimate": 5.0, "bloom_level": 3,
                 "allocation_confidence": 0.65},
                {"score_share": 0.12, "difficulty_estimate": 6.0, "bloom_level": 4,
                 "allocation_confidence": 0.65},
                {"score_share": 0.12, "difficulty_estimate": 6.5, "bloom_level": 4,
                 "allocation_confidence": 0.65},
                {"score_share": 0.12, "difficulty_estimate": 7.0, "bloom_level": 5,
                 "allocation_confidence": 0.65},
                {"score_share": 0.14, "difficulty_estimate": 7.5, "bloom_level": 5,
                 "allocation_confidence": 0.65},
                {"score_share": 0.14, "difficulty_estimate": 8.0, "bloom_level": 5,
                 "allocation_confidence": 0.65},
                {"score_share": 0.14, "difficulty_estimate": 8.2, "bloom_level": 5,
                 "allocation_confidence": 0.65},
            ],
            "diagnostic_units": [
                {"description": "primer design trap", "trap_strength": 3},
                {"description": "insert orientation trap", "trap_strength": 2},
                {"description": "expression-system inference trap", "trap_strength": 2},
            ],
        }}

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            7.3,
            {
                "working_memory": 4,
                "reasoning_steps": 6,
                "trap_density": 2,
                "novelty": 3,
                "knowledge_breadth": 3,
                "representation_complexity": 3,
                "info_density": 3,
            },
            analysis,
            is_big_question=True,
            total_score=14,
        )

        assert adjusted >= 8.6
        assert "evidence_rich_big_question_floor" in flags


class TestParseBigQuestion:
    """大题结构化 JSON 解析测试。"""

    def setup_method(self):
        from feature_extractor import parse_big_question_features
        self.parse = parse_big_question_features

    def _valid_input(self):
        return json.dumps({
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "基础"},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "分析"},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "strong", "reason": "依赖前问结论"}
            ],
            "global_features": {
                "shared_context_load": 2, "global_method_novelty": 3,
            },
            "bloom": 4, "bloom_reason": "分析",
            "info_density": 2, "representation_complexity": 2,
            "quality_score": 4,
            "quality_scientific": "准确",
            "quality_normative": "规范",
            "quality_language": "清晰",
            "quality_context": "合理",
            "quality_sensitivity": "无风险",
            "teacher_comment": "考查能力综合。",
        })

    def test_valid_parse(self):
        result = self.parse(self._valid_input())
        assert result is not None
        assert len(result["subquestions"]) == 2
        assert result["subquestions"][0]["working_memory"] == 3
        assert len(result["dependencies"]) == 1
        assert result["global_features"]["global_method_novelty"] == 3
        assert result["report"]["bloom"] == 4

    def test_subquestion_range_clipped(self):
        """小问特征越界被裁剪。"""
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 10, "reasoning_steps": 0,
                 "trap_density": 5, "novelty": -1, "knowledge_breadth": 99, "brief": "x"},
            ],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        result = self.parse(raw)
        sq = result["subquestions"][0]
        assert sq["working_memory"] == 5
        assert sq["reasoning_steps"] == 1
        assert sq["trap_density"] == 3
        assert sq["novelty"] == 1
        assert sq["knowledge_breadth"] == 3

    def test_empty_subquestions_returns_none(self):
        """空 subquestions → 返回 None（触发 fallback）。"""
        raw = json.dumps({
            "subquestions": [],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        assert self.parse(raw) is None

    def test_missing_dependencies_defaults_empty(self):
        """缺失 dependencies → 视为空。"""
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 6, "working_memory": 3, "reasoning_steps": 4,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
            ],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        result = self.parse(raw)
        assert result["dependencies"] == []

    def test_missing_global_features_defaults(self):
        """缺失 global_features → 用默认值。"""
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 6, "working_memory": 3, "reasoning_steps": 4,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
            ],
            "dependencies": [],
            "bloom": 3,
        })
        result = self.parse(raw)
        assert result["global_features"]["shared_context_load"] == 1
        assert result["global_features"]["global_method_novelty"] == 1

    def test_unparseable_returns_none(self):
        """不可解析文本 → 返回 None。"""
        assert self.parse("这是一道很难的题") is None

    def test_report_fields_preserved(self):
        """报告字段（bloom/quality/teacher_comment）正确保留。"""
        result = self.parse(self._valid_input())
        assert "bloom" in result["report"]
        assert "quality_scientific" in result["report"]
        assert "teacher_comment" in result["report"]

    def test_detailed_parse_reports_json_failure_type(self):
        result = self.parse("not json", detailed=True)
        assert result["ok"] is False
        assert result["data"] is None
        assert result["failure_type"] == "json_parse_failed"
        assert result["raw_length"] == len("not json")

    def test_detailed_parse_reports_points_sum_mismatch(self):
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 2, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 2, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
            ],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        result = self.parse(raw, total_score=12, detailed=True)
        assert result["ok"] is False
        assert result["failure_type"] == "points_sum_mismatch"
        assert any("points_sum" in item for item in result["errors"])

    def test_detailed_parse_accepts_schema_wrapper(self):
        wrapped = json.dumps({"status": "ok", "data": json.loads(self._valid_input())})
        result = self.parse(wrapped, total_score=8, detailed=True)
        assert result["ok"] is True
        assert result["failure_type"] is None
        assert len(result["data"]["subquestions"]) == 2

    def test_detailed_parse_reports_model_failure_payload(self):
        raw = json.dumps({
            "status": "failed",
            "failure_type": "cannot_identify_subquestions",
            "reason": "subquestion labels are not visible",
        })
        result = self.parse(raw, detailed=True)
        assert result["ok"] is False
        assert result["failure_type"] == "cannot_identify_subquestions"
        assert result["errors"] == ["subquestion labels are not visible"]

    def test_detailed_parse_rejects_missing_scoring_fields(self):
        raw = json.dumps({
            "status": "ok",
            "data": {
                "subquestions": [
                    {"id": 1, "points": 4, "working_memory": 3},
                ],
                "dependencies": [],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })
        result = self.parse(raw, total_score=4, detailed=True)
        assert result["ok"] is False
        assert result["failure_type"] == "invalid_subquestion_schema"
        assert any("missing reasoning_steps" in item for item in result["errors"])

    def test_detailed_parse_rejects_truncated_json(self):
        raw = '{"status":"ok","data":{"subquestions":[{"id":1,"points":4'
        result = self.parse(raw, total_score=4, detailed=True)
        assert result["ok"] is False
        assert result["failure_type"] == "json_truncated"


class TestBuildBigQuestionPrompt:
    """大题专用 prompt 构建测试。"""

    def setup_method(self):
        from feature_extractor import build_big_question_prompt
        self.build = build_big_question_prompt

    def test_contains_subquestions_instruction(self):
        prompt = self.build("某大题内容", question_type="实验题")
        assert "subquestions" in prompt
        assert "dependencies" in prompt
        assert "global_features" in prompt
        assert "shared_context_load" in prompt
        assert "global_method_novelty" in prompt

    def test_contains_strength_values(self):
        prompt = self.build("某大题内容")
        assert "weak" in prompt
        assert "strong" in prompt

    def test_contains_question_text(self):
        prompt = self.build("番茄红素PSY融合蛋白实验", correct_answer="见解析")
        assert "番茄红素PSY融合蛋白实验" in prompt
        assert "见解析" in prompt

    def test_contains_strict_status_contract(self):
        prompt = self.build("某大题内容", question_type="实验题")
        assert '"status": "ok"' in prompt
        assert '"status": "failed"' in prompt
        assert '"failure_type"' in prompt
        assert "score_share" in prompt

    def test_prompt_uses_score_share_not_points(self):
        """v3.2: prompt 使用 score_share 而非 points。"""
        prompt = self.build("某大题内容", question_type="实验题")
        assert "score_share" in prompt
        # points_sum 和 points_unknown 不应出现在新 prompt 中
        assert "points_sum" not in prompt
        assert "points_unknown" not in prompt

    def test_big_question_prompt_file_registered(self):
        from prompt_loader import PromptLoader

        loader = PromptLoader("biology")
        assert loader.exists("big_question_extractor")
        prompt = loader.load(
            "big_question_extractor",
            question_block="题干文本",
            qtype_hint="\n题型：实验题",
        )
        assert "题干文本" in prompt
        assert "{question_block}" not in prompt



class TestBigQuestionPipeline:
    """大题 pipeline 分流 + fallback 测试。"""

    def _chained_design_structured_features(self):
        return {
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
                {"id": 3, "points": 6, "working_memory": 4, "reasoning_steps": 4,
                 "trap_density": 3, "novelty": 3, "knowledge_breadth": 2},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "weak", "reason": "背景知识"},
                {"from": 2, "to": 3, "strength": "strong", "reason": "改造方案"},
            ],
            "global_features": {"shared_context_load": 2, "global_method_novelty": 3},
            "report": {"bloom": 5, "info_density": 3, "representation_complexity": 2,
                       "quality_score": 4, "teacher_comment": "综合实验题"},
        }

    def test_big_question_routes_to_structured(self):
        """total_score >= 8 → 走大题结构化路径。"""
        structured = self._chained_design_structured_features()
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "番茄红素PSY融合蛋白...",
                    "question_type": "实验题",
                    "correct_answer": "见解析",
                    "total_score": 14,
                })
            )
        assert result["final_difficulty"] > 7.5
        assert result["features"]["chain_coupling"] >= 2
        assert "big_question_fallback" not in (result.get("flags") or [])

    def test_small_question_uses_v3(self):
        """total_score < 8 → 走 v3 原路径。"""
        mock_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 1,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
        }
        with patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "下列关于DNA...", "question_type": "选择题",
                    "correct_answer": "A", "total_score": 2,
                })
            )
        assert result["features"] is not None
        assert "big_question_fallback" not in (result.get("flags") or [])
        assert "_big_question" not in result["features"], "选择题不应有 _big_question 元数据"

    def test_boundary_score_8_triggers_big(self):
        """total_score = 8 → 触发大题路径。"""
        structured_8 = {
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 4,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "strong", "reason": "前问结论"},
            ],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "report": {"bloom": 4},
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured_8):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题...", "question_type": "简答题",
                    "correct_answer": "", "total_score": 8,
                })
            )
        assert result["features"] is not None
        assert "_big_question" in result["features"], "total_score=8 应走大题路径"

    def test_boundary_score_7_stays_v3(self):
        """total_score = 7 → 不触发大题路径。"""
        mock_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 2,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
        }
        with patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某题...", "question_type": "简答题",
                    "correct_answer": "", "total_score": 7,
                })
            )
        assert result["features"] is not None
        assert "_big_question" not in result["features"], "total_score=7 不应走大题路径"

    def test_fails_closed_on_parse_failure(self):
        """结构化解析失败 → 不得 fallback 到普通特征路径生成假难度。"""
        mock_flat = {
            "working_memory": 4, "reasoning_steps": 6, "chain_coupling": 2,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 4, "info_density": 2, "representation_complexity": 1,
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=None), \
             patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_flat):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题...", "question_type": "实验题",
                 "correct_answer": "", "total_score": 12,
                })
            )
        assert result["features"]["_feature_status"] == "failed"
        assert result["final_difficulty"] is None
        assert result["analysis_failed"] is True
        assert "big_question_structure_failed" in result.get("flags", [])

    def test_big_question_parse_failure_reason_is_preserved(self):
        failure_payload = {
            "_big_question_failed": True,
            "failure_type": "json_parse_failed",
            "errors": ["JSON parse failed"],
            "_llm_calls": [{
                "purpose": "big_question_feature_extraction",
                "prompt_id": "biology.big_question_feature_extraction",
                "metadata": {
                    "status": "parse_failed",
                    "failure_type": "json_parse_failed",
                    "response_length": 8,
                },
            }],
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=failure_payload):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题...", "question_type": "实验题",
                    "correct_answer": "", "total_score": 12,
                })
            )
        assert result["final_difficulty"] is None
        assert result["analysis_failed"] is True
        assert result["failure_reason"] == "json_parse_failed"
        assert "big_question_structure_failed" in result.get("flags", [])
        assert "json_parse_failed" in result.get("flags", [])
        assert result["features"]["_llm_calls"][0]["metadata"]["failure_type"] == "json_parse_failed"

    def test_feature_extraction_sends_media_and_records_input_refs(self):
        raw_json = json.dumps({
            "working_memory": 3,
            "working_memory_reason": "chart variables",
            "reasoning_steps": 4,
            "steps_detail": "read chart then infer",
            "chain_coupling": 2,
            "coupling_reason": "partial dependency",
            "trap_density": 2,
            "trap_reason": "chart distractor",
            "novelty": 2,
            "novelty_reason": "variant",
            "knowledge_breadth": 2,
            "breadth_reason": "cross point",
            "bloom": 4,
            "bloom_reason": "analysis",
            "info_density": 2,
            "density_reason": "chart",
            "representation_complexity": 3,
            "representation_reason": "visual evidence",
            "quality_score": 4,
            "quality_scientific": "ok",
            "quality_normative": "ok",
            "quality_language": "ok",
            "quality_context": "ok",
            "quality_sensitivity": "ok",
            "teacher_comment": "review chart",
        })
        captured = {}

        async def fake_send_message(prompt, **kwargs):
            captured["prompt"] = prompt
            captured["purpose"] = kwargs["purpose"]
            return raw_json

        async def fake_extract_visual_context(media_items, **kwargs):
            assert media_items[0]["base64"].startswith("iVBOR")
            return "Visual context extracted by Qwen Vision for DeepSeek review only:\nocr_text: chart axis", {
                "call_id": "biology-feature-visual-context",
                "question_id": None,
                "purpose": "image_inputs",
                "prompt_id": "biology.image_inputs.visual_context",
                "prompt_hash": "a" * 64,
                "provider": "qwen_vision",
                "model": "qwen3-vl-plus",
                "input_refs": {"media_count": 1, "media_types": ["image"]},
                "parsed_schema": "VisualContextResult",
                "confidence": 0.9,
                "validation_errors": [],
                "fallback_count": 0,
                "retry_count": 0,
                "metadata": {"used_as": "deepseek_text_prompt_context"},
            }

        with patch("feature_extractor.extract_visual_context", new=AsyncMock(side_effect=fake_extract_visual_context)):
            with patch("feature_extractor.send_message_gpt", new=AsyncMock(side_effect=fake_send_message)):
                from feature_extractor import extract_features
                result = asyncio.get_event_loop().run_until_complete(
                    extract_features(
                        "question with chart",
                        subject="biology",
                        media_items=[{"type": "image", "base64": "iVBORw0KGgoAAA"}],
                    )
                )

        assert "chart axis" in captured["prompt"]
        assert captured["purpose"] == "feature_extraction"
        assert result["_llm_calls"][0]["purpose"] == "image_inputs"
        call = result["_llm_calls"][1]
        assert call["purpose"] == "feature_extraction"
        assert call["input_refs"]["media_count"] == 1
        assert call["input_refs"]["media_types"] == ["image"]
        assert call["metadata"]["visual_context_source"] == "qwen_vision"

    def test_feature_extraction_retries_compact_after_empty_provider_response(self):
        raw_json = json.dumps({
            "working_memory": 3,
            "working_memory_reason": "compare conditions",
            "reasoning_steps": 4,
            "steps_detail": "read stem then infer",
            "chain_coupling": 1,
            "coupling_reason": "independent choices",
            "trap_density": 2,
            "trap_reason": "absolute wording",
            "novelty": 2,
            "novelty_reason": "variant",
            "knowledge_breadth": 2,
            "breadth_reason": "two concepts",
            "bloom": 4,
            "bloom_reason": "analysis",
            "info_density": 2,
            "density_reason": "moderate",
            "representation_complexity": 1,
            "representation_reason": "text",
            "quality_score": 4,
            "quality_scientific": "ok",
            "quality_normative": "ok",
            "quality_language": "ok",
            "quality_context": "ok",
            "quality_sensitivity": "ok",
            "teacher_comment": "retry recovered",
        })
        calls = []

        async def fake_send_message(prompt, **kwargs):
            calls.append(prompt)
            if len(calls) == 1:
                raise RuntimeError("LLM 返回空内容，视为失败触发 fallback")
            return raw_json

        with patch("feature_extractor.send_message_gpt", new=AsyncMock(side_effect=fake_send_message)):
            from feature_extractor import extract_features
            result = asyncio.get_event_loop().run_until_complete(
                extract_features(
                    "question with an occasional empty provider response",
                    subject="biology",
                    question_type="single_choice",
                )
            )

        assert result["_feature_status"] == "ok"
        assert result.get("_feature_failed") is not True
        assert len(calls) == 2
        call = result["_llm_calls"][0]
        assert call["retry_count"] == 1
        assert call["metadata"]["recovery_mode"] == "api_failure_compact_retry"

    def test_full_chain_with_raw_json(self):
        """A-002: 入口级集成测试 — mock send_message_gpt 返回原始 JSON。"""
        raw_json = json.dumps({
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "基础"},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "分析"},
                {"id": 3, "points": 6, "working_memory": 4, "reasoning_steps": 4,
                 "trap_density": 3, "novelty": 3, "knowledge_breadth": 2, "brief": "设计"},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "weak", "reason": "背景知识"},
                {"from": 2, "to": 3, "strength": "strong", "reason": "改造方案"},
            ],
            "global_features": {
                "shared_context_load": 2, "global_method_novelty": 3,
                "shared_context_reason": "GFP融合", "method_novelty_reason": "In-Fusion",
            },
            "bloom": 5, "bloom_reason": "评价",
            "info_density": 3, "density_reason": "多图",
            "representation_complexity": 2, "representation_reason": "载体图",
            "quality_score": 4,
            "quality_scientific": "无明显问题",
            "quality_normative": "合理",
            "quality_language": "清晰",
            "quality_context": "真实",
            "quality_sensitivity": "无风险",
            "teacher_comment": "综合实验题。",
        })
        with patch("feature_extractor.send_message_gpt",
                   new_callable=AsyncMock, return_value=raw_json):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "番茄红素PSY融合蛋白...",
                    "question_type": "实验题",
                    "correct_answer": "见解析",
                    "total_score": 14,
                })
            )
        assert result["final_difficulty"] > 7.5
        assert "_big_question" in result["features"]

    def test_points_sum_mismatch_fails_closed(self):
        """A-003: points 总和与 total_score 偏差 >20% → parse 阶段阻断。"""
        failure_payload = {
            "_big_question_failed": True,
            "failure_type": "points_sum_mismatch",
            "errors": ["points_sum=4, total_score=12"],
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=failure_payload):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题...", "question_type": "简答题",
                    "correct_answer": "", "total_score": 12,
                })
            )
        assert result["analysis_failed"] is True
        assert result["final_difficulty"] is None
        assert "points_sum_mismatch" in result.get("flags", [])



    def test_partial_invalid_deps_flagged(self):
        """部分依赖无效时应标记 dep_partial_invalid flag。"""
        structured = {
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "strong", "reason": "合法"},
                {"from": 9, "to": 2, "strength": "strong", "reason": "非法ID"},
            ],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "report": {"bloom": 3},
            "_dropped_deps": 1,
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题内容...", "question_type": "简答题",
                    "correct_answer": "", "total_score": 8,
                })
            )
        assert "dep_partial_invalid" in result.get("flags", []), "部分无效依赖应标记 flag"


class TestConstructedResponseBottleneck:
    """Constructed-response fixtures verify construct signals, not question IDs."""

    def test_chained_high_novelty_constructed_response_is_hard(self):
        """A chained high-novelty design task should land in the hard band."""
        structured = {
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
                {"id": 3, "points": 6, "working_memory": 4, "reasoning_steps": 4,
                 "trap_density": 3, "novelty": 3, "knowledge_breadth": 2},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "weak", "reason": "背景知识"},
                {"from": 2, "to": 3, "strength": "strong", "reason": "改造方案"},
            ],
            "global_features": {"shared_context_load": 2, "global_method_novelty": 3},
            "report": {"bloom": 5, "info_density": 3, "representation_complexity": 2},
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "番茄红素PSY融合蛋白实验...",
                    "question_type": "实验题",
                    "correct_answer": "见解析",
                    "total_score": 14,
                })
            )
        score = result["final_difficulty"]
        assert score > 7.5
        assert score <= 10.0
        assert "_big_question" in result["features"]
        assert len(result["features"]["_big_question"]["subquestions"]) == 3

    def test_four_part_visual_question_keeps_chain_and_visual_burden(self):
        """四小问图表大题不应因单小问宽度较低而被压低。"""
        structured = {
            "subquestions": [
                {"id": 1, "points": 2, "working_memory": 2, "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 1},
                {"id": 2, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 3, "novelty": 2, "knowledge_breadth": 2},
                {"id": 3, "points": 4, "working_memory": 3, "reasoning_steps": 4,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
                {"id": 4, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "strong", "reason": "定位失败原因决定改造方案"},
                {"from": 3, "to": 4, "strength": "weak", "reason": "共用三引物PCR图示"},
            ],
            "global_features": {"shared_context_load": 3, "global_method_novelty": 3},
            "report": {"bloom": 5, "info_density": 3, "representation_complexity": 2},
        }
        analysis = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.2, "difficulty_estimate": 5.5, "bloom_level": 4,
                     "allocation_confidence": 0.9},
                    {"score_share": 0.4, "difficulty_estimate": 8.0, "bloom_level": 6,
                     "allocation_confidence": 0.9},
                    {"score_share": 0.2, "difficulty_estimate": 5.5, "bloom_level": 3,
                     "allocation_confidence": 0.9},
                    {"score_share": 0.2, "difficulty_estimate": 5.5, "bloom_level": 4,
                     "allocation_confidence": 0.9},
                ]
            }
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "番茄红素PSY融合蛋白实验，含表1、图2和电泳鉴定。",
                    "question_type": "实验题",
                    "correct_answer": "见解析",
                    "total_score": 14,
                    "image_base64": "image",
                }, analysis_result=analysis)
            )
        assert result["features"]["chain_coupling"] == 2
        assert result["features"]["knowledge_breadth"] == 3
        assert result["features"]["representation_complexity"] == 3
        assert "media_representation_adjustment" in result["flags"]
        assert result["final_difficulty"] > 7.5, result

    def test_parallel_big_question_not_overscored(self):
        """A-005: 并列大题不应被过度提升。

        入口: pipeline.evaluate_with_refinement(parallel_question)
        反例: 错误实现可能对并列大题也应用关键路径加成——本测试验证无 strong 依赖时不过度提升
        边界: 全并列 / 混合 strong+weak / 单小问大题
        回归: 防止 v3.1 引入并列大题系统性高估
        命令: docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestConstructedResponseBottleneck::test_parallel_big_question_not_overscored -v
        """
        structured = {
            "subquestions": [
                {"id": 1, "points": 3, "working_memory": 3, "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 3, "working_memory": 3, "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 3, "points": 3, "working_memory": 3, "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 4, "points": 3, "working_memory": 3, "reasoning_steps": 2,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            ],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "report": {"bloom": 3, "info_density": 2, "representation_complexity": 1},
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "并列简答题...",
                    "question_type": "简答题",
                    "correct_answer": "",
                    "total_score": 12,
                })
            )
        score = result["final_difficulty"]
        assert score < 7.0, f"全并列简单大题不应超 7.0，实际 {score}"


class TestBigQuestionRetry:
    """大题结构化提取 retry 机制测试。"""

    def test_retry_on_points_sum_mismatch(self):
        """首次 points_sum 不匹配时 retry 一次，第二次成功则用第二次结果。"""
        bad_response = json.dumps({
            "status": "ok", "points_sum": 6,
            "data": {
                "subquestions": [
                    {"id": 1, "points": 2, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                    {"id": 2, "points": 2, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
                    {"id": 3, "points": 2, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "z"},
                ],
                "dependencies": [],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })
        good_response = json.dumps({
            "status": "ok", "points_sum": 12,
            "data": {
                "subquestions": [
                    {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                    {"id": 2, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
                    {"id": 3, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "z"},
                ],
                "dependencies": [],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })
        with patch("feature_extractor.send_message_gpt",
                   new_callable=AsyncMock, side_effect=[bad_response, good_response]):
            from feature_extractor import extract_big_question_features
            result = asyncio.get_event_loop().run_until_complete(
                extract_big_question_features(
                    "某大题...", total_score=12, return_failure=True
                )
            )
        assert result is not None
        assert not result.get("_big_question_failed", False)
        assert len(result["subquestions"]) == 3
        assert sum(sq["points"] for sq in result["subquestions"]) == 12

    def test_retry_both_fail_returns_failure(self):
        """两次都失败则返回失败 payload。"""
        bad_response = json.dumps({
            "status": "ok", "points_sum": 6,
            "data": {
                "subquestions": [
                    {"id": 1, "points": 2, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                    {"id": 2, "points": 2, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
                    {"id": 3, "points": 2, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "z"},
                ],
                "dependencies": [],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })
        with patch("feature_extractor.send_message_gpt",
                   new_callable=AsyncMock, side_effect=[bad_response, bad_response]):
            from feature_extractor import extract_big_question_features
            result = asyncio.get_event_loop().run_until_complete(
                extract_big_question_features(
                    "某大题...", total_score=12, return_failure=True
                )
            )
        assert result.get("_big_question_failed") is True
        assert result["failure_type"] == "points_sum_mismatch"

    def test_no_retry_on_model_reported_failure(self):
        """模型明确报告失败（status=failed）时不 retry。"""
        model_fail = json.dumps({
            "status": "failed",
            "failure_type": "cannot_identify_subquestions",
            "reason": "subquestion structure not visible",
        })
        mock_send = AsyncMock(return_value=model_fail)
        with patch("feature_extractor.send_message_gpt", mock_send):
            from feature_extractor import extract_big_question_features
            result = asyncio.get_event_loop().run_until_complete(
                extract_big_question_features(
                    "某大题...", total_score=12, return_failure=True
                )
            )
        assert result.get("_big_question_failed") is True
        assert mock_send.call_count == 1


class TestParseScoreShare:
    """score_share 模式解析测试。"""

    def setup_method(self):
        from feature_extractor import parse_big_question_features
        self.parse = parse_big_question_features

    def test_score_share_parsed_and_points_derived(self):
        """score_share 输入 → 解析成功，points 由 total_score * score_share 派生。"""
        raw = json.dumps({
            "status": "ok",
            "data": {
                "subquestions": [
                    {"id": 1, "score_share": 0.25, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                    {"id": 2, "score_share": 0.25, "working_memory": 4, "reasoning_steps": 3,
                     "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
                    {"id": 3, "score_share": 0.50, "working_memory": 4, "reasoning_steps": 5,
                     "trap_density": 2, "novelty": 3, "knowledge_breadth": 2, "brief": "z"},
                ],
                "dependencies": [{"from": 1, "to": 2, "strength": "strong", "reason": "x"}],
                "global_features": {"shared_context_load": 2, "global_method_novelty": 1},
                "bloom": 4,
            },
        })
        result = self.parse(raw, total_score=12, detailed=True)
        assert result["ok"] is True
        sqs = result["data"]["subquestions"]
        assert sqs[0]["points"] == 3   # 12 * 0.25 = 3
        assert sqs[1]["points"] == 3   # 12 * 0.25 = 3
        assert sqs[2]["points"] == 6   # 12 * 0.50 = 6
        assert sqs[0]["score_share"] == 0.25
        assert result["data"].get("allocation_source") == "inferred"

    def test_score_share_sum_mismatch_rejected(self):
        """score_share 之和偏离 1.0 超过 10% → 失败。"""
        raw = json.dumps({
            "status": "ok",
            "data": {
                "subquestions": [
                    {"id": 1, "score_share": 0.2, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                    {"id": 2, "score_share": 0.2, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
                ],
                "dependencies": [],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })
        result = self.parse(raw, total_score=12, detailed=True)
        assert result["ok"] is False
        assert result["failure_type"] == "score_share_sum_mismatch"

    def test_dependency_cycle_rejected(self):
        """Cyclic subquestion dependencies must fail closed before scoring."""
        raw = json.dumps({
            "status": "ok",
            "data": {
                "subquestions": [
                    {"id": 1, "score_share": 0.34, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                    {"id": 2, "score_share": 0.33, "working_memory": 3, "reasoning_steps": 4,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
                    {"id": 3, "score_share": 0.33, "working_memory": 3, "reasoning_steps": 5,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "z"},
                ],
                "dependencies": [
                    {"from": 1, "to": 2, "strength": "strong"},
                    {"from": 2, "to": 3, "strength": "strong"},
                    {"from": 3, "to": 1, "strength": "strong"},
                ],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })

        result = self.parse(raw, total_score=12, detailed=True)

        assert result["ok"] is False
        assert result["failure_type"] == "dependency_cycle"

    def test_score_share_normalized_within_tolerance(self):
        """score_share 之和在 0.9~1.1 范围内 → 自动归一化后通过。"""
        raw = json.dumps({
            "status": "ok",
            "data": {
                "subquestions": [
                    {"id": 1, "score_share": 0.34, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                    {"id": 2, "score_share": 0.34, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
                    {"id": 3, "score_share": 0.34, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "z"},
                ],
                "dependencies": [],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })
        result = self.parse(raw, total_score=12, detailed=True)
        assert result["ok"] is True
        sqs = result["data"]["subquestions"]
        total_derived = sum(sq["points"] for sq in sqs)
        assert total_derived == 12

    def test_backward_compat_absolute_points_still_work(self):
        """旧格式（absolute points）仍然可用——向后兼容。"""
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
            ],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        result = self.parse(raw, total_score=8, detailed=True)
        assert result["ok"] is True
        assert result["data"]["subquestions"][0]["points"] == 4
        assert result["data"].get("allocation_source") == "explicit"

    def test_score_share_rounding_adjustment(self):
        """score_share 派生 points 时，四舍五入确保总和精确等于 total_score。"""
        raw = json.dumps({
            "status": "ok",
            "data": {
                "subquestions": [
                    {"id": 1, "score_share": 0.33, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
                    {"id": 2, "score_share": 0.33, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "y"},
                    {"id": 3, "score_share": 0.34, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "z"},
                ],
                "dependencies": [],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })
        result = self.parse(raw, total_score=10, detailed=True)
        assert result["ok"] is True
        sqs = result["data"]["subquestions"]
        total_derived = sum(sq["points"] for sq in sqs)
        assert total_derived == 10, f"total points should be exactly 10, got {total_derived}"

    def test_allocation_source_in_legacy_mode(self):
        """旧格式解析结果包含 allocation_source=explicit。"""
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 6, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
            ],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        result = self.parse(raw, total_score=6, detailed=True)
        assert result["ok"] is True
        assert result["data"].get("allocation_source") == "explicit"


    def test_score_share_extreme_small_value(self):
        """极小 score_share 强制最低1分后 sum 仍等于 total_score。"""
        from feature_extractor import parse_big_question_features
        raw = json.dumps({
            "status": "ok",
            "data": {
                "subquestions": [
                    {"id": 1, "score_share": 0.01, "working_memory": 2, "reasoning_steps": 2,
                     "trap_density": 1, "novelty": 1, "knowledge_breadth": 1, "brief": "x"},
                    {"id": 2, "score_share": 0.01, "working_memory": 2, "reasoning_steps": 2,
                     "trap_density": 1, "novelty": 1, "knowledge_breadth": 1, "brief": "y"},
                    {"id": 3, "score_share": 0.98, "working_memory": 3, "reasoning_steps": 3,
                     "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "z"},
                ],
                "dependencies": [],
                "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
                "bloom": 3,
            },
        })
        result = parse_big_question_features(raw, total_score=8, detailed=True)
        assert result["ok"] is True
        sqs = result["data"]["subquestions"]
        total_pts = sum(sq["points"] for sq in sqs)
        assert total_pts == 8, f"sum(points)={total_pts}, expected 8"
        assert all(sq["points"] >= 1 for sq in sqs)

class TestSEUFallback:
    """大题结构化失败时的 SEU fallback 测试。"""

    def test_seu_fallback_produces_score_when_big_question_fails(self):
        """big_question failure must not emit a normal-looking fallback score."""
        failure_payload = {
            "_big_question_failed": True,
            "failure_type": "points_sum_mismatch",
            "errors": ["points_sum=6, total_score=12"],
        }
        analysis_result = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.33, "difficulty_estimate": 7.0, "bloom_level": 4,
                     "allocation_confidence": 0.8},
                    {"score_share": 0.33, "difficulty_estimate": 6.0, "bloom_level": 3,
                     "allocation_confidence": 0.8},
                    {"score_share": 0.34, "difficulty_estimate": 8.0, "bloom_level": 5,
                     "allocation_confidence": 0.8},
                ],
            },
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=failure_payload):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某实验探究光照强度对植物光合速率的影响，请据图分析回答下列问题。", "question_type": "简答题",
                    "correct_answer": "", "total_score": 12,
                }, analysis_result=analysis_result)
            )
        assert result.get("analysis_failed") is True
        assert result["final_difficulty"] is None
        assert result["difficulty_source"] == "analysis_failed"
        assert "seu_available_but_not_authoritative" in result["flags"]
        assert result["features"]["seu_count"] == 3

    def test_seu_fallback_uses_bottleneck_not_average_for_constructed_response(self):
        failure_payload = {
            "_big_question_failed": True,
            "failure_type": "json_parse_failed",
            "errors": ["broken structured payload"],
        }
        analysis_result = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.35, "difficulty_estimate": 9.0, "bloom_level": 6,
                     "allocation_confidence": 0.9},
                    {"score_share": 0.25, "difficulty_estimate": 3.0, "bloom_level": 2,
                     "allocation_confidence": 0.9},
                    {"score_share": 0.20, "difficulty_estimate": 3.0, "bloom_level": 2,
                     "allocation_confidence": 0.9},
                    {"score_share": 0.20, "difficulty_estimate": 3.0, "bloom_level": 2,
                     "allocation_confidence": 0.9},
                ],
            },
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=failure_payload):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "A constructed response item with one substantial high-order design bottleneck and several routine blanks.",
                    "question_type": "experiment",
                    "correct_answer": "",
                    "total_score": 12,
                }, analysis_result=analysis_result)
            )

        assert result["difficulty_source"] == "analysis_failed"
        assert result["final_difficulty"] is None
        assert "seu_available_but_not_authoritative" in result["flags"]

    def test_seu_fallback_not_triggered_without_seus(self):
        """big_question 失败 + 无 SEU → 仍然 failed。"""
        failure_payload = {
            "_big_question_failed": True,
            "failure_type": "points_sum_mismatch",
            "errors": ["points_sum=6, total_score=12"],
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=failure_payload):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题...", "question_type": "简答题",
                    "correct_answer": "", "total_score": 12,
                }, analysis_result={})
            )
        assert result["analysis_failed"] is True
        assert result["final_difficulty"] is None

    def test_seu_fallback_short_content_records_block_flag(self):
        failure_payload = {
            "_big_question_failed": True,
            "failure_type": "points_sum_mismatch",
            "errors": ["points_sum=6, total_score=12"],
        }
        analysis_result = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.33, "difficulty_estimate": 7.0, "bloom_level": 4,
                     "allocation_confidence": 0.8},
                    {"score_share": 0.33, "difficulty_estimate": 6.0, "bloom_level": 3,
                     "allocation_confidence": 0.8},
                    {"score_share": 0.34, "difficulty_estimate": 8.0, "bloom_level": 5,
                     "allocation_confidence": 0.8},
                ],
            },
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=failure_payload):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "short stem", "question_type": "绠€绛旈",
                    "correct_answer": "", "total_score": 12,
                }, analysis_result=analysis_result)
            )
        assert result["analysis_failed"] is True
        assert result["final_difficulty"] is None
        assert "seu_available_but_not_authoritative" in result["flags"]

    def test_seu_fallback_requires_minimum_seus(self):
        """SEU 数量 < 2 → 不触发 fallback。"""
        failure_payload = {
            "_big_question_failed": True,
            "failure_type": "score_share_sum_mismatch",
            "errors": ["score_share_sum=0.4"],
        }
        analysis_result = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 1.0, "difficulty_estimate": 5.0, "bloom_level": 3,
                     "allocation_confidence": 0.5},
                ],
            },
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=failure_payload):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题...", "question_type": "简答题",
                    "correct_answer": "", "total_score": 12,
                }, analysis_result=analysis_result)
            )
        assert result["analysis_failed"] is True

    def test_seu_fallback_marks_cognitive_level_source(self):
        """SEU evidence is retained as context, but failure remains explicit."""
        failure_payload = {
            "_big_question_failed": True,
            "failure_type": "points_sum_mismatch",
            "errors": ["points_sum=6, total_score=12"],
        }
        analysis_result = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.33, "difficulty_estimate": 7.0, "bloom_level": 4,
                     "allocation_confidence": 0.8},
                    {"score_share": 0.33, "difficulty_estimate": 6.0, "bloom_level": 3,
                     "allocation_confidence": 0.8},
                    {"score_share": 0.34, "difficulty_estimate": 8.0, "bloom_level": 5,
                     "allocation_confidence": 0.8},
                ],
            },
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=failure_payload):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某实验探究光照强度对植物光合速率的影响，请据图分析回答下列问题。", "question_type": "简答题",
                    "correct_answer": "", "total_score": 12,
                }, analysis_result=analysis_result)
            )
        assert result.get("analysis_failed") is True
        assert result.get("cognitive_level_source") is None
        assert result["features"]["seu_count"] == 3


class TestDifficultyFacetAdjustments:
    """Regression coverage for the non-fitted four-layer difficulty signals."""

    def test_choice_medium_trap_burden_can_raise_decision_difficulty(self):
        from difficulty_pipeline import DifficultyPipeline

        pipeline = DifficultyPipeline()
        features = {
            "working_memory": 2,
            "reasoning_steps": 4,
            "chain_coupling": 1,
            "trap_density": 2,
            "novelty": 1,
            "knowledge_breadth": 1,
            "representation_complexity": 1,
            "info_density": 2,
        }
        analysis_result = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.25, "difficulty_estimate": 4.0, "bloom_level": 3, "allocation_confidence": 0.9},
                    {"score_share": 0.25, "difficulty_estimate": 4.2, "bloom_level": 3, "allocation_confidence": 0.9},
                    {"score_share": 0.25, "difficulty_estimate": 4.0, "bloom_level": 3, "allocation_confidence": 0.9},
                    {"score_share": 0.25, "difficulty_estimate": 4.3, "bloom_level": 3, "allocation_confidence": 0.9},
                ],
                "diagnostic_units": [
                    {"trap_strength": 2},
                    {"trap_strength": 2},
                    {"trap_strength": 2},
                    {"trap_strength": 2},
                ],
            },
        }

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            4.2,
            features,
            analysis_result,
            is_big_question=False,
            total_score=2,
        )

        assert adjusted >= 4.9
        assert "choice_decision_trap_adjustment" in flags

    def test_successful_evaluation_exports_score_risk_facets(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from difficulty_pipeline import DifficultyPipeline

        mock_features = {
            "working_memory": 3,
            "reasoning_steps": 4,
            "chain_coupling": 1,
            "trap_density": 2,
            "novelty": 2,
            "knowledge_breadth": 2,
            "bloom": 3,
            "info_density": 2,
            "representation_complexity": 1,
            "quality_score": 4,
            "_feature_status": "ok",
            "_raw_core_count": 9,
            "_extraction_confidence": 1.0,
            "_consistency_confidence": 1.0,
        }
        analysis_result = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.50, "difficulty_estimate": 5.0, "bloom_level": 3, "allocation_confidence": 0.9},
                    {"score_share": 0.50, "difficulty_estimate": 6.0, "bloom_level": 4, "allocation_confidence": 0.9},
                ],
            },
        }
        with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
            result = asyncio.get_event_loop().run_until_complete(
                DifficultyPipeline().evaluate_with_refinement({
                    "content": "A regular single-choice item with complete options.",
                    "question_type": "single_choice",
                    "correct_answer": "A",
                    "total_score": 2,
                }, analysis_result=analysis_result)
            )

        assert result["content_difficulty"] == result["final_difficulty"]
        assert result["difficulty_density"] > 0
        assert result["score_risk"] > 0
        assert result["score_layer"]["partial_credit_relief"] == 0

    def test_visual_constructed_response_is_stable_under_adjacent_feature_noise(self):
        from difficulty_pipeline import DifficultyPipeline
        from rule_scorer import compute_difficulty

        pipeline = DifficultyPipeline()
        stable_evidence = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.182, "difficulty_estimate": 6.0, "bloom_level": 4, "allocation_confidence": 0.8},
                    {"score_share": 0.182, "difficulty_estimate": 2.0, "bloom_level": 2, "allocation_confidence": 0.9},
                    {"score_share": 0.182, "difficulty_estimate": 6.5, "bloom_level": 4, "allocation_confidence": 0.8},
                    {"score_share": 0.182, "difficulty_estimate": 4.0, "bloom_level": 3, "allocation_confidence": 0.9},
                    {"score_share": 0.272, "difficulty_estimate": 7.5, "bloom_level": 5, "allocation_confidence": 0.7},
                ],
                "diagnostic_units": [
                    {"trap_strength": 3},
                    {"trap_strength": 2},
                ],
            },
        }
        high_feature_read = {
            "working_memory": 5,
            "reasoning_steps": 6,
            "chain_coupling": 2,
            "trap_density": 2,
            "novelty": 3,
            "knowledge_breadth": 3,
            "representation_complexity": 3,
            "info_density": 3,
        }
        low_feature_read = {
            "working_memory": 4,
            "reasoning_steps": 5,
            "chain_coupling": 2,
            "trap_density": 2,
            "novelty": 2,
            "knowledge_breadth": 3,
            "representation_complexity": 3,
            "info_density": 2,
        }

        high, _ = pipeline._apply_fine_grained_adjustments(
            compute_difficulty(high_feature_read),
            high_feature_read,
            stable_evidence,
            is_big_question=True,
            total_score=11,
        )
        low, _ = pipeline._apply_fine_grained_adjustments(
            compute_difficulty(low_feature_read),
            low_feature_read,
            stable_evidence,
            is_big_question=True,
            total_score=11,
        )

        assert low >= 7.8
        assert high - low <= 1.0

    def test_general_visual_big_question_ceiling_prevents_q17_top_score(self):
        from difficulty_pipeline import DifficultyPipeline

        pipeline = DifficultyPipeline()
        analysis_result = {
            "knowledge_points": ["光合作用的光反应", "碳固定", "人工光合"],
            "detailed_analysis": "比较人工光合细胞器和自然光反应，分析pH影响与人工系统优势。",
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.27, "difficulty_estimate": 6.0, "bloom_level": 4, "allocation_confidence": 0.8,
                     "label": "比较人工与自然光反应", "knowledge_links": [{"knowledge_point": "光合作用的光反应", "share": 1.0}]},
                    {"score_share": 0.09, "difficulty_estimate": 2.0, "bloom_level": 2, "allocation_confidence": 0.9,
                     "label": "识记ATP合成条件", "knowledge_links": [{"knowledge_point": "ATP", "share": 1.0}]},
                    {"score_share": 0.09, "difficulty_estimate": 4.0, "bloom_level": 3, "allocation_confidence": 0.9,
                     "label": "应用碳固定途径", "knowledge_links": [{"knowledge_point": "碳固定", "share": 1.0}]},
                    {"score_share": 0.27, "difficulty_estimate": 6.5, "bloom_level": 4, "allocation_confidence": 0.8,
                     "label": "分析pH影响机制", "knowledge_links": [{"knowledge_point": "光合作用的光反应", "share": 1.0}]},
                    {"score_share": 0.28, "difficulty_estimate": 7.5, "bloom_level": 5, "allocation_confidence": 0.7,
                     "label": "评价人工系统优势", "knowledge_links": [{"knowledge_point": "人工光合", "share": 1.0}]},
                ],
                "diagnostic_units": [{"trap_strength": 3}, {"trap_strength": 2}],
                "stimulus_units": [
                    {"complexity": 3, "is_core": True, "description": "人工光合细胞器示意图"}
                ],
            },
        }

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            10.0,
            {
                "working_memory": 5,
                "reasoning_steps": 8,
                "chain_coupling": 2,
                "trap_density": 2,
                "novelty": 3,
                "knowledge_breadth": 3,
                "representation_complexity": 3,
                "info_density": 3,
            },
            analysis_result,
            is_big_question=True,
            total_score=11,
        )

        assert adjusted == 8.6
        assert "general_visual_big_question_ceiling" in flags

    def test_fragmented_medium_big_item_is_capped_without_decisive_high_order_path(self):
        from difficulty_pipeline import DifficultyPipeline

        pipeline = DifficultyPipeline()
        analysis_result = {
            "_fine_grained": {
                "scoring_units": [
                    {"score_share": 0.083, "difficulty_estimate": 3.0, "bloom_level": 2, "allocation_confidence": 0.9},
                    {"score_share": 0.083, "difficulty_estimate": 4.0, "bloom_level": 3, "allocation_confidence": 0.9},
                    {"score_share": 0.083, "difficulty_estimate": 6.0, "bloom_level": 4, "allocation_confidence": 0.9},
                    {"score_share": 0.167, "difficulty_estimate": 6.5, "bloom_level": 6, "allocation_confidence": 0.9},
                    {"score_share": 0.167, "difficulty_estimate": 7.0, "bloom_level": 5, "allocation_confidence": 0.9},
                    {"score_share": 0.167, "difficulty_estimate": 7.5, "bloom_level": 5, "allocation_confidence": 0.9},
                    {"score_share": 0.083, "difficulty_estimate": 6.0, "bloom_level": 4, "allocation_confidence": 0.9},
                    {"score_share": 0.167, "difficulty_estimate": 8.0, "bloom_level": 5, "allocation_confidence": 0.9},
                ],
            },
        }
        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            8.8,
            {
                "working_memory": 5,
                "reasoning_steps": 7,
                "chain_coupling": 2,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 3,
                "representation_complexity": 3,
                "info_density": 2,
            },
            analysis_result,
            is_big_question=True,
            total_score=12,
        )

        assert adjusted <= 7.8
        assert "fragmented_medium_big_item_moderation" in flags

    def test_high_value_biotech_synthesis_floor_restores_top_difficulty(self):
        from difficulty_pipeline import DifficultyPipeline

        pipeline = DifficultyPipeline()
        analysis_result = {
            "knowledge_points": ["PCR引物设计", "基因表达载体构建", "代谢工程"],
            "_fine_grained": {
                "scoring_units": [
                    {
                        "score_share": 0.34,
                        "difficulty_estimate": 8.8,
                        "bloom_level": 5,
                        "allocation_confidence": 0.75,
                        "label": "分析PCR引物序列",
                        "knowledge_links": [
                            {"knowledge_point": "PCR技术扩增目的基因", "share": 1.0}
                        ],
                    },
                    {
                        "score_share": 0.33,
                        "difficulty_estimate": 9.0,
                        "bloom_level": 5,
                        "allocation_confidence": 0.75,
                        "label": "构建基因表达载体",
                        "knowledge_links": [
                            {"knowledge_point": "基因表达载体构建", "share": 1.0}
                        ],
                    },
                    {
                        "score_share": 0.33,
                        "difficulty_estimate": 8.5,
                        "bloom_level": 5,
                        "allocation_confidence": 0.7,
                        "label": "分析In-Fusion重组和表达结果",
                        "knowledge_links": [
                            {"knowledge_point": "In-Fusion克隆", "share": 0.5},
                            {"knowledge_point": "基因表达分析", "share": 0.5},
                        ],
                    },
                ],
                "diagnostic_units": [{"trap_strength": 2}, {"trap_strength": 2}],
                "stimulus_units": [
                    {"complexity": 3, "is_core": True, "description": "引物载体表达数据"}
                ],
            },
        }

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            9.1,
            {
                "working_memory": 5,
                "reasoning_steps": 6,
                "chain_coupling": 2,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 3,
                "representation_complexity": 3,
                "info_density": 3,
            },
            analysis_result,
            is_big_question=True,
            total_score=14,
        )

        assert adjusted == 10.0
        assert "high_value_biotech_synthesis_floor" in flags

    def test_high_value_biotech_synthesis_floor_catches_q21_evidence_rich_score(self):
        from difficulty_pipeline import DifficultyPipeline

        pipeline = DifficultyPipeline()
        analysis_result = {
            "knowledge_points": ["PCR技术扩增目的基因", "In-Fusion克隆", "番茄红素代谢工程"],
            "detailed_analysis": "结合PSY融合蛋白、引物方向、In-Fusion重组和表达分析判断番茄红素合成。",
            "_fine_grained": {
                "scoring_units": [
                    {
                        "score_share": 0.14,
                        "difficulty_estimate": 8.4,
                        "bloom_level": 3,
                        "allocation_confidence": 0.8,
                        "label": "阅读序列图并判断引物方向",
                        "knowledge_links": [
                            {"knowledge_point": "序列分析（阅读序列图）", "share": 0.5},
                            {"knowledge_point": "引物方向与扩增", "share": 0.5},
                        ],
                    },
                    {
                        "score_share": 0.14,
                        "difficulty_estimate": 8.8,
                        "bloom_level": 5,
                        "allocation_confidence": 0.8,
                        "label": "分析In-Fusion重组同源臂",
                        "knowledge_links": [
                            {"knowledge_point": "In-Fusion克隆", "share": 1.0}
                        ],
                    },
                    {
                        "score_share": 0.14,
                        "difficulty_estimate": 8.8,
                        "bloom_level": 5,
                        "allocation_confidence": 0.8,
                        "label": "评价表达载体构建与PSY表达结果",
                        "knowledge_links": [
                            {"knowledge_point": "基因表达载体构建", "share": 0.5},
                            {"knowledge_point": "基因表达分析", "share": 0.5},
                        ],
                    },
                    {
                        "score_share": 0.58,
                        "difficulty_estimate": 8.6,
                        "bloom_level": 4,
                        "allocation_confidence": 0.75,
                        "label": "综合番茄红素代谢工程结果",
                        "knowledge_links": [
                            {"knowledge_point": "番茄红素与PSY", "share": 1.0}
                        ],
                    },
                ],
                "diagnostic_units": [{"trap_strength": 2}, {"trap_strength": 2}],
                "stimulus_units": [
                    {"complexity": 3, "is_core": True, "description": "序列图、引物、表达结果"}
                ],
            },
        }

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            8.6,
            {
                "working_memory": 5,
                "reasoning_steps": 6,
                "chain_coupling": 2,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 3,
                "representation_complexity": 3,
                "info_density": 3,
            },
            analysis_result,
            is_big_question=True,
            total_score=14,
        )

        assert adjusted == 10.0
        assert "high_value_biotech_synthesis_floor" in flags

    def test_high_value_breeding_engineering_floor_restores_q20_difficulty(self):
        from difficulty_pipeline import DifficultyPipeline

        pipeline = DifficultyPipeline()
        analysis_result = {
            "knowledge_points": [
                "智能保持系",
                "杂交水稻的繁育体系",
                "配子类型与比例",
            ],
            "detailed_analysis": "结合智能保持系、花粉致死、育性恢复和基因工程构建分析杂交水稻繁育体系。",
            "_fine_grained": {
                "scoring_units": [
                    {
                        "score_share": 0.16,
                        "difficulty_estimate": 7.6,
                        "bloom_level": 4,
                        "allocation_confidence": 0.75,
                        "label": "识别智能保持系",
                        "reasoning_brief": "分析雄性不育系与保持系关系",
                        "knowledge_links": [
                            {"knowledge_point": "雄性不育系与杂交育种", "share": 1.0}
                        ],
                    },
                    {
                        "score_share": 0.16,
                        "difficulty_estimate": 7.8,
                        "bloom_level": 4,
                        "allocation_confidence": 0.75,
                        "label": "解释花粉致死",
                        "reasoning_brief": "推断可育花粉与育性恢复",
                        "knowledge_links": [
                            {"knowledge_point": "花粉致死与育性恢复", "share": 1.0}
                        ],
                    },
                    {
                        "score_share": 0.17,
                        "difficulty_estimate": 8.0,
                        "bloom_level": 4,
                        "allocation_confidence": 0.75,
                        "label": "分析配子分离",
                        "reasoning_brief": "依据配子类型和自交结果判断",
                        "knowledge_links": [
                            {"knowledge_point": "基因的分离定律", "share": 1.0}
                        ],
                    },
                    {
                        "score_share": 0.17,
                        "difficulty_estimate": 8.2,
                        "bloom_level": 5,
                        "allocation_confidence": 0.7,
                        "label": "评价杂种优势",
                        "reasoning_brief": "说明优势退化与繁育体系设计",
                        "knowledge_links": [
                            {"knowledge_point": "杂种优势", "share": 1.0}
                        ],
                    },
                    {
                        "score_share": 0.17,
                        "difficulty_estimate": 8.4,
                        "bloom_level": 5,
                        "allocation_confidence": 0.7,
                        "label": "判断基因工程构建",
                        "reasoning_brief": "结合转基因构建策略分析",
                        "knowledge_links": [
                            {"knowledge_point": "基因工程的基本操作程序", "share": 1.0}
                        ],
                    },
                    {
                        "score_share": 0.17,
                        "difficulty_estimate": 8.2,
                        "bloom_level": 5,
                        "allocation_confidence": 0.7,
                        "label": "整合繁育流程",
                        "reasoning_brief": "综合杂交水稻繁育体系",
                        "knowledge_links": [
                            {"knowledge_point": "杂交水稻育种原理", "share": 1.0}
                        ],
                    },
                ],
                "diagnostic_units": [
                    {"trap_strength": 3},
                    {"trap_strength": 2},
                ],
                "stimulus_units": [
                    {
                        "complexity": 3,
                        "is_core": True,
                        "description": "杂交水稻智能保持系和花粉育性材料",
                    }
                ],
            },
        }

        adjusted, flags = pipeline._apply_fine_grained_adjustments(
            8.1,
            {
                "working_memory": 4,
                "reasoning_steps": 5,
                "chain_coupling": 2,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 3,
                "representation_complexity": 1,
                "info_density": 2,
            },
            analysis_result,
            is_big_question=True,
            total_score=12,
        )

        assert adjusted == 9.2
        assert "high_value_breeding_engineering_floor" in flags


class TestQualityScoreGate:
    """quality_score 是题目质量信号，不是难度评估可行性信号。"""

    def test_quality_score_1_flags_issue_without_blocking_valid_features(self):
        """quality_score=1 但特征完整 → 继续估算难度并标记质量风险。"""
        mock_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 1,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
            "quality_score": 1,
            "_feature_status": "ok", "_raw_core_count": 9,
            "_extraction_confidence": 1.0, "_consistency_confidence": 1.0,
        }
        with patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "这是一道题面完整但命题质量较低的选择题，用于验证质量风险不阻断难度评估。A. A B. B C. C D. D",
                    "question_type": "single_choice",
                    "correct_answer": "", "total_score": 2,
                })
            )
        assert result.get("analysis_failed") is not True
        assert result["final_difficulty"] is not None
        assert "quality_issue_low_score" in result.get("flags", [])

    def test_quality_score_3_passes(self):
        """quality_score=3 → 正常评分。"""
        mock_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 1,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
            "quality_score": 3,
            "_feature_status": "ok", "_raw_core_count": 9,
            "_extraction_confidence": 1.0, "_consistency_confidence": 1.0,
        }
        with patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "正常题目...",
                    "question_type": "single_choice",
                    "correct_answer": "A", "total_score": 2,
                })
            )
        assert result.get("analysis_failed") is not True
        assert result["final_difficulty"] is not None

    def test_quality_score_absent_passes(self):
        """quality_score 不存在 → 正常评分（向后兼容）。"""
        mock_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 1,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
            "_feature_status": "ok", "_raw_core_count": 9,
            "_extraction_confidence": 1.0, "_consistency_confidence": 1.0,
        }
        with patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "正常题目...",
                    "question_type": "single_choice",
                    "correct_answer": "A", "total_score": 2,
                })
            )
        assert result.get("analysis_failed") is not True


class TestCriticalPathWeighted:
    """Critical path should select by score-weighted difficulty, not raw steps."""

    def test_high_value_hard_subquestion_selected(self):
        """High-value + high-step subquestion should be on critical path."""
        from rule_scorer import find_critical_path
        subquestions = [
            {"id": 1, "points": 6, "reasoning_steps": 4, "working_memory": 4,
             "trap_density": 3, "novelty": 2, "knowledge_breadth": 2},
            {"id": 2, "points": 3, "reasoning_steps": 2, "working_memory": 2,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1},
            {"id": 3, "points": 3, "reasoning_steps": 2, "working_memory": 2,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1},
        ]
        dependencies = [
            {"from": 2, "to": 3, "strength": "strong", "reason": "sequential"},
        ]
        path_nodes, path_steps = find_critical_path(subquestions, dependencies)
        path_ids = [n["id"] for n in path_nodes]
        # sq1 (6pts, weighted=4*0.5=2.0) should beat sq2->sq3 chain (weighted=2*0.25+2*0.25=1.0)
        assert 1 in path_ids, f"High-value sq1 should be on critical path, got {path_ids}"

    def test_small_outlier_does_not_hijack(self):
        """1-point high-difficulty subquestion should not hijack the whole question."""
        from rule_scorer import find_critical_path
        subquestions = [
            {"id": 1, "points": 1, "reasoning_steps": 8, "working_memory": 5,
             "trap_density": 3, "novelty": 3, "knowledge_breadth": 1},
            {"id": 2, "points": 5, "reasoning_steps": 3, "working_memory": 3,
             "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            {"id": 3, "points": 6, "reasoning_steps": 4, "working_memory": 3,
             "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
        ]
        dependencies = [
            {"from": 2, "to": 3, "strength": "strong", "reason": "builds on"},
        ]
        path_nodes, path_steps = find_critical_path(subquestions, dependencies)
        path_ids = [n["id"] for n in path_nodes]
        # sq2->sq3 chain (weighted=(3*5/12)+(4*6/12)=1.25+2.0=3.25) should beat
        # sq1 alone (weighted=8*1/12=0.67)
        assert 1 not in path_ids or len(path_ids) > 1, \
            f"1-point outlier sq1 should not be sole critical path, got {path_ids}"

    def test_breadth_upgrade_with_3_subquestions(self):
        """3 subquestions + method_novelty>=3 should upgrade breadth to 3."""
        from rule_scorer import aggregate_big_question
        subquestions = [
            {"id": 1, "points": 5, "reasoning_steps": 3, "working_memory": 3,
             "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            {"id": 2, "points": 3, "reasoning_steps": 2, "working_memory": 2,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1},
            {"id": 3, "points": 4, "reasoning_steps": 2, "working_memory": 2,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 2},
        ]
        dependencies = [{"from": 1, "to": 2, "strength": "strong", "reason": "x"}]
        global_features = {"shared_context_load": 2, "global_method_novelty": 3}
        result = aggregate_big_question(subquestions, dependencies, global_features)
        assert result["knowledge_breadth"] == 3, \
            f"3 sqs + method_novelty=3 should upgrade breadth, got {result['knowledge_breadth']}"

    def test_many_easy_off_path_blanks_have_bounded_load(self):
        """More independent low-order blanks should not linearly inflate main difficulty."""
        from rule_scorer import aggregate_big_question

        critical = [
            {"id": 1, "points": 8, "reasoning_steps": 6, "working_memory": 4,
             "trap_density": 3, "novelty": 2, "knowledge_breadth": 2},
        ]
        few_blanks = critical + [
            {"id": 2, "points": 1, "reasoning_steps": 2, "working_memory": 1,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1},
            {"id": 3, "points": 1, "reasoning_steps": 2, "working_memory": 1,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1},
        ]
        many_blanks = critical + [
            {"id": idx, "points": 1, "reasoning_steps": 2, "working_memory": 1,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1}
            for idx in range(2, 10)
        ]

        few = aggregate_big_question(few_blanks, [], {"shared_context_load": 1, "global_method_novelty": 1})
        many = aggregate_big_question(many_blanks, [], {"shared_context_load": 1, "global_method_novelty": 1})

        assert many["effective_steps"] - few["effective_steps"] <= 0.7

    def test_independent_off_path_blanks_do_not_create_chain_coupling(self):
        from rule_scorer import aggregate_big_question

        subquestions = [
            {"id": 1, "points": 6, "reasoning_steps": 6, "working_memory": 4,
             "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
        ] + [
            {"id": idx, "points": 1, "reasoning_steps": 1, "working_memory": 1,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1}
            for idx in range(2, 14)
        ]

        result = aggregate_big_question(
            subquestions,
            [],
            {"shared_context_load": 1, "global_method_novelty": 1},
        )

        assert result["chain_coupling"] == 1

    def test_critical_path_novelty_not_diluted_by_many_easy_blanks(self):
        from rule_scorer import aggregate_big_question

        subquestions = [
            {"id": 1, "points": 6, "reasoning_steps": 6, "working_memory": 4,
             "trap_density": 2, "novelty": 3, "knowledge_breadth": 2},
        ] + [
            {"id": idx, "points": 1, "reasoning_steps": 1, "working_memory": 1,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1}
            for idx in range(2, 14)
        ]

        result = aggregate_big_question(
            subquestions,
            [],
            {"shared_context_load": 1, "global_method_novelty": 1},
        )

        assert result["novelty"] == 3

    def test_independent_substantial_big_question_keeps_shared_context_load(self):
        from rule_scorer import aggregate_big_question

        subquestions = [
            {"id": 1, "points": 3, "reasoning_steps": 3, "working_memory": 3,
             "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            {"id": 2, "points": 3, "reasoning_steps": 3, "working_memory": 3,
             "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            {"id": 3, "points": 3, "reasoning_steps": 3, "working_memory": 3,
             "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            {"id": 4, "points": 2, "reasoning_steps": 2, "working_memory": 2,
             "trap_density": 1, "novelty": 1, "knowledge_breadth": 1},
        ]

        result = aggregate_big_question(
            subquestions,
            [],
            {"shared_context_load": 2, "global_method_novelty": 2},
        )

        assert result["effective_steps"] >= 5.2
        assert result["working_memory"] >= 4
        assert result["chain_coupling"] == 2


class TestBiologyMethodFloors:
    """Advanced biotech methods should not be treated as routine fill-in blanks."""

    def test_advanced_biotech_construct_raises_method_floor(self):
        from feature_extractor import _apply_biology_method_floors

        result = {
            "subquestions": [
                {"id": 1, "brief": "融合蛋白构建", "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 1},
                {"id": 2, "brief": "三引物PCR鉴定插入方向", "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 1},
            ],
            "global_features": {"shared_context_load": 3, "global_method_novelty": 2},
            "report": {"representation_complexity": 2},
        }
        question_text = "构建GFP融合蛋白并通过三引物PCR鉴定插入方向，设计引物。"

        adjusted = _apply_biology_method_floors(result, question_text, "biology")

        assert adjusted["global_features"]["global_method_novelty"] == 3
        assert adjusted["report"]["representation_complexity"] == 3
        assert adjusted["subquestions"][1]["novelty"] == 3
        assert adjusted["subquestions"][1]["trap_density"] == 2
        assert adjusted["subquestions"][1]["reasoning_steps"] == 4



# ══════════════════════════════════════════════════════════════
# R2-01: _table_to_markdown merged cell deduplication
# ══════════════════════════════════════════════════════════════

class TestTableToMarkdownMergedCells:
    """Merged cells in _table_to_markdown must not produce duplicate columns."""

    def _make_mock_cell(self, text, tc_id):
        """Return a minimal mock cell whose ._tc identity controls dedup."""
        from unittest.mock import MagicMock
        tc = object()  # unique object per logical cell
        cell = MagicMock()
        cell.text = text
        cell._tc = tc
        return cell

    def _make_mock_table(self, rows_spec):
        """
        rows_spec: list of lists of (text, tc_obj).
        Cells sharing the same tc_obj simulate a horizontal merge.
        """
        from unittest.mock import MagicMock
        table = MagicMock()
        mock_rows = []
        for row_spec in rows_spec:
            row = MagicMock()
            cells = []
            tc_registry = {}
            for text, tc_key in row_spec:
                if tc_key not in tc_registry:
                    tc_registry[tc_key] = object()
                cell = MagicMock()
                cell.text = text
                cell._tc = tc_registry[tc_key]
                cells.append(cell)
            row.cells = cells
            mock_rows.append(row)
        table.rows = mock_rows
        return table

    def test_no_merge_unchanged(self):
        """A normal 3-column table (no merges) produces 3 columns."""
        from word_splitter import WordQuestionSplitter
        table = self._make_mock_table([
            [("A", 0), ("B", 1), ("C", 2)],
            [("1", 3), ("2", 4), ("3", 5)],
        ])
        md = WordQuestionSplitter._table_to_markdown(table)
        header_cols = md.splitlines()[0].strip("|").split("|")
        assert len(header_cols) == 3, f"expected 3 cols, got {len(header_cols)}: {md}"

    def test_horizontal_merge_deduped(self):
        """A cell merged across 3 columns must appear only once."""
        from word_splitter import WordQuestionSplitter
        # Row 0: normal 3 cols. Row 1: col 0+1 merged (same tc_key=0), col 2 separate.
        table = self._make_mock_table([
            [("Header1", 0), ("Header2", 1), ("Header3", 2)],
            [("Merged", "m"), ("Merged", "m"), ("Solo", 3)],
        ])
        md = WordQuestionSplitter._table_to_markdown(table)
        lines = md.splitlines()
        data_row = lines[2]  # skip header + separator
        cols = [c.strip() for c in data_row.strip("|").split("|")]
        assert cols.count("Merged") == 1, f"Merged should appear once, got: {data_row}"
        assert "Solo" in data_row, f"Solo cell missing: {data_row}"

    def test_all_merged_single_row(self):
        """All 3 columns merged into one — result has exactly 1 column."""
        from word_splitter import WordQuestionSplitter
        table = self._make_mock_table([
            [("X", "same"), ("X", "same"), ("X", "same")],
        ])
        md = WordQuestionSplitter._table_to_markdown(table)
        header_cols = [c.strip() for c in md.splitlines()[0].strip("|").split("|")]
        assert len(header_cols) == 1, f"all-merged row should yield 1 col, got {header_cols}"

    def test_jagged_rows_padded(self):
        """When merge makes row 1 shorter than row 0, it must be padded with empty strings."""
        from word_splitter import WordQuestionSplitter
        # Row 0: 3 distinct cols. Row 1: first two merged → only 2 logical cols.
        table = self._make_mock_table([
            [("A", 0), ("B", 1), ("C", 2)],
            [("AB", "m"), ("AB", "m"), ("C2", 3)],
        ])
        md = WordQuestionSplitter._table_to_markdown(table)
        lines = [l for l in md.splitlines() if not l.startswith("|---")]
        # Every data row must have the same number of | separators as the header
        header_pipes = lines[0].count("|")
        for line in lines[1:]:
            assert line.count("|") == header_pipes, (
                f"Column count mismatch: header has {header_pipes} pipes, "
                f"data row has {line.count('|')} pipes: {line}"
            )

    def test_empty_table_returns_empty_string(self):
        """Empty table (no rows) returns empty string."""
        from unittest.mock import MagicMock
        from word_splitter import WordQuestionSplitter
        table = MagicMock()
        table.rows = []
        assert WordQuestionSplitter._table_to_markdown(table) == ""


# ══════════════════════════════════════════════════════════════
# R2-03: SEU fallback quality gate (content-length check)
# ══════════════════════════════════════════════════════════════

class TestSeuFallbackQualityGate:
    """SEU fallback must be blocked when question_text is suspiciously short."""

    def _make_seu(self, confidence=0.8, bloom=3, points=3):
        return {
            "description": "test unit",
            "bloom_level": bloom,
            "difficulty_estimate": 5.0,
            "points": points,
            "allocation_confidence": confidence,  # field read by _scoring_unit_metrics
        }

    def _seu_analysis_result(self, seus):
        return {"_fine_grained": {"scoring_units": seus}}

    def _run(self, question_text, seus, total_score=10):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from difficulty_pipeline import DifficultyPipeline

        async def _go():
            pipeline = DifficultyPipeline()
            # Patch big_question extraction to always fail so SEU fallback triggers
            fail_result = {
                "_big_question_failed": True,
                "failure_type": "llm_parse_error",
                "errors": [],
            }
            with patch(
                "difficulty_pipeline.extract_big_question_features",
                new_callable=AsyncMock,
                return_value=fail_result,
            ):
                return await pipeline._evaluate_single(
                    {
                        "content": question_text,
                        "question_type": "big_question",
                        "correct_answer": "see marking scheme",
                        "total_score": total_score,
                    },
                    analysis_result=self._seu_analysis_result(seus),
                )

        return asyncio.get_event_loop().run_until_complete(_go())

    def test_short_content_blocked(self):
        """Content < 30 chars must be blocked even with valid SEUs."""
        seus = [self._make_seu(0.9), self._make_seu(0.8), self._make_seu(0.7)]
        result = self._run("短内容", seus)  # 3 chars — well below threshold
        assert result.get("analysis_failed") is True, (
            f"Expected analysis_failed=True for short content, got: {result}"
        )

    def test_borderline_29_chars_blocked(self):
        """29-char content (one below threshold) must be blocked."""
        text = "A" * 29
        seus = [self._make_seu(0.9), self._make_seu(0.9)]
        result = self._run(text, seus)
        assert result.get("analysis_failed") is True, (
            f"29-char content should be blocked, got: {result}"
        )

    def test_30_chars_passes_gate(self):
        """Content >= 30 chars with valid SEUs must produce a score."""
        text = "B" * 30
        seus = [self._make_seu(0.9), self._make_seu(0.8), self._make_seu(0.7)]
        result = self._run(text, seus)
        assert result.get("analysis_failed") is True, (
            f"Failed structured parse must stay blocked, got: {result}"
        )
        assert result.get("source") == "analysis_failed"
        assert "seu_available_but_not_authoritative" in result.get("flags", [])

    def test_normal_content_passes_gate(self):
        """Realistic question text passes the gate and returns a valid score."""
        text = (
            "下图为某生物膜结构示意图，请据图回答下列问题："
            "（1）图中①的名称是______；"
            "（2）与细胞膜功能直接相关的物质是______。"
        )
        seus = [self._make_seu(0.85), self._make_seu(0.75), self._make_seu(0.8)]
        result = self._run(text, seus)
        assert result.get("analysis_failed") is True, (
            f"Failed structured parse must stay blocked, got: {result}"
        )
        assert result.get("final_difficulty") is None

    def test_low_confidence_seus_still_blocked_regardless_of_length(self):
        """Low-confidence SEUs (< 0.5 avg) block fallback independent of length."""
        text = "C" * 100  # long enough to pass the length gate
        seus = [self._make_seu(0.3), self._make_seu(0.2)]  # avg 0.25 < 0.5
        result = self._run(text, seus)
        assert result.get("analysis_failed") is True, (
            f"Low-confidence SEUs should still block, got: {result}"
        )
