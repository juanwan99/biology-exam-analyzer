"""Tests for pipeline error classification and checkpoint."""
import pytest
import httpx
from pipeline.errors import PipelineError, ErrorCategory, StepCheckpoint


class TestPipelineError:
    def test_from_timeout(self):
        e = PipelineError.from_exception(
            httpx.ReadTimeout("read timed out"), step="analyze", question_id=3
        )
        assert e.category == ErrorCategory.LLM_TIMEOUT
        assert e.retryable is True
        assert e.question_id == 3

    def test_from_rate_limit(self):
        e = PipelineError.from_exception(
            RuntimeError("HTTP 429 Too Many Requests"), step="analyze"
        )
        assert e.category == ErrorCategory.LLM_RATE_LIMIT
        assert e.retryable is True

    def test_from_auth(self):
        e = PipelineError.from_exception(
            RuntimeError("HTTP 401 Unauthorized"), step="analyze"
        )
        assert e.category == ErrorCategory.LLM_AUTH
        assert e.retryable is False

    def test_from_parse(self):
        e = PipelineError.from_exception(
            ValueError("JSON decode error"), step="analyze"
        )
        assert e.category == ErrorCategory.LLM_INVALID_RESPONSE
        assert e.retryable is True

    def test_from_generic(self):
        e = PipelineError.from_exception(RuntimeError("something broke"))
        assert e.category == ErrorCategory.INTERNAL
        assert e.retryable is False

    def test_to_dict(self):
        e = PipelineError("timeout", ErrorCategory.LLM_TIMEOUT,
                          step="analyze", question_id=5, retryable=True)
        d = e.to_dict()
        assert d["category"] == "llm_timeout"
        assert d["retryable"] is True
        assert d["question_id"] == 5


class TestStepCheckpoint:
    def test_mark_and_check(self):
        cp = StepCheckpoint()
        cp.mark_done("analyze", "q1", {"answer": "A"})
        assert cp.is_done("analyze", "q1")
        assert not cp.is_done("analyze", "q2")

    def test_get_result(self):
        cp = StepCheckpoint()
        cp.mark_done("analyze", "q1", {"answer": "A"})
        assert cp.get_result("analyze", "q1")["answer"] == "A"
        assert cp.get_result("analyze", "q2") is None

    def test_get_pending(self):
        cp = StepCheckpoint()
        cp.mark_done("analyze", "q1", {})
        cp.mark_done("analyze", "q3", {})
        pending = cp.get_pending("analyze", ["q1", "q2", "q3", "q4"])
        assert pending == ["q2", "q4"]

    def test_completed_count(self):
        cp = StepCheckpoint()
        cp.mark_done("a", "1", {})
        cp.mark_done("b", "2", {})
        assert cp.completed_count == 2

    def test_clear(self):
        cp = StepCheckpoint()
        cp.mark_done("a", "1", {})
        cp.clear()
        assert cp.completed_count == 0
