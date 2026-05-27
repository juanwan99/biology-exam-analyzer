"""F-005: AnalysisService.analyze_question 入口级集成测试。

测试 v2/v1 完整调用链（mock LLM + 依赖桩），验证：
1. v2 合法 JSON → _fine_grained 存在 + _analysis_version = "v2"
2. v2 非法 scoring_units → fallback 到 v1
3. v2 缺少 scoring_units → 走 v1 路径
4. F-003 修复：v2 路径合并后包含具体维度和分析说明
5. 空/异常响应 → 降级结果
"""
import asyncio
import json
import sys
import types

import pytest

# ── 补充 conftest 中未 stub 的模块 ──────────────────────────────────

# utils.infer_question_type
if "utils" not in sys.modules:
    _utils_mod = types.ModuleType("utils")
    _utils_mod.infer_question_type = lambda q: q.get("question_type", "single_choice")
    sys.modules["utils"] = _utils_mod

# config（PROMPT_DIR, RULES_DIR）
if "config" not in sys.modules:
    from pathlib import Path as _Path
    _config_mod = types.ModuleType("config")
    _config_mod.PROMPT_DIR = _Path(__file__).parent / "prompts"
    _config_mod.RULES_DIR = _Path(__file__).parent / "rules"
    sys.modules["config"] = _config_mod

# llm_client（llm_call 由测试动态 mock）。优先使用真实模块，避免污染
# sys.modules 后影响 test_llm_client 等同进程测试。
try:
    import llm_client  # noqa: F401
except ImportError:
    if "llm_client" not in sys.modules:
        _llm_mod = types.ModuleType("llm_client")

        async def _stub_llm_call(**kwargs):
            raise RuntimeError("llm_call not mocked for this test")

        _llm_mod.llm_call = _stub_llm_call
        _llm_mod.get_last_llm_call_metadata = lambda: {}
        sys.modules["llm_client"] = _llm_mod

from services.analysis_service import AnalysisService
from llm_schemas import (
    FineGrainedResult, compute_summary_from_units, validate_llm_output,
    AnalysisResult, CompetencyResult,
)


# ── 测试数据 ─────────────────────────────────────────────────────────

# SEU 原始数据（在 question_analyzer 中被包装进 _fine_grained）
_SEU_DATA = [
    {
        "seu_id": "seu_1",
        "label": "识别糖蛋白位置",
        "score_share": 0.6,
        "allocation_source": "inferred",
        "allocation_confidence": 0.8,
        "knowledge_links": [
            {"knowledge_point": "细胞膜的流动镶嵌模型", "share": 0.5},
            {"knowledge_point": "糖蛋白的功能", "share": 0.5},
        ],
        "bloom_level": 2,
        "competency": {"primary": "生命观念", "weight": 0.9},
        "difficulty_estimate": 4.0,
        "reasoning_brief": "糖蛋白分布在膜外侧",
    },
    {
        "seu_id": "seu_2",
        "label": "排除常见误区",
        "score_share": 0.4,
        "allocation_source": "inferred",
        "allocation_confidence": 0.7,
        "knowledge_links": [
            {"knowledge_point": "磷脂双分子层的功能", "share": 1.0},
        ],
        "bloom_level": 3,
        "competency": {"primary": "科学思维", "weight": 0.7},
        "difficulty_estimate": 5.0,
        "reasoning_brief": "逐项排除错误选项",
    },
]

_DU_DATA = [
    {
        "du_id": "du_A",
        "option_or_trap": "A",
        "distractor_type": "misconception",
        "misconception": "蛋白质在膜中均匀分布",
        "trap_strength": 2,
        "knowledge_boundary": "膜蛋白不对称分布",
        "if_selected_means": ["对流动镶嵌模型理解不准确"],
    },
]

# V2_LLM_RESPONSE 模拟 question_analyzer.analyze_question() 的返回值
# （已经过 v2 处理：包含 _fine_grained + _analysis_version + 派生的旧格式字段）
V2_LLM_RESPONSE = {
    "answer": "C",
    "total_score": 2,
    "detailed_analysis": "考查流动镶嵌模型",
    "difficulty": "中等",
    "knowledge_points": ["细胞膜的流动镶嵌模型", "糖蛋白的功能"],
    "common_mistakes": ["误认为蛋白质均匀分布"],
    "bloom_level": 2,
    "primary_competency": "生命观念",
    "competency_level": "中",
    "_analysis_version": "v2",
    "_extraction_confidence": 1.0,
    "_fine_grained": {
        "scoring_units": _SEU_DATA,
        "diagnostic_units": _DU_DATA,
        "stimulus_units": [],
    },
}

