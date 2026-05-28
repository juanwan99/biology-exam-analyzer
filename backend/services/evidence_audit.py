"""Audit contract for evidence-enhanced exam review runs."""
from __future__ import annotations

from typing import Any


def summarize_evidence_usage(
    questions: list[dict[str, Any]] | None,
    insights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize model, Ranking, Grounding and Agent Search usage.

    This is intentionally data-only. Enforcement belongs to AnalysisService so
    the same contract can be reused by API responses, tests and smoke checks.
    """

    questions = questions or []
    insights = insights or {}
    question_calls: list[dict[str, Any]] = []
    rank_contexts: list[dict[str, Any]] = []
    agent_search_contexts: list[dict[str, Any]] = []
    question_ids = [_question_id(question) for question in questions if _question_id(question) is not None]

    for question in questions:
        envelope = question.get("_metadata_envelope") if isinstance(question, dict) else {}
        if not isinstance(envelope, dict):
            continue
        for call in envelope.get("llm_calls") or []:
            if not isinstance(call, dict):
                continue
            question_calls.append(call)
            context = _metadata(call).get("evidence_context")
            if _is_rank_context(context):
                rank_contexts.append({
                    "question_id": context.get("question_id") or call.get("question_id") or _question_id(question),
                    "ranked_count": context.get("ranked_count"),
                    "candidate_count": context.get("candidate_count"),
                    "record_ids": context.get("record_ids") or [],
                })
                agent_answer = context.get("agent_search_answer")
                if _is_agent_answer_context(agent_answer):
                    agent_search_contexts.append({
                        "question_id": context.get("question_id") or call.get("question_id") or _question_id(question),
                        "citation_count": agent_answer.get("citation_count"),
                        "status": agent_answer.get("status"),
                    })

    report_calls = [
        call for call in (insights.get("_llm_calls") or [])
        if isinstance(call, dict)
    ]
    grounding_checks = [
        check for check in (insights.get("_grounding_checks") or [])
        if isinstance(check, dict)
    ]
    discovery_grounding_checks = [
        check for check in grounding_checks
        if _is_discovery_grounding_check(check)
    ]

    all_model_calls = question_calls + report_calls
    unsupported_generation_calls = [
        call for call in all_model_calls
        if call.get("provider") == "discovery_engine"
        and _metadata(call).get("operation") == "generate_grounded_content"
    ]
    agent_search_answer_calls = [
        call for call in all_model_calls
        if call.get("provider") == "discovery_engine"
        and _metadata(call).get("operation") == "answer_query"
    ]
    direct_model_calls = [
        call for call in all_model_calls
        if call.get("purpose") != "report_grounding_check"
        and call not in unsupported_generation_calls
        and call not in agent_search_answer_calls
    ]
    ranked_question_ids = [
        item.get("question_id") for item in rank_contexts
        if item.get("question_id") not in (None, "")
    ]
    missing_rank_question_ids = [
        question_id for question_id in question_ids
        if question_id not in set(ranked_question_ids)
    ]
    evidence_gap_questions = sorted(set(missing_rank_question_ids))
    grounding_needs_review = [
        {
            "section": check.get("section"),
            "support_score": check.get("support_score"),
            "threshold": check.get("threshold"),
        }
        for check in grounding_checks
        if check.get("status") not in (None, "ok")
    ]

    rank_count = len(rank_contexts)
    grounding_check_count = len(discovery_grounding_checks)

    return {
        "question_count": len(questions),
        "question_ids": question_ids,
        "question_llm_call_count": len(question_calls),
        "report_llm_call_count": len(report_calls),
        "model_call_count": len(all_model_calls),
        "direct_model_call_count": len(direct_model_calls),
        "evidence_generation_count": len(unsupported_generation_calls),
        "discovery_generation_count": len(unsupported_generation_calls),
        "unsupported_generation_count": len(unsupported_generation_calls),
        "unsupported_generation_call_ids": [
            call.get("call_id") for call in unsupported_generation_calls if call.get("call_id")
        ],
        "agent_search_answer_count": len(agent_search_answer_calls) + len(agent_search_contexts),
        "agent_search_answer_question_ids": [
            item.get("question_id") for item in agent_search_contexts
            if item.get("question_id") not in (None, "")
        ],
        "evidence_rank_count": rank_count,
        "discovery_rank_count": rank_count,
        "discovery_rank_question_ids": ranked_question_ids,
        "evidence_rank_question_ids": ranked_question_ids,
        "missing_rank_question_ids": missing_rank_question_ids,
        "evidence_gap_questions": evidence_gap_questions,
        "evidence_grounding_check_count": grounding_check_count,
        "discovery_grounding_check_count": grounding_check_count,
        "grounding_check_count": len(grounding_checks),
        "grounding_status": insights.get("_grounding_status"),
        "grounding_needs_review": grounding_needs_review,
    }


def _question_id(question: dict[str, Any]) -> Any:
    if not isinstance(question, dict):
        return None
    return question.get("id") or question.get("question_id")


def _metadata(call_or_check: dict[str, Any]) -> dict[str, Any]:
    metadata = call_or_check.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _is_rank_context(context: Any) -> bool:
    return (
        isinstance(context, dict)
        and context.get("provider") == "discovery_engine"
        and context.get("operation") == "rank"
    )


def _is_agent_answer_context(context: Any) -> bool:
    return (
        isinstance(context, dict)
        and context.get("provider") == "discovery_engine"
        and context.get("operation") == "answer_query"
        and context.get("status") == "ok"
        and int(context.get("citation_count") or 0) > 0
    )


def _is_discovery_grounding_check(check: dict[str, Any]) -> bool:
    metadata = _metadata(check)
    return (
        metadata.get("provider") == "discovery_engine"
        and metadata.get("operation") == "check_grounding"
    ) or metadata.get("discovery_operation") == "check_grounding"


__all__ = ["summarize_evidence_usage"]
