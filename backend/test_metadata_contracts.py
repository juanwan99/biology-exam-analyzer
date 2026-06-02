from pathlib import Path

import pytest
from pydantic import ValidationError

from metadata_contracts import (
    AnalyzedQuestionEnvelope,
    LLMCallRecord,
    PromptRegistry,
    PromptSpec,
    build_default_prompt_registry,
)


def test_prompt_spec_from_file_records_hash_and_relative_path(tmp_path):
    prompt_file = tmp_path / "prompts" / "biology" / "feature_extractor.txt"
    prompt_file.parent.mkdir(parents=True)
    prompt_file.write_text("Question: {question_block}\nType: {qtype_hint}\n", encoding="utf-8")

    spec = PromptSpec.from_file(
        prompt_id="biology.feature_extractor",
        purpose="feature_extraction",
        subject="biology",
        path=prompt_file,
        project_root=tmp_path,
        variables=["question_block", "qtype_hint"],
        output_schema="FeatureResult",
        owner_module="feature_extractor.extract_features",
    )

    assert spec.prompt_hash
    assert len(spec.prompt_hash) == 64
    assert spec.path == "prompts/biology/feature_extractor.txt"
    assert spec.variables == ["question_block", "qtype_hint"]


def test_prompt_registry_rejects_duplicate_prompt_ids(tmp_path):
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("prompt", encoding="utf-8")
    spec = PromptSpec.from_file(
        prompt_id="biology.analysis",
        purpose="question_analysis",
        subject="biology",
        path=prompt_file,
        project_root=tmp_path,
        variables=[],
        output_schema="FineGrainedResult",
        owner_module="question_analyzer.analyze_question",
    )

    registry = PromptRegistry([spec])
    assert registry.get("biology.analysis") == spec

    with pytest.raises(ValueError, match="Duplicate prompt_id"):
        PromptRegistry([spec, spec])


def test_llm_call_record_validates_hash_and_trust_score():
    record = LLMCallRecord(
        call_id="q1-main-analysis",
        question_id=1,
        purpose="question_analysis",
        prompt_id="biology.analysis.v2",
        prompt_hash="a" * 64,
        provider="primary",
        model="deepseek-chat",
        input_refs={"question_id": 1, "media_refs": ["page_1"]},
        raw_output_ref="llm/q1-main-analysis.json",
        parsed_schema="FineGrainedResult",
        confidence=0.86,
        validation_errors=[],
        fallback_count=0,
        retry_count=1,
    )

    assert record.is_trusted(min_confidence=0.8)

    with pytest.raises(ValidationError):
        LLMCallRecord(
            call_id="bad",
            purpose="question_analysis",
            prompt_id="biology.analysis.v2",
            prompt_hash="not-a-sha",
            provider="primary",
            model="deepseek-chat",
            input_refs={},
            parsed_schema="FineGrainedResult",
            confidence=1.2,
        )


def test_analyzed_question_envelope_requires_question_id_and_tracks_lineage():
    call = LLMCallRecord(
        call_id="q1-main-analysis",
        question_id=1,
        purpose="question_analysis",
        prompt_id="biology.analysis.v2",
        prompt_hash="b" * 64,
        provider="primary",
        model="deepseek-chat",
        input_refs={"question_id": 1},
        parsed_schema="FineGrainedResult",
        confidence=0.9,
    )

    envelope = AnalyzedQuestionEnvelope(
        question={"id": 1, "content": "题干", "question_type": "single_choice"},
        llm_calls=[call],
        analysis_units={
            "scoring_units": [{"seu_id": "seu_1"}],
            "diagnostic_units": [],
            "stimulus_units": [],
        },
        derived={"knowledge": {"source": "scoring_units"}},
        confidence={"overall": 0.9},
        lineage={"knowledge_points": "analysis_units.scoring_units.knowledge_links"},
        warnings=[],
    )

    assert envelope.question_id == 1
    assert envelope.lineage["knowledge_points"] == "analysis_units.scoring_units.knowledge_links"

    with pytest.raises(ValidationError):
        AnalyzedQuestionEnvelope(question={}, llm_calls=[])


def test_build_default_prompt_registry_discovers_biology_prompt_contracts(tmp_path):
    files = {
        "backend/prompts/" + "analysis_prompt" + "_v" + "2.txt": "analysis {question_type}",
        "backend/prompts/competency_analysis_prompt.txt": "competency {question_text}",
        "prompts/biology/feature_extractor.txt": "feature {question_block}",
        "prompts/biology/big_question_extractor.txt": "big {question_block}",
        "prompts/biology/split_prompt.txt": "split",
        "prompts/biology/report_insights_prompt.txt": "report {exam_name}",
    }
    for rel_path, content in files.items():
        path = tmp_path / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    registry = build_default_prompt_registry(tmp_path, subject="biology")

    assert registry.get("biology.question_analysis.v2").output_schema == "FineGrainedResult"
    assert registry.get("biology.feature_extraction").owner_module == "feature_extractor.extract_features"
    report = registry.get("biology.report_insights")
    assert report.source == "inline"
    assert report.path == "backend/report_insights.py:_build_overall_prompt"
    teaching = registry.get("biology.report_teaching_suggestions")
    assert teaching.source == "inline"
    assert teaching.output_schema == "TeachingSuggestions"
    assert len(registry.all()) == 7
