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
            "confidence": {"overall": 0.9, "analysis": 0.9, "features": 0.9, "competency": 0.9},
            "lineage": {"competency": "competency"},
            "warnings": [],
        },
    }


def _ready_question_with_ranked_evidence(question_id=1):
    question = _ready_question(question_id)
    question.update({
        "content": "Question stem",
        "total_score": 2,
        "analysis": {"answer": "A", "knowledge_points": ["遗传规律"], "total_score": 2},
        "difficulty": {"final_difficulty": 5.0, "features": {"_feature_status": "ok"}},
        "competency": {"primary_competency": "科学思维"},
    })
    question["_metadata_envelope"]["llm_calls"][0]["metadata"] = {
        "evidence_context": {
            "provider": "evidence_service",
            "operation": "rank",
            "question_id": question_id,
            "ranked_count": 5,
            "candidate_count": 32,
        }
    }
    return question


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
            "confidence": {"overall": 0.9, "analysis": 0.9, "features": 0.9, "competency": 0.9},
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
async def test_analyze_question_app_builder_channel_enables_evidence_ranking():
    class RecordingAnalyzer(FakeAnalyzer):
        def __init__(self):
            self.calls = []

        async def analyze_question(self, **kwargs):
            self.calls.append(kwargs)
            return await super().analyze_question(**kwargs)

    analyzer = RecordingAnalyzer()
    service = AnalysisService(
        analyzer=analyzer,
        difficulty_engine=FakeDifficultyEngine(),
        competency_analyzer=FakeCompetencyAnalyzer(),
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )

    await service.analyze_question(
        {"id": 1, "content": "question", "total_score": 2},
        image_bytes=[],
        mode="deep",
        exam_review_channel="app_builder",
    )

    assert analyzer.calls[0]["evidence_ranking_enabled"] is True
    assert analyzer.calls[0]["agent_search_enabled"] is False


@pytest.mark.asyncio
async def test_analyze_question_agent_search_channel_enables_answer_context():
    class RecordingAnalyzer(FakeAnalyzer):
        def __init__(self):
            self.calls = []

        async def analyze_question(self, **kwargs):
            self.calls.append(kwargs)
            return await super().analyze_question(**kwargs)

    analyzer = RecordingAnalyzer()
    service = AnalysisService(
        analyzer=analyzer,
        difficulty_engine=FakeDifficultyEngine(),
        competency_analyzer=FakeCompetencyAnalyzer(),
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )

    await service.analyze_question(
        {"id": 1, "content": "question", "total_score": 2},
        image_bytes=[],
        mode="deep",
        exam_review_channel="agent_search",
    )

    assert analyzer.calls[0]["evidence_ranking_enabled"] is True
    assert analyzer.calls[0]["agent_search_enabled"] is True


@pytest.mark.asyncio
async def test_analyze_question_model_channel_disables_evidence_ranking():
    class RecordingAnalyzer(FakeAnalyzer):
        def __init__(self):
            self.calls = []

        async def analyze_question(self, **kwargs):
            self.calls.append(kwargs)
            return await super().analyze_question(**kwargs)

    analyzer = RecordingAnalyzer()
    service = AnalysisService(
        analyzer=analyzer,
        difficulty_engine=FakeDifficultyEngine(),
        competency_analyzer=FakeCompetencyAnalyzer(),
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )

    await service.analyze_question(
        {"id": 1, "content": "question", "total_score": 2},
        image_bytes=[],
        mode="deep",
        exam_review_channel="model",
    )

    assert analyzer.calls[0]["evidence_ranking_enabled"] is False
    assert analyzer.calls[0]["agent_search_enabled"] is False


@pytest.mark.asyncio
async def test_auto_analysis_blocks_app_builder_when_ranking_usage_missing():
    class LocalWordSplitter:
        def split(self, file_path):
            return {"questions": [{"id": 1, "content": "Question stem", "total_score": 2}]}

    class LocalDocProcessor:
        def process_docx(self, file_path):
            return []

    service = AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=LocalDocProcessor(),
        word_splitter=LocalWordSplitter(),
        pdf_splitter=None,
    )

    async def fake_analyze_questions_batch(
        questions, image_bytes, mode, subject="biology", exam_review_channel=None
    ):
        return [_ready_question(1)]

    service.analyze_questions_batch = fake_analyze_questions_batch
    service.build_competency_summary = lambda questions: {}
    service.aggregate_statistics = lambda questions, competency_summary: {}

    with pytest.raises(RuntimeError, match="缺少 Ranking 证据"):
        await service.run_auto_analysis(
            "exam.docx",
            "exam.docx",
            b"",
            generate_report=False,
            exam_review_channel="app_builder",
        )


