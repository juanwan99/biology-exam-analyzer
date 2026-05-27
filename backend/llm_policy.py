"""Exam review model policy.

This module is the single place that knows the Gemini model split for the
exam-review pipeline. Business modules should pass a purpose string to
llm_call/send_message_gpt instead of hard-coding provider model ids.
"""
from dataclasses import dataclass
import os


POLICY_ID = "exam-review-gemini31-global"
DEFAULT_FLASH_MODEL = "publishers/google/models/gemini-3-flash-preview"
DEFAULT_PRO_MODEL = "publishers/google/models/gemini-3.1-pro-preview"
DISCONTINUED_MODELS = {
    "gemini-3-pro-preview": DEFAULT_PRO_MODEL,
    "publishers/google/models/gemini-3-pro-preview": DEFAULT_PRO_MODEL,
}

FLASH_MODEL_ENV = "LLM_EXAM_REVIEW_FLASH_MODEL"
PRO_MODEL_ENV = "LLM_EXAM_REVIEW_PRO_MODEL"
LEGACY_MODEL_ENV = "LLM_NATIVE_MODEL"

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
    """Resolve the model profile for one LLM call.

    Explicit model_override is intentionally kept at the gateway boundary. It
    lets one-off tests or emergency operations choose a model without teaching
    business modules about provider-specific routing.
    """
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
