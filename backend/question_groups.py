"""Word / PDF 拆题共用的题组判定（#45）：「阅读下列材料，完成下面小题。」+ 材料，是后面几道题共用的题干。

引导语结束上一题（不再并进上一题的题干或【答案】块），引导语和材料存进组内题的 `_group_material`，分析时接在题干后
（题干在前：下游重试按长度截断，材料长了也不挤掉本题题干，ap-review #47）。
组到哪道题为止：解析版卷子题组的答案合在组末一题后（「【答案】10. A    11. D」），所以组内连到第一道带答案的题；
卷子没有答案块就只给组内第一题，不猜组长。
"""

import re
from typing import Dict, List, Optional

# 只认「小题」或题号范围：「回答下列问题」是大题内部的设问，不是题组（ap-review #47）
_GROUP_INTRO = re.compile(r"^(?:阅读|根据)(?:下列|下面|以下)?的?(?:材料|资料)[，,、]?\s*(?:完成|回答)[^。]{0,15}?"
                          r"(?:小题|\d+\s*[~～\-—至到、和]\s*\d+\s*小?题)")


def is_group_intro(text: str) -> bool:
    return bool(_GROUP_INTRO.match(text.strip()))


def group_spans(starts: List[bool], answered: List[bool], sections: List[Optional[str]]) -> Dict[int, List[int]]:
    """按题序：哪道题开了题组（材料在它前面）、哪道题带答案块、所在分节 → {组首题下标: 组内题下标}。"""
    answer_version = any(answered)
    spans = {}
    for i, start in enumerate(starts):
        if not start:
            continue
        j = i
        if answer_version:
            while (not answered[j] and j + 1 < len(starts) and not starts[j + 1]
                   and sections[j + 1] == sections[i]):
                j += 1
            if not answered[j]:  # 一直没等到组末答案，组长不可信
                j = i
        spans[i] = list(range(i, j + 1))
    return spans


def with_group_material(question: Dict) -> str:
    """送 AI 的题干：本题题干 + 题组材料。"""
    content = question.get("content", "")
    material = question.get("_group_material")
    return f"{content}\n【题组材料】{material}" if material else content