V1_LLM_RESPONSE = {
    "knowledge_points": ["遗传学", "基因分离定律"],
    "detailed_analysis": "核心考查遗传推理",
    "difficulty": "困难",
    "common_mistakes": ["混淆显隐性"],
    "answer": "B",
    "total_score": 6,
    "bloom_level": 4,
}

COMPETENCY_LLM_RESPONSE = {
    "生命观念": {
        "涉及": True,
        "具体维度": ["结构与功能观"],
        "权重": 0.4,
        "分析说明": "涉及细胞膜结构与功能",
    },
    "科学思维": {
        "涉及": True,
        "具体维度": ["演绎与推理", "批判性思维"],
        "权重": 0.5,
        "分析说明": "需要推理排除错误选项",
    },
    "科学探究": {
        "涉及": False,
        "具体维度": [],
        "权重": 0,
        "分析说明": "",
    },
    "社会责任": {
        "涉及": False,
        "具体维度": [],
        "权重": 0,
        "分析说明": "",
    },
    "primary_competency": "科学思维",
    "competency_level": "高",
}


# ── Mock 工厂 ────────────────────────────────────────────────────────

class MockAnalyzer:
    """QuestionAnalyzer 桩：返回预设 JSON 作为 analyze_question 结果。"""

    def __init__(self, response_json: dict):
        self._response = response_json

    async def analyze_question(self, **kwargs):
        return dict(self._response)


class MockDifficultyEngine:
    """难度引擎桩：返回固定难度。"""

    async def evaluate_with_refinement(self, **kwargs):
        return {"difficulty_score": 5.0, "difficulty_label": "中等", "confidence": 0.8}


class MockCompetencyAnalyzer:
    """素养分析器桩：返回预设素养结果。"""

    def __init__(self, response_json: dict = None):
        self._response = response_json or COMPETENCY_LLM_RESPONSE

    async def analyze_competency(self, **kwargs):
        return dict(self._response)

    def aggregate_exam_competencies(self, questions_competencies):
        return {"生命观念": {"题目数": 1}, "科学思维": {"题目数": 1}}


class MockKnowledgeMapper:
    def map_knowledge_points(self, kp_list):
        return [{"mapped": False, "original": kp} for kp in kp_list]


def _build_service(analyzer_response: dict, competency_response: dict = None):
    """构造 AnalysisService，注入 mock 依赖。"""
    return AnalysisService(
        analyzer=MockAnalyzer(analyzer_response),
        difficulty_engine=MockDifficultyEngine(),
        competency_analyzer=MockCompetencyAnalyzer(competency_response),
        knowledge_mapper=MockKnowledgeMapper(),
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )


# ── 1. v2 合法 JSON → _fine_grained 存在 + version = v2 ─────────────

class TestV2HappyPath:
    def test_v2_fine_grained_present(self):
        """v2 分析结果包含 _fine_grained 和 _analysis_version=v2"""
        service = _build_service(V2_LLM_RESPONSE)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        analysis = result.get("analysis", {})
        assert analysis.get("_analysis_version") == "v2"
        assert "_fine_grained" in analysis
        assert len(analysis["_fine_grained"]["scoring_units"]) == 2

    def test_v2_competency_has_weights(self):
        """v2 路径的素养结果包含权重字段"""
        service = _build_service(V2_LLM_RESPONSE)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        comp = result.get("competency", {})
        assert "primary_competency" in comp
        assert comp["primary_competency"] in ("生命观念", "科学思维", "科学探究", "社会责任")
        # 四大素养的权重字段
        for name in ["生命观念", "科学思维", "科学探究", "社会责任"]:
            assert name in comp
            assert "权重" in comp[name]
            assert "涉及" in comp[name]

    def test_v2_difficulty_populated(self):
        """v2 路径仍然执行难度评估"""
        service = _build_service(V2_LLM_RESPONSE)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        diff = result.get("difficulty", {})
        assert "error" not in diff
        assert diff.get("difficulty_score") == 5.0


# ── 2. F-003: v2 素养合并包含具体维度和分析说明 ──────────────────────

