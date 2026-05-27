from services.review_channel import (
    channel_evidence_ranking_enabled,
    channel_grounding_enabled,
    channel_requires_grounded_generation,
    channel_uses_agent_search,
    channel_uses_evidence,
    normalize_review_channel,
)


def test_app_builder_alias_is_evidence_enhanced_not_generation_only():
    assert normalize_review_channel("app_builder") == "evidence"
    assert normalize_review_channel("1000-grant") == "evidence"
    assert channel_uses_evidence("app_builder") is True
    assert channel_evidence_ranking_enabled("app_builder") is True
    assert channel_grounding_enabled("app_builder") is True
    assert channel_requires_grounded_generation("app_builder") is False


def test_explicit_grounded_generation_channel_is_separate_fail_closed_mode():
    assert normalize_review_channel("grounded-generation") == "grounded_generation"
    assert channel_requires_grounded_generation("grounded_generation") is True
    assert channel_uses_evidence("grounded_generation") is False


def test_agent_search_channel_is_evidence_channel_with_distinct_mode():
    assert normalize_review_channel("agent-search") == "agent_search"
    assert channel_uses_agent_search("agent_search") is True
    assert channel_uses_evidence("agent_search") is True
