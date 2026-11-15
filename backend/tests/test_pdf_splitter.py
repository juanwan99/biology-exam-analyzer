"""PDF 规则拆题：大题号 / 小问 / 卷首说明 / 页眉导航（#7）、剥【解析】（#28）。

真卷回归：卷子不进仓（仓公开），设 BEA_REAL_DIR 指向放卷子的目录才跑（ECS /home/ops/bea-work7，见 REAL_PAPERS）：
  BEA_REAL_DIR=/w python -m pytest -q tests/test_pdf_splitter.py
"""
import base64
import io
import os
import re

import pytest
from PIL import Image

from pdf_splitter import PDFQuestionSplitter
from score_rules import paper_score

NAV = ["2026届高三考试 生 物", "No.", "题 号", "1 2 3 4", "5 6 7 8", "温馨提示：点击No.按钮关闭"]


def _pages(*bodies):
    return [{"page_num": i, "lines": NAV + list(lines), "boxes": [(0, 0, 1, 1)] * (len(NAV) + len(lines))}
            for i, lines in enumerate(bodies)]


def _split(pages):
    splitter = PDFQuestionSplitter()
    return [splitter._question_to_dict(q) for q in splitter._split_questions(pages)]


PAPER = _pages(
    ["使用说明", "1. 本课件建议用 Office 2016 打开", "2. 本课件仅限课堂讲评使用"],
    ["一、选择题：本题共2小题，每小题2分，共4分。", "1.下列叙述错误的是", "A.甲", "B.乙"],
    ["2.下列说法正确的是", "A.丙", "【解析】A正确。"],
    ["二、非选择题：本题包括1小题，共12分。", "3.（12分）回答下列问题：", "（1）该酶分布在叶绿体基质", "(2)其作用是促进细胞伸长"],
    ["（3）据图分析，限制因素是光照强度", "【解析】（3）略"],
)


def test_sub_questions_stay_in_parent():
    qs = _split(PAPER)
    assert [q["id"] for q in qs] == [1, 2, 3]
    assert "（1）该酶" in qs[2]["content"] and "(2)其作用" in qs[2]["content"]
    assert "（3）据图" in qs[2]["content"]
    assert qs[2]["page_indices"] == [3, 4]


def test_preamble_before_first_section_dropped():
    qs = _split(PAPER)
    assert all("课件" not in q["content"] for q in qs)
    assert qs[0]["_section_header"].startswith("一、选择题")


def test_numbered_list_without_sections_kept():
    qs = _split(_pages(["1.甲题", "A.选项"], ["2.乙题"], ["3.丙题"], ["4.丁题"]))
    assert [q["id"] for q in qs] == [1, 2, 3, 4]


def test_running_lines_not_in_content():
    qs = _split(PAPER)
    for q in qs:
        for line in NAV:
            assert line not in q["content"].split("\n")
    # 页数少于 RUNNING_MIN_PAGES 不判页眉，行照留
    short = _split(_pages(["1.甲题", "1 2 3 4"], ["2.乙题", "1 2 3 4"]))
    assert "1 2 3 4" in short[0]["content"]


def test_answer_blocks_moved_out_of_content():
    qs = _split(PAPER)
    assert all("【解析】" not in q["content"] for q in qs)
    assert "answer" not in qs[0]
    assert qs[1]["answer"] == "【解析】A正确。"
    assert qs[2]["answer"] == "【解析】（3）略" and "（3）据图分析" in qs[2]["content"]


def test_scores_from_section_and_head():
    qs = _split(PAPER)
    assert [paper_score(q) for q in qs] == [(2.0, "section"), (2.0, "section"), (12.0, "paper")]



def test_answer_version_paper():
    # 解析版：全角「1．」注意事项、「单选题」分节、【分析】里的「1、2、」列表、行首小数都不拆成题（#43）
    qs = _split(_pages(
        ["1．答题前，先将自己的姓名、准考证号填写在答题卡上。", "2．考试结束后，请将试卷和答题卡一并上交。",
         "一、单选题（每小题6分，共12分）", "1. 生态足迹由0.3212hm2下降至", "0.2958hm2，下列叙述正确的是（ ）"],
        ["【答案】D", "【分析】1、脂肪：由三分子脂肪酸构成", "2、磷脂：构成膜的重要成分", "3、固醇：维持新陈代谢"],
        ["2. 下列叙述错误的是（ ）", "【答案】C"],
    ))
    assert [q["id"] for q in qs] == [1, 2]
    assert [paper_score(q)[0] for q in qs] == [6.0, 6.0]
    assert "2、磷脂：构成膜的重要成分" in qs[0]["answer"] and "0.2958hm2" in qs[0]["content"]


def test_section_intro_line_joins_header():
    qs = _split(_pages(["第一部分", "本部分共2题，每题2分，共4分。在每题列出的四个选项中，选出最符合题目要求的一项。",
                        "1.甲题", "2.乙题"]))
    assert [q["id"] for q in qs] == [1, 2]
    assert [paper_score(q)[0] for q in qs] == [2.0, 2.0]
    assert "本部分" not in qs[0]["content"]

REAL_DIR = os.environ.get("BEA_REAL_DIR")
# 卷子 → 每题卷面分值（题号从 1 连续；None = 卷面没标该题分值），期望值对卷面分节说明 / 题头人工核
REAL_PAPERS = {
    "mock2026.pdf": [2.0] * 12 + [4.0] * 4 + [12.0] * 5,  # 12×2 + 4×4 + 5 大题（#7）
    "gk-jiangsu.pdf": [2.0] * 15 + [3.0] * 4 + [None] * 5,  # 单选 + 多选 + 5 大题未标分（#42）
    "gk-hubei.pdf": [2.0] * 18 + [None] * 4,  # 18 单选 + 4 大题未标分（#42；浙江卷待 #45 题组材料修好再进）
}


@pytest.mark.skipif(not REAL_DIR, reason="真卷不进仓；设 BEA_REAL_DIR 才跑")
@pytest.mark.parametrize("name, scores", REAL_PAPERS.items())
def test_real_pdf_regression(name, scores):
    path = os.path.join(REAL_DIR, name)
    splitter = PDFQuestionSplitter()
    pages = splitter._extract_text(path)
    questions = splitter._split_questions(pages)
    qs = [splitter._question_to_dict(q) for q in questions]
    assert [q["id"] for q in qs] == list(range(1, len(scores) + 1))
    assert [paper_score(q)[0] for q in qs] == scores
    assert splitter._calculate_confidence(questions, pages) >= 0.7  # 低于 0.7 才告警
    assert all("选选项项" not in q["content"] for q in qs)
    # #28：解析版每题的【答案】【解析】都剥进 answer，题干不剩；页面图上答案行涂白
    assert all(not re.search("【(答案|解析)】", q["content"]) and q["answer"].startswith("【") for q in qs)
    masks = splitter._answer_boxes(questions, pages)
    page_num = min(masks)
    dpi = 50
    img = Image.open(io.BytesIO(base64.b64decode(
        splitter._convert_to_images(path, dpi, masks)[page_num])))
    x0, top, x1, bottom = (v * dpi / 72 for v in masks[page_num][0])
    region = img.convert("L").crop((int(x0), int(top), int(x1), int(bottom)))
    assert region.getextrema()[0] > 240
