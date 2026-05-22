import io
import json

import pytest
from fastapi import UploadFile

import analysis_router


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


def _question(question_id=1, overall=0.55):
    calls = [_call("question_analysis"), _call("feature_extraction"), _call("competency_analysis")]
    return {
        "id": question_id,
        "content": "题干",
        "total_score": 2,
        "analysis": {"knowledge_points": ["酶"], "answer": "A"},
        "difficulty": {"final_difficulty": 5.0, "features": {"_feature_status": "partial"}},
        "competency": {"primary_competency": "科学思维"},
        "_metadata_envelope": {
            "question": {"id": question_id},
            "llm_calls": calls,
            "analysis_units": {},
            "derived": {},
            "confidence": {"overall": overall, "analysis": 0.9, "features": 0.55, "competency": 0.9},
            "lineage": {
                "knowledge_points": "analysis.knowledge_points",
                "difficulty_features": "difficulty.features",
                "competency": "competency",
            },
            "warnings": ["feature_status:partial"],
        },
    }


class FakeWordSplitter:
    def split(self, file_path):
        return {"questions": [{"id": 1, "content": "题干"}]}


class FakeDocProcessor:
    def process_docx(self, file_path):
        return []

    def images_to_bytes(self, images):
        return []


class FakeCompetencyAnalyzer:
    def aggregate_exam_competencies(self, competency_list):
        return {}