def test_evidence_channel_allows_direct_model_generation_when_ranking_recorded():
    usage = {
        "direct_model_call_count": 1,
        "evidence_generation_count": 0,
        "evidence_rank_count": 1,
        "missing_rank_question_ids": [],
    }

    AnalysisService.assert_channel_usage("app_builder", usage)


def test_evidence_channel_blocks_question_missing_ranked_evidence():
    usage = {
        "direct_model_call_count": 2,
        "evidence_rank_count": 1,
        "missing_rank_question_ids": [21],
    }

    with pytest.raises(RuntimeError, match="第 21 题缺少 Ranking 证据"):
        AnalysisService.assert_channel_usage("app_builder", usage)


def test_agent_search_channel_requires_answer_query_evidence():
    usage = {
        "direct_model_call_count": 1,
        "evidence_rank_count": 1,
        "missing_rank_question_ids": [],
        "agent_search_answer_count": 0,
    }

    with pytest.raises(RuntimeError, match="answer_query evidence"):
        AnalysisService.assert_channel_usage("agent_search", usage)


def test_agent_search_channel_accepts_rank_and_answer_query_evidence():
    usage = {
        "direct_model_call_count": 1,
        "evidence_rank_count": 1,
        "missing_rank_question_ids": [],
        "agent_search_answer_count": 1,
    }

    AnalysisService.assert_channel_usage("agent_search", usage)


@pytest.mark.asyncio
async def test_auto_analysis_reports_app_builder_channel_usage_when_ranking_recorded():
    class LocalWordSplitter:
        def split(self, file_path):
            return {"questions": [{"id": 1, "content": "Question stem", "total_score": 2}]}

    class LocalDocProcessor:
        def process_docx(self, file_path):
            return []

    service = AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=LocalDocProcessor(),
        word_splitter=LocalWordSplitter(),
        pdf_splitter=None,
    )

    async def fake_analyze_questions_batch(
        questions, image_bytes, mode, subject="biology", exam_review_channel=None
    ):
        return [_ready_question_with_ranked_evidence(1)]

    service.analyze_questions_batch = fake_analyze_questions_batch
    service.build_competency_summary = lambda questions: {}
    service.aggregate_statistics = lambda questions, competency_summary: {}

    result = await service.run_auto_analysis(
        "exam.docx",
        "exam.docx",
        b"",
        generate_report=False,
        exam_review_channel="app_builder",
    )

    assert result["channel_usage"]["evidence_rank_count"] == 1
    assert result["channel_usage"]["evidence_rank_question_ids"] == [1]
    assert result["channel_usage"]["model_call_count"] == 3
    assert result["channel_usage"]["direct_model_call_count"] == 3
    assert result["channel_usage"]["evidence_generation_count"] == 0


@pytest.mark.asyncio
async def test_analyze_question_passes_media_to_difficulty_and_competency():
    class CapturingDifficultyEngine(FakeDifficultyEngine):
        def __init__(self):
            self.question = None

        async def evaluate_with_refinement(self, **kwargs):
            self.question = kwargs["question"]
            return await super().evaluate_with_refinement(**kwargs)

    class CapturingCompetencyAnalyzer(FakeCompetencyAnalyzer):
        def __init__(self):
            self.question = None

        async def analyze_competency(self, **kwargs):
            self.question = kwargs["question"]
            return await super().analyze_competency(**kwargs)

    difficulty = CapturingDifficultyEngine()
    competency = CapturingCompetencyAnalyzer()
    service = AnalysisService(
        analyzer=FakeAnalyzer(),
        difficulty_engine=difficulty,
        competency_analyzer=competency,
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )

    await service.analyze_question(
        {
            "id": 3,
            "content": "question with chart",
            "total_score": 2,
            "_media_for_ai": [{"type": "image", "base64": "iVBORw0KGgoAAA"}],
        },
        image_bytes=[],
        mode="deep",
    )

    assert difficulty.question["media_items"][0]["base64"] == "iVBORw0KGgoAAA"
    assert competency.question["media_items"][0]["base64"] == "iVBORw0KGgoAAA"


