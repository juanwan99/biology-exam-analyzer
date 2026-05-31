import os
import tempfile
from unittest.mock import patch

import pytest


def test_default_policy_uses_pro(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.setenv("LLM_EXAM_REVIEW_PRO_MODEL", "pro-model-preview")
    profile = resolve_model_profile()

    assert profile.role == "pro"
    assert profile.model == "pro-model-preview"


def test_fast_purpose_uses_flash(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.setenv("LLM_EXAM_REVIEW_FLASH_MODEL", "flash-model-preview")
    profile = resolve_model_profile("question_split")

    assert profile.role == "flash"
    assert profile.model == "flash-model-preview"


def test_critical_purpose_uses_pro(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.setenv("LLM_EXAM_REVIEW_PRO_MODEL", "pro-model-preview")
    profile = resolve_model_profile("difficulty_review")

    assert profile.role == "pro"
    assert profile.model == "pro-model-preview"


def test_explicit_model_override_keeps_vendor_choice_at_gateway_boundary():
    from llm_policy import resolve_model_profile

    profile = resolve_model_profile(
        "question_split",
        model_override="custom-model",
    )

    assert profile.role == "custom"
    assert profile.model == "custom-model"


def test_preview_env_values_are_not_downgraded(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.setenv(
        "LLM_EXAM_REVIEW_FLASH_MODEL",
        "flash-model-preview",
    )
    monkeypatch.setenv(
        "LLM_EXAM_REVIEW_PRO_MODEL",
        "pro-model-preview",
    )

    assert (
        resolve_model_profile("question_split").model
        == "flash-model-preview"
    )
    assert (
        resolve_model_profile("difficulty_review").model
        == "pro-model-preview"
    )


def test_discontinued_model_fails_closed(monkeypatch):
    import llm_policy
    from llm_policy import resolve_model_profile

    monkeypatch.setattr(llm_policy, "DISCONTINUED_MODELS", {"discontinued-model": "pro-model-preview"})
    monkeypatch.setenv(
        "LLM_EXAM_REVIEW_PRO_MODEL",
        "discontinued-model",
    )

    with pytest.raises(ValueError, match="discontinued"):
        resolve_model_profile("difficulty_review")




def test_qwen_key_enables_vision_provider_only_by_default(monkeypatch):
    from llm_config import get_providers

    monkeypatch.setenv("QWEN_API_KEY", "test-qwen")
    monkeypatch.setenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.delenv("QWEN_TEXT_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_SA_CREDENTIALS", raising=False)

    text_providers = get_providers(purpose="question_analysis", requires_images=False)
    assert text_providers == []

    providers = get_providers(purpose="question_analysis", requires_images=True)
    assert [provider["name"] for provider in providers] == ["qwen_vision"]
    assert providers[0]["model"] == "qwen3-vl-plus"
    assert providers[0]["key_env"] == "QWEN_API_KEY"
    assert providers[0]["response_format"] == "json_object"


def test_qwen_vision_does_not_validate_unused_native_model(monkeypatch):
    from llm_config import get_providers

    monkeypatch.setenv("QWEN_API_KEY", "test-qwen")
    monkeypatch.setenv("LLM_VISION_PROVIDER", "qwen")
    monkeypatch.setenv(
        "LLM_EXAM_REVIEW_PRO_MODEL",
        "discontinued-model",
    )
    monkeypatch.delenv("LLM_SA_CREDENTIALS", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    providers = get_providers(purpose="question_analysis", requires_images=True)

    assert [provider["name"] for provider in providers] == ["qwen_vision"]


def test_image_requests_auto_prefer_configured_qwen_over_native_provider():
    from llm_config import get_providers

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b"{}")
        sa_path = f.name
    env = {
        "QWEN_API_KEY": "test-qwen",
        "LLM_SA_CREDENTIALS": sa_path,
        "LLM_SDK_MODULE": "test.sdk",
        "LLM_CLOUD_MODE": "true",
        "DEEPSEEK_API_KEY": "",
        "LLM_EXAM_REVIEW_FLASH_MODEL": "flash-model-preview",
        "LLM_EXAM_REVIEW_PRO_MODEL": "pro-model-preview",
    }
    try:
        with patch.dict(os.environ, env, clear=True):
            providers = get_providers(purpose="question_split", requires_images=True)
            assert [provider["name"] for provider in providers] == ["qwen_vision"]
    finally:
        os.unlink(sa_path)


def test_general_text_requests_prefer_deepseek_then_qwen_without_native_by_default():
    from llm_config import get_providers

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b"{}")
        sa_path = f.name
    env = {
        "DEEPSEEK_API_KEY": "test-deepseek",
        "QWEN_API_KEY": "test-qwen",
        "LLM_SA_CREDENTIALS": sa_path,
        "LLM_SDK_MODULE": "test.sdk",
        "LLM_CLOUD_MODE": "true",
        "LLM_ENABLE_NATIVE_TEXT_FALLBACK": "false",
        "LLM_EXAM_REVIEW_FLASH_MODEL": "flash-model-preview",
        "LLM_EXAM_REVIEW_PRO_MODEL": "pro-model-preview",
    }
    try:
        with patch.dict(os.environ, env, clear=True):
            providers = get_providers(purpose="difficulty_review")
            assert [provider["name"] for provider in providers] == ["deepseek"]
            assert all(provider.get("api_format") != "native_sdk" for provider in providers)
            assert providers[0]["model_policy"] == "exam-review-deepseek-primary"
    finally:
        os.unlink(sa_path)




@pytest.mark.parametrize(
    "purpose",
    [
        "big_question_feature_extraction",
        "competency_analysis",
        "feature_extraction",
        "missing_evidence_repair",
        "question_analysis",
        "question_analysis_retry",
        "report_teaching_suggestions",
    ],
)
def test_review_text_purposes_use_deepseek_without_qwen_text_by_default(purpose):
    from llm_config import get_providers

    env = {
        "DEEPSEEK_API_KEY": "test-deepseek",
        "QWEN_API_KEY": "test-qwen",
        "LLM_ENABLE_NATIVE_TEXT_FALLBACK": "false",
        "LLM_EXAM_REVIEW_FLASH_MODEL": "flash-model-preview",
        "LLM_EXAM_REVIEW_PRO_MODEL": "pro-model-preview",
    }
    with patch.dict(os.environ, env, clear=True):
        providers = get_providers(purpose=purpose)
        assert [provider["name"] for provider in providers] == ["deepseek"]
        assert providers[0]["model_policy"] == "exam-review-deepseek-primary"


def test_qwen_text_fallback_requires_explicit_opt_in():
    from llm_config import get_providers

    env = {
        "DEEPSEEK_API_KEY": "test-deepseek",
        "QWEN_API_KEY": "test-qwen",
        "LLM_ENABLE_QWEN_TEXT_FALLBACK": "true",
        "LLM_ENABLE_NATIVE_TEXT_FALLBACK": "false",
        "LLM_EXAM_REVIEW_FLASH_MODEL": "flash-model-preview",
        "LLM_EXAM_REVIEW_PRO_MODEL": "pro-model-preview",
    }
    with patch.dict(os.environ, env, clear=True):
        providers = get_providers(purpose="question_analysis")
        assert [provider["name"] for provider in providers] == ["deepseek", "qwen_text"]
        assert providers[0]["model_policy"] == "exam-review-deepseek-primary"
        assert providers[1]["model_policy"] == "exam-review-qwen-text"




