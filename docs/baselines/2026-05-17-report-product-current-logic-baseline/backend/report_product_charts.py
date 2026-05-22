"""Static SVG charts for the commercial exam report.

The module produces inline SVG so the HTML report remains self-contained and
PDF-friendly. It follows the existing backend SVG chart pattern instead of
introducing a separate front-end runtime.
"""
from __future__ import annotations

from html import escape
from math import cos, pi, sin
from typing import Any, Dict, Iterable, List


PALETTE = {
    "ink": "#030404",
    "muted": "#666666",
    "line": "#d2d3d1",
    "panel": "#ffffff",
    "risk": "#cc0000",
    "watch": "#777877",
    "positive": "#333333",
    "accent": "#cc0000",
    "teal": "#777877",
    "blue": "#666666",
    "purple": "#a5a4a4",
    "sand": "#f3f0ea",
    "copper": "#cc2027",
    "platinum": "#d2d3d1",
    "sage": "#a5a4a4",
}

FONT_STACK = '"Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "PingFang SC", Arial, sans-serif'

CHART_LABELS = {
    "difficulty-gradient": "难度梯度坡度图",
    "bloom-distribution": "认知层级堆叠条",
    "knowledge-top-points": "知识点 Pareto 排名",
    "competency-distribution": "核心素养雷达图",
    "question-risk-distribution": "题目风险分布图",
    "metadata-quality": "元数据质量图",
    "fine-grained-heatmap": "题目压力因子热力图",
    "seu-competency-matrix": "SEU 知识点素养矩阵",
    "du-trap-map": "DU 误区与陷阱强度图",
    "question-portfolio": "题目组合气泡图",
    "methodology-llm": "LLM 调用结构图",
}


