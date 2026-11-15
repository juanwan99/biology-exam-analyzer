"""大题号判定（#43）：卷首注意事项、分节标题、答案块里的编号列表、分隔符后紧跟数字。"""
from question_numbering import Numbering, question_number, section_header


def _accepted(lines, sections=()):
    numbering = Numbering()
    out = []
    for line in lines:
        if line in sections:
            numbering.section()
        elif (qid := numbering.accept(line)) is not None:
            out.append(qid)
    return out


def test_notice_items_with_fullwidth_dot_are_not_questions():
    for line in ("1．答题前，先将自己的姓名、准考证号填写在答题卡上", "4．考试结束后，请将试卷和答题卡一并上交。",
                 "2.回答选择题时，选出每小题答案后，用铅笔把答题卡上对应题目的答案标号涂黑"):
        assert question_number(line) == (None, None)
    assert question_number("1．制醋是我国传统发酵技术") == (1, ".")
    assert question_number("2、下列叙述正确的是") == (2, "、")
    assert question_number("（多选）16．（3分）种皮会限制O2进入种子") == (16, ".")


def test_section_headers():
    assert section_header("一、单选题（每小题6分，共36分）")
    assert section_header("二．多选题：本题共5小题")
    assert section_header("第一部分")
    assert section_header("三、非选择题：本题共5小题，共55分。")
    assert section_header("（二）选考题：共15分。请考生从2道题中任选一题作答")
    assert section_header("一、下列叙述正确的是") is None


def test_numbered_list_in_answer_block_stays_in_question():
    lines = ["1. 大豆是重要粮食作物。下列叙述错误的是", "【答案】D", "【分析】1、脂肪：由三分子脂肪酸构成",
             "2、磷脂：构成膜的重要成分", "3、固醇：维持新陈代谢", "【详解】A、植物脂肪含不饱和脂肪酸",
             "2. 下列关于酶的叙述正确的是", "【分析】1、酶是活细胞产生的", "2、酶具有专一性", "4、离谱编号",
             "3. 回答下列问题"]
    assert _accepted(lines) == [1, 2, 3]


def test_same_separator_questions_still_split_after_answer():
    assert _accepted(["1、甲题", "【答案】A", "2、乙题", "【答案】B", "3、丙题"]) == [1, 2, 3]


def test_numbering_restarts_after_section_even_from_answer_block():
    lines = ["1.甲题", "【答案】A", "一、选择题", "1.乙题", "【解析】1、略", "2.丙题"]
    assert _accepted(lines, sections={"一、选择题"}) == [1, 1, 2]


def test_digit_after_separator_only_next_number():
    assert _accepted(["3. 下列叙述", "0.2958hm2 下降至", "1.2×103", "4.2025年调查"]) == [3, 4]


def test_numbers_may_jump_after_answer_block():
    # 理综抽出的生物卷：32 题后是选考 37、38，中间分节标题认不认得出都不吞题
    lines = ["32. 回答下列问题", "【答案】（1）略", "（二）选考题：共15分", "37. 选修一", "【答案】（1）略", "38. 选修三"]
    assert _accepted(lines, sections={"（二）选考题：共15分"}) == [32, 37, 38]
    assert _accepted([line for line in lines if not line.startswith("（二）")]) == [32, 37, 38]
