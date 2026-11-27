import asyncio
import io
import json
from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from httpx import ASGITransport, AsyncClient

import analysis_router
from score_rules import SOURCE_MODEL, paper_score
from tests.fakes.fake_llm_client import FakeLlmClient


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
    def aggregate_exam_competencies(self, competency_list, subject=None):
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
        )

    assert exc.value.status_code == 410


@pytest.mark.asyncio
async def test_analysis_pipeline_produces_metadata_quality(monkeypatch):
    """analyze_auto 异步化后，metadata_quality 由后台管线 _run_analysis_pipeline 产出，
    经 task_manager.complete 存入 task result（前端轮询 status 取回）。"""
    captured = {}

    async def fake_analyze_question_full(question, image_bytes, mode):
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
        competency_analyzer=FakeCompetencyAnalyzer(),
        generate_report=False,
        report_mode="full",
        filename="exam.docx",
        start_time=datetime.now(),
    )

    assert captured["metadata_quality"]["low_confidence_questions"] == [1]
    assert captured["metadata_quality"]["warning_questions"] == [
        {"id": 1, "warnings": ["feature_status:partial"]}
    ]


@pytest.mark.asyncio
async def test_analysis_pipeline_signs_report_url(monkeypatch):
    """后台管线生成的报告 URL 必须带 HMAC 签名（Phase 2.5 防报告 PII 匿名遍历）。"""
    captured = {}

    async def fake_analyze_question_full(question, image_bytes, mode):
        return _question(1, overall=0.9)

    async def fake_generate_report_artifacts(
        questions, competency_summary, exam_statistics, exam_info, report_mode, pdf_path,
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

    async def fake_analyze_question_full(question, image_bytes, mode):
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
        authorization="Bearer token",
    )

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

    async def fake_analyze_question_full(question, image_bytes, mode):
        return _question(1, overall=0.9)

    async def fake_generate_report_artifacts(
        questions, competency_summary, exam_statistics, exam_info, report_mode, pdf_path,
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


@pytest.fixture
async def upload_client(monkeypatch, tmp_path):
    import database
    import prediction_service
    from auth_router import active_tokens

    active_tokens["expert"] = {"id": 1, "username": "reviewer"}

    async def verify_token(token):
        assert token == "teacher"
        return {"id": 2, "email": "teacher@example.com"}

    async def get_balance(user_id):
        assert user_id == 2
        return 1000

    async def consume(user_id, cost, reason):
        assert user_id == 2

    def split_word(path, *, subject):
        return {"questions": [
            {"id": 1, "content": "1. 题干", "question_type": "single_choice"},
            {"id": 2, "content": "2.（10分）题干", "question_type": "short_answer"},
            {"id": 3, "content": "3. 第一题简答", "question_type": "short_answer"},
            {"id": 4, "content": "4. 第二题简答", "question_type": "short_answer"},
        ]}

    llm = FakeLlmClient({
        FakeLlmClient.hash_content(content): json.dumps({"total_score": score})
        for content, score in [("1. 题干", 2), ("3. 第一题简答", 8), ("4. 第二题简答", 10)]
    })

    async def analyze_question_full(question, image_bytes, mode):
        score, source = paper_score(question)
        if score is None:
            response = await llm.llm_call([{"role": "user", "content": question["content"]}])
            score, source = json.loads(response)["total_score"], SOURCE_MODEL
        return {
            **_question(question["id"]), **question,
            "total_score": score, "score_source": source, "score_status": "valid",
        }

    class FakeSession:
        async def close(self):
            pass

    class FakePredictionService:
        def __init__(self, db):
            pass

        async def predict_exam_score(self, *, total_score, **kwargs):
            return {"total_score": total_score}

    async def get_db_session():
        return FakeSession()

    monkeypatch.setattr(analysis_router, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(analysis_router, "split_word_with_visual", split_word)
    monkeypatch.setattr(analysis_router, "get_doc_processor", FakeDocProcessor)
    monkeypatch.setattr(analysis_router, "get_word_splitter", FakeWordSplitter)
    monkeypatch.setattr(analysis_router, "get_pdf_splitter", lambda: None)
    monkeypatch.setattr(analysis_router, "get_competency_analyzer", FakeCompetencyAnalyzer)
    monkeypatch.setattr(analysis_router, "analyze_question_full", analyze_question_full)
    monkeypatch.setattr(analysis_router.credits_service, "verify_token", verify_token)
    monkeypatch.setattr(analysis_router.credits_service, "get_balance", get_balance)
    monkeypatch.setattr(analysis_router.credits_service, "consume", consume)
    monkeypatch.setattr(database, "get_db_session", get_db_session)
    monkeypatch.setattr(prediction_service, "PredictionService", FakePredictionService)

    app = FastAPI()
    app.include_router(analysis_router.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _submit_upload(client, token, full_mark=None, filename="exam.docx"):
    return await client.post(
        "/api/analyze_auto",
        files={"file": (filename, b"docx")},
        data={} if full_mark is None else {"full_mark": str(full_mark)},
        headers={"Authorization": f"Bearer {token}"},
    )


async def _upload_result(client, response):
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    status = (await client.get(f"/api/analysis/status/{task_id}")).json()
    assert status["status"] == "completed", status
    return status["result"]


def _scores(result):
    return [q["total_score"] for q in result["questions"]]


async def test_analyze_auto_without_full_mark_preserves_existing_result(upload_client):
    response = await _submit_upload(upload_client, "expert")
    await asyncio.gather(*analysis_router._bg_tasks)
    result = await _upload_result(upload_client, response)
    assert "full_mark_result" not in result
    assert _scores(result) == [2, 10, 8, 10]
    assert [q["score_source"] for q in result["questions"]] == ["model", "paper", "model", "model"]
    assert result["score_warnings"] == []
    assert result["score_prediction"]["total_score"] == 30


async def test_analyze_auto_concurrent_uploads_keep_full_mark_per_task(upload_client, monkeypatch):
    analyze = analysis_router.analyze_question_full
    both_started = asyncio.Event()
    started = 0

    async def analyze_together(question, image_bytes, mode):
        nonlocal started
        if question["id"] == 1:
            started += 1
            if started == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=5)
        return await analyze(question, image_bytes, mode)

    monkeypatch.setattr(analysis_router, "analyze_question_full", analyze_together)
    with_mark, without_mark = await asyncio.gather(
        _submit_upload(upload_client, "expert", 100),
        _submit_upload(upload_client, "teacher", filename="other-exam.docx"),
    )
    await asyncio.gather(*analysis_router._bg_tasks)

    assert started == 2
    with_result = await _upload_result(upload_client, with_mark)
    assert with_result.get("full_mark_result") == {"full_mark": 100, "adjusted": 2, "fixed_total": 12}
    assert _scores(with_result) == [2, 10, 39, 49]
    assert with_result["score_prediction"]["total_score"] == 100
    without_result = await _upload_result(upload_client, without_mark)
    assert "full_mark_result" not in without_result
    assert _scores(without_result) == [2, 10, 8, 10]


async def test_analyze_auto_same_paper_reuploaded_with_changed_full_mark(upload_client):
    first = await _submit_upload(upload_client, "teacher", 100)
    await asyncio.gather(*analysis_router._bg_tasks)
    first_result = await _upload_result(upload_client, first)
    second = await _submit_upload(upload_client, "teacher", 80)
    await asyncio.gather(*analysis_router._bg_tasks)
    second_result = await _upload_result(upload_client, second)

    assert first.json()["task_id"] != second.json()["task_id"]
    assert first_result.get("full_mark_result") == {"full_mark": 100, "adjusted": 2, "fixed_total": 12}
    assert second_result.get("full_mark_result") == {"full_mark": 80, "adjusted": 2, "fixed_total": 12}
    assert _scores(first_result) == [2, 10, 39, 49]
    assert _scores(second_result) == [2, 10, 30, 38]
    assert await _upload_result(upload_client, first) == first_result


@pytest.mark.parametrize("full_mark", [0, -1])
async def test_analyze_auto_rejects_nonpositive_full_mark(upload_client, full_mark):
    response = await _submit_upload(upload_client, "expert", full_mark)
    await asyncio.gather(*analysis_router._bg_tasks)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "full_mark"]


@pytest.mark.parametrize(("full_mark", "question_total", "prediction_total"), [
    (20, 20, 20),
    (None, 14, 100),
    (8, 14, 100),
])
async def test_analyze_auto_predicts_from_successfully_apportioned_small_full_mark(
    upload_client, monkeypatch, full_mark, question_total, prediction_total,
):
    def split_quiz(path, *, subject):
        return {"questions": [
            {"id": i, "content": f"{i}.（1分）题干", "question_type": "single_choice"}
            for i in range(1, 13)
        ] + [
            {"id": i, "content": f"{i}. 简答", "question_type": "short_answer"}
            for i in range(13, 15)
        ]}

    analyze = analysis_router.analyze_question_full

    async def analyze_quiz(question, image_bytes, mode):
        result = await analyze(question, image_bytes, mode)
        if question["question_type"] == "short_answer":
            result["total_score"] = 1
        return result

    monkeypatch.setattr(analysis_router, "split_word_with_visual", split_quiz)
    monkeypatch.setattr(analysis_router, "analyze_question_full", analyze_quiz)

    response = await _submit_upload(upload_client, "teacher", full_mark)
    await asyncio.gather(*analysis_router._bg_tasks)
    result = await _upload_result(upload_client, response)
    assert sum(_scores(result)) == question_total
    assert result["score_prediction"]["total_score"] == prediction_total
