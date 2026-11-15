"""Word 拆题题号 / 分节规则（#40、#43）、题组材料（#45）。

真卷回归（#35、#42）：卷子不进仓（仓公开），设 BEA_REAL_DIR 指向放卷子的目录才跑（ECS /home/ops/bea-work7，见 REAL_PAPERS）：
  BEA_REAL_DIR=/w python -m pytest -q tests/test_word_splitter.py
"""
import os

import pytest
from docx import Document

from score_rules import paper_score
from visual_word_splitter import split_word_with_visual


def _split(tmp_path, lines):
    doc = Document()
    for line in lines:
        if isinstance(line, list):
            table = doc.add_table(rows=1, cols=len(line))
            for cell, value in zip(table.rows[0].cells, line):
                cell.text = value
        else:
            doc.add_paragraph(line)
    path = tmp_path / "paper.docx"
    doc.save(path)
    return split_word_with_visual(str(path), "biology")["questions"]


PAPER = [
    "2026年9月 高三生物试题",
    "一、单项选择题",
    "(本题共2小题,每小题2分,共4分。)",
    "1.2026年两会提出健康饮食建议。以下叙述正确的是",
    "A.甲",
    "2.下列叙述正确的是",
    "A.乙",
    "二、非选择题",
    "(共1小题,共12分)",
    "3.(12分)某河道修复工程结果见表1",
    "0.85",
    "1.2×103",
    "25.6",
    ["样区", "多样性指数"],
    "(1)根据表1推测样区 ________ 。",
    "(2)计算群落总同化量。",
    "4.2025年某地调查结果如下",
]


def test_sub_questions_and_table_decimals_stay_in_parent(tmp_path):
    qs = _split(tmp_path, PAPER)
    assert [q["id"] for q in qs] == [1, 2, 3, 4]
    assert qs[0]["content"].startswith("1.2026年") and qs[3]["content"].startswith("4.2025年")
    assert all(v in qs[2]["content"] for v in ("0.85", "1.2×103", "25.6"))
    assert "(1)根据表1" in qs[2]["content"] and "(2)计算" in qs[2]["content"]


def test_section_intro_paragraph_joins_header(tmp_path):
    qs = _split(tmp_path, PAPER)
    assert qs[0]["_section_header"] == "一、单项选择题(本题共2小题,每小题2分,共4分。)"
    assert "共12分" not in qs[1]["content"]
    assert [paper_score(q)[0] for q in qs[:3]] == [2.0, 2.0, 12.0]


def test_numbering_may_restart_without_section_header(tmp_path):
    qs = _split(tmp_path, ["一、选择题", "1.甲题", "2.乙题", "第Ⅱ卷 非选择题", "乙题续文", "1.丙题", "(1)小问"])
    assert [q["id"] for q in qs] == [1, 2, 1]
    assert "(1)小问" in qs[2]["content"]
    # 分节标题后不像分节说明的文字照旧归上一题，不并进标题（ap-review #41）
    assert "乙题续文" in qs[1]["content"] and "乙题续文" not in qs[2]["_section_header"]



def test_answer_version_paper(tmp_path):
    # 解析版：全角「1．」注意事项、「单选题」分节、【分析】里的「1、2、」列表都不拆成题（#43）
    qs = _split(tmp_path, [
        "注意事项：", "1．答题前，先将自己的姓名、准考证号填写在答题卡上。", "2．考试结束后，请将试卷和答题卡一并上交。",
        "一、单选题（每小题6分，共12分）",
        "1. 下列叙述正确的是（    ）", "A. 甲", "【答案】C", "【解析】", "【分析】1、植物激素是植物体内产生的",
        "2、植物激素包括生长素等", "【详解】A、赤霉素促进种子萌发",
        "2. 下列叙述错误的是（    ）", "【答案】D",
    ])
    assert [q["id"] for q in qs] == [1, 2]
    assert [paper_score(q)[0] for q in qs] == [6.0, 6.0]
    assert "2、植物激素包括生长素等" in qs[0]["answer"] and "答题卡" not in qs[0]["content"]