@pytest.mark.asyncio
async def test_analyze_question_passes_structured_options_to_difficulty():
    class CapturingDifficultyEngine(FakeDifficultyEngine):
        def __init__(self):
            self.question = None

        async def evaluate_with_refinement(self, **kwargs):
            self.question = kwargs["question"]
            return await super().evaluate_with_refinement(**kwargs)

    difficulty = CapturingDifficultyEngine()
    service = AnalysisService(
        analyzer=FakeAnalyzer(),
        difficulty_engine=difficulty,
        competency_analyzer=FakeCompetencyAnalyzer(),
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )

    await service.analyze_question(
        {
            "id": 2,
            "content": "choice stem",
            "total_score": 2,
            "options": {"A": "alpha", "B": "beta", "C": "gamma", "D": "delta"},
        },
        image_bytes=[],
        mode="deep",
    )

    assert difficulty.question["options"] == {
        "A": "alpha",
        "B": "beta",
        "C": "gamma",
        "D": "delta",
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


def test_metadata_envelope_uses_successful_call_confidence_for_missing_result_confidence():
    service = _service_without_dependencies()
    feature_call = _call("biology-big-feature", "big_question_feature_extraction", "BigQuestionFeatureResult")
    feature_call["confidence"] = 0.83
    competency_call = _call("question-21-competency", "competency_analysis", "CompetencyResult")
    competency_call["confidence"] = 0.91
    question = {
        "id": 21,
        "content": "big question",
        "total_score": 14,
        "analysis_confidence": 0.97,
        "analysis": {
            "_extraction_confidence": 1.0,
            "knowledge_points": ["PCR"],
            "_llm_calls": [_call("question-21-analysis", "question_analysis", "AnalysisResult")],
            "_fine_grained": {
                "scoring_units": [{"label": "unit", "score_share": 1.0}],
                "diagnostic_units": [{"misconception": "trap"}],
                "stimulus_units": [{"description": "diagram", "complexity": 3, "is_core": True}],
            },
        },
        "difficulty": {
            "final_difficulty": 9.2,
            "features": {"_feature_status": "ok", "_llm_calls": [feature_call]},
        },
        "competency": {
            "primary_competency": "science thinking",
            "_llm_calls": [competency_call],
        },
    }

    service._attach_metadata_envelope(question)

    confidence = question["_metadata_envelope"]["confidence"]
    assert confidence["features"] == 0.83
    assert confidence["competency"] == 0.91


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
    warnings = results[0]["_metadata_envelope"]["warnings"]
    assert "question_retried_after_metadata_failure:missing_metadata_envelope" not in warnings
    assert results[0]["_metadata_envelope"]["lineage"]["recovered_retry"] == {
        "reason": "missing_metadata_envelope",
        "recovered_by": "sequential_retry",
        "warning_emitted": False,
    }


def test_metadata_retry_requires_independent_competency_call():
    question = _ready_question_with_envelope(
        purposes=["question_analysis", "feature_extraction"],
    )

    assert AnalysisService._metadata_retry_needed(question) is True


def test_zero_component_confidence_blocks_pipeline_instead_of_using_overall_confidence():
    service = _service_without_dependencies()
    question = _ready_question(1)
    question["_metadata_envelope"]["confidence"]["features"] = 0.0

    with pytest.raises(ValueError, match="component confidence failed"):
        service.validate_report_metadata([question])

    audit = AnalysisService.build_pipeline_audit({
        "failed_component_confidence_questions": [
            {"id": 1, "component": "features", "confidence": 0.0}
        ],
    })

    assert audit["status"] == "blocked"
    assert audit["blockers"][0]["code"] == "failed_component_confidence"


def test_low_nonzero_component_confidence_is_visible_warning_not_generation_blocker():
    service = _service_without_dependencies()
    question = _ready_question(1)
    question["_metadata_envelope"]["confidence"]["features"] = 0.55

    result = service.validate_report_metadata([question])
    assert result["blocked_questions"] == []
    assert result["low_component_confidence_questions"] == [
        {"id": 1, "component": "features", "confidence": 0.55}
    ]

    audit = AnalysisService.build_pipeline_audit({
        "low_component_confidence_questions": [
            {"id": 1, "component": "features", "confidence": 0.55}
        ],
    })
    assert audit["status"] == "ok"
    assert audit["warnings"][0]["code"] == "low_component_confidence"


def test_invalid_llm_call_record_becomes_metadata_warning_and_pipeline_blocker():
    service = _service_without_dependencies()
    question = {
        "id": 1,
        "content": "题干",
        "total_score": 2,
        "analysis_confidence": 0.9,
        "analysis": {
            "knowledge_points": ["遗传规律"],
            "_extraction_confidence": 0.9,
            "_llm_calls": [
                _call("question-analysis", "question_analysis", "AnalysisResult"),
                {"call_id": "bad-call", "purpose": "feature_extraction"},
            ],
        },
        "difficulty": {
            "final_difficulty": 5.8,
            "confidence": 0.9,
            "features": {
                "_extraction_confidence": 0.9,
                "_llm_calls": [_call("feature-extraction", "feature_extraction", "FeatureResult")],
            },
        },
        "competency": {
            "primary_competency": "科学思维",
            "_extraction_confidence": 0.9,
            "_llm_calls": [_call("competency-analysis", "competency_analysis", "CompetencyResult")],
        },
    }

    service._attach_metadata_envelope(question)

    warnings = question["_metadata_envelope"]["warnings"]
    assert "invalid_llm_call:1" in warnings
    assert question["_metadata_envelope"]["derived"]["invalid_llm_call_errors"]

    audit = AnalysisService.build_pipeline_audit({
        "warning_questions": [{"id": 1, "warnings": warnings}],
    })
    assert audit["status"] == "blocked"
    assert audit["blockers"][0]["code"] == "hard_warning"


def test_metadata_envelope_warns_when_media_was_not_passed_downstream():
    service = AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )
    feature_call = _call("biology-feature-extraction", "feature_extraction", "FeatureResult")
    feature_call["input_refs"] = {"question_text_length": 20}
    competency_call = _call("question-3-competency", "competency_analysis", "CompetencyResult")
    competency_call["input_refs"] = {"question_text_length": 20, "media_count": 1}
    question = {
        "id": 3,
        "content": "question with image",
        "total_score": 2,
        "_media_for_ai": [{"type": "image", "base64": "iVBORw0KGgoAAA"}],
        "analysis": {
            "knowledge_points": ["experiment"],
            "_llm_calls": [_call("question-3-analysis", "question_analysis", "AnalysisResult")],
        },
        "difficulty": {
            "final_difficulty": 5.0,
            "features": {"_feature_status": "ok", "_llm_calls": [feature_call]},
        },
        "competency": {
            "primary_competency": "科学思维",
            "_llm_calls": [competency_call],
        },
    }

    service._attach_metadata_envelope(question)

    warnings = question["_metadata_envelope"]["warnings"]
    assert "media_not_passed:question_analysis" in warnings
    assert "media_not_passed:feature_extraction" in warnings
    assert "media_not_passed:competency_analysis" not in warnings


