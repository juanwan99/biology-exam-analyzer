import pytest

from question_analyzer import QuestionAnalyzer


def _unit(label, share):
    return {
        "seu_id": label,
        "label": label,
        "score_share": share,
        "allocation_source": "explicit",
        "allocation_confidence": 0.9,
        "knowledge_links": [{"knowledge_point": label, "share": 1.0}],
        "bloom_level": 3,
        "competency_weights": {
            "生命观念": 0.25,
            "科学思维": 0.25,
            "科学探究": 0.25,
            "社会责任": 0.25,
        },
        "difficulty_estimate": 5.0,
        "reasoning_brief": label,
    }


def test_near_miss_score_share_sum_is_normalized_with_metadata():
    data = {
        "total_score": 12,
        "scoring_units": [
            _unit("u1", 0.333),
            _unit("u2", 0.333),
            _unit("u3", 0.418),
        ],
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    assert "score_share_sum_normalized" in notes
    assert sum(unit["score_share"] for unit in normalized["scoring_units"]) == pytest.approx(1.0)
    assert normalized["_normalization_metadata"]["score_share_sum_normalized_from"] == 1.084
    assert normalized["_normalization_metadata"]["score_share_sum_normalized_to"] == 1.0


def test_large_score_share_sum_mismatch_is_not_normalized():
    data = {
        "total_score": 12,
        "scoring_units": [
            _unit("u1", 0.4),
            _unit("u2", 0.4),
        ],
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    assert "score_share_sum_normalized" not in notes
    assert "_normalization_metadata" not in normalized
    assert sum(unit["score_share"] for unit in normalized["scoring_units"]) == 0.8