REAL_DIR = os.environ.get("BEA_REAL_DIR")
# 卷子 → (每题卷面分值, 是不是解析版)；题号从 1 连续，None = 卷面没标该题分值，期望值对卷面人工核
REAL_PAPERS = {
    "word06.docx": ([2.0] * 12 + [4.0] * 4 + [12.0, 12.0, 12.0, 10.0, 14.0], False),  # 12×2 + 4×4 + 5 大题（#35）
    "gk-shandong.docx": ([2.0] * 15 + [3.0] * 5 + [9.0, 16.0, 9.0, 9.0, 12.0], True),  # 题头标分，三节（#42）
    "gk-jia.docx": ([6.0] * 6 + [None] * 6, True),  # 理综抽出的生物，大题未标分（#42）
    "gk-zhejiang.docx": ([2.0] * 20 + [None] * 5, True),  # 20 选择含两个题组，大题未标分（#45）
}
# 卷子 → 题组（组内题号）；组内只有组末一题带答案（#45）
REAL_GROUPS = {"gk-zhejiang.docx": [[10, 11], [19, 20]]}


@pytest.mark.skipif(not REAL_DIR, reason="真卷不进仓；设 BEA_REAL_DIR 才跑")
@pytest.mark.parametrize("name, scores, with_answers", [(n, *v) for n, v in REAL_PAPERS.items()])
def test_real_word_regression(name, scores, with_answers):
    qs = split_word_with_visual(os.path.join(REAL_DIR, name), "biology")["questions"]
    assert [q["id"] for q in qs] == list(range(1, len(scores) + 1))
    assert [paper_score(q)[0] for q in qs] == scores
    assert all("【答案】" not in q["content"] and "【解析】" not in q["content"] for q in qs)
    groups = REAL_GROUPS.get(name, [])
    assert [q["id"] for q in qs if q["_group_material"]] == [i for g in groups for i in g]
    assert all("阅读下列材料" not in q["content"] + q.get("answer", "") for q in qs)
    unanswered = {i for g in groups for i in g[:-1]}
    assert all(bool(q.get("answer")) == (with_answers and q["id"] not in unanswered) for q in qs)


def test_group_material_shared_within_group(tmp_path):
    # 题组引导语 + 材料（含表）不归上一题，组内各题共用，连到组末带答案的那题为止（#45）
    qs = _split(tmp_path, [
        "一、选择题（每小题2分，共8分）",
        "1. 甲题（    ）", "【答案】A",
        "阅读下面的材料，完成下面小题。", "柿子醋的酿造工艺流程见下表。", ["加酶榨汁", "酒精发酵"],
        "2. 乙题（    ）", "3. 丙题（    ）", "【答案】2. A    3. D",
        "4. 丁题（    ）", "【答案】B",
    ])
    assert [q["id"] for q in qs] == [1, 2, 3, 4]
    assert "柿子" not in qs[0]["content"] + qs[0]["answer"]
    material = qs[1]["_group_material"]
    assert material.startswith("阅读下面的材料") and "柿子醋" in material and "加酶榨汁" in material
    assert [q["_group_material"] for q in qs] == ["", material, material, ""]
    assert [sum(m["type"] == "table" for m in q["_media_for_ai"]) for q in qs] == [0, 1, 1, 0]
    assert [q["media_integrity"]["expected_table"] for q in qs] == [False, True, True, False]  # 「下表」在材料里
    assert "answer" not in qs[1] and qs[2]["answer"].startswith("【答案】2. A")
    assert [paper_score(q)[0] for q in qs] == [2.0] * 4


def test_group_material_without_answers_goes_to_first_question(tmp_path):
    # 原卷没有答案块，看不出组到哪题为止，只给组内第一题；大题里的「回答下列问题」不是题组；
    # 引导语后到卷末都没有题，材料照旧归最后一题
    qs = _split(tmp_path, ["1. 甲题", "阅读下列材料，回答下列小题。", "材料正文", "2. 乙题", "3. 丙题",
                           "4. 丁题", "阅读下列材料，回答下列问题。", "（1）小问", "阅读材料，完成下面小题。", "卷末材料"])
    assert [q["id"] for q in qs] == [1, 2, 3, 4]
    assert "材料正文" not in qs[0]["content"]
    assert [bool(q["_group_material"]) for q in qs] == [False, True, False, False]
    assert "（1）小问" in qs[3]["content"] and "卷末材料" in qs[3]["content"]