def test_metadata_envelope_warns_on_llm_provider_fallback():
    service = AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=None,
        word_splitter=None,
        pdf_splitter=None,
    )
    call = _call("question-4-competency", "competency_analysis", "CompetencyResult")
    call["fallback_count"] = 1
    call["metadata"] = {
        "provider_errors": [{"provider": "primary", "message": "timeout"}],
        "status": "ok",
    }
    question = {
        "id": 4,
        "content": "question",
        "total_score": 2,
        "analysis": {
            "knowledge_points": ["experiment"],
            "_llm_calls": [_call("question-4-analysis", "question_analysis", "AnalysisResult")],
        },
        "difficulty": {
            "final_difficulty": 5.0,
            "features": {"_feature_status": "ok", "_llm_calls": [_call("biology-feature-extraction", "feature_extraction", "FeatureResult")]},
        },
        "competency": {
            "primary_competency": "科学思维",
            "_llm_calls": [call],
        },
    }

    service._attach_metadata_envelope(question)

    warnings = question["_metadata_envelope"]["warnings"]
    assert "llm_fallback:competency_analysis" in warnings
    assert "llm_provider_error:competency_analysis" in warnings


def test_successful_evidence_repair_call_is_not_a_retry_warning():
    service = _service_without_dependencies()
    repair_call = _call("question-18-evidence-repair", "missing_evidence_repair", "EvidenceUnitsResult")
    repair_call["prompt_id"] = "biology.question_analysis.v2.evidence_retry"
    repair_call["retry_count"] = 1
    repair_call["metadata"] = {
        "validation_errors": [],
        "repair_attempt": 1,
        "diagnostic_units_count": 1,
        "stimulus_units_count": 1,
    }
    question = {
        "id": 18,
        "content": "stem",
        "total_score": 12,
        "analysis_confidence": 0.9,
        "analysis": {
            "knowledge_points": ["inheritance"],
            "_extraction_confidence": 0.9,
            "_fine_grained": {
                "scoring_units": [{"label": "analysis", "score_share": 1.0}],
                "diagnostic_units": [{"du_id": "du_1", "option_or_trap": "trap", "misconception": "gap"}],
                "stimulus_units": [{"su_id": "su_1", "stimulus_type": "text", "description": "context"}],
            },
            "_llm_calls": [
                _call("question-18-analysis", "question_analysis", "AnalysisResult"),
                repair_call,
            ],
        },
        "difficulty": {
            "final_difficulty": 7.0,
            "features": {
                "_feature_status": "ok",
                "_llm_calls": [_call("question-18-feature", "big_question_feature_extraction", "FeatureResult")],
            },
        },
        "competency": {
            "primary_competency": "科学思维",
            "_llm_calls": [_call("question-18-competency", "competency_analysis", "CompetencyResult")],
        },
    }

    service._attach_metadata_envelope(question)

    warnings = question["_metadata_envelope"]["warnings"]
    assert "llm_retry:missing_evidence_repair" not in warnings
    assert "llm_parse_failure:missing_evidence_repair" not in warnings
    assert any(
        call["purpose"] == "missing_evidence_repair"
        for call in question["_metadata_envelope"]["llm_calls"]
    )


