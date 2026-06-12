import io
import json
from datetime import datetime

import pytest
from fastapi import HTTPException, UploadFile

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


def _skip_score_prediction(monkeypatch):
    """拦截后台管线的 score_prediction 段，防止测试真连 DB 写 ScorePrediction 表。
    _run_analysis_pipeline 内 `from database import get_db_session` 在函数执行时取
    database 模块属性 → monkeypatch database.get_db_session 即可让其抛错走 except 分支。"""
    import database

    async def _raise():
        raise RuntimeError("score_prediction skipped in test")

    monkeypatch.setattr(database, "get_db_session", _raise)


@pytest.mark.asyncio
async def test_analyze_document_route_is_offline_410(monkeypatch, tmp_path):
    """analyze_document 已下线（410），杜绝绕过付费墙的免费分析。"""
    monkeypatch.setattr(analysis_router, "UPLOAD_DIR", tmp_path)

    upload = UploadFile(filename="exam.docx", file=io.BytesIO(b"docx"))

    with pytest.raises(HTTPException) as exc:
        await analysis_router.analyze_document(
            file=upload,
            mode=analysis_router.AnalysisMode.DEEP,
            generate_report=False,
            exam_review_channel="model",
        )

    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_analysis_pipeline_produces_metadata_quality(monkeypatch):
    """analyze_auto 异步化后，metadata_quality 由后台管线 _run_analysis_pipeline 产出，
    经 task_manager.complete 存入 task result（前端轮询 status 取回）。"""
    captured = {}

    async def fake_analyze_question_full(question, image_bytes, mode, exam_review_channel=None):
        captured["exam_review_channel"] = exam_review_channel
        return _question(1, overall=0.55)

    _skip_score_prediction(monkeypatch)
    monkeypatch.setattr(analysis_router.task_manager, "complete", lambda tid, result: captured.update(result))
    monkeypatch.setattr(analysis_router, "generate_exam_statistics", lambda questions, summary: {})
    monkeypatch.setattr(analysis_router, "analyze_question_full", fake_analyze_question_full)

    await analysis_router._run_analysis_pipeline(
        task_id="t1",
        questions=[{"id": 1, "content": "题干", "_media_for_ai": []}],
        image_bytes=[],
        mode=analysis_router.AnalysisMode.DEEP,
        effective_review_channel="model",
        competency_analyzer=FakeCompetencyAnalyzer(),
        generate_report=False,
        report_mode="full",
        filename="exam.docx",
        start_time=datetime.now(),
    )

    assert captured["exam_review_channel"] == "model"
    assert captured["metadata_quality"]["low_confidence_questions"] == [1]
    assert captured["metadata_quality"]["warning_questions"] == [
        {"id": 1, "warnings": ["feature_status:partial"]}
    ]


@pytest.mark.asyncio
async def test_analysis_pipeline_signs_report_url(monkeypatch):
    """后台管线生成的报告 URL 必须带 HMAC 签名（Phase 2.5 防报告 PII 匿名遍历）。"""
    captured = {}

    async def fake_analyze_question_full(question, image_bytes, mode, exam_review_channel=None):
        return _question(1, overall=0.9)

    async def fake_generate_report_artifacts(
        questions, competency_summary, exam_statistics, exam_info, report_mode, pdf_path,
        exam_review_channel=None,
    ):
        return {"pdf_path": str(pdf_path), "html_path": str(pdf_path.with_suffix(".html"))}

    _skip_score_prediction(monkeypatch)
    monkeypatch.setattr(analysis_router.task_manager, "complete", lambda tid, result: captured.update(result))
    monkeypatch.setattr(analysis_router, "generate_exam_statistics", lambda questions, summary: {})
    monkeypatch.setattr(analysis_router, "analyze_question_full", fake_analyze_question_full)
    monkeypatch.setattr(analysis_router, "_validate_report_metadata_for_route", lambda questions: None)
    monkeypatch.setattr(analysis_router, "_generate_route_report_artifacts", fake_generate_report_artifacts)

    await analysis_router._run_analysis_pipeline(
        task_id="t1",
        questions=[{"id": 1, "content": "题干", "_media_for_ai": []}],
        image_bytes=[],
        mode=analysis_router.AnalysisMode.DEEP,
        effective_review_channel="model",
        competency_analyzer=FakeCompetencyAnalyzer(),
        generate_report=True,
        report_mode="full",
        filename="exam.docx",
        start_time=datetime.now(),
    )

    assert captured["report_url"].split("?")[0].endswith(".pdf")
    assert "sig=" in captured["report_url"] and "exp=" in captured["report_url"]
    assert captured["html_report_url"].split("?")[0].endswith(".html")
    assert "sig=" in captured["html_report_url"] and "exp=" in captured["html_report_url"]


@pytest.mark.asyncio
async def test_confirm_split_route_returns_metadata_quality(monkeypatch, tmp_path):
    captured = {}

    async def fake_verify_token(token):
        return {"id": 1, "email": "teacher@example.com"}

    async def fake_get_balance(user_id):
        return 1000

    async def fake_consume(user_id, cost, reason):
        return None

    async def fake_analyze_question_full(question, image_bytes, mode, exam_review_channel=None):
        captured["exam_review_channel"] = exam_review_channel
        return _question(1, overall=0.55)

    session_file = tmp_path / "session.docx"
    session_file.write_bytes(b"docx")

    monkeypatch.setattr(analysis_router.credits_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(analysis_router.credits_service, "get_balance", fake_get_balance)
    monkeypatch.setattr(analysis_router.credits_service, "consume", fake_consume)
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
        exam_review_channel="model",
        authorization="Bearer token",
    )

    assert captured["exam_review_channel"] == "model"
    assert result["exam_review_channel"] == "model"
    assert result["metadata_quality"]["low_confidence_questions"] == [1]
    assert result["metadata_quality"]["warning_questions"] == [
        {"id": 1, "warnings": ["feature_status:partial"]}
    ]


@pytest.mark.asyncio
async def test_confirm_split_route_returns_html_report_url(monkeypatch, tmp_path):
    async def fake_verify_token(token):
        return {"id": 1, "email": "teacher@example.com"}

    async def fake_get_balance(user_id):
        return 1000

    async def fake_consume(user_id, cost, reason):
        return None

    async def fake_analyze_question_full(question, image_bytes, mode, exam_review_channel=None):
        return _question(1, overall=0.9)

    async def fake_generate_report_artifacts(
        questions, competency_summary, exam_statistics, exam_info, report_mode, pdf_path,
        exam_review_channel=None,
    ):
        return {"pdf_path": str(pdf_path), "html_path": str(pdf_path.with_suffix(".html"))}

    session_file = tmp_path / "session.docx"
    session_file.write_bytes(b"docx")

    monkeypatch.setattr(analysis_router.credits_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(analysis_router.credits_service, "get_balance", fake_get_balance)
    monkeypatch.setattr(analysis_router.credits_service, "consume", fake_consume)
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
        authorization="Bearer token",
    )

    assert result["report_url"].split("?")[0] == "/api/reports/session-1.pdf"
    assert "sig=" in result["report_url"] and "exp=" in result["report_url"]
    assert result["html_report_url"].split("?")[0] == "/api/reports/session-1.html"
    assert "sig=" in result["html_report_url"] and "exp=" in result["html_report_url"]
