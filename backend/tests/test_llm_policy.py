import os
from unittest.mock import patch

import pytest


def test_qwen_key_alone_gives_qwen_text_for_text_and_qwen_vision_for_images(monkeypatch):
    from llm_config import get_providers

    monkeypatch.setenv("QWEN_API_KEY", "test-qwen")
    monkeypatch.setenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.delenv("QWEN_TEXT_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("QWEN_VISION_MODEL", "qwen3-vl-plus")

    text_providers = get_providers(purpose="question_analysis", requires_images=False)
    assert [provider["name"] for provider in text_providers] == ["qwen_text"]
    assert text_providers[0]["model"] == "qwen-plus"

    providers = get_providers(purpose="question_analysis", requires_images=True)
    assert [provider["name"] for provider in providers] == ["qwen_vision"]
    assert providers[0]["model"] == "qwen3-vl-plus"
    assert providers[0]["key_env"] == "QWEN_API_KEY"
    assert providers[0]["response_format"] == "json_object"


@pytest.mark.parametrize(
    "purpose",
    [
        "big_question_feature_extraction",
        "competency_analysis",
        "difficulty_review",
        "feature_extraction",
        "feature_difficulty",
        "missing_evidence_repair",
        "question_analysis",
        "question_analysis_retry",
        "report_insights",
        "report_teaching_suggestions",
    ],
)
def test_text_purposes_use_deepseek_then_qwen_text(purpose):
    from llm_config import get_providers

    env = {
        "DEEPSEEK_API_KEY": "test-deepseek",
        "QWEN_API_KEY": "test-qwen",
    }
    with patch.dict(os.environ, env, clear=True):
        providers = get_providers(purpose=purpose)
        assert [provider["name"] for provider in providers] == ["deepseek", "qwen_text"]
        assert providers[0]["model_policy"] == "exam-review-deepseek-primary"
        assert providers[1]["model_policy"] == "exam-review-qwen-text"