def test_successful_feature_compact_retry_is_not_a_retry_warning():
    service = _service_without_dependencies()
    feature_call = _call("question-13-feature", "feature_extraction", "FeatureResult")
    feature_call["retry_count"] = 1
    feature_call["metadata"] = {
        "provider_errors": [],
        "feature_status": "ok",
        "recovery_mode": "api_failure_compact_retry",
        "recovery_status": "ok",
    }
    question = {
        "id": 13,
        "content": "stem",
        "total_score": 4,
        "analysis_confidence": 0.9,
        "analysis": {
            "knowledge_points": ["蛋白质的定向转运"],
            "_extraction_confidence": 0.9,
            "_llm_calls": [_call("question-13-analysis", "question_analysis", "AnalysisResult")],
        },
        "difficulty": {
            "final_difficulty": 5.9,
            "features": {
                "_feature_status": "ok",
                "_extraction_confidence": 1.0,
                "_llm_calls": [feature_call],
            },
        },
        "competency": {
            "primary_competency": "科学思维",
            "_llm_calls": [_call("question-13-competency", "competency_analysis", "CompetencyResult")],
        },
    }

    service._attach_metadata_envelope(question)

    warnings = question["_metadata_envelope"]["warnings"]
    assert "llm_retry:feature_extraction" not in warnings
    assert "llm_parse_failure:feature_extraction" not in warnings


def test_internal_analysis_warnings_enter_metadata_and_block_pipeline():
    service = _service_without_dependencies()
    question = {
        "id": 5,
        "content": "question",
        "total_score": 12,
        "_analysis_warnings": ["seu_derivation_failed:ValueError"],
        "analysis": {
            "knowledge_points": ["experiment"],
            "_llm_calls": [_call("question-5-analysis", "question_analysis", "AnalysisResult")],
        },
        "difficulty": {
            "final_difficulty": 7.0,
            "features": {
                "_feature_status": "ok",
                "_llm_calls": [_call("question-5-feature", "feature_extraction", "FeatureResult")],
            },
        },
        "competency": {
            "primary_competency": "科学思维",
            "_llm_calls": [_call("question-5-competency", "competency_analysis", "CompetencyResult")],
        },
    }

    service._attach_metadata_envelope(question)
    warnings = question["_metadata_envelope"]["warnings"]

    assert "seu_derivation_failed:ValueError" in warnings

    audit = service.build_pipeline_audit({
        "warning_questions": [{"id": 5, "warnings": warnings}],
    })
    assert audit["blockers"][0]["code"] == "hard_warning"
    assert "seu_derivation_failed:ValueError" in audit["blockers"][0]["message"]


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


