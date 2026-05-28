from services.evidence_audit import summarize_evidence_usage


def _call(call_id, purpose, *, provider="llm_client", metadata=None):
    return {
        "call_id": call_id,
        "purpose": purpose,
        "provider": provider,
        "metadata": metadata or {},
    }


def test_summarize_evidence_usage_reports_missing_ranked_questions():
    questions = [
        {
            "id": 1,
            "_metadata_envelope": {
                "llm_calls": [
                    _call(
                        "q1-analysis",
                        "question_analysis",
                        metadata={
                            "evidence_context": {
                                "provider": "discovery_engine",
                                "operation": "rank",
                                "question_id": 1,
                                "ranked_count": 5,
                                "candidate_count": 20,
                            }
                        },
                    )
                ]
            },
        },
        {
            "id": 2,
            "_metadata_envelope": {
                "llm_calls": [_call("q2-analysis", "question_analysis")]
            },
        },
    ]

    usage = summarize_evidence_usage(questions)

    assert usage["question_count"] == 2
    assert usage["discovery_rank_count"] == 1
    assert usage["discovery_rank_question_ids"] == [1]
    assert usage["missing_rank_question_ids"] == [2]
    assert usage["evidence_gap_questions"] == [2]


def test_summarize_evidence_usage_counts_agent_search_answer_in_context():
    questions = [{
        "id": 21,
        "_metadata_envelope": {
            "llm_calls": [
                _call(
                    "q21-analysis",
                    "question_analysis",
                    metadata={
                        "evidence_context": {
                            "provider": "discovery_engine",
                            "operation": "rank",
                            "question_id": 21,
                            "ranked_count": 5,
                            "candidate_count": 20,
                            "agent_search_answer": {
                                "provider": "discovery_engine",
                                "operation": "answer_query",
                                "status": "ok",
                                "citation_count": 3,
                            },
                        }
                    },
                )
            ]
        },
    }]

    usage = summarize_evidence_usage(questions)

    assert usage["discovery_rank_count"] == 1
    assert usage["agent_search_answer_count"] == 1
    assert usage["agent_search_answer_question_ids"] == [21]
    assert usage["missing_rank_question_ids"] == []


def test_summarize_evidence_usage_counts_grounding_and_unsupported_generation():
    questions = [{
        "id": 1,
        "_metadata_envelope": {
            "llm_calls": [
                _call(
                    "q1-unsupported",
                    "question_analysis",
                    provider="discovery_engine",
                    metadata={"operation": "generate_grounded_content"},
                )
            ]
        },
    }]
    insights = {
        "_grounding_status": "needs_review",
        "_grounding_checks": [{
            "section": "summary",
            "status": "needs_review",
            "support_score": 0.42,
            "threshold": 0.6,
            "metadata": {"provider": "discovery_engine", "operation": "check_grounding"},
        }],
        "_llm_calls": [
            _call("report", "report_overall"),
            _call("ground", "report_grounding_check"),
        ],
    }

    usage = summarize_evidence_usage(questions, insights)

    assert usage["unsupported_generation_count"] == 1
    assert usage["unsupported_generation_call_ids"] == ["q1-unsupported"]
    assert usage["discovery_grounding_check_count"] == 1
    assert usage["grounding_needs_review"] == [{
        "section": "summary",
        "support_score": 0.42,
        "threshold": 0.6,
    }]
