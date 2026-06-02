"""LLM model policy for explicit fallback paths.

The main exam-review LLM chain is purpose-aware: Qwen text is first for
structured long-form analysis paths that must not truncate, DeepSeek remains in
the text chain for general/report analysis, and Qwen vision handles image
inputs. This module resolves the flash/pro model profile for grounded
generation and explicit model-split paths.
Business modules should still pass a purpose string to llm_call/send_message_gpt
instead of hard-coding provider model ids.
"""
from dataclasses import dataclass
import os


POLICY_ID = os.environ.get("LLM_POLICY_ID", "exam-review-global")
DEFAULT_FLASH_MODEL = os.environ.get("LLM_EXAM_REVIEW_FLASH_MODEL", "")
DEFAULT_PRO_MODEL = os.environ.get("LLM_EXAM_REVIEW_PRO_MODEL", "")
DISCONTINUED_MODELS: dict[str, str] = {}

FLASH_MODEL_ENV = "LLM_EXAM_REVIEW_FLASH_MODEL"
PRO_MODEL_ENV = "LLM_EXAM_REVIEW_PRO_MODEL"

_FLASH_PURPOSES = {
    "question_split",
    "split_questions",
    "metadata_extraction",
    "feature_extraction",
    "competency_analysis",
}

_PRO_PURPOSES = {
    "question_analysis",
    "question_analysis_retry",
    "fine_grained_analysis",
    "missing_evidence_repair",
    "difficulty_review",
    "report_insights",
    "report_teaching_suggestions",
    "final_report",
}


@dataclass(frozen=True)
class ModelProfile:
    purpose: str
    role: str
    model: str
    policy_id: str = POLICY_ID


def _configured_model(env_name: str, default: str) -> str:
    configured = os.environ.get(env_name, "").strip()
    return _validate_model(configured or default)


def _validate_model(model: str) -> str:
    replacement = DISCONTINUED_MODELS.get(model)
    if replacement:
        raise ValueError(
            f"{model} is discontinued; set the model to {replacement} "
            "and use LLM_LOCATION=global."
        )
    return model


def resolve_model_profile(
    purpose: str | None = None,
    model_override: str | None = None,
) -> ModelProfile:
    """Resolve the model profile for one LLM call."""
    normalized = (purpose or "default").strip() or "default"
    if model_override:
        return ModelProfile(
            purpose=normalized,
            role="custom",
            model=_validate_model(model_override),
        )

    if normalized in _FLASH_PURPOSES:
        return ModelProfile(
            purpose=normalized,
            role="flash",
            model=_configured_model(FLASH_MODEL_ENV, DEFAULT_FLASH_MODEL),
        )

    if normalized in _PRO_PURPOSES or normalized == "default":
        return ModelProfile(
            purpose=normalized,
            role="pro",
            model=_configured_model(PRO_MODEL_ENV, DEFAULT_PRO_MODEL),
        )

    return ModelProfile(
        purpose=normalized,
        role="pro",
        model=_configured_model(PRO_MODEL_ENV, DEFAULT_PRO_MODEL),
    )