def test_seu_competency_supplement_failure_is_soft_when_weights_exist():
    audit = AnalysisService.build_pipeline_audit({
        "warning_questions": [
            {
                "id": 19,
                "warnings": ["competency_supplement_soft_failed:empty response"],
            }
        ],
    })

    assert audit["status"] == "ok"
    assert audit["blockers"] == []
    assert audit["warnings"] == [
        {"id": 19, "warning": "competency_supplement_soft_failed:empty response"}
    ]


def test_split_integrity_rejects_missing_tail_question_from_source_text():
    service = _service_without_dependencies()
    source_text = "\n".join(f"{idx}. stem {idx}" for idx in range(1, 22))
    questions = [{"id": idx, "content": f"{idx}. stem {idx}"} for idx in range(1, 21)]

    with pytest.raises(ValueError, match="split integrity failed"):
        service.validate_split_integrity(questions, source_text)


def test_document_extraction_failures_are_explicit_events(monkeypatch):
    import document_processor
    from document_processor import DocumentProcessor

    def broken_document(path):
        raise RuntimeError("bad docx")

    monkeypatch.setattr(document_processor, "Document", broken_document)

    result = DocumentProcessor.extract_word_content("broken.docx")

    assert result["text"] == ""
    assert result["failure_events"][0]["stage"] == "document_extraction"
    assert result["failure_events"][0]["file_type"] == "docx"
    assert "bad docx" in result["failure_events"][0]["reason"]


@pytest.mark.asyncio
async def test_auto_pdf_analysis_propagates_document_failure_events():
    class FakeImage:
        info = {
            "failure_events": [{
                "stage": "document_extraction",
                "severity": "blocked",
                "file_type": "pdf",
                "reason": "pdf text layer unreadable",
            }]
        }

    class FakePdfSplitter:
        def split(self, file_path):
            return {"questions": [{"id": 1, "content": "1. stem", "total_score": 2}]}

    class FakeDocProcessor:
        def process_pdf(self, file_path):
            return [FakeImage()]

        def images_to_bytes(self, images):
            return [b"image"]

    class AutoService(AnalysisService):
        async def analyze_questions_batch(self, questions, image_bytes, mode="deep", subject="biology"):
            assert image_bytes == [b"image"]
            return [_ready_question(1)]

        def build_competency_summary(self, questions):
            return {}

        def aggregate_statistics(self, questions, competency_summary):
            return {}

    service = AutoService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=FakeDocProcessor(),
        word_splitter=None,
        pdf_splitter=FakePdfSplitter(),
    )

    result = await service.run_auto_analysis(
        "paper.pdf",
        "paper.pdf",
        b"%PDF",
        generate_report=False,
        exam_review_channel="model",
    )

    assert result["document_failure_events"][0]["file_type"] == "pdf"
    assert result["exam_statistics"]["document_failure_events"][0]["reason"] == "pdf text layer unreadable"
    assert result["metadata_quality"]["failure_events"][0]["file_type"] == "pdf"


@pytest.mark.asyncio
async def test_generate_report_delegates_grounding_to_environment_and_stores_report_insights(monkeypatch, tmp_path):
    service = _service_without_dependencies()
    monkeypatch.delenv("EXAM_REVIEW_CHANNEL", raising=False)
    monkeypatch.setattr(service, "validate_report_metadata", lambda questions: {})

    captured = {}

    def fake_aggregate_report_data(questions, competency_summary, exam_statistics, exam_info):
        return {
            "questions": questions,
            "exam_info": exam_info,
            "metrics": {},
            "difficulty_gradient": {},
            "knowledge": {},
            "competency": {},
            "feature_profile": {},
            "metadata_quality": {},
        }

    async def fake_generate_insights(report_data, mode="full", **kwargs):
        captured["grounding_enabled"] = kwargs.get("grounding_enabled")
        return {
            "overall_assessment": "ok",
            "_grounding_status": "ok",
            "_grounding_checks": [{"status": "ok", "support_score": 0.9}],
            "_llm_calls": [_call("report-grounding", "report_grounding_check", "GroundingCheck")],
        }

    def fake_write_report_artifacts(report_data, insights, mode="full", pdf_path=None):
        captured["insights"] = insights
        captured["pdf_path"] = str(pdf_path)

    monkeypatch.setattr("report_data.aggregate_report_data", fake_aggregate_report_data)
    monkeypatch.setattr("report_insights.generate_insights", fake_generate_insights)
    monkeypatch.setattr("report_product_publish.write_report_artifacts", fake_write_report_artifacts)
    monkeypatch.setattr("exam_diagnostics.diagnose_exam", lambda *args, **kwargs: {})

    pdf_path = tmp_path / "report.pdf"
    result = await service.generate_report(
        questions=[_ready_question(1)],
        competency_summary={},
        exam_statistics={},
        exam_info={"name": "exam", "total_score": 100},
        mode="full",
        output_path=str(pdf_path),
    )

    assert result == str(pdf_path)
    assert captured["grounding_enabled"] is None
    assert captured["insights"]["_grounding_status"] == "ok"
    assert service._last_report_insights["_grounding_checks"][0]["support_score"] == 0.9


