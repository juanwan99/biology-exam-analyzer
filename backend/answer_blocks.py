"""卷面【答案】【解析】块：分析前从题干剥掉，原文留给报告（#28）。

答案版、课件版卷子每题（或每个小问）后面跟着【答案】【解析】【详解】等块，AI 看到会把难度判低。
块从标记行开始，到题干下一个小问号为止：（n）后接（n+1）、Ⅰ.后接Ⅱ.、①后接②。
块里自己的「（1）…（2）…」逐问详解不算，只有题干里还没出现过的下一个号才结束块；题干没出现过的层级不结束块。
只认行首的方括号标记，题干里的「分析」「答案」字样不动；填在空里的答案（如「叶绿体基质（1分）」）不动。
"""

import re
from typing import List, Tuple

ANSWER_MARK = re.compile(r"^\s*【(?:参考答案|答案|解析|详解|分析|点睛|考点|点评)】")
_PAREN = re.compile(r"^\s*[（(]\s*(\d{1,2})\s*[）)]")
_ROMAN = re.compile(r"^\s*([ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ])\s*[.、．]")
_CIRCLED = re.compile(r"^\s*([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])")
_ROMAN_NUM = {c: i for i, c in enumerate("ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ", 1)}
_CIRCLED_NUM = {c: i for i, c in enumerate("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳", 1)}


def _sub_marker(line: str):
    """行首小问号 → (层级, 序号)；不是小问号返回 None。"""
    m = _PAREN.match(line)
    if m:
        return "paren", int(m.group(1))
    m = _ROMAN.match(line)
    if m:
        return "roman", _ROMAN_NUM[m.group(1)]
    m = _CIRCLED.match(line)
    if m:
        return "circled", _CIRCLED_NUM[m.group(1)]
    return None


def answer_line_flags(lines: List[str]) -> List[bool]:
    """逐行标出哪些属于【答案】【解析】块。"""
    last = {"paren": 0, "roman": 0, "circled": 0}
    in_block = False
    flags = []
    for line in lines:
        if ANSWER_MARK.match(line):
            in_block = True
        elif in_block:
            marker = _sub_marker(line)
            in_block = not (marker and last[marker[0]] and marker[1] == last[marker[0]] + 1)
        if not in_block:
            marker = _sub_marker(line)
            if marker:
                level, n = marker
                last[level] = n
                if level == "paren":
                    last["roman"] = last["circled"] = 0
                elif level == "roman":
                    last["circled"] = 0
        flags.append(in_block)
    return flags


def split_answer(text: str) -> Tuple[str, str]:
    """题目原文 → (题干, 答案解析原文)；没有答案块时答案为空串。"""
    lines = text.split("\n")
    flags = answer_line_flags(lines)
    stem = "\n".join(line for line, f in zip(lines, flags) if not f)
    answer = "\n".join(line for line, f in zip(lines, flags) if f)
    return stem, answer
