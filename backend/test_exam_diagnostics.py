from exam_diagnostics import _analyze_difficulty_spread


def test_difficulty_spread_ignores_fail_closed_none_difficulty():
    questions = [
        {"id": 1, "difficulty": {"final_difficulty": 4.0}},
        {
            "id": 2,
            "difficulty": {
                "final_difficulty": None,
                "analysis_failed": True,
                "failure_reason": "insufficient_stem",
            },
        },
        {"id": 3, "difficulty": {"final_difficulty": 8.0}},
        {"id": 4, "difficulty": {"final_difficulty": 6.0}},
    ]

    result = _analyze_difficulty_spread(questions, {})

    assert result["difficulty_mean"] == 6.0
    assert result["difficulty_range"] == 4.0
    assert result["unavailable_questions"] == [2]