@pytest.mark.asyncio
async def test_generate_report_app_builder_channel_enables_grounding(monkeypatch, tmp_path):
    service = _service_without_dependencies()
    monkeypatch.setattr(service, "validate_report_metadata", lambda questions: {})
    captured = {}

    monkeypatch.setattr("report_data.aggregate_report_data", lambda *args, **kwargs: {"questions": [], "exam_info": {}})

    async def fake_generate_insights(report_data, mode="full", **kwargs):
        captured["grounding_enabled"] = kwargs.get("grounding_enabled")
        return {
            "_grounding_status": "ok",
            "_grounding_checks": [{
                "support_score": 0.9,
                "metadata": {"provider": "evidence_service", "operation": "check_grounding"},
            }],
        }

    monkeypatch.setattr("report_insights.generate_insights", fake_generate_insights)
    monkeypatch.setattr("report_product_publish.write_report_artifacts", lambda *args, **kwargs: None)
    monkeypatch.setattr("exam_diagnostics.diagnose_exam", lambda *args, **kwargs: {})

    await service.generate_report(
        [_ready_question_with_ranked_evidence(1)],
        {},
        {},
        {"name": "exam"},
        output_path=str(tmp_path / "report.pdf"),
        exam_review_channel="app_builder",
    )

    assert captured["grounding_enabled"] is True


@pytest.mark.asyncio
async def test_generate_report_model_channel_disables_grounding(monkeypatch, tmp_path):
    service = _service_without_dependencies()
    monkeypatch.setattr(service, "validate_report_metadata", lambda questions: {})
    captured = {}

    monkeypatch.setattr("report_data.aggregate_report_data", lambda *args, **kwargs: {"questions": [], "exam_info": {}})

    async def fake_generate_insights(report_data, mode="full", **kwargs):
        captured["grounding_enabled"] = kwargs.get("grounding_enabled")
        return {}

    monkeypatch.setattr("report_insights.generate_insights", fake_generate_insights)
    monkeypatch.setattr("report_product_publish.write_report_artifacts", lambda *args, **kwargs: None)
    monkeypatch.setattr("exam_diagnostics.diagnose_exam", lambda *args, **kwargs: {})

    await service.generate_report(
        [_ready_question(1)],
        {},
        {},
        {"name": "exam"},
        output_path=str(tmp_path / "report.pdf"),
        exam_review_channel="model",
    )

    assert captured["grounding_enabled"] is False


@pytest.mark.asyncio
async def test_generate_report_blocks_app_builder_grounding_needs_review(monkeypatch, tmp_path):
    service = _service_without_dependencies()
    monkeypatch.setattr(service, "validate_report_metadata", lambda questions: {})
    write_called = False

    monkeypatch.setattr("report_data.aggregate_report_data", lambda *args, **kwargs: {"questions": [], "exam_info": {}})

    async def fake_generate_insights(report_data, mode="full", **kwargs):
        return {
            "_grounding_status": "needs_review",
            "_grounding_checks": [{
                "status": "needs_review",
                "support_score": 0.42,
                "threshold": 0.6,
                "metadata": {"provider": "evidence_service", "operation": "check_grounding"},
            }],
            "_llm_calls": [_call("report-grounding", "report_grounding_check", "GroundingCheck")],
        }

    def fake_write_report_artifacts(*args, **kwargs):
        nonlocal write_called
        write_called = True

    monkeypatch.setattr("report_insights.generate_insights", fake_generate_insights)
    monkeypatch.setattr("report_product_publish.write_report_artifacts", fake_write_report_artifacts)
    monkeypatch.setattr("exam_diagnostics.diagnose_exam", lambda *args, **kwargs: {})

    with pytest.raises(RuntimeError, match="report_grounding"):
        await service.generate_report(
            [_ready_question_with_ranked_evidence(1)],
            {},
            {},
            {"name": "exam"},
            output_path=str(tmp_path / "report.pdf"),
            exam_review_channel="app_builder",
        )

    assert write_called is False


