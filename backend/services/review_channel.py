"""Review-channel switch for model and evidence-enhanced exam review."""
from __future__ import annotations

import os


APP_BUILDER_ALIASES = {"app_builder", "grant", "1000_grant"}
EVIDENCE_CHANNELS = {"evidence", "evidence_enhanced", "agent_evidence"} | APP_BUILDER_ALIASES
AGENT_SEARCH_CHANNELS = {"agent_search"}
GROUNDED_GENERATION_CHANNELS = {"grounded_generation", "evidence_generation"}
MODEL_CHANNELS = {"model", "llm", "standard"}


def normalize_review_channel(value: str | None = None) -> str | None:
    raw = value if value is not None else os.environ.get("EXAM_REVIEW_CHANNEL")
    if raw is None:
        return None
    channel = str(raw).strip().lower().replace("-", "_")
    if not channel:
        return None
    if channel in EVIDENCE_CHANNELS:
        return "evidence"
    if channel in AGENT_SEARCH_CHANNELS:
        return "agent_search"
    if channel in GROUNDED_GENERATION_CHANNELS:
        return "grounded_generation"
    if channel in MODEL_CHANNELS:
        return "model"
    return channel


def channel_uses_app_builder(value: str | None = None) -> bool:
    """Backward-compatible alias: App Builder now means evidence enhancement."""
    return channel_uses_evidence(value)


def channel_uses_evidence(value: str | None = None) -> bool:
    return normalize_review_channel(value) in {"evidence", "agent_search"}


def channel_uses_agent_search(value: str | None = None) -> bool:
    return normalize_review_channel(value) == "agent_search"


def channel_requires_grounded_generation(value: str | None = None) -> bool:
    return normalize_review_channel(value) == "grounded_generation"


def channel_evidence_ranking_enabled(value: str | None = None) -> bool | None:
    channel = normalize_review_channel(value)
    if channel in {"evidence", "agent_search"}:
        return True
    if channel == "model":
        return False
    return None


def channel_grounding_enabled(value: str | None = None) -> bool | None:
    channel = normalize_review_channel(value)
    if channel in {"evidence", "agent_search"}:
        return True
    if channel == "model":
        return False
    return None
