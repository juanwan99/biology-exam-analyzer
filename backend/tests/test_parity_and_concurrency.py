"""Parity + concurrency + error matrix tests — 补 GPT review F-001/F-005/F-007."""
import json
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

FIXTURES = Path(__file__).parent / "fixtures"


# ── F-001: Parity test — service 输出 = 原 router 输出结构 ──────────

class TestAnalysisServiceParity:
    """验证 AnalysisService.analyze_question 输出结构与原 router 行为一致。"""

    def _make_service(self, analysis_ret, difficulty_ret, competency_ret):
        from services.analysis_service import AnalysisService

        analyzer = MagicMock()
        analyzer.analyze_question = AsyncMock(return_value=analysis_ret)

        difficulty_engine = MagicMock()
        difficulty_engine.evaluate_with_refinement = AsyncMock(return_value=difficulty_ret)

        competency_analyzer = MagicMock()
        competency_analyzer.analyze_competency = AsyncMock(return_value=competency_ret)

        return AnalysisService(
            analyzer=analyzer,
            difficulty_engine=difficulty_engine,
            competency_analyzer=competency_analyzer,
            knowledge_mapper=MagicMock(),
            doc_processor=MagicMock(),
            word_splitter=MagicMock(),
            pdf_splitter=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_success_output_has_all_fields(self):
        """成功分析时，输出必须包含 analysis/difficulty/competency 三个 key。"""
        analysis = json.loads((FIXTURES / "fake_analysis_results.json").read_text())["1"]
        difficulty = json.loads((FIXTURES / "fake_difficulty_results.json").read_text())["1"]
        competency = json.loads((FIXTURES / "fake_competency_results.json").read_text())["1"]

        svc = self._make_service(analysis, difficulty, competency)
        question = {"id": 1, "content": "test question", "total_score": 2}
        result = await svc.analyze_question(question, [], "deep")

        assert "analysis" in result
        assert "difficulty" in result
        assert "competency" in result
        assert result["analysis"]["answer"] == "B"
        assert result["difficulty"]["final_difficulty"] == 3.2
        assert result["competency"]["primary_competency"] == "生命观念"

    @pytest.mark.asyncio
    async def test_failure_output_has_error_fields(self):
        """LLM 失败时，输出必须有 error 字段（不是抛异常）— 与原 router 行为一致。"""
        svc = self._make_service(None, None, None)
        svc.analyzer.analyze_question = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        question = {"id": 1, "content": "test", "total_score": 2}
        result = await svc.analyze_question(question, [], "deep")

        assert "error" in result["analysis"]
        assert "error" in result["difficulty"]
        assert "error" in result["competency"]
        assert result["analysis"]["knowledge_points"] == []
        assert result["analysis"]["answer"] == "分析失败"

    @pytest.mark.asyncio
    async def test_question_type_inferred(self):
        """题型推断必须写入 question["question_type"]。"""
        analysis = {"knowledge_points": ["x"], "answer": "A", "total_score": 2, "num_options": 4}
        svc = self._make_service(analysis, {"final_difficulty": 3}, {"primary_competency": "生命观念"})

        question = {"id": 1, "content": "A. x\nB. y\nC. z\nD. w", "total_score": 2}
        result = await svc.analyze_question(question, [], "deep")
        assert "question_type" in result

    @pytest.mark.asyncio
    async def test_image_resolution_media_for_ai(self):
        """_media_for_ai 字段优先于 image_indices — 与原 router 行为一致。"""
        import base64
        img_data = b"fake_image_data"
        b64 = base64.b64encode(img_data).decode()

        analysis = {"knowledge_points": [], "answer": "A", "total_score": 2, "num_options": 4}
        svc = self._make_service(analysis, {"final_difficulty": 3}, {"primary_competency": "x"})

        question = {
            "id": 1, "content": "test", "total_score": 2,
            "_media_for_ai": [{"type": "image", "base64": b64}],
            "image_indices": [0],
        }
        await svc.analyze_question(question, [b"other_image"], "deep")

        call_args = svc.analyzer.analyze_question.call_args
        passed_images = call_args.kwargs.get("question_images", [])
        assert len(passed_images) == 1
        assert passed_images[0] == img_data  # must be _media_for_ai content, not image_indices


# ── F-005: Concurrent batch analysis ──────────────────────────────

class TestBatchConcurrency:
    """验证批量分析的并发行为。"""

    @pytest.mark.asyncio
    async def test_batch_preserves_order(self):
        """批量分析结果顺序必须与输入题目顺序一致。"""
        from services.analysis_service import AnalysisService

        call_order = []

        async def fake_analyze(q_data, **kwargs):
            q_id = q_data.get("id", 0)
            call_order.append(q_id)
            await asyncio.sleep(0.01 * (5 - q_id))  # 后面的题先完成
            return {"knowledge_points": [], "answer": str(q_id), "total_score": 2, "num_options": 4}

        analyzer = MagicMock()
        analyzer.analyze_question = fake_analyze
        difficulty = MagicMock()
        difficulty.evaluate_with_refinement = AsyncMock(return_value={"final_difficulty": 3})
        competency = MagicMock()
        competency.analyze_competency = AsyncMock(return_value={"primary_competency": "x"})

        svc = AnalysisService(
            analyzer=analyzer, difficulty_engine=difficulty,
            competency_analyzer=competency, knowledge_mapper=MagicMock(),
            doc_processor=MagicMock(), word_splitter=MagicMock(),
            pdf_splitter=MagicMock(), max_workers=5,
        )

        questions = [{"id": i, "content": f"q{i}", "total_score": 2} for i in range(1, 5)]
        results = await svc.analyze_questions_batch(questions, [], "deep")

        # Results must be in input order regardless of completion order
        result_ids = [r["id"] for r in results]
        assert result_ids == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_single_failure_does_not_crash_batch(self):
        """单题失败不应影响其他题目。"""
        from services.analysis_service import AnalysisService

        call_count = 0

        async def fake_analyze(**kwargs):
            nonlocal call_count
            call_count += 1
            q_text = kwargs.get("question_text", "")
            if "q2" in q_text:
                raise RuntimeError("LLM failed for q2")
            return {"knowledge_points": [], "answer": "A", "total_score": 2, "num_options": 4}

        analyzer = MagicMock()
        analyzer.analyze_question = AsyncMock(side_effect=fake_analyze)
        difficulty = MagicMock()
        difficulty.evaluate_with_refinement = AsyncMock(return_value={"final_difficulty": 3})
        competency = MagicMock()
        competency.analyze_competency = AsyncMock(return_value={"primary_competency": "x"})

        svc = AnalysisService(
            analyzer=analyzer, difficulty_engine=difficulty,
            competency_analyzer=competency, knowledge_mapper=MagicMock(),
            doc_processor=MagicMock(), word_splitter=MagicMock(),
            pdf_splitter=MagicMock(),
        )

        questions = [{"id": i, "content": f"q{i}", "total_score": 2} for i in range(1, 4)]
        results = await svc.analyze_questions_batch(questions, [], "deep")

        assert len(results) == 3
        # q1 and q3 should succeed
        assert "error" not in results[0].get("analysis", {})
        # q2 should have error
        assert "error" in results[1].get("analysis", {})
        assert "error" not in results[2].get("analysis", {})


# ── F-007: Error classification matrix ────────────────────────────

class TestErrorClassificationMatrix:
    """验证各种异常类型的分类正确性。"""

    def test_httpx_read_timeout(self):
        import httpx
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(httpx.ReadTimeout("timeout"))
        assert e.category == ErrorCategory.LLM_TIMEOUT
        assert e.retryable is True

    def test_httpx_connect_timeout(self):
        import httpx
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(httpx.ConnectTimeout("connect timeout"))
        assert e.category == ErrorCategory.LLM_TIMEOUT
        assert e.retryable is True

    def test_httpx_connect_error(self):
        import httpx
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(httpx.ConnectError("connection refused"))
        assert e.category == ErrorCategory.INTERNAL
        assert e.retryable is False

    def test_http_429(self):
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(RuntimeError("Client error '429 Too Many Requests'"))
        assert e.category == ErrorCategory.LLM_RATE_LIMIT
        assert e.retryable is True

    def test_http_401(self):
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(RuntimeError("Client error '401 Unauthorized'"))
        assert e.category == ErrorCategory.LLM_AUTH
        assert e.retryable is False

    def test_http_403(self):
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(RuntimeError("Client error '403 Forbidden'"))
        assert e.category == ErrorCategory.LLM_AUTH
        assert e.retryable is False

    def test_json_decode_error(self):
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(json.JSONDecodeError("err", "", 0))
        assert e.category == ErrorCategory.LLM_INVALID_RESPONSE
        assert e.retryable is True

    def test_value_error_parse(self):
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(ValueError("Cannot parse JSON response"))
        assert e.category == ErrorCategory.LLM_INVALID_RESPONSE

    def test_file_not_found(self):
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(FileNotFoundError("no such file"))
        assert e.category == ErrorCategory.FILE_ERROR
        assert e.retryable is False

    def test_generic_runtime_error(self):
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(RuntimeError("something unexpected"))
        assert e.category == ErrorCategory.INTERNAL
        assert e.retryable is False

    def test_deepseek_specific_error(self):
        """DeepSeek API 返回的特定错误格式。"""
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(
            RuntimeError("HTTP 429 rate limit exceeded, retry after 30s"),
            step="analyze", question_id=5
        )
        assert e.category == ErrorCategory.LLM_RATE_LIMIT
        assert e.step == "analyze"
        assert e.question_id == 5

    def test_provider_auth_error(self):
        """API key 无效。"""
        from pipeline.errors import PipelineError, ErrorCategory
        e = PipelineError.from_exception(
            RuntimeError("HTTP 403 API key not valid. Please pass a valid API key.")
        )
        assert e.category == ErrorCategory.LLM_AUTH
        assert e.retryable is False