@pytest.mark.asyncio
async def test_generate_report_grounding_validation_error_is_readable_block(monkeypatch, tmp_path):
    service = _service_without_dependencies()
    monkeypatch.setattr(service, "validate_report_metadata", lambda questions: {})

    monkeypatch.setattr(
        "report_data.aggregate_report_data",
        lambda *args, **kwargs: {"questions": [], "exam_info": {}},
    )

    grounding_call = _call("report-grounding", "report_grounding_check", "GroundingCheck")
    grounding_call["validation_errors"] = ["grounding_status=needs_review"]

    async def fake_generate_insights(report_data, mode="full", **kwargs):
        return {
            "_grounding_status": "needs_review",
            "_grounding_checks": [{
                "section": "recommendations",
                "status": "needs_review",
                "support_score": 0.42,
                "threshold": 0.6,
                "metadata": {"provider": "evidence_service", "operation": "check_grounding"},
            }],
            "_llm_calls": [grounding_call],
        }

    monkeypatch.setattr("report_insights.generate_insights", fake_generate_insights)
    monkeypatch.setattr("report_product_publish.write_report_artifacts", lambda *args, **kwargs: None)
    monkeypatch.setattr("exam_diagnostics.diagnose_exam", lambda *args, **kwargs: {})

    with pytest.raises(RuntimeError, match="report_grounding.grounding_not_ok"):
        await service.generate_report(
            [_ready_question_with_ranked_evidence(1)],
            {},
            {},
            {"name": "exam"},
            output_path=str(tmp_path / "report.pdf"),
            exam_review_channel="app_builder",
        )

    assert service._last_report_insights["_grounding_checks"][0]["section"] == "recommendations"
    assert service._last_pipeline_audit["blockers"][0]["stage"] == "report_grounding"
    assert service._last_pipeline_audit["blockers"][0]["code"] == "grounding_not_ok"
    assert "first failed section=recommendations" in service._last_pipeline_audit["blockers"][0]["message"]


@pytest.mark.asyncio
async def test_auto_analysis_blocks_report_generation_when_llm_fallback_warning_exists(tmp_path):
    class LocalWordSplitter:
        def split(self, file_path):
            return {"questions": [{"id": 1, "content": "Question stem"}]}

    class LocalDocProcessor:
        def process_docx(self, file_path):
            return []

    service = AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=LocalDocProcessor(),
        word_splitter=LocalWordSplitter(),
        pdf_splitter=None,
    )
    report_called = False

    async def fake_generate_report(*args, **kwargs):
        nonlocal report_called
        report_called = True

    q = _ready_question(1)
    q["_metadata_envelope"]["warnings"] = ["llm_fallback:question_analysis"]

    async def fake_analyze_questions_batch_with_fallback(questions, image_bytes, mode, subject="biology"):
        return [q]

    service.analyze_questions_batch = fake_analyze_questions_batch_with_fallback
    service.build_competency_summary = lambda questions: {}
    service.aggregate_statistics = lambda questions, competency_summary: {}
    service.generate_report = fake_generate_report

    with pytest.raises(RuntimeError, match="pipeline gate failed"):
        await service.run_auto_analysis(
            "exam.docx",
            "exam.docx",
            b"",
            generate_report=True,
            reports_dir=str(tmp_path),
            exam_id="exam-1",
            exam_review_channel="model",
        )

    assert report_called is False
    assert service._last_pipeline_audit["status"] == "blocked"
    assert any(
        blocker["stage"] == "question_metadata"
        and blocker["code"] == "hard_warning"
        for blocker in service._last_pipeline_audit["blockers"]
    )


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
    assert result["_metadata_envelope"]["lineage"]["failure_reason"] == "provider 400"
    assert "analysis_failed" in result["_metadata_envelope"]["warnings"]
    with pytest.raises(ValueError, match="analysis failed"):
        service.validate_report_metadata([result])

    no_score_result = await service.analyze_question(
        {"id": 10, "content": "第 10 题（2 分）bad prompt"},
        [],
        "deep",
    )
    assert no_score_result["analysis_failed"] is True
    assert no_score_result.get("total_score") is None