def _e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _num(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def _pct(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("占比", value.get("percentage", value.get("value", 0)))
    if not isinstance(value, (int, float)):
        return 0.0
    return float(value) * 100 if value <= 1 else float(value)


def _status_label(value: Any) -> str:
    return {
        "warning": "告警题",
        "missing": "缺失",
        "high": "高风险",
        "medium": "关注",
        "low": "稳定",
        "question_analysis": "题目结构分析",
        "feature_extraction": "难度质量抽取",
        "big_question_feature_extraction": "大题特征抽取",
        "competency_analysis": "核心素养分析",
        "split_questions": "题目拆分",
    }.get(str(value), str(value).replace("_", " "))


def _truncate(value: Any, max_len: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _svg(chart_id: str, width: int, height: int, body: str) -> str:
    safe_id = "".join(ch if ch.isalnum() else "_" for ch in chart_id)
    label = CHART_LABELS.get(chart_id, chart_id.replace("-", " "))
    desc = f"{label}，用于展示试卷质量报告中的结构化指标。"
    canvas = (
        "<defs>"
        f'<style>text {{ font-family: {FONT_STACK}; }}</style>'
        f'<linearGradient id="{safe_id}_paper" x1="0" x2="1" y1="0" y2="1">'
        '<stop offset="0%" stop-color="#ffffff"/>'
        '<stop offset="100%" stop-color="#f8f8f8"/>'
        "</linearGradient>"
        f'<filter id="{safe_id}_soft_shadow" x="-8%" y="-8%" width="116%" height="116%">'
        '<feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#000000" flood-opacity="0.10"/>'
        "</filter>"
        "</defs>"
        f'<rect x="4" y="4" width="{width - 8}" height="{height - 8}" rx="0" fill="url(#{safe_id}_paper)" '
        f'stroke="{PALETTE["line"]}" filter="url(#{safe_id}_soft_shadow)"/>'
        f'<rect x="20" y="54" width="{width - 40}" height="1" fill="{PALETTE["platinum"]}" opacity=".62"/>'
    )
    return (
        f'<svg class="report-chart chart-{_e(chart_id)}" id="chart-{_e(chart_id)}" data-style="bain-exhibit" '
        f'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-labelledby="{safe_id}_title {safe_id}_desc">'
        f'<title id="{safe_id}_title">{_e(label)}</title>'
        f'<desc id="{safe_id}_desc">{_e(desc)}</desc>'
        f'{canvas}{body}</svg>'
    )


def _title(text: str, width: int) -> str:
    return (
        f'<text x="{width / 2:.1f}" y="32" text-anchor="middle" '
        f'font-size="20" font-weight="850" fill="{PALETTE["ink"]}">{_e(text)}</text>'
    )


def _axis_label(text: str, x: float, y: float, anchor: str = "middle") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-size="14" fill="{PALETTE["muted"]}">{_e(text)}</text>'
    )


def _note(text: str, x: float, y: float, anchor: str = "start") -> str:
    return (
        f'<text data-role="chart-note" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-size="14" fill="{PALETTE["muted"]}">{_e(text)}</text>'
    )


def _callout(text: str, x: float, y: float, anchor: str = "middle") -> str:
    return (
        f'<text data-role="callout" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-size="15" font-weight="850" fill="{PALETTE["accent"]}">{_e(text)}</text>'
    )


def _benchmark_line(x1: float, y1: float, x2: float, y2: float, label: str, label_x: float, label_y: float, anchor: str = "end") -> str:
    return (
        f'<line data-role="benchmark-line" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{PALETTE["accent"]}" stroke-width="1.4" stroke-dasharray="5 4"/>'
        f'{_callout(label, label_x, label_y, anchor)}'
    )


def _baseline(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        f'<line data-role="baseline" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{PALETTE["ink"]}" stroke-width="1.2" opacity=".72"/>'
    )


def _highlight_rect(x: float, y: float, width: float, height: float, opacity: float = 0.06) -> str:
    return (
        f'<rect data-role="highlight" x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'fill="{PALETTE["accent"]}" fill-opacity="{opacity:.3f}"/>'
    )


def _empty_chart(chart_id: str, title: str) -> str:
    body = (
        f'{_title(title, 620)}'
        f'<rect x="24" y="44" width="572" height="120" rx="10" fill="{PALETTE["sand"]}" />'
        f'<text x="310" y="112" text-anchor="middle" font-size="14" fill="{PALETTE["muted"]}">暂无可视化数据</text>'
    )
    return _svg(chart_id, 620, 190, body)


def _bar_color(index: int) -> str:
    colors = [PALETTE["watch"], PALETTE["blue"], PALETTE["purple"], PALETTE["copper"], PALETTE["sage"], PALETTE["accent"]]
    return colors[index % len(colors)]


def render_difficulty_gradient(data: Dict[str, Any]) -> str:
    values = [
        ("前段", data.get("front")),
        ("中段", data.get("middle")),
        ("后段", data.get("back")),
    ]
    points = [(label, _num(value)) for label, value in values if isinstance(value, (int, float))]
    if not points:
        return _empty_chart("difficulty-gradient", "难度梯度坡度图")

    width, height = 720, 340
    left, right, top, bottom = 88, 64, 82, 72
    plot_w, plot_h = width - left - right, height - top - bottom
    max_y = max(10, max(value for _, value in points))
    min_y = 0

    coords = []
    for index, (label, value) in enumerate(points):
        x = left + (plot_w * index / max(1, len(points) - 1))
        y = top + plot_h - ((value - min_y) / (max_y - min_y or 1)) * plot_h
        coords.append((label, value, x, y))

    path = " ".join(("M" if index == 0 else "L") + f"{x:.1f},{y:.1f}" for index, (_, _, x, y) in enumerate(coords))
    avg = data.get("avg_difficulty")
    avg_line = ""
    if isinstance(avg, (int, float)):
        y = top + plot_h - ((_num(avg) - min_y) / (max_y - min_y or 1)) * plot_h
        avg_line = _benchmark_line(left, y, width - right, y, "平均难度 " + f"{avg:.1f}", left + 10, y - 14, "start")

    grid = "".join(
        f'<line x1="{left}" y1="{top + plot_h * i / 4:.1f}" x2="{width - right}" y2="{top + plot_h * i / 4:.1f}" stroke="{PALETTE["line"]}" stroke-width="1"/>'
        for i in range(5)
    )
    risk_band_y = top + plot_h - (6.5 / max_y) * plot_h
    risk_band = (
        _highlight_rect(left, risk_band_y, plot_w, height - bottom - risk_band_y, 0.055)
        + f'{_axis_label("高压区：难度 ≥ 6.5", left + 8, top + 22, "start")}'
    )
    label_parts = []
    for index, (label, value, x, y) in enumerate(coords):
        is_key_point = index == len(coords) - 1
        label_parts.append(_axis_label(label, x, height - 24))
        label_parts.append(
            f'<circle data-role="{"highlight" if is_key_point else "context"}" cx="{x:.1f}" cy="{y:.1f}" r="7" '
            f'fill="{PALETTE["accent"] if is_key_point else PALETTE["platinum"]}" '
            f'stroke="{PALETTE["ink"] if is_key_point else "#ffffff"}" stroke-width="1.5" />'
        )
        label_parts.append(
            f'<text x="{x:.1f}" y="{y - 16:.1f}" text-anchor="middle" font-size="14" font-weight="700" fill="{PALETTE["ink"]}">{value:.1f}</text>'
        )
    labels = "".join(label_parts)
    slope = ""
    if len(coords) >= 2:
        delta = coords[-1][1] - coords[0][1]
        slope = _callout(f"后段较前段 +{delta:.1f}", width - right, top - 18, "end")
    body = (
        _title("难度梯度坡度图", width)
        + grid
        + risk_band
        + avg_line
        + f'<path d="{path}" fill="none" stroke="{PALETTE["accent"]}" stroke-width="3.5" stroke-linecap="round"/>'
        + labels
        + slope
        + _note("口径：按题序切分前/中/后三段；红色只标识关键压力点，灰色保留上下文。", left, height - 8, "start")
    )
    return _svg("difficulty-gradient", width, height, body)


def render_bloom_distribution(data: Dict[str, Any]) -> str:
    items = [(str(key), _pct(value)) for key, value in _dict(data).items() if _pct(value) > 0]
    if not items:
        return _empty_chart("bloom-distribution", "认知层级堆叠条")
    width, height = 720, 260
    x, y, bar_w, bar_h = 70, 104, 580, 40
    total = sum(value for _, value in items) or 1
    cursor = x
    bars = []
    legend = []
    high_order_share = sum(value for index, (_, value) in enumerate(items) if index >= max(0, len(items) - 2))
    for index, (label, value) in enumerate(items):
        seg_w = bar_w * value / total
        is_high_order = index == len(items) - 1
        color = PALETTE["accent"] if is_high_order else [PALETTE["platinum"], PALETTE["watch"], PALETTE["blue"], PALETTE["purple"]][index % 4]
        role = ' data-role="highlight"' if is_high_order else ""
        bars.append(f'<rect{role} x="{cursor:.1f}" y="{y}" width="{seg_w:.1f}" height="{bar_h}" fill="{color}" />')
        if seg_w > 34:
            bars.append(f'<text x="{cursor + seg_w / 2:.1f}" y="{y + 26}" text-anchor="middle" font-size="14" fill="#fff">{value:.0f}%</text>')
        legend.append(
            f'<rect x="{70 + (index % 3) * 190}" y="{172 + (index // 3) * 26}" width="12" height="12" fill="{color}" />'
            f'<text x="{90 + (index % 3) * 190}" y="{183 + (index // 3) * 26}" font-size="14" fill="{PALETTE["ink"]}">{_e(label)} {value:.0f}%</text>'
        )
        cursor += seg_w
    marker_x = x + bar_w * 0.5
    body = (
        _title("认知层级堆叠条", width)
        + _baseline(x, y + bar_h + 12, x + bar_w, y + bar_h + 12)
        + "".join(bars)
        + _benchmark_line(marker_x, y - 12, marker_x, y + bar_h + 16, "50% 阈值", marker_x + 10, y - 22, "start")
        + _callout(f"高阶合计 {high_order_share:.0f}%", x + bar_w, y - 22, "end")
        + "".join(legend)
    )
    body += _note("口径：红色标识最高认知层级，灰阶展示其余层级占比。", 70, height - 16, "start")
    return _svg("bloom-distribution", width, height, body)


def render_knowledge_bars(data: Any) -> str:
    rows = []
    for item in _items(data)[:8]:
        item = _dict(item)
        label = item.get("name", item.get("label", "未命名"))
        value = _num(item.get("weighted_score", item.get("value", item.get("count"))))
        if value > 0:
            rows.append({
                "label": str(label),
                "value": value,
                "question_count": int(_num(item.get("question_count"))),
                "risk_count": int(_num(item.get("risk_count"))),
                "seu_count": int(_num(item.get("seu_count"))),
                "avg_bloom": _num(item.get("avg_bloom")),
            })
    if not rows:
        return _empty_chart("knowledge-top-points", "知识点 Pareto 排名")
    rows = sorted(rows, key=lambda item: (-item["value"], -item["risk_count"], item["label"]))[:8]
    width = 940
    row_h = 44
    height = 140 + row_h * len(rows)
    max_v = max(row["value"] for row in rows) or 1
    body = [_title("知识点 Pareto 排名", width)]
    body.append(_axis_label("分值权重", 190, 68, "start"))
    body.append(_axis_label("题数", 700, 68, "middle"))
    body.append(_axis_label("风险", 760, 68, "middle"))
    body.append(_axis_label("SEU", 820, 68, "middle"))
    body.append(_axis_label("认知", 880, 68, "middle"))
    body.append(_baseline(190, 78, 880, 78))
    top3_total = sum(row["value"] for row in rows[:3])
    for index, row in enumerate(rows):
        y = 104 + index * row_h
        bar_w = 430 * row["value"] / max_v
        is_top = index == 0 or row["risk_count"] > 0
        color = PALETTE["accent"] if is_top else [PALETTE["platinum"], PALETTE["watch"], PALETTE["blue"], PALETTE["purple"]][index % 4]
        body.append(_axis_label(_truncate(row["label"], 16), 170, y + 20, "end"))
        body.append(f'<rect data-role="{"highlight" if is_top else "context"}" x="190" y="{y}" width="{bar_w:.1f}" height="24" rx="4" fill="{color}" />')
        body.append(f'<text x="{202 + min(bar_w, 430):.1f}" y="{y + 18}" font-size="14" fill="{PALETTE["ink"]}">{row["value"]:g}</text>')
        body.append(f'<text x="700" y="{y + 18}" text-anchor="middle" font-size="14" fill="{PALETTE["ink"]}">{row["question_count"]}</text>')
        body.append(f'<text x="760" y="{y + 18}" text-anchor="middle" font-size="14" font-weight="800" fill="{PALETTE["accent"] if row["risk_count"] else PALETTE["muted"]}">{row["risk_count"]}</text>')
        body.append(f'<text x="820" y="{y + 18}" text-anchor="middle" font-size="14" fill="{PALETTE["ink"]}">{row["seu_count"]}</text>')
        body.append(f'<text x="880" y="{y + 18}" text-anchor="middle" font-size="14" fill="{PALETTE["ink"]}">{row["avg_bloom"]:.1f}</text>')
        if index == 2:
            body.append(_benchmark_line(190, y + 34, 880, y + 34, "Top 3 截止", 190, y + 54, "start"))
    if len(rows) >= 2:
        body.append(_callout(f"Top 3 合计 {top3_total:g}", 880, 92, "end"))
        body.append(_note("口径：由 SEU 聚合题数、风险题数、采分单元数和平均 Bloom；红色表示最高权重或关联风险题。", 190, height - 14, "start"))
    return _svg("knowledge-top-points", width, height, "".join(body))


def render_competency_radar(data: Dict[str, Any]) -> str:
    dimensions = [("生命观念", _pct(data.get("生命观念"))), ("科学思维", _pct(data.get("科学思维"))), ("科学探究", _pct(data.get("科学探究"))), ("社会责任", _pct(data.get("社会责任")))]
    if not any(value > 0 for _, value in dimensions):
        return _empty_chart("competency-distribution", "核心素养雷达图")
    width, height = 720, 430
    cx, cy, radius = 360, 222, 92
    rings = []
    for level in (0.33, 0.66, 1.0):
        pts = []
        for index in range(len(dimensions)):
            angle = -pi / 2 + 2 * pi * index / len(dimensions)
            pts.append(f"{cx + radius * level * cos(angle):.1f},{cy + radius * level * sin(angle):.1f}")
        rings.append(f'<polygon points="{" ".join(pts)}" fill="none" stroke="{PALETTE["line"]}" />')
    data_pts = []
    labels = []
    strongest = max(dimensions, key=lambda item: item[1])
    for index, (label, value) in enumerate(dimensions):
        angle = -pi / 2 + 2 * pi * index / len(dimensions)
        axis_x, axis_y = cx + radius * cos(angle), cy + radius * sin(angle)
        data_x, data_y = cx + radius * min(value, 100) / 100 * cos(angle), cy + radius * min(value, 100) / 100 * sin(angle)
        data_pts.append(f"{data_x:.1f},{data_y:.1f}")
        labels.append(f'<line x1="{cx}" y1="{cy}" x2="{axis_x:.1f}" y2="{axis_y:.1f}" stroke="{PALETTE["line"]}" />')
        label_x = cx + (radius + 56) * cos(angle)
        label_y = cy + (radius + 56) * sin(angle)
        labels.append(f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="15" fill="{PALETTE["ink"]}">{_e(label)} {value:.0f}%</text>')
    body = (
        _title("核心素养雷达图", width)
        + "".join(rings)
        + "".join(labels)
        + f'<polygon data-role="highlight" points="{" ".join(data_pts)}" fill="{PALETTE["accent"]}" fill-opacity=".12" stroke="{PALETTE["accent"]}" stroke-width="3" />'
        + f'<circle cx="{cx}" cy="{cy}" r="3" fill="{PALETTE["accent"]}" />'
        + _callout(f"主导素养：{strongest[0]} {strongest[1]:.0f}%", width - 54, 76, "end")
        + _note("口径：按题目/采分点权重聚合；红色轮廓用于显示素养结构张力。", 88, height - 18, "start")
    )
    return _svg("competency-distribution", width, height, body)


def render_risk_distribution(data: Dict[str, Any]) -> str:
    rows = [("高风险", _num(data.get("high")), PALETTE["risk"]), ("关注", _num(data.get("medium")), PALETTE["watch"]), ("稳定", _num(data.get("low")), PALETTE["positive"])]
    total = sum(value for _, value, _ in rows)
    if total <= 0:
        return _empty_chart("question-risk-distribution", "题目风险分层图")
    width, height = 720, 270
    body = [_title("题目风险分层图", width)]
    start_x, y = 92, 106
    max_v = max(value for _, value, _ in rows) or 1
    body.append(_baseline(start_x - 8, y + 100, start_x + 500, y + 100))
    for index, (label, value, color) in enumerate(rows):
        x = start_x + index * 190
        h = 94 * value / max_v
        is_high_risk = index == 0
        fill = PALETTE["accent"] if is_high_risk else [PALETTE["watch"], PALETTE["platinum"]][index - 1]
        body.append(f'<rect data-role="{"highlight" if is_high_risk else "context"}" x="{x}" y="{y + 94 - h:.1f}" width="84" height="{h:.1f}" rx="5" fill="{fill}" />')
        body.append(f'<text x="{x + 42}" y="{y + 120}" text-anchor="middle" font-size="15" fill="{PALETTE["ink"]}">{label}</text>')
        body.append(f'<text x="{x + 42}" y="{y + 78 - h:.1f}" text-anchor="middle" font-size="22" font-weight="800" fill="{fill}">{value:g}</text>')
    high_share = rows[0][1] / total * 100 if total else 0
    body.append(_benchmark_line(start_x, y + 94 * .35, start_x + 500, y + 94 * .35, "复核阈值", start_x + 500, y + 94 * .35 - 10, "end"))
    body.append(_callout(f"高风险占比 {high_share:.0f}%", width - 72, 74, "end"))
    body.append(_note("口径：红色为必须优先复核；灰阶表示关注/稳定题组的抽样优先级。", 92, height - 18, "start"))
    return _svg("question-risk-distribution", width, height, "".join(body))


def render_metadata_quality(data: Dict[str, Any]) -> str:
    total = _num(data.get("total_questions"))
    warning = len(_items(data.get("warning_questions")))
    low = len(_items(data.get("low_confidence_questions")))
    missing = len(_items(data.get("missing_envelope_questions")))
    calls = sum(_num(v) for v in _dict(data.get("llm_call_counts")).values())
    rows = [("题目总数", total, PALETTE["blue"]), ("告警题", warning, PALETTE["watch"]), ("低置信度", low, PALETTE["accent"]), ("缺失元数据包", missing, PALETTE["risk"]), ("LLM 调用", calls, PALETTE["teal"])]
    width, height = 720, 320
    max_v = max(value for _, value, _ in rows) or 1
    body = [_title("元数据治理仪表图", width)]
    threshold_x = 190 + 420 * 0.25
    body.append(_baseline(190, 68, 610, 68))
    body.append(_benchmark_line(threshold_x, 82, threshold_x, 266, "治理阈值", threshold_x + 10, 88, "start"))
    for index, (label, value, color) in enumerate(rows):
        y = 90 + index * 40
        is_governance_gap = index in (2, 3)
        fill = PALETTE["accent"] if is_governance_gap else [PALETTE["platinum"], PALETTE["watch"], PALETTE["platinum"], PALETTE["platinum"], PALETTE["blue"]][index]
        body.append(_axis_label(label, 166, y + 20, "end"))
        body.append(f'<rect data-role="{"highlight" if is_governance_gap else "context"}" x="190" y="{y}" width="{420 * value / max_v:.1f}" height="24" rx="4" fill="{fill}" />')
        body.append(f'<text x="628" y="{y + 18}" font-size="15" fill="{PALETTE["ink"]}">{value:g}</text>')
    body.append(_callout(f"治理缺口 {low + missing:g}", 628, 170, "end"))
    body.append(_note("口径：低置信与缺失元数据包用红色标识；LLM 调用量只作为覆盖校验。", 190, height - 18, "start"))
    return _svg("metadata-quality", width, height, "".join(body))


def render_fine_grained_heatmap(rows: Any) -> str:
    items = sorted(
        [_dict(row) for row in _items(rows)],
        key=lambda row: (-_num(row.get("pressure_index")), row.get("question_id") or 0),
    )[:14]
    if not items:
        return _empty_chart("fine-grained-heatmap", "题目 × 难度因子热力图")
    factors = [
        ("pressure_index", "压力指数", 100),
        ("metadata_gap", "元数据缺口", 1),
        ("evidence_density", "证据密度", max(_num(row.get("evidence_density")) for row in items) or 1),
        ("difficulty", "难度", 10),
        ("quality_score", "质量", 5),
        ("seu_count", "SEU", max(_num(row.get("seu_count")) for row in items) or 1),
        ("du_count", "DU", max(_num(row.get("du_count")) for row in items) or 1),
        ("max_trap_strength", "陷阱", 3),
    ]
    width, height = 940, 168 + len(items) * 34
    left, top = 112, 122
    cell_w, cell_h = 98, 27
    body = [_title("Top 压力题 × 难度因子热力图", width)]
    body.append(_axis_label("按压力指数排序，保留最能解释风险来源的关键因子", left, 62, "start"))
    metadata_line_x = left + cell_w * 1.5
    body.append(_benchmark_line(metadata_line_x, top - 22, metadata_line_x, top + len(items) * 34 - 4, "元数据缺口阈值", metadata_line_x + 10, top - 34, "start"))
    for col, (_, label, _) in enumerate(factors):
        body.append(_axis_label(label, left + col * cell_w + cell_w / 2, top - 10))
    max_cell = ("", "", 0.0)
    for row_index, row in enumerate(items):
        y = top + row_index * 34
        qid = row.get("question_id")
        body.append(_axis_label(f"Q{qid}", left - 20, y + 20, "end"))
        for col, (key, label, max_value) in enumerate(factors):
            value = _num(row.get(key))
            ratio = max(0, min(1, value / (max_value or 1)))
            if key in {"quality_score", "metadata_confidence"}:
                ratio = 1 - ratio
            color = PALETTE["platinum"] if ratio < .45 else PALETTE["watch"] if ratio < .72 else PALETTE["accent"]
            role = "highlight" if ratio >= .72 else "context"
            if ratio > max_cell[2]:
                max_cell = (f"Q{qid}", label, ratio)
            x = left + col * cell_w
            body.append(f'<rect data-role="{role}" x="{x}" y="{y}" width="{cell_w - 4}" height="{cell_h}" rx="3" fill="{color}" fill-opacity="{0.18 + ratio * 0.62:.2f}" stroke="#fff"/>')
            body.append(f'<text x="{x + (cell_w - 4) / 2:.1f}" y="{y + 20}" text-anchor="middle" font-size="14" font-weight="700" fill="{PALETTE["ink"]}">{value:g}</text>')
    body.append(_callout(f"最高压力：{max_cell[0]} {max_cell[1]}", width - 34, 72, "end"))
    body.append(_note("口径：压力指数为难度、质量缺口、元数据缺口、陷阱强度和证据密度的加权综合。", left, height - 18, "start"))
    return _svg("fine-grained-heatmap", width, height, "".join(body))


def render_seu_competency_matrix(rows: Any) -> str:
    items = [_dict(row) for row in _items(rows)]
    if not items:
        return _empty_chart("seu-competency-matrix", "SEU × 知识点 × 素养矩阵")
    matrix: Dict[str, Dict[str, float]] = {}
    for row in items:
        knowledge = str(row.get("knowledge_point") or "未标注知识点")
        competency = str(row.get("competency") or "未标注素养")
        matrix.setdefault(knowledge, {})
        matrix[knowledge][competency] = matrix[knowledge].get(competency, 0) + _num(row.get("weighted_score"))
    knowledge_rows = sorted(matrix.items(), key=lambda item: -sum(item[1].values()))[:8]
    competencies = []
    for _, values in knowledge_rows:
        for competency in values:
            if competency not in competencies:
                competencies.append(competency)
    competencies = competencies[:5]
    max_value = max((value for _, values in knowledge_rows for value in values.values()), default=1)
    width, height = 920, 162 + len(knowledge_rows) * 44
    left, top = 210, 122
    cell_w, cell_h = 122, 31
    body = [_title("SEU × 知识点 × 素养矩阵", width)]
    body.append(_axis_label("颜色深浅代表该知识点-素养组合承载的分值", left, 64, "start"))
    body.append(_benchmark_line(left + cell_w * 1.5, top - 22, left + cell_w * 1.5, top + len(knowledge_rows) * 44 - 8, "覆盖阈值", left + cell_w * 1.5 + 10, top - 34, "start"))
    for col, competency in enumerate(competencies):
        body.append(_axis_label(_truncate(competency, 8), left + col * cell_w + cell_w / 2, top - 14))
    max_cell = ("", "", 0.0)
    for row_index, (knowledge, values) in enumerate(knowledge_rows):
        y = top + row_index * 44
        body.append(_axis_label(_truncate(knowledge, 16), left - 18, y + 22, "end"))
        for col, competency in enumerate(competencies):
            value = values.get(competency, 0)
            ratio = value / (max_value or 1)
            x = left + col * cell_w
            is_max = value > 0 and value == max_value
            fill = PALETTE["accent"] if is_max else PALETTE["platinum"]
            if ratio > max_cell[2]:
                max_cell = (_truncate(knowledge, 8), _truncate(competency, 8), ratio)
            body.append(f'<rect data-role="{"highlight" if is_max else "context"}" x="{x}" y="{y}" width="{cell_w - 6}" height="{cell_h}" rx="4" fill="{fill}" fill-opacity="{0.08 + ratio * .72:.2f}" stroke="{PALETTE["line"]}"/>')
            if value > 0:
                body.append(f'<text x="{x + (cell_w - 6) / 2:.1f}" y="{y + 21}" text-anchor="middle" font-size="14" font-weight="700" fill="{PALETTE["ink"]}">{value:.1f}</text>')
    body.append(_callout(f"主承载：{max_cell[0]} × {max_cell[1]}", width - 34, 66, "end"))
    body.append(_note("口径：SEU 分值按知识点与核心素养交叉聚合；红色为最大承载组合。", left, height - 18, "start"))
    return _svg("seu-competency-matrix", width, height, "".join(body))


def render_du_trap_map(rows: Any) -> str:
    items = [_dict(row) for row in _items(rows) if row]
    if not items:
        return _empty_chart("du-trap-map", "DU 误区与陷阱强度图")
    items = sorted(items, key=lambda row: (-_num(row.get("trap_strength")), row.get("question_id") or 0))[:10]
    width, height = 980, 126 + len(items) * 42
    max_strength = max(_num(row.get("trap_strength")) for row in items) or 1
    body = [_title("DU 误区与陷阱强度图", width)]
    body.append(_axis_label("每条横线对应一个诊断干扰单元，服务讲评和命题修订", 84, 66, "start"))
    body.append(_baseline(170, 78, 670, 78))
    body.append(_benchmark_line(170 + 500 * (2 / max_strength), 86, 170 + 500 * (2 / max_strength), height - 34, "强度 2 阈值", 170 + 500 * (2 / max_strength) + 10, 96, "start"))
    for index, row in enumerate(items):
        y = 98 + index * 42
        strength = _num(row.get("trap_strength"))
        color = PALETTE["accent"] if strength >= 3 else PALETTE["watch"] if strength >= 2 else PALETTE["platinum"]
        label = f"Q{row.get('question_id')} {row.get('option_or_trap')}"
        text = str(row.get("misconception") or row.get("knowledge_boundary") or "未标注误区")
        body.append(_axis_label(label, 148, y + 20, "end"))
        body.append(f'<rect data-role="{"highlight" if strength >= 3 else "context"}" x="170" y="{y}" width="{500 * strength / max_strength:.1f}" height="24" rx="4" fill="{color}" />')
        body.append(f'<text x="690" y="{y + 18}" font-size="14" fill="{PALETTE["ink"]}">{_e(_truncate(text, 16))}</text>')
        body.append(f'<text x="910" y="{y + 18}" font-size="14" font-weight="800" fill="{color}">强度 {strength:g}</text>')
    top = items[0]
    body.append(_callout(f"首要陷阱：Q{top.get('question_id')}", width - 34, 66, "end"))
    body.append(_note("口径：DU 按陷阱强度排序；红色表示进入必须讲评/修订的干扰单元。", 170, height - 18, "start"))
    return _svg("du-trap-map", width, height, "".join(body))


def render_portfolio_bubble(rows: Iterable[Dict[str, Any]]) -> str:
    items = [_dict(row) for row in rows]
    points = [row for row in items if isinstance(row.get("difficulty"), (int, float)) and isinstance(row.get("score"), (int, float))]
    if not points:
        return _empty_chart("question-portfolio", "题目组合气泡图")
    width, height = 980, 470
    left, right, top, bottom = 82, 56, 78, 104
    plot_w, plot_h = width - left - right, height - top - bottom
    max_score = max(_num(row.get("score")) for row in points) or 1
    avg_difficulty = sum(_num(row.get("difficulty")) for row in points) / len(points)
    avg_pressure = sum(_num(row.get("pressure_index"), _num(row.get("score")) / max_score * 100) for row in points) / len(points)
    color_map = {"high": PALETTE["accent"], "medium": PALETTE["watch"], "low": PALETTE["platinum"]}
    label_ids = {str(row.get("question_id")) for row in points if row.get("risk_level") == "high"}
    for key in ("pressure_index", "difficulty", "score"):
        label_ids.add(str(max(points, key=lambda row: _num(row.get(key))).get("question_id")))
    body = [_title("题目组合气泡图：难度 × 压力指数 × 分值", width)]
    body.append(_highlight_rect(left + plot_w * .65, top, plot_w * .35, plot_h * .45, 0.06))
    body.append(_axis_label("高难高压复核区", left + plot_w - 10, top + 22, "end"))
    body.append(f'<rect x="{left}" y="{top + plot_h * .62:.1f}" width="{plot_w * .38:.1f}" height="{plot_h * .38:.1f}" fill="{PALETTE["platinum"]}" fill-opacity="0.24"/>')
    body.append(_axis_label("基础稳定区", left + 10, top + plot_h - 12, "start"))
    for i in range(6):
        y = top + plot_h * i / 5
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="{PALETTE["line"]}" />')
        body.append(_axis_label(str(100 - i * 20), left - 16, y + 5, "end"))
    for i in range(0, 11, 2):
        x = left + plot_w * i / 10
        body.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height - bottom}" stroke="{PALETTE["line"]}" />')
        body.append(_axis_label(str(i), x, height - 58))
    difficulty_x = left + plot_w * avg_difficulty / 10
    pressure_y = top + plot_h - plot_h * avg_pressure / 100
    body.append(_baseline(left, height - bottom, width - right, height - bottom))
    body.append(_baseline(left, top, left, height - bottom))
    body.append(_benchmark_line(difficulty_x, top, difficulty_x, height - bottom, f"平均难度 {avg_difficulty:.1f}", difficulty_x + 10, top + 22, "start"))
    body.append(_benchmark_line(left, pressure_y, width - right, pressure_y, f"平均压力 {avg_pressure:.1f}", width - right, pressure_y - 12, "end"))
    body.append(_axis_label("难度", width / 2, height - 32))
    body.append(_axis_label("压力指数 / 气泡=分值", 28, top + 22, "start"))
    placed_labels: List[tuple[float, float]] = []
    for row in points:
        difficulty = max(0, min(10, _num(row.get("difficulty"))))
        score = _num(row.get("score"))
        pressure = max(0, min(100, _num(row.get("pressure_index"), score / max_score * 100)))
        x = left + plot_w * difficulty / 10
        y = top + plot_h - plot_h * pressure / 100
        r = 7 + 9 * score / max_score
        color = color_map.get(row.get("risk_level"), PALETTE["watch"])
        role = "highlight" if row.get("risk_level") == "high" else "context"
        text_fill = "#fff" if row.get("risk_level") == "high" else PALETTE["ink"]
        body.append(f'<circle data-role="{role}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}" fill-opacity="0.82" stroke="#fff" stroke-width="2" />')
        should_label = str(row.get("question_id")) in label_ids
        too_close = any((x - px) ** 2 + (y - py) ** 2 < 900 for px, py in placed_labels)
        if should_label and not too_close:
            placed_labels.append((x, y))
            body.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="13" font-weight="800" fill="{text_fill}">Q{_e(row.get("question_id"))}</text>')
    legend_x = width - 266
    body.append(f'<circle cx="{legend_x}" cy="{height - 32}" r="8" fill="{PALETTE["risk"]}" fill-opacity=".78"/>')
    body.append(_axis_label("高风险", legend_x + 20, height - 27, "start"))
    body.append(f'<circle cx="{legend_x + 92}" cy="{height - 32}" r="8" fill="{PALETTE["watch"]}" fill-opacity=".78"/>')
    body.append(_axis_label("关注", legend_x + 112, height - 27, "start"))
    body.append(f'<circle cx="{legend_x + 176}" cy="{height - 32}" r="8" fill="{PALETTE["positive"]}" fill-opacity=".78"/>')
    body.append(_axis_label("稳定", legend_x + 196, height - 27, "start"))
    high_count = sum(1 for row in points if row.get("risk_level") == "high")
    body.append(_callout(f"高风险 {high_count} 题", width - 64, 68, "end"))
    body.append(_note("口径：气泡=分值；主导压力与密集题号见下方明细表。", left, height - 18, "start"))
    return _svg("question-portfolio", width, height, "".join(body))


def render_methodology_chart(methodology: Dict[str, Any]) -> str:
    counts = _dict(_dict(methodology.get("llm_call_summary")).get("purpose_counts"))
    rows = [(_status_label(key), _num(value)) for key, value in counts.items() if _num(value) > 0]
    if not rows:
        return _empty_chart("methodology-llm", "LLM 调用结构图")
    rows = sorted(rows, key=lambda item: -item[1])
    width = 920
    row_h = 44
    height = 116 + len(rows) * row_h
    max_v = max(value for _, value in rows) or 1
    body = [_title("LLM 调用结构图", width)]
    body.append(_baseline(300, 74, 800, 74))
    body.append(_benchmark_line(300 + 500 * .5, 86, 300 + 500 * .5, height - 42, "覆盖阈值", 300 + 500 * .5 + 10, 88, "start"))
    for index, (label, value) in enumerate(rows):
        y = 100 + index * row_h
        is_primary = index == 0
        fill = PALETTE["accent"] if is_primary else [PALETTE["platinum"], PALETTE["watch"], PALETTE["blue"], PALETTE["purple"]][index % 4]
        body.append(_axis_label(label, 278, y + 22, "end"))
        body.append(f'<rect data-role="{"highlight" if is_primary else "context"}" x="300" y="{y}" width="{500 * value / max_v:.1f}" height="26" rx="5" fill="{fill}" />')
        body.append(f'<text x="828" y="{y + 20}" font-size="15" fill="{PALETTE["ink"]}">{value:g}</text>')
    body.append(_callout(f"主调用：{rows[0][0]}", width - 78, 68, "end"))
    body.append(_note("口径：按调用目的聚合 LLM 调用；红色为最大调用目的。", 300, height - 18, "start"))
    return _svg("methodology-llm", width, height, "".join(body))


def render_figure_chart(figure: Dict[str, Any]) -> str:
    figure_id = str(figure.get("id") or "")
    data = figure.get("data")
    if figure_id == "difficulty_gradient":
        return render_difficulty_gradient(_dict(data))
    if figure_id == "bloom_distribution":
        return render_bloom_distribution(_dict(data))
    if figure_id == "knowledge_top_points":
        return render_knowledge_bars(data)
    if figure_id == "competency_distribution":
        return render_competency_radar(_dict(data))
    if figure_id == "question_risk_distribution":
        return render_risk_distribution(_dict(data))
    if figure_id == "metadata_quality":
        return render_metadata_quality(_dict(data))
    if figure_id == "fine_grained_heatmap":
        return render_fine_grained_heatmap(data)
    if figure_id == "seu_competency_matrix":
        return render_seu_competency_matrix(data)
    if figure_id == "du_trap_map":
        return render_du_trap_map(data)
    return ""
