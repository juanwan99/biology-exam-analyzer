"""卷面分值规则：题号后「（N分）」优先，其次分节「每小题 N 分」；分节合计不符标 inferred。"""
from copy import deepcopy

import pytest
import score_rules

from score_rules import (
    SOURCE_MODEL, SOURCE_PAPER, SOURCE_SECTION, SOURCE_SECTION_AVG, SOURCE_SECTION_SCALED,
    exceeds_section_total, mark_section_mismatch, paper_score, section_average_score, section_count_total,
)

CHOICE = "一、选择题：本题共12小题，每小题2分，共24分。在每小题给出的四个选项中，只有一项是符合题目要求的。"
BIG = "三、非选择题：本题共5小题，共60分。"


def test_head_score_after_number():
    assert paper_score({"content": "17.（12分）对硝基苯酚可用于……", "_section_header": BIG}) == (12.0, SOURCE_PAPER)
    assert paper_score({"content": "5. (10分) 为探究光照强度……", "_section_header": BIG}) == (10.0, SOURCE_PAPER)
    assert paper_score({"content": "20．（本题满分14分）气味分子……", "_section_header": BIG}) == (14.0, SOURCE_PAPER)


def test_sub_question_scores_are_not_whole_question_score():
    content = "18. 未成熟豌豆豆荚……回答下列问题：\n（1）由图可知……（2分）\n（2）……（4分）"
    assert paper_score({"content": content, "_section_header": BIG}) == (None, None)


def test_section_per_question_score():
    assert paper_score({"content": "3. 下列叙述错误的是（　　）", "_section_header": CHOICE}) == (2.0, SOURCE_SECTION)


def test_section_count_total_and_average():
    assert section_count_total(CHOICE) == (12, 24.0)
    assert section_count_total("三、非选择题：本题共5小题．共55分。") == (5, 55.0)
    assert section_average_score({"_section_header": "三、非选择题：本题共5小题．共55分。"}) == 11.0
    assert section_average_score({"_section_header": "三、非选择题"}) is None
    big = {"_section_header": "二、非选择题（本题共 2 小题，共 22 分）"}
    assert exceeds_section_total(big, 22) and not exceeds_section_total(big, 12)
    assert not exceeds_section_total({"_section_header": "三、选做题：本题共1小题，共15分。"}, 15)
    assert not exceeds_section_total({"_section_header": "三、非选择题"}, 22)


def test_mark_section_mismatch_only_touches_model_scores():
    qs = [{"id": i, "_section_header": BIG, "total_score": 12.0, "score_status": "valid",
           "score_source": SOURCE_MODEL} for i in range(17, 21)]
    qs.append({"id": 21, "_section_header": BIG, "total_score": 10.0, "score_status": "valid",
               "score_source": SOURCE_PAPER})
    warnings = mark_section_mismatch(qs)
    assert warnings and warnings[0]["expected_total"] == 60.0 and warnings[0]["actual_total"] == 58.0
    assert [q["score_status"] for q in qs] == ["inferred"] * 4 + ["valid"]


def test_mark_section_mismatch_noop_when_totals_match():
    qs = [{"id": i, "_section_header": BIG, "total_score": 12.0, "score_status": "valid",
           "score_source": SOURCE_MODEL} for i in range(17, 22)]
    assert mark_section_mismatch(qs) == []
    assert all(q["score_status"] == "valid" for q in qs)


def _scored_question(score, source=SOURCE_MODEL, question_type="short_answer", status="valid"):
    return {"total_score": score, "score_source": source, "question_type": question_type, "score_status": status}


@pytest.mark.parametrize(("full_mark", "allocated"), [(60, [14, 14, 18]), (54, [12, 12, 16])])
def test_full_mark_apportions_only_eligible_questions(full_mark, allocated):
    fixed = [
        _scored_question(2, question_type="single_choice"),
        _scored_question(2, question_type="multiple_choice"),
        _scored_question(10, SOURCE_PAPER),
    ]
    before = deepcopy(fixed)
    questions = fixed + [_scored_question(score) for score in (8, 8, 10)]

    assert score_rules.apportion_full_mark(questions, full_mark) == {
        "full_mark": full_mark, "adjusted": 3, "fixed_total": 14,
    }
    assert questions[:3] == before
    assert questions[3:] == [_scored_question(score, "full_mark_scaled") for score in allocated]
    assert all(type(q["total_score"]) is int for q in questions[3:])
    assert sum(q["total_score"] for q in questions) == full_mark


@pytest.mark.parametrize(("questions", "full_mark", "fixed_total"), [
    ([_scored_question(10, SOURCE_PAPER), _scored_question(8)], 9, 10),
    ([_scored_question(10, SOURCE_PAPER), _scored_question(8)], 10, 10),
    ([_scored_question(10, SOURCE_PAPER), _scored_question(5, SOURCE_SECTION)], 20, 15),
    ([_scored_question(10, SOURCE_PAPER), _scored_question(8)], 10.25, 10),
    ([_scored_question(1), _scored_question(1)], 1, 0),
    ([_scored_question(8), _scored_question(10)], 18, 0),
    ([], 100, 0),
])
def test_full_mark_leaves_scores_intact_when_no_allocation_changes_them(questions, full_mark, fixed_total):
    before = deepcopy(questions)
    assert score_rules.apportion_full_mark(questions, full_mark) == {
        "full_mark": full_mark, "adjusted": 0, "fixed_total": fixed_total,
    }
    assert questions == before


def test_full_mark_supports_half_points_and_preserves_failed_and_scaled_questions():
    fixed = [
        _scored_question(9, SOURCE_SECTION_SCALED),
        _scored_question(8, status="inferred"),
        {**_scored_question(6), "analysis_failed": True},
        {**_scored_question(7), "error": "分析失败"},
        _scored_question(None, status="missing"),
    ]
    before = deepcopy(fixed)
    questions = fixed + [_scored_question(8, SOURCE_SECTION_AVG), _scored_question(8)]

    assert score_rules.apportion_full_mark(questions, 99.5) == {
        "full_mark": 99.5, "adjusted": 2, "fixed_total": 30,
    }
    assert questions[:5] == before
    assert questions[5:] == [_scored_question(35, "full_mark_scaled"), _scored_question(34.5, "full_mark_scaled")]
    assert sum(q["total_score"] or 0 for q in questions) == 99.5


def test_full_mark_changes_source_only_for_changed_scores():
    questions = [_scored_question(2), _scored_question(3)]

    assert score_rules.apportion_full_mark(questions, 6)["adjusted"] == 1
    assert questions == [_scored_question(2), _scored_question(4, "full_mark_scaled")]


def test_mark_section_mismatch_includes_full_mark_scaled_questions():
    questions = [
        {**_scored_question(12, SOURCE_PAPER), "id": 1, "_section_header": BIG},
        *[{**_scored_question(12), "id": i, "_section_header": BIG} for i in range(2, 6)],
    ]

    assert score_rules.apportion_full_mark(questions, 100)["adjusted"] == 4
    assert mark_section_mismatch(questions) == [{
        "section": BIG,
        "expected_total": 60.0,
        "actual_total": 100.0,
        "inferred_question_ids": [2, 3, 4, 5],
    }]
    assert [q["score_status"] for q in questions] == ["valid"] + ["inferred"] * 4
