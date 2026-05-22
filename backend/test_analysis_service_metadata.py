import pytest

from services.analysis_service import AnalysisService


def _call(call_id, purpose, schema):
    return {
        "call_id": call_id,
        "purpose": purpose,
        "prompt_id": f"biology.{purpose}",
        "prompt_hash": "a" * 64,
        "provider": "llm_client",
        "model": "configured_provider_chain",
        "input_refs": {},
        "parsed_schema": schema,
        "confidence": 0.9,
        "validation_errors": [],
        "fallback_count": 0,
        "retry_count": 0,
        "metadata": {},
    }


def _ready_question(question_id=1):
    calls = [
        _call("question-analysis", "question_analysis", "AnalysisResult"),
        _call("feature-extraction", "feature_extraction", "FeatureResult"),
        _call("competency-analysis", "competency_analysis", "CompetencyResult"),
    ]
    return {
        "id": question_id,
        "_metadata_envelope": {
            "question": {"id": question_id},
            "llm_calls": calls,
            "analysis_units": {},
            "derived": {"competency": "科学思维"},
            "confidence": {"overall": 0.9},
            "lineage": {"competency": "competency"},
            "warnings": [],
        },
    }


def _ready_question_with_envelope(question_id=1, *, purposes=None, warnings=None):
    purposes = purposes or ["question_analysis", "feature_extraction", "competency_analysis"]
    calls = [
        _call(f"{purpose}-{idx}", purpose, "Result")
        for idx, purpose in enumerate(purposes, 1)
    ]
    return {
        "id": question_id,
        "_metadata_envelope": {
            "question": {"id": question_id, "total_score": 10},
            "llm_calls": calls,
            "analysis_units": {
                "scoring_units": [{"label": "unit", "score_share": 1.0}],
            },
            "derived": {"competency": "科学思维"},
            "confidence": {"overall": 0.9},
            "lineage": {"competency": "competency"},
            "warnings": warnings or [],
        },
    }


def _service_without_dependencies():
    return AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )


class FakeAnalyzer:
    async def analyze_question(self, **kwargs):
        return {
            "knowledge_points": ["酶"],
            "answer": "A",
            "bloom_level": 4,
            "total_score": 2,
            "_extraction_confidence": 0.9,
            "_llm_calls": [_call("question-1-analysis", "question_analysis", "AnalysisResult")],
        }


class FakeDifficultyEngine:
    async def evaluate_with_refinement(self, **kwargs):
        return {
            "final_difficulty": 5.2,
            "confidence": 0.8,
            "features": {
                "working_memory": 3,
                "_feature_status": "ok",
                "_llm_calls": [_call("biology-feature-extraction", "feature_extraction", "FeatureResult")],
            },
        }


class FakeCompetencyAnalyzer:
    async def analyze_competency(self, **kwargs):
        return {
            "primary_competency": "科学思维",
            "科学思维": {"涉及": True, "权重": 1.0},
            "_extraction_confidence": 0.95,
            "_llm_calls": [_call("question-1-competency", "competency_analysis", "CompetencyResult")],
        }


@pytest.mark.asyncio
async def test_analysis_service_builds_question_metadata_envelope():
    service = AnalysisService(
        analyzer=FakeAnalyzer(),
        difficulty_engine=FakeDifficultyEngine(),
        competency_analyzer=FakeCompetencyAnalyzer(),
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )
    question = {
        "id": 1,
        "content": "酶活性实验题",
        "total_score": 2,
        "_llm_calls": [_call("exam-split-questions", "split_questions", "SplitQuestionList")],
    }

    result = await service.analyze_question(question, image_bytes=[], mode="deep")

    purposes = [call["purpose"] for call in result["_llm_calls"]]
    assert purposes == [
        "split_questions",
        "question_analysis",
        "feature_extraction",
        "competency_analysis",
    ]
    envelope = result["_metadata_envelope"]
    assert envelope["question"]["id"] == 1
    assert len(envelope["llm_calls"]) == 4
    assert envelope["confidence"]["overall"] == result["analysis_confidence"]
    assert envelope["lineage"]["knowledge_points"] == "analysis.knowledge_points"
    assert envelope["lineage"]["difficulty_features"] == "difficulty.features"
    assert envelope["lineage"]["competency"] == "competency"


@pytest.mark.asyncio
async def test_analysis_service_retries_questions_with_missing_metadata_envelope():
    class RetryService(AnalysisService):
        def __init__(self):
            super().__init__(
                analyzer=None,
                difficulty_engine=None,
                competency_analyzer=None,
                knowledge_mapper=None,
                doc_processor=None,
                word_splitter=None,
                pdf_splitter=None,
                max_workers=1,
            )
            self.calls = 0

        async def analyze_question(self, question, image_bytes, mode="deep"):
            self.calls += 1
            if self.calls == 1:
                return {"id": question["id"], "analysis": {"error": "transient"}}
            return _ready_question(question["id"])

    service = RetryService()

    results = await service.analyze_questions_batch([{"id": 1, "content": "题干"}], [], "deep")

    assert service.calls == 2
    assert results[0]["_metadata_envelope"]["llm_calls"][0]["purpose"] == "question_analysis"


def test_metadata_retry_requires_independent_competency_call():
    question = _ready_question_with_envelope(
        purposes=["question_analysis", "feature_extraction"],
    )

    assert AnalysisService._metadata_retry_needed(question) is True


@pytest.mark.parametrize(
    "warning",
    [
        "llm_parse_failure:question_analysis",
        "diagnostic_units_missing",
        "stimulus_units_missing",
        "stimulus_units_blank",
    ],
)
def test_metadata_retry_on_parse_or_evidence_gap_warnings(warning):
    question = _ready_question_with_envelope(warnings=[warning])

    assert AnalysisService._metadata_retry_needed(question) is True


def test_split_integrity_rejects_missing_tail_question_from_source_text():
    service = _service_without_dependencies()
    source_text = "\n".join(f"{idx}. stem {idx}" for idx in range(1, 22))
    questions = [{"id": idx, "content": f"{idx}. stem {idx}"} for idx in range(1, 21)]

    with pytest.raises(ValueError, match="split integrity failed"):
        service.validate_split_integrity(questions, source_text)


@pytest.mark.asyncio
async def test_failed_question_analysis_gets_failure_envelope_and_remains_blocked():
    class BrokenAnalyzer:
        async def analyze_question(self, **kwargs):
            raise RuntimeError("provider 400")

    service = AnalysisService(
        analyzer=BrokenAnalyzer(),
        difficulty_engine=FakeDifficultyEngine(),
        competency_analyzer=FakeCompetencyAnalyzer(),
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )

    result = await service.analyze_question({"id": 9, "content": "bad prompt", "total_score": 2}, [], "deep")

    assert result["analysis_failed"] is True
    assert result["_metadata_envelope"]["status"] == "analysis_failed"
    assert "analysis_failed" in result["_metadata_envelope"]["warnings"]
    with pytest.raises(ValueError, match="analysis failed"):
        service.validate_report_metadata([result])
