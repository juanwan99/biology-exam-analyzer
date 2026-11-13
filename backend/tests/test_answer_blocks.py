"""【答案】【解析】块从题干剥离（#28）。"""
import visual_word_splitter
from answer_blocks import split_answer


def test_interleaved_blocks_end_at_next_sub_question():
    text = "\n".join([
        "17.（12分）回答下列问题：",
        "（1）该酶分布在 叶绿体基质（1分）",
        "【解析】（1）暗反应在叶绿体基质，",
        "生长素促进细胞伸长。",
        "（2）实验方案如下：",
        "①设置 9（1分） 个处理组",
        "【解析】（2）①自变量为Mg和Zn",
        "②提出两种假设：",
        "Ⅰ.实验步骤：",
        "【解析】Ⅰ.由于假设二",
        "Ⅱ.实验结果与结论：",
        "【答案】略",
    ])
    stem, answer = split_answer(text)
    assert stem.split("\n") == [
        "17.（12分）回答下列问题：", "（1）该酶分布在 叶绿体基质（1分）", "（2）实验方案如下：",
        "①设置 9（1分） 个处理组", "②提出两种假设：", "Ⅰ.实验步骤：", "Ⅱ.实验结果与结论：",
    ]
    assert answer.split("\n") == [
        "【解析】（1）暗反应在叶绿体基质，", "生长素促进细胞伸长。", "【解析】（2）①自变量为Mg和Zn",
        "【解析】Ⅰ.由于假设二", "【答案】略",
    ]


def test_end_block_keeps_its_own_per_question_explanations():
    stem, answer = split_answer("\n".join([
        "18.回答下列问题：", "（1）甲是什么", "（2）乙是什么",
        "【答案】（1）甲", "（2）乙", "【详解】（1）因为甲", "（2）因为乙", "A、错误",
    ]))
    assert stem == "18.回答下列问题：\n（1）甲是什么\n（2）乙是什么"
    assert answer.endswith("（2）因为乙\nA、错误")


def test_level_unseen_in_stem_does_not_end_block():
    stem, answer = split_answer("\n".join([
        "5.下列叙述正确的是", "A.甲 B.乙 C.丙 D.丁", "【详解】", "①甲错误", "②乙正确", "故选B。",
    ]))
    assert stem == "5.下列叙述正确的是\nA.甲 B.乙 C.丙 D.丁"
    assert answer.endswith("②乙正确\n故选B。")


def test_no_block_leaves_text_untouched():
    text = "3.据图分析，下列答案正确的是\nA.甲\n分析：乙"
    assert split_answer(text) == (text, "")


def test_word_entry_strips_and_keeps_answer(monkeypatch):
    monkeypatch.setattr(visual_word_splitter, "_split_word", lambda path, subject: {"questions": [
        {"id": 1, "content": "1.下列叙述错误的是\nA.甲\n【答案】A\n【解析】甲错"},
        {"id": 2, "content": "2.乙题\nA.乙"},
    ]})
    qs = visual_word_splitter.split_word_with_visual("x.docx")["questions"]
    assert qs[0]["content"] == "1.下列叙述错误的是\nA.甲" and qs[0]["answer"] == "【答案】A\n【解析】甲错"
    assert qs[1]["content"] == "2.乙题\nA.乙" and "answer" not in qs[1]