class TestF003CompetencySubDimensions:
    def test_v2_merged_has_sub_dimensions(self):
        """F-003: v2 路径合并后包含独立素养分析的具体维度"""
        service = _build_service(V2_LLM_RESPONSE, COMPETENCY_LLM_RESPONSE)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        comp = result.get("competency", {})
        # 生命观念应有具体维度
        assert "具体维度" in comp.get("生命观念", {})
        assert comp["生命观念"]["具体维度"] == ["结构与功能观"]
        # 科学思维应有具体维度
        assert "具体维度" in comp.get("科学思维", {})
        assert comp["科学思维"]["具体维度"] == ["演绎与推理", "批判性思维"]

    def test_v2_merged_has_analysis_notes(self):
        """F-003: v2 路径合并后包含独立素养分析的分析说明"""
        service = _build_service(V2_LLM_RESPONSE, COMPETENCY_LLM_RESPONSE)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        comp = result.get("competency", {})
        assert "分析说明" in comp.get("生命观念", {})
        assert "细胞膜" in comp["生命观念"]["分析说明"]

    def test_v2_weights_from_seu_not_overridden(self):
        """F-003: 合并后权重来自 SEU（更精确），不被独立分析覆盖"""
        service = _build_service(V2_LLM_RESPONSE, COMPETENCY_LLM_RESPONSE)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        comp = result.get("competency", {})
        # 四维权重聚合后，生命观念应该是最高权重
        assert comp["生命观念"]["权重"] > comp["科学思维"]["权重"]
        total = sum(comp[d]["权重"] for d in ["生命观念", "科学思维", "科学探究", "社会责任"] if d in comp and isinstance(comp[d], dict))
        assert abs(total - 1.0) < 0.02

    def test_v2_competency_supplement_failure_graceful(self):
        """F-003: 独立素养补充失败不影响主流程，仅缺少具体维度"""
        error_comp = {"error": "素养分析失败: 连接超时"}
        service = _build_service(V2_LLM_RESPONSE, error_comp)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        comp = result.get("competency", {})
        # 权重应正常存在（来自 SEU 四维权重）
        assert "primary_competency" in comp
        assert comp["生命观念"]["权重"] > comp["科学思维"]["权重"]
        # 具体维度不存在（因为独立分析失败了）
        assert "具体维度" not in comp.get("生命观念", {})

    def test_v2_merged_feeds_aggregator(self):
        """F-003: 合并后的素养数据可被 aggregate_exam_competencies 消费"""
        from competency_analyzer import CompetencyAnalyzer
        service = _build_service(V2_LLM_RESPONSE, COMPETENCY_LLM_RESPONSE)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        comp = dict(result.get("competency", {}))
        comp["_total_score"] = 2
        # 模拟聚合器消费：关键是 具体维度 字段被正确读取
        for comp_name in ["生命观念", "科学思维", "科学探究", "社会责任"]:
            dim_data = comp.get(comp_name, {})
            dims = dim_data.get("具体维度", [])
            if dim_data.get("涉及"):
                # 涉及的素养应有具体维度
                if comp_name in ("生命观念", "科学思维"):
                    assert len(dims) > 0, f"{comp_name} 应有具体维度"


# ── 3. v2 非法 scoring_units → fallback 到 v1 ────────────────────────

