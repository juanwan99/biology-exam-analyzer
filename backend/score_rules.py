# -*- coding: utf-8 -*-
"""卷面分值规则：题号后标的「（N分）」、分节「每小题 N 分」「共 K 小题，共 N 分」。

卷面写明的分值以卷面为准，不交给 LLM 猜；卷面没写才用 LLM 的结果。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_NUM = r"(\d+(?:\.\d+)?)"
# 题干开头（第一个小问之前）的整题分值：「17.（12分）」「17．(本题满分12分)」
_HEAD_SCORE = re.compile(r"[（(]\s*(?:本小?题)?\s*(?:满分)?\s*(?:共)?\s*" + _NUM + r"\s*分\s*[）)]")
_FIRST_SUBQ = re.compile(r"[（(]\s*[1１一]\s*[）)]|①")
_PER_QUESTION = re.compile(r"每小?题\s*" + _NUM + r"\s*分")
_SECTION_COUNT = re.compile(r"共\s*(\d+)\s*(?:小|道)?题")
_SECTION_TOTAL = re.compile(r"共\s*" + _NUM + r"\s*分")

SOURCE_PAPER = "paper"            # 题号后卷面标注
SOURCE_SECTION = "section"        # 分节「每小题 N 分」
SOURCE_SECTION_AVG = "section_average"  # 分节「共 K 小题，共 N 分」均分（LLM 无有效分值时兜底）
SOURCE_MODEL = "model"            # LLM 推断
SOURCE_SECTION_SCALED = "section_scaled"  # LLM 推断后按分节小计等比缩放

# 猜的分合计与小计差太多（多半是拆题 / 分节识别错）就不缩放，只标 inferred
_SCALE_MIN, _SCALE_MAX = 0.5, 2.0


def _head(content: str) -> str:
    text = content or ""
    m = _FIRST_SUBQ.search(text)
    head = text[: m.start()] if m else text
    return head[:300]


def paper_score(question: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    """卷面写明的本题满分；取不到返回 (None, None)。"""
    head_match = _HEAD_SCORE.search(_head(question.get("content") or ""))
    if head_match:
        score = float(head_match.group(1))
        if score > 0:
            return score, SOURCE_PAPER
    per = _PER_QUESTION.search(question.get("_section_header") or "")
    if per:
        score = float(per.group(1))
        if score > 0:
            return score, SOURCE_SECTION
    return None, None


def section_count_total(header: str) -> Tuple[Optional[int], Optional[float]]:
    header = header or ""
    count_match = _SECTION_COUNT.search(header)
    totals = [float(v) for v in _SECTION_TOTAL.findall(header)]
    count = int(count_match.group(1)) if count_match else None
    # 「每小题2分，共24分」：取最后一个「共 N 分」作分节总分
    total = totals[-1] if totals else None
    return count, total


def section_average_score(question: Dict[str, Any]) -> Optional[float]:
    count, total = section_count_total(question.get("_section_header") or "")
    if count and total and count > 0:
        return round(total / count, 2)
    return None


def apportion(values: List[float], target: float) -> Optional[List[float]]:
    """把 values 等比缩放到合计 = target，按最大余数取整（target 是整数取整分，是 .5 取半分）。"""
    unit = 1.0 if float(target).is_integer() else 0.5 if float(target * 2).is_integer() else None
    total = sum(values)
    if unit is None or total <= 0:
        return None
    raw = [v * target / total for v in values]
    base = [int(r // unit) for r in raw]
    left = int(round(target / unit)) - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] / unit - base[i]), i))
    for i in order[:left]:
        base[i] += 1
    scaled = [b * unit for b in base]
    if any(v <= 0 for v in scaled):
        return None
    return scaled


def scale_section_scores(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """分节写了「共 N 分」而题分合计对不上时，把本节 LLM 猜的分等比缩放到合计 = N。

    卷面标的分（paper / section）不动，只缩放 model / section_average 来源的题。
    拆题数与分节题数不符、或缩放比例超出 0.5–2 倍时不缩放（交给 mark_section_mismatch 标 inferred）。
    就地改 total_score / score_source，返回改动列表 [{id, old, new, section}]。
    """
    sections: Dict[str, List[Dict[str, Any]]] = {}
    for q in questions:
        header = q.get("_section_header")
        if header:
            sections.setdefault(header, []).append(q)
    changes = []
    for header, qs in sections.items():
        count, total = section_count_total(header)
        if not total or (count and count != len(qs)):
            continue
        guessed = [q for q in qs if q.get("score_source") in (SOURCE_MODEL, SOURCE_SECTION_AVG)
                   and q.get("score_status") == "valid"]
        if not guessed:
            continue
        fixed = sum(float(q.get("total_score") or 0) for q in qs if q not in guessed)
        target = total - fixed
        current = [float(q.get("total_score") or 0) for q in guessed]
        if abs(sum(current) - target) < 1e-6 or sum(current) <= 0 or target <= 0:
            continue
        ratio = target / sum(current)
        if not (_SCALE_MIN <= ratio <= _SCALE_MAX):
            continue
        scaled = apportion(current, target)
        if not scaled:
            continue
        for q, old, new in zip(guessed, current, scaled):
            if abs(old - new) < 1e-6:
                continue
            q["total_score"] = int(new) if float(new).is_integer() else new
            q["score_source"] = SOURCE_SECTION_SCALED
            changes.append({"id": q.get("id"), "old": old, "new": new, "section": header[:40]})
    return changes


def mark_section_mismatch(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """分节写了「共 N 分」而本节题分合计不符时，把本节 LLM 推断分值的题标 score_status=inferred。

    只改 score_status（展示 / 对账用），不动分值本身，不影响已完成的难度评估。返回告警列表。
    """
    sections: Dict[str, List[Dict[str, Any]]] = {}
    for q in questions:
        header = q.get("_section_header")
        if header:
            sections.setdefault(header, []).append(q)
    warnings = []
    for header, qs in sections.items():
        count, total = section_count_total(header)
        if not total:
            continue
        if count and count != len(qs):
            continue  # 拆题数与分节题数不符，合计没有意义
        actual = sum(float(q.get("total_score") or 0) for q in qs)
        if abs(actual - total) < 1e-6:
            continue
        guessed = [q for q in qs if q.get("score_source") in (SOURCE_MODEL, SOURCE_SECTION_AVG)]
        for q in guessed:
            if q.get("score_status") == "valid":
                q["score_status"] = "inferred"
        warnings.append({
            "section": header[:40],
            "expected_total": total,
            "actual_total": round(actual, 2),
            "inferred_question_ids": [q.get("id") for q in guessed],
        })
    return warnings
