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
            {"description": "confuses screening purpose"},
            {"description": "confuses cell source"},
            {"description": "confuses culture condition"},
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

        assert with_du["final_difficulty"] - plain["final_difficulty"] >= 0.5
        assert "diagnostic_burden_adjustment" in with_du.get("flags", [])


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
        assert "points_sum" in prompt

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

    def _q21_structured_features(self):
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
        structured = self._q21_structured_features()
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
        assert result["final_difficulty"] >= 9.0, f"Q21 应 >=9.0，实际 {result['final_difficulty']}"
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
        assert result["final_difficulty"] >= 9.0, f"全链路 Q21 应 >=9.0，实际 {result['final_difficulty']}"
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


class TestQ21EndToEnd:
    """Q21 端到端验证：v3.1 修正低估。"""

    def test_q21_score_at_least_9(self):
        """Q21（14分番茄红素 PSY 融合蛋白）评分应 >= 9.0。"""
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
        assert score >= 9.0, f"Q21 v3.1 应 >=9.0（修正 v3 的 8.2），实际 {score}"
        assert score <= 10.0
        assert "_big_question" in result["features"]
        assert len(result["features"]["_big_question"]["subquestions"]) == 3

    def test_q21_four_part_visual_question_keeps_chain_and_visual_burden(self):
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
        assert result["final_difficulty"] >= 9.0, result

    def test_parallel_big_question_not_overscored(self):
        """A-005: 并列大题不应被过度提升。

        入口: pipeline.evaluate_with_refinement(parallel_question)
        反例: 错误实现可能对并列大题也应用关键路径加成——本测试验证无 strong 依赖时不过度提升
        边界: 全并列 / 混合 strong+weak / 单小问大题
        回归: 防止 v3.1 引入并列大题系统性高估
        命令: docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestQ21EndToEnd::test_parallel_big_question_not_overscored -v
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
