"""Word 拆题题号 / 分节规则（#40）。

真卷回归（#35）：卷子不进仓（仓公开），设 BEA_WORD_BIO06 指向 06_生物_试题.docx 才跑：
  BEA_WORD_BIO06=/w/word06.docx python -m pytest -q tests/test_word_splitter.py
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
    qs = _split(tmp_path, ["一、选择题", "1.甲题", "2.乙题", "第Ⅱ卷 非选择题", "1.丙题", "(1)小问"])
    assert [q["id"] for q in qs] == [1, 2, 1]
    assert "(1)小问" in qs[2]["content"]


BIO06 = os.environ.get("BEA_WORD_BIO06")


@pytest.mark.skipif(not BIO06, reason="真卷不进仓；设 BEA_WORD_BIO06 才跑")
def test_bio06_word_regression():
    qs = split_word_with_visual(BIO06, "biology")["questions"]
    assert [q["id"] for q in qs] == list(range(1, 22))
    assert [paper_score(q)[0] for q in qs] == [2.0] * 12 + [4.0] * 4 + [12.0, 12.0, 12.0, 10.0, 14.0]
