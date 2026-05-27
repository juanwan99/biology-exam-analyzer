import os
import tempfile
from unittest.mock import patch

import pytest


def test_default_policy_uses_gemini_31_pro(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.delenv("LLM_EXAM_REVIEW_PRO_MODEL", raising=False)
    profile = resolve_model_profile()

    assert profile.role == "pro"
    assert profile.model == "publishers/google/models/gemini-3.1-pro-preview"


def test_fast_purpose_uses_gemini_3_flash(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.delenv("LLM_EXAM_REVIEW_FLASH_MODEL", raising=False)
    profile = resolve_model_profile("question_split")

    assert profile.role == "flash"
    assert profile.model == "publishers/google/models/gemini-3-flash-preview"


def test_critical_purpose_uses_gemini_31_pro(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.delenv("LLM_EXAM_REVIEW_PRO_MODEL", raising=False)
    profile = resolve_model_profile("difficulty_review")

    assert profile.role == "pro"
    assert profile.model == "publishers/google/models/gemini-3.1-pro-preview"


def test_explicit_model_override_keeps_vendor_choice_at_gateway_boundary():
    from llm_policy import resolve_model_profile

    profile = resolve_model_profile(
        "question_split",
        model_override="publishers/google/models/custom-model",
    )

    assert profile.role == "custom"
    assert profile.model == "publishers/google/models/custom-model"


def test_gemini_3_preview_env_values_are_not_downgraded(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.setenv(
        "LLM_EXAM_REVIEW_FLASH_MODEL",
        "publishers/google/models/gemini-3-flash-preview",
    )
    monkeypatch.setenv(
        "LLM_EXAM_REVIEW_PRO_MODEL",
        "publishers/google/models/gemini-3.1-pro-preview",
    )

    assert (
        resolve_model_profile("question_split").model
        == "publishers/google/models/gemini-3-flash-preview"
    )
    assert (
        resolve_model_profile("difficulty_review").model
        == "publishers/google/models/gemini-3.1-pro-preview"
    )


def test_discontinued_gemini_3_pro_preview_fails_closed(monkeypatch):
    from llm_policy import resolve_model_profile

    monkeypatch.setenv(
        "LLM_EXAM_REVIEW_PRO_MODEL",
        "publishers/google/models/gemini-3-pro-preview",
    )

    with pytest.raises(ValueError, match="discontinued"):
        resolve_model_profile("difficulty_review")


def test_get_providers_applies_policy_to_native_provider():
    from llm_config import get_providers

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b"{}")
        sa_path = f.name
    env = {
        "LLM_SA_CREDENTIALS": sa_path,
        "LLM_SDK_MODULE": "google.genai",
        "LLM_CLOUD_MODE": "true",
        "DEEPSEEK_API_KEY": "",
    }
    try:
        with patch.dict(os.environ, env, clear=True):
            providers = get_providers(purpose="question_split")
            native = [p for p in providers if p.get("api_format") == "native_sdk"]
            assert len(native) == 1
            assert native[0]["model"] == "publishers/google/models/gemini-3-flash-preview"
            assert native[0]["model_role"] == "flash"
            assert native[0]["model_policy"] == "exam-review-gemini31-global"
    finally:
        os.unlink(sa_path)


def test_legacy_native_model_env_does_not_override_policy_by_default():
    from llm_config import get_providers

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(b"{}")
        sa_path = f.name
    env = {
        "LLM_SA_CREDENTIALS": sa_path,
        "LLM_SDK_MODULE": "google.genai",
        "LLM_CLOUD_MODE": "true",
        "LLM_NATIVE_MODEL": "publishers/google/models/gemini-2.5-pro",
        "DEEPSEEK_API_KEY": "",
    }
    try:
        with patch.dict(os.environ, env, clear=True):
            providers = get_providers(purpose="difficulty_review")
            native = [p for p in providers if p.get("api_format") == "native_sdk"]
            assert len(native) == 1
            assert native[0]["model"] == "publishers/google/models/gemini-3.1-pro-preview"
            assert native[0]["model_role"] == "pro"
    finally:
        os.unlink(sa_path)
