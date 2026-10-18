"""卷面分值规则：题号后「（N分）」优先，其次分节「每小题 N 分」；分节合计不符标 inferred。"""
from score_rules import (
    SOURCE_MODEL, SOURCE_PAPER, SOURCE_SECTION, mark_section_mismatch, paper_score,
    section_average_score, section_count_total,
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
