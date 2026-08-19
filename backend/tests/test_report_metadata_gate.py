import pytest

from report_data import aggregate_report_data
from report_insights import _build_overall_prompt
from services.analysis_service import AnalysisService


def _call(purpose):
    return {
        "call_id": purpose,
        "purpose": purpose,
        "prompt_id": f"biology.{purpose}",
        "prompt_hash": "a" * 64,
        "provider": "llm_client",
        "model": "configured_provider_chain",
        "input_refs": {},
        "parsed_schema": "Schema",
        "confidence": 0.9,
        "validation_errors": [],
        "fallback_count": 0,
        "retry_count": 0,
        "metadata": {},
    }


def _envelope(question_id=1, overall=0.9, warnings=None):
    calls = [
        _call("question_analysis"),
        _call("feature_extraction"),
        _call("competency_analysis"),
    ]
    return {
        "question": {"id": question_id},
        "llm_calls": calls,
        "analysis_units": {},
        "derived": {},
        "confidence": {"overall": overall, "analysis": 0.9, "features": 0.8, "competency": 0.9},
        "lineage": {
            "knowledge_points": "analysis.knowledge_points",
            "difficulty_features": "difficulty.features",
            "competency": "competency",
        },
        "warnings": warnings or [],
    }


def _seu_derived_envelope(question_id=1):
    calls = [
        _call("question_analysis"),
        _call("feature_extraction"),
    ]
    return {
        "question": {"id": question_id},
        "llm_calls": calls,
        "analysis_units": {"scoring_units": [{"seu_id": "seu_1", "score_share": 1.0}]},
        "derived": {"competency": "科学思维"},
        "confidence": {"overall": 0.9, "analysis": 0.9, "features": 0.8, "competency": 0.0},
        "lineage": {
            "knowledge_points": "analysis.knowledge_points",
            "difficulty_features": "difficulty.features",
            "competency": "analysis._fine_grained.scoring_units.competency_weights",
        },
        "warnings": [],
    }


def _question(question_id=1, overall=0.9, warnings=None):
    return {
        "id": question_id,
        "content": "题干",
        "total_score": 2,
        "analysis": {"knowledge_points": ["酶"], "answer": "A"},
        "difficulty": {"final_difficulty": 5.0, "features": {"_feature_status": "ok"}},
        "competency": {"primary_competency": "科学思维"},
        "_metadata_envelope": _envelope(question_id, overall, warnings),
    }


def _seu_derived_question(question_id=1):
    q = _question(question_id)
    q["_metadata_envelope"] = _seu_derived_envelope(question_id)
    q["competency"] = {"primary_competency": "科学思维"}
    return q


def _service():
    return AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )


def test_report_metadata_gate_blocks_missing_envelope():
    with pytest.raises(ValueError, match="metadata envelope missing"):
        _service().validate_report_metadata([{"id": 7, "content": "缺元数据"}])


def test_report_metadata_gate_surfaces_low_confidence_and_warnings():
    result = _service().validate_report_metadata([
        _question(1, overall=0.55, warnings=["feature_status:partial"]),
        _question(2, overall=0.92),
    ])

    assert result["total_questions"] == 2
    assert result["blocked_questions"] == []
    assert result["low_confidence_questions"] == [1]
    assert result["warning_questions"] == [{"id": 1, "warnings": ["feature_status:partial"]}]


def test_report_metadata_gate_accepts_v2_seu_derived_competency():
    result = _service().validate_report_metadata([_seu_derived_question(12)])

    assert result["blocked_questions"] == []


def test_report_metadata_gate_blocks_missing_competency_source():
    q = _question(12)
    q["_metadata_envelope"]["llm_calls"] = [
        _call("question_analysis"),
        _call("feature_extraction"),
    ]
    q["_metadata_envelope"]["analysis_units"] = {}
    q["_metadata_envelope"]["derived"] = {}

    with pytest.raises(ValueError, match="required metadata source missing"):
        _service().validate_report_metadata([q])


def test_report_data_and_prompt_expose_metadata_quality():
    data = aggregate_report_data(
        [_question(1, overall=0.55, warnings=["feature_status:partial"])],
        competency_summary={},
        exam_statistics={},
        exam_info={"name": "元数据测试卷", "total": 1, "mode": "deep"},
    )

    assert data["metadata_quality"]["low_confidence_questions"] == [1]
    assert data["questions"][0]["metadata_warnings"] == ["feature_status:partial"]
    prompt = _build_overall_prompt(data)
    assert "元数据治理" in prompt
    assert "低置信度题目" in prompt
    assert "feature_status:partial" in prompt