@pytest.mark.asyncio
async def test_analyze_document_route_preserves_service_metadata_quality(monkeypatch, tmp_path):
    class FakeService:
        async def run_full_analysis(self, **kwargs):
            return {
                "questions": [_question(1, overall=0.55)],
                "competency_summary": {},
                "exam_statistics": {},
                "metadata_quality": {
                    "low_confidence_questions": [1],
                    "warning_questions": [{"id": 1, "warnings": ["feature_status:partial"]}],
                },
                "report_url": None,
                "report_error": None,
            }

    monkeypatch.setattr(analysis_router, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(analysis_router, "get_analysis_service", lambda: FakeService())

    upload = UploadFile(filename="exam.docx", file=io.BytesIO(b"docx"))

    result = await analysis_router.analyze_document(
        file=upload,
        mode=analysis_router.AnalysisMode.DEEP,
        generate_report=False,
    )

    assert result["metadata_quality"]["low_confidence_questions"] == [1]


@pytest.mark.asyncio
async def test_analyze_auto_route_returns_metadata_quality(monkeypatch, tmp_path):
    async def fake_verify_token(token):
        return {"id": 1, "email": "teacher@example.com"}

    async def fake_get_balance(user_id):
        return 1000

    async def fake_consume(user_id, cost, reason):
        return None

    async def fake_analyze_question_full(question, image_bytes, mode):
        return _question(1, overall=0.55)

    monkeypatch.setattr(analysis_router.credits_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(analysis_router.credits_service, "get_balance", fake_get_balance)
    monkeypatch.setattr(analysis_router.credits_service, "consume", fake_consume)
    monkeypatch.setattr(analysis_router, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(analysis_router, "get_word_splitter", lambda: FakeWordSplitter())
    monkeypatch.setattr(analysis_router, "get_doc_processor", lambda: FakeDocProcessor())
    monkeypatch.setattr(analysis_router, "get_competency_analyzer", lambda: FakeCompetencyAnalyzer())
    monkeypatch.setattr(analysis_router, "generate_exam_statistics", lambda questions, summary: {})
    monkeypatch.setattr(analysis_router, "analyze_question_full", fake_analyze_question_full)

    upload = UploadFile(filename="exam.docx", file=io.BytesIO(b"docx"))

    result = await analysis_router.analyze_auto(
        file=upload,
        mode=analysis_router.AnalysisMode.DEEP,
        generate_report=False,
        authorization="Bearer token",
    )

    assert result["metadata_quality"]["low_confidence_questions"] == [1]
    assert result["metadata_quality"]["warning_questions"] == [
        {"id": 1, "warnings": ["feature_status:partial"]}
    ]


@pytest.mark.asyncio
async def test_analyze_auto_route_returns_html_report_url(monkeypatch, tmp_path):
    async def fake_verify_token(token):
        return {"id": 1, "email": "teacher@example.com"}

    async def fake_get_balance(user_id):
        return 1000

    async def fake_consume(user_id, cost, reason):
        return None

    async def fake_analyze_question_full(question, image_bytes, mode):
        return _question(1, overall=0.9)

    async def fake_generate_report_artifacts(
        questions, competency_summary, exam_statistics, exam_info, report_mode, pdf_path
    ):
        return {"pdf_path": str(pdf_path), "html_path": str(pdf_path.with_suffix(".html"))}

    monkeypatch.setattr(analysis_router.credits_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(analysis_router.credits_service, "get_balance", fake_get_balance)
    monkeypatch.setattr(analysis_router.credits_service, "consume", fake_consume)
    monkeypatch.setattr(analysis_router, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(analysis_router, "get_word_splitter", lambda: FakeWordSplitter())
    monkeypatch.setattr(analysis_router, "get_doc_processor", lambda: FakeDocProcessor())
    monkeypatch.setattr(analysis_router, "get_competency_analyzer", lambda: FakeCompetencyAnalyzer())
    monkeypatch.setattr(analysis_router, "generate_exam_statistics", lambda questions, summary: {})
    monkeypatch.setattr(analysis_router, "analyze_question_full", fake_analyze_question_full)
    monkeypatch.setattr(analysis_router, "_validate_report_metadata_for_route", lambda questions: None)
    monkeypatch.setattr(analysis_router, "_generate_route_report_artifacts", fake_generate_report_artifacts)

    upload = UploadFile(filename="exam.docx", file=io.BytesIO(b"docx"))

    result = await analysis_router.analyze_auto(
        file=upload,
        mode=analysis_router.AnalysisMode.DEEP,
        generate_report=True,
        authorization="Bearer token",
    )

    assert result["report_url"].endswith(".pdf")
    assert result["html_report_url"].endswith(".html")


@pytest.mark.asyncio
async def test_confirm_split_route_returns_metadata_quality(monkeypatch, tmp_path):
    async def fake_analyze_question_full(question, image_bytes, mode):
        return _question(1, overall=0.55)

    session_file = tmp_path / "session.docx"
    session_file.write_bytes(b"docx")

    monkeypatch.setattr(
        analysis_router,
        "get_session",
        lambda session_id: {
            "file_path": str(session_file),
            "filename": "exam.docx",
            "auto_split_result": {"questions": [{"id": 1, "content": "题干", "_media_for_ai": []}]},
        },
    )
    monkeypatch.setattr(analysis_router, "get_competency_analyzer", lambda: FakeCompetencyAnalyzer())
    monkeypatch.setattr(analysis_router, "generate_exam_statistics", lambda questions, summary: {})
    monkeypatch.setattr(analysis_router, "analyze_question_full", fake_analyze_question_full)

    result = await analysis_router.confirm_split(
        session_id="session-1",
        corrected_questions=json.dumps([{"id": 1, "content": "题干"}]),
        mode=analysis_router.AnalysisMode.DEEP,
        generate_report=False,
    )

    assert result["metadata_quality"]["low_confidence_questions"] == [1]
    assert result["metadata_quality"]["warning_questions"] == [
        {"id": 1, "warnings": ["feature_status:partial"]}
    ]


@pytest.mark.asyncio
async def test_confirm_split_route_returns_html_report_url(monkeypatch, tmp_path):
    async def fake_analyze_question_full(question, image_bytes, mode):
        return _question(1, overall=0.9)

    async def fake_generate_report_artifacts(
        questions, competency_summary, exam_statistics, exam_info, report_mode, pdf_path
    ):
        return {"pdf_path": str(pdf_path), "html_path": str(pdf_path.with_suffix(".html"))}

    session_file = tmp_path / "session.docx"
    session_file.write_bytes(b"docx")

    monkeypatch.setattr(
        analysis_router,
        "get_session",
        lambda session_id: {
            "file_path": str(session_file),
            "filename": "exam.docx",
            "auto_split_result": {"questions": [{"id": 1, "content": "题干", "_media_for_ai": []}]},
        },
    )
    monkeypatch.setattr(analysis_router, "get_competency_analyzer", lambda: FakeCompetencyAnalyzer())
    monkeypatch.setattr(analysis_router, "generate_exam_statistics", lambda questions, summary: {})
    monkeypatch.setattr(analysis_router, "analyze_question_full", fake_analyze_question_full)
    monkeypatch.setattr(analysis_router, "_validate_report_metadata_for_route", lambda questions: None)
    monkeypatch.setattr(analysis_router, "_generate_route_report_artifacts", fake_generate_report_artifacts)

    result = await analysis_router.confirm_split(
        session_id="session-1",
        corrected_questions=json.dumps([{"id": 1, "content": "题干"}]),
        mode=analysis_router.AnalysisMode.DEEP,
        generate_report=True,
    )

    assert result["report_url"] == "/api/reports/session-1.pdf"
    assert result["html_report_url"] == "/api/reports/session-1.html"
