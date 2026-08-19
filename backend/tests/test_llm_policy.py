import os
from unittest.mock import patch

import pytest


def test_qwen_key_enables_vision_provider_only_by_default(monkeypatch):
    from llm_config import get_providers

    monkeypatch.setenv("QWEN_API_KEY", "test-qwen")
    monkeypatch.setenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.delenv("QWEN_TEXT_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("QWEN_VISION_MODEL", "qwen3-vl-plus")

    text_providers = get_providers(purpose="question_analysis", requires_images=False)
    assert text_providers == []

    providers = get_providers(purpose="question_analysis", requires_images=True)
    assert [provider["name"] for provider in providers] == ["qwen_vision"]
    assert providers[0]["model"] == "qwen3-vl-plus"
    assert providers[0]["key_env"] == "QWEN_API_KEY"
    assert providers[0]["response_format"] == "json_object"


def test_general_text_requests_prefer_deepseek():
    from llm_config import get_providers

    env = {
        "DEEPSEEK_API_KEY": "test-deepseek",
        "QWEN_API_KEY": "test-qwen",
    }
    with patch.dict(os.environ, env, clear=True):
        providers = get_providers(purpose="difficulty_review")
        assert [provider["name"] for provider in providers] == ["deepseek"]
        assert providers[0]["model_policy"] == "exam-review-deepseek-primary"




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
    }
    with patch.dict(os.environ, env, clear=True):
        providers = get_providers(purpose="question_analysis")
        assert [provider["name"] for provider in providers] == ["deepseek", "qwen_text"]
        assert providers[0]["model_policy"] == "exam-review-deepseek-primary"
        assert providers[1]["model_policy"] == "exam-review-qwen-text"




