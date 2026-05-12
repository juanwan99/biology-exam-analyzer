"""Pipeline error classification and recovery support."""
from enum import Enum
from typing import Optional


class ErrorCategory(str, Enum):
    """错误分类 — 决定前端展示和重试策略。"""
    LLM_TIMEOUT = "llm_timeout"
    LLM_RATE_LIMIT = "llm_rate_limit"
    LLM_AUTH = "llm_auth"
    LLM_INVALID_RESPONSE = "llm_invalid_response"
    PARSE_ERROR = "parse_error"
    FILE_ERROR = "file_error"
    INTERNAL = "internal"


class PipelineError(Exception):
    """带分类的 pipeline 错误。"""

    def __init__(self, message: str, category: ErrorCategory,
                 step: str = "", question_id: int = 0,
                 retryable: bool = False, original: Exception = None):
        super().__init__(message)
        self.category = category
        self.step = step
        self.question_id = question_id
        self.retryable = retryable
        self.original = original

    def to_dict(self) -> dict:
        return {
            "error": str(self),
            "category": self.category.value,
            "step": self.step,
            "question_id": self.question_id,
            "retryable": self.retryable,
        }

    @classmethod
    def from_exception(cls, e: Exception, step: str = "",
                        question_id: int = 0) -> "PipelineError":
        msg = str(e)
        etype = type(e).__name__
        if "timeout" in msg.lower() or "Timeout" in etype:
            return cls(msg, ErrorCategory.LLM_TIMEOUT, step, question_id, retryable=True, original=e)
        if "429" in msg or "rate" in msg.lower():
            return cls(msg, ErrorCategory.LLM_RATE_LIMIT, step, question_id, retryable=True, original=e)
        if "401" in msg or "403" in msg or "auth" in msg.lower():
            return cls(msg, ErrorCategory.LLM_AUTH, step, question_id, retryable=False, original=e)
        if "json" in msg.lower() or "parse" in msg.lower() or "decode" in msg.lower() or "JSONDecode" in etype:
            return cls(msg, ErrorCategory.LLM_INVALID_RESPONSE, step, question_id, retryable=True, original=e)
        if "file" in msg.lower() or "FileNotFound" in type(e).__name__:
            return cls(msg, ErrorCategory.FILE_ERROR, step, question_id, retryable=False, original=e)
        return cls(msg, ErrorCategory.INTERNAL, step, question_id, retryable=False, original=e)


class StepCheckpoint:
    """Step 级别的 checkpoint — 支持部分失败恢复。

    内存实现，不持久化到数据库（当前规模不需要）。
    """

    def __init__(self):
        self._completed: dict[str, dict] = {}

    def mark_done(self, step: str, item_key: str, result: dict):
        key = f"{step}:{item_key}"
        self._completed[key] = result

    def is_done(self, step: str, item_key: str) -> bool:
        return f"{step}:{item_key}" in self._completed

    def get_result(self, step: str, item_key: str) -> dict | None:
        return self._completed.get(f"{step}:{item_key}")

    def get_pending(self, step: str, all_keys: list[str]) -> list[str]:
        return [k for k in all_keys if not self.is_done(step, k)]

    @property
    def completed_count(self) -> int:
        return len(self._completed)

    def clear(self):
        self._completed.clear()
