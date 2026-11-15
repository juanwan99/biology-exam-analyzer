"""Word / PDF 拆题共用的大题号判定（#43）：卷首注意事项、分节标题、这一行的题号接不接受。

解析版卷子每题后面跟着【答案】【分析】【详解】，里面常有「1、脂肪…」「2、磷脂…」这种列表，
编号还可能恰好等于下一题号；所以本题进了答案块之后，只接受比当前题号大、且分隔符和本题同类的题号
（理综抽出的生物卷 32 题后直接是 37 题，不能只认 +1）。
「1.2026年」「0.85」这种分隔符后紧跟数字的，同样只认下一题号（#40）。分节标题之后本节第一题不限。
"""

import re
from typing import Optional, Tuple

from answer_blocks import ANSWER_MARK

# 题号前可带题型标签：菁优网「（多选）16．（3分）…」
_ARABIC = re.compile(r"^(?:[（(【]\s*(?:单选|多选|不定项)题?\s*[）)】]\s*)?(\d+)([.、．])\s*")
_CHINESE = re.compile(r"^([一二三四五六七八九十]+)[.、．]\s*")
_DIGIT_AFTER_SEP = re.compile(r"^\d+[.、．]\d")
_CHINESE_NUM = {c: i for i, c in enumerate("一二三四五六七八九", 1)}

# 卷首「1．答题前…准考证号」「3．考试结束后…」这类编号项不是题（只看前 50 字）
_NOTICE = [
    re.compile(r"^\s*\d{1,2}[.、．]\s*(答卷前|答题前|请按|选择题用|考试结束|注意事项|填涂|核对)"),
    re.compile(r"^\s*\d{1,2}[.、．].*(答题卡|试题卷|试卷|草稿纸|准考证|条形码|铅笔|签字笔)"),
]

_SECTION = [
    re.compile(r"^[一二三四五六七八九十]+[.、．]\s*.*(选择题|单选题|多选题|非选择题|实验题|综合题|填空题|简答题|选考题)"),
    re.compile(r"^[一二三四五六七八九十]+[.、．]\s*本题共\d+小题"),
    re.compile(r"^第[一二三四五六七八九十]+部分"),
    re.compile(r"^[（(][一二三四五六七八九十]+[）)]\s*.*(必考题|选考题|选择题|非选择题)"),
]

# 分节说明另起一段 / 一行，如「(本题共12小题,每小题2分,共24分。)」「本部分共15题，每题2分」
_SECTION_INTRO = re.compile(r"共\s*\d+\s*小?题|每小题|共\s*\d+\s*分")


def is_section_intro(text: str) -> bool:
    return bool(_SECTION_INTRO.search(text))


def is_notice(text: str) -> bool:
    return any(p.search(text[:50]) for p in _NOTICE)


def section_header(text: str) -> Optional[str]:
    """分节标题（「一、选择题：本题共12小题…」「第二部分」）→ 原文；不是返回 None。"""
    head = text[:100]
    return text.strip() if any(p.search(head) for p in _SECTION) else None


def _chinese_to_num(chinese: str) -> int:
    if chinese.startswith("十"):
        return 10 + _CHINESE_NUM.get(chinese[1:], 0)
    if len(chinese) == 2 and chinese[1] == "十":
        return _CHINESE_NUM.get(chinese[0], 0) * 10
    return _CHINESE_NUM.get(chinese, 0)


def question_number(text: str) -> Tuple[Optional[int], Optional[str]]:
    """行首大题号 → (题号, 分隔符类：'.' / '、' / 'chinese')；注意事项编号项和非题号返回 (None, None)。"""
    if is_notice(text):
        return None, None
    m = _ARABIC.match(text)
    if m:
        return int(m.group(1)), "、" if m.group(2) == "、" else "."
    m = _CHINESE.match(text)
    if m:
        return _chinese_to_num(m.group(1)), "chinese"
    return None, None


class Numbering:
    """按原文顺序逐行喂：section() 记分节标题，accept(text) 判这一行是不是新大题的开头。"""

    def __init__(self) -> None:
        self.current: Optional[int] = None
        self.sep: Optional[str] = None
        self.in_intro = False  # 分节标题之后、本节第一题之前
        self.in_answer = False  # 本题已出现【答案】【解析】等块

    def section(self) -> None:
        self.in_intro = True

    def accept(self, text: str) -> Optional[int]:
        qid, sep = question_number(text)
        if qid is None:
            if ANSWER_MARK.match(text):
                self.in_answer = True
            return None
        if self.current is not None and not self.in_intro:
            if self.in_answer and (qid <= self.current or sep != self.sep):
                return None
            if _DIGIT_AFTER_SEP.match(text) and qid != self.current + 1:
                return None
        self.current, self.sep, self.in_intro, self.in_answer = qid, sep, False, False
        return qid