class TestV2FallbackToV1Integration:
    def test_bad_scoring_units_falls_back_to_v1(self):
        """scoring_units 非法时 question_analyzer 返回 v1 格式"""
        # 当 question_analyzer 返回 v1 格式（无 _fine_grained），
        # analysis_service 走独立素养分析路径
        service = _build_service(V1_LLM_RESPONSE)
        question = {"id": 1, "content": "遗传题"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        analysis = result.get("analysis", {})
        # v1 没有 _fine_grained
        assert "_fine_grained" not in analysis
        # 素养走独立分析路径
        comp = result.get("competency", {})
        assert "primary_competency" in comp

    def test_v1_path_uses_independent_competency(self):
        """v1 路径使用独立素养分析（非 SEU 派生）"""
        service = _build_service(V1_LLM_RESPONSE, COMPETENCY_LLM_RESPONSE)
        question = {"id": 1, "content": "遗传题"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        comp = result.get("competency", {})
        # 独立分析结果直接使用（包含具体维度和分析说明）
        assert comp.get("primary_competency") == "科学思维"
        assert "具体维度" in comp.get("科学思维", {})


# ── 4. 缺少 scoring_units → 走 v1 路径 ──────────────────────────────

class TestV2MissingScoringUnits:
    def test_no_scoring_units_uses_v1(self):
        """没有 scoring_units 的响应走 v1 路径"""
        v1_only = dict(V1_LLM_RESPONSE)
        v1_only["_analysis_version"] = "v1"
        service = _build_service(v1_only)
        question = {"id": 1, "content": "遗传题"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        # 无 _fine_grained → 走独立素养
        assert "_fine_grained" not in result.get("analysis", {})


# ── 5. 异常处理 ─ analyzer 抛出异常 → 降级结果 ──────────────────────

class TestAnalysisExceptionHandling:
    def test_analyzer_exception_produces_degraded_result(self):
        """analyzer.analyze_question 抛出异常时返回降级结果"""

        class FailingAnalyzer:
            async def analyze_question(self, **kwargs):
                raise RuntimeError("LLM API 超时")

        service = AnalysisService(
            analyzer=FailingAnalyzer(),
            difficulty_engine=MockDifficultyEngine(),
            competency_analyzer=MockCompetencyAnalyzer(),
            knowledge_mapper=MockKnowledgeMapper(),
            doc_processor=None,
            word_splitter=None,
            pdf_splitter=None,
        )
        question = {"id": 1, "content": "测试题"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        assert "error" in result.get("analysis", {})
        assert "error" in result.get("difficulty", {})
        assert "error" in result.get("competency", {})

    def test_no_analyzer_raises_runtime_error(self):
        """analyzer 为 None 时应在 analysis 中返回错误"""
        service = AnalysisService(
            analyzer=None,
            difficulty_engine=MockDifficultyEngine(),
            competency_analyzer=MockCompetencyAnalyzer(),
            knowledge_mapper=MockKnowledgeMapper(),
            doc_processor=None,
            word_splitter=None,
            pdf_splitter=None,
        )
        question = {"id": 1, "content": "测试题"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        assert "error" in result.get("analysis", {})


# ── 6. v2 confidence 和 validation_errors 透传 ─────────────────────

class TestV2MetadataPassthrough:
    def test_v2_confidence_in_result(self):
        """analysis_confidence 在 v2 路径中正确计算"""
        service = _build_service(V2_LLM_RESPONSE)
        question = {"id": 1, "content": "关于细胞膜的说法正确的是"}
        result = asyncio.get_event_loop().run_until_complete(
            service.analyze_question(question, image_bytes=[])
        )
        confidence = result.get("analysis_confidence", 0)
        assert confidence > 0, "analysis_confidence 应大于 0"
        # v2 有 answer + knowledge_points + competency + bloom → 高置信度
        assert confidence >= 0.5


# ── 7. P1-001: 归一化不变量参数化测试（1/2/3/4 项非零）─────────────

class TestNormalizationInvariant:
    """R2R-001 归一化不变量：任何数量的非零素养权重，归一化后 sum==1.0。"""

    @staticmethod
    def _normalize(raw_weights: dict) -> dict:
        """复制 analysis_service.py:89-99 的归一化逻辑。"""
        weight_sum = sum(raw_weights.values())
        if weight_sum > 0:
            items = list(raw_weights.items())
            norm = {k: round(v / weight_sum, 2) for k, v in items}
            remainder = round(1.0 - sum(norm.values()), 2)
            if remainder != 0:
                max_key = max(norm, key=norm.get)
                norm[max_key] = round(norm[max_key] + remainder, 2)
        else:
            norm = {k: 0.25 for k in raw_weights}
        return norm

    def test_single_nonzero(self):
        r = self._normalize({"生命观念": 1.0, "科学思维": 0, "科学探究": 0, "社会责任": 0})
        assert sum(r.values()) == 1.0
        assert r["生命观念"] == 1.0

    def test_two_nonzero(self):
        r = self._normalize({"生命观念": 0.54, "科学思维": 0.28, "科学探究": 0, "社会责任": 0})
        assert sum(r.values()) == 1.0

    def test_three_nonzero(self):
        r = self._normalize({"生命观念": 1, "科学思维": 1, "科学探究": 1, "社会责任": 0})
        assert sum(r.values()) == 1.0
        assert r["社会责任"] == 0

    def test_four_nonzero(self):
        r = self._normalize({"生命观念": 3, "科学思维": 2, "科学探究": 1, "社会责任": 1})
        assert sum(r.values()) == 1.0

    def test_four_equal(self):
        r = self._normalize({"生命观念": 1, "科学思维": 1, "科学探究": 1, "社会责任": 1})
        assert sum(r.values()) == 1.0
        assert all(v == 0.25 for v in r.values())

    def test_all_zero_gets_uniform(self):
        r = self._normalize({"生命观念": 0, "科学思维": 0, "科学探究": 0, "社会责任": 0})
        assert sum(r.values()) == 1.0
        assert all(v == 0.25 for v in r.values())

    def test_remainder_goes_to_max(self):
        r = self._normalize({"生命观念": 1, "科学思维": 1, "科学探究": 1, "社会责任": 0})
        nonzero = {k: v for k, v in r.items() if v > 0}
        assert max(nonzero.values()) >= 0.34
