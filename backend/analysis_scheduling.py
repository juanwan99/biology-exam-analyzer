# -*- coding: utf-8 -*-
"""整卷并发分析的调度：长题先开跑。

大题一道要串行好几轮 LLM（分析 → 大题提取 → 特征），是整卷耗时的关键路径；
按原题序排队时大题排在最后，要等前面的选择题腾出并发位才开始。
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List


def analysis_cost(question: Dict[str, Any]) -> int:
    media = question.get("_media_for_ai") or []
    return len(question.get("content") or "") + 500 * len(media)


async def gather_longest_first(
    questions: List[Dict[str, Any]],
    run: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> List[Any]:
    """按 analysis_cost 从大到小启动 run(q)，结果仍按原题序返回。"""
    order = sorted(range(len(questions)), key=lambda i: -analysis_cost(questions[i]))
    futures: List[Any] = [None] * len(questions)
    for i in order:
        futures[i] = asyncio.ensure_future(run(questions[i]))
    return list(await asyncio.gather(*futures))
