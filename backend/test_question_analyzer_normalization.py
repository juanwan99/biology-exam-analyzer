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


def test_ultra_compact_du_su_numeric_aliases_are_normalized():
    data = {
        "diagnostic_units": [
            {
                "du_id": "du_1",
                "option_or_trap": "trap_1",
                "misconception": "忽略证据",
                "trap_strength": 0.8,
                "knowledge_boundary": "遗传推理",
                "if_selected_means": "证据链断裂",
            },
            {
                "du_id": "du_2",
                "option_or_trap": "trap_2",
                "misconception": "混淆概念",
                "trap_strength": "中等",
                "knowledge_boundary": "概念边界",
                "if_selected_means": ["概念未分化"],
            },
        ],
        "stimulus_units": [
            {
                "su_id": "su_1",
                "stimulus_type": "text",
                "complexity": "中等",
                "is_core": True,
                "description": "遗传材料",
            }
        ],
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    assert normalized["diagnostic_units"][0]["trap_strength"] == 3
    assert normalized["diagnostic_units"][0]["if_selected_means"] == ["证据链断裂"]
    assert normalized["diagnostic_units"][1]["trap_strength"] == 2
    assert normalized["stimulus_units"][0]["complexity"] == 2
    assert "trap_strength_to_int" in notes
    assert "stimulus_complexity_to_int" in notes
