"""Static SVG charts for the commercial exam report.

The module produces inline SVG so the HTML report remains self-contained and
PDF-friendly. It follows the existing backend SVG chart pattern instead of
introducing a separate front-end runtime.
"""
from __future__ import annotations

import math
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
    "difficulty-gradient": "逐题难度曲线",
    "bloom-distribution": "认知层级堆叠条",
    "knowledge-top-points": "知识点重要性排名",
    "competency-distribution": "核心素养雷达图",
    "question-risk-distribution": "题目风险分布图",
    "metadata-quality": "元数据质量图",
    "fine-grained-heatmap": "题目压力因子热力图",
    "seu-competency-matrix": "采分点知识点素养矩阵",
    "du-trap-map": "学生误区负荷图",
    "question-portfolio": "题目组合气泡图",
    "methodology-llm": "AI 调用结构图",
}

BLOOM_HIGH_ORDER_LABELS = {"分析", "评价", "创造"}


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


def _pct_label(value: float) -> str:
    return "<1%" if 0 < value < 1 else f"{value:.0f}%"


def _status_label(value: Any) -> str:
    return {
        "warning": "告警题",
        "missing": "缺失",
        "high": "高风险",
        "medium": "关注",
        "low": "稳定",
        "question_analysis": "题目结构分析",
        "image_inputs": "图像识别",
        "feature_extraction": "难度与质量特征抽取",
        "big_question_feature_extraction": "大题结构特征抽取",
        "split_questions": "题目拆分",
        "report_insights": "报告综合分析",
        "report_teaching_suggestions": "教学建议生成",
        "report_grounding_check": "证据核查",
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
    extra_attrs = ""
    if chart_id == "competency-distribution":
        extra_attrs = ' data-mode="coverage" data-active="life-concept"'
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
        f'role="img" aria-labelledby="{safe_id}_title {safe_id}_desc"{extra_attrs}>'
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
    question_points = [
        _dict(row) for row in _items(data.get("question_points"))
        if isinstance(_dict(row).get("difficulty"), (int, float))
    ]
    if question_points:
        points = sorted(question_points, key=lambda row: _num(row.get("question_id")))
        width, height = 780, 450
        left, right, top, bottom = 72, 42, 82, 120
        plot_w, plot_h = width - left - right, height - top - bottom
        max_y, min_y = 10.0, 0.0
        coords = []
        for index, row in enumerate(points):
            difficulty = max(min_y, min(max_y, _num(row.get("difficulty"))))
            x = left + plot_w * index / max(1, len(points) - 1)
            y = top + plot_h - ((difficulty - min_y) / (max_y - min_y)) * plot_h
            coords.append((row, difficulty, x, y))
        path = " ".join(("M" if index == 0 else "L") + f"{x:.1f},{y:.1f}" for index, (_, _, x, y) in enumerate(coords))
        grid_parts = []
        for tick in range(0, 11, 2):
            y = top + plot_h - (tick / max_y) * plot_h
            grid_parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="{PALETTE["line"]}" stroke-width="1"/>')
            grid_parts.append(_axis_label(str(tick), left - 14, y + 5, "end"))
        risk_band_y = top + plot_h - (6.5 / max_y) * plot_h
        risk_band = _highlight_rect(left, top, plot_w, risk_band_y - top, 0.055)
        risk_line = _benchmark_line(left, risk_band_y, width - right, risk_band_y, "高压区：难度 ≥ 6.5", left + 8, risk_band_y - 10, "start")
        avg = data.get("avg_difficulty")
        avg_line = ""
        if isinstance(avg, (int, float)):
            avg_y = top + plot_h - (_num(avg) / max_y) * plot_h
            avg_line = _benchmark_line(left, avg_y, width - right, avg_y, f"加权均值 {avg:.1f}", width - right, avg_y - 12, "end")
        point_parts = []
        important_ids = {
            row.get("question_id")
            for row, difficulty, _, _ in sorted(coords, key=lambda item: item[1], reverse=True)[:3]
        }
        important_rows = [
            (row.get("question_id"), difficulty)
            for row, difficulty, _, _ in sorted(coords, key=lambda item: item[1], reverse=True)[:3]
        ]
        important_summary = " · ".join(f"Q{qid} {difficulty:.1f}" for qid, difficulty in important_rows)
        mobile_cards = []
        for row, difficulty, _, _ in sorted(coords, key=lambda item: item[1], reverse=True)[:5]:
            qid = row.get("question_id")
            score = _num(row.get("score", row.get("total_score")))
            mobile_cards.append(
                '<article class="chart-mobile-card">'
                f'<div><strong>Q{_e(qid)}</strong><span>难度 {difficulty:.1f}</span></div>'
                f'<p>分值 {score:g}；用于定位讲评和复核优先级。</p>'
                '</article>'
            )
        mobile_cards.append(
            '<article class="chart-mobile-card">'
            '<div><strong>三段均值</strong><span>走势</span></div>'
            f'<p>前段 {data.get("front", 0):.1f} · 中段 {data.get("middle", 0):.1f} · 后段 {data.get("back", 0):.1f}</p>'
            '<small>口径：逐题难度仍以完整曲线为准，手机端只展示关键高压点。</small>'
            '</article>'
        )
        for row, difficulty, x, y in coords:
            qid = row.get("question_id")
            is_key = difficulty >= 6.5 or qid in important_ids
            fill = PALETTE["accent"] if is_key else PALETTE["platinum"]
            radius = 6.5 if is_key else 4.5
            point_parts.append(f'<circle data-role="{"highlight" if is_key else "context"}" cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{fill}" stroke="#fff" stroke-width="1.4"/>')
        x_labels = []
        last_qid = int(_num(coords[-1][0].get("question_id"))) if coords else 0
        label_ids = {1, 5, 10, 15, last_qid}
        if last_qid - 20 >= 2:
            label_ids.add(20)
        for row, _, x, _ in coords:
            qid = int(_num(row.get("question_id")))
            if qid in label_ids:
                x_labels.append(_axis_label(f"Q{qid}", x, height - 82))
        segment_labels = (
            _axis_label(f"前段 {data.get('front', 0):.1f}" if isinstance(data.get("front"), (int, float)) else "前段", left + plot_w * .16, height - 52)
            + _axis_label(f"中段 {data.get('middle', 0):.1f}" if isinstance(data.get("middle"), (int, float)) else "中段", left + plot_w * .50, height - 52)
            + _axis_label(f"后段 {data.get('back', 0):.1f}" if isinstance(data.get("back"), (int, float)) else "后段", left + plot_w * .84, height - 52)
        )
        body = (
            _title("逐题难度曲线", width)
            + _axis_label("每个点对应一道题；红点为高难或高压题，灰线保留整卷走势", left, 66, "start")
            + "".join(grid_parts)
            + risk_band
            + risk_line
            + avg_line
            + _callout(f"高难题：{important_summary}", width - right, 66, "end")
            + f'<path d="{path}" fill="none" stroke="{PALETTE["accent"]}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>'
            + "".join(point_parts)
            + "".join(x_labels)
            + segment_labels
            + _note("口径：逐题难度来自题目与采分点综合估计；三段均值仅作为背景参考，不替代逐题判断。", left, height - 20, "start")
        )
        mobile_list = (
            '<div class="chart-mobile-list chart-difficulty-mobile-list" aria-label="逐题难度移动端重点列表">'
            + "".join(mobile_cards)
            + "</div>"
        )
        return _svg("difficulty-gradient", width, height, body) + mobile_list

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
    high_order_share = sum(value for label, value in items if label in BLOOM_HIGH_ORDER_LABELS)
    for index, (label, value) in enumerate(items):
        seg_w = bar_w * value / total
        is_high_order = label in BLOOM_HIGH_ORDER_LABELS
        color = PALETTE["accent"] if is_high_order else [PALETTE["platinum"], PALETTE["watch"], PALETTE["blue"], PALETTE["purple"]][index % 4]
        role = ' data-role="highlight"' if is_high_order else ""
        bars.append(f'<rect{role} x="{cursor:.1f}" y="{y}" width="{seg_w:.1f}" height="{bar_h}" fill="{color}" />')
        if seg_w > 34:
            bars.append(f'<text x="{cursor + seg_w / 2:.1f}" y="{y + 26}" text-anchor="middle" font-size="14" fill="#fff">{value:.0f}%</text>')
        legend.append(
            f'<rect x="{70 + (index % 3) * 190}" y="{172 + (index // 3) * 26}" width="12" height="12" fill="{color}" />'
            f'<text x="{90 + (index % 3) * 190}" y="{183 + (index // 3) * 26}" font-size="14" fill="{PALETTE["ink"]}">{_e(label)} {_e(_pct_label(value))}</text>'
        )
        cursor += seg_w
    marker_x = x + bar_w * 0.5
    body = (
        _title("认知层级堆叠条", width)
        + _baseline(x, y + bar_h + 12, x + bar_w, y + bar_h + 12)
        + "".join(bars)
        + _benchmark_line(marker_x, y - 12, marker_x, y + bar_h + 16, "高阶参考线 50%", marker_x + 10, y - 22, "start")
        + _callout(f"高阶合计 {high_order_share:.0f}%", x + bar_w, y - 22, "end")
        + "".join(legend)
    )
    body += _note("口径：高阶=分析/评价/创造；按采分点分值加权统计。", 70, height - 16, "start")
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
                "aliases": [str(a) for a in (item.get("aliases") or [])],
            })
    if not rows:
        return _empty_chart("knowledge-top-points", "知识点重要性排名")
    rows = sorted(rows, key=lambda item: (-item["value"], -item["risk_count"], item["label"]))[:8]
    width = 940
    row_h = 44
    height = 140 + row_h * len(rows)
    max_v = max(row["value"] for row in rows) or 1
    body = [_title("知识点重要性排名", width)]
    body.append(_axis_label("分值权重", 190, 68, "start"))
    body.append(_axis_label("题数", 700, 68, "middle"))
    body.append(_axis_label("风险", 760, 68, "middle"))
    body.append(_axis_label("采分点", 820, 68, "middle"))
    body.append(_axis_label("认知", 880, 68, "middle"))
    body.append(_baseline(190, 78, 880, 78))
    top3_total = sum(row["value"] for row in rows[:3])
    for index, row in enumerate(rows):
        y = 104 + index * row_h
        bar_w = 430 * row["value"] / max_v
        is_top = index == 0 or row["risk_count"] > 0
        color = PALETTE["accent"] if is_top else [PALETTE["platinum"], PALETTE["watch"], PALETTE["blue"], PALETTE["purple"]][index % 4]
        _kn_label = row["label"]
        if row.get("aliases"):
            _kn_label = f'{_kn_label}·含{row["aliases"][0]}等'
        body.append(_axis_label(_truncate(_kn_label, 18), 170, y + 20, "end"))
        body.append(f'<rect data-role="{"highlight" if is_top else "context"}" x="190" y="{y}" width="{bar_w:.1f}" height="24" rx="4" fill="{color}" />')
        body.append(f'<text x="{202 + min(bar_w, 430):.1f}" y="{y + 18}" font-size="14" fill="{PALETTE["ink"]}">{row["value"]:g}</text>')
        body.append(f'<text x="700" y="{y + 18}" text-anchor="middle" font-size="14" fill="{PALETTE["ink"]}">{row["question_count"]}</text>')
        body.append(f'<text x="760" y="{y + 18}" text-anchor="middle" font-size="14" font-weight="800" fill="{PALETTE["accent"] if row["risk_count"] else PALETTE["muted"]}">{row["risk_count"]}</text>')
        body.append(f'<text x="820" y="{y + 18}" text-anchor="middle" font-size="14" fill="{PALETTE["ink"]}">{row["seu_count"]}</text>')
        body.append(f'<text x="880" y="{y + 18}" text-anchor="middle" font-size="14" fill="{PALETTE["ink"]}">{row["avg_bloom"]:.1f}</text>')
        if index == 2:
            body.append(_benchmark_line(190, y + 34, 880, y + 34, "前 3 截止", 190, y + 54, "start"))
    if len(rows) >= 2:
        body.append(_callout(f"前 3 合计 {top3_total:g}", 880, 92, "end"))
        body.append(_note("口径：由知识点覆盖题数、风险题数、采分点数和平均能力层级聚合；红色表示最高权重或关联风险题。", 190, height - 14, "start"))
    return _svg("knowledge-top-points", width, height, "".join(body))


def _question_ids_label(ids: Any) -> str:
    values = []
    for item in _items(ids):
        if isinstance(item, (int, float)):
            values.append(f"Q{int(item)}")
        elif item:
            text = str(item)
            values.append(text if text.startswith("Q") else f"Q{text}")
    return f"{len(values)}题" if values else "暂无题号"


def render_competency_radar(data: Dict[str, Any]) -> str:
    source = _dict(data)
    distribution = _dict(source.get("distribution")) if "distribution" in source else source
    detail_rows = sorted(
        [_dict(row) for row in _items(source.get("detail_rows"))],
        key=lambda row: -_num(row.get("score_contribution")),
    )
    gap_rows = [_dict(row) for row in _items(source.get("gap_rows"))]
    dimensions = [
        ("life-concept", "生命观念", _pct(distribution.get("生命观念"))),
        ("scientific-thinking", "科学思维", _pct(distribution.get("科学思维"))),
        ("scientific-inquiry", "科学探究", _pct(distribution.get("科学探究"))),
        ("social-responsibility", "社会责任", _pct(distribution.get("社会责任"))),
    ]
    if not any(value > 0 for _, _, value in dimensions):
        return _empty_chart("competency-distribution", "核心素养结构诊断")
    width, height = 720, 470
    cx, cy, radius = 188, 264, 104
    panel_x, panel_y, panel_w, panel_h = 374, 116, 310, 286
    dim_map = {label: value for _, label, value in dimensions}
    strongest = max(dimensions, key=lambda item: item[2])
    grouped: Dict[str, List[Dict[str, Any]]] = {label: [] for _, label, _ in dimensions}
    for row in detail_rows:
        competency = str(row.get("competency") or "")
        if competency in grouped:
            grouped[competency].append(row)
    coverage: Dict[str, Dict[str, Any]] = {
        label: {"question_ids": set(), "seu_count": 0}
        for _, label, _ in dimensions
    }
    for label, rows in grouped.items():
        for row in rows:
            qids = set(_items(row.get("question_ids")))
            coverage[label]["question_ids"].update(qids)
            row_seu_count = int(_num(row.get("seu_count"), len(qids)))
            coverage[label]["seu_count"] += row_seu_count or len(qids)
        if not coverage[label]["question_ids"]:
            dist_item = _dict(distribution.get(label))
            q_count = int(_num(dist_item.get("题目数"), 0))
            if q_count:
                coverage[label]["question_ids"].update(range(1, q_count + 1))
                coverage[label]["seu_count"] = max(coverage[label]["seu_count"], q_count)
    coverage_counts = {label: len(item["question_ids"]) for label, item in coverage.items()}
    max_coverage_questions = max(coverage_counts.values(), default=1) or 1
    max_pct = max(value for _, _, value in dimensions) or 100
    strongest_coverage = max(dimensions, key=lambda item: coverage_counts.get(item[1], 0))

    hover_hide = ",".join(
        f".hit-{key}:hover ~ .competency-panels .competency-panel,.hit-{key}:focus ~ .competency-panels .competency-panel"
        for key, _, _ in dimensions
    )
    hover_show = "".join(
        (
            f".hit-{key}:hover ~ .competency-panels .panel-{key},"
            f".hit-{key}:focus ~ .competency-panels .panel-{key}"
            "{display:inline;}"
        )
        for key, _, _ in dimensions
    )
    active_show = "".join(
        f'svg[data-active="{key}"] .panel-{key}' + "{display:inline;}"
        for key, _, _ in dimensions
    )
    style = (
        "<style>"
        ".coverage-layer{display:inline;}"
        ".load-layer{display:none;}"
        "svg[data-mode=\"load\"] .coverage-layer{display:none;}"
        "svg[data-mode=\"load\"] .load-layer{display:inline;}"
        ".mode-button{cursor:pointer;}"
        ".mode-button rect{fill:#fff;stroke:#d2d3d1;stroke-width:1.2;}"
        ".mode-button text{font-size:13px;font-weight:850;fill:#030404;}"
        ".mode-coverage rect{stroke:#cc0000;}"
        "svg[data-mode=\"load\"] .mode-coverage rect{stroke:#d2d3d1;}"
        "svg[data-mode=\"load\"] .mode-load rect{stroke:#cc0000;}"
        ".competency-panel{display:none;}"
        ".panel-life-concept{display:inline;}"
        ".competency-hit{cursor:pointer;pointer-events:all;}"
        ".competency-hit:focus{outline:none;}"
        ".mode-button rect:focus{outline:none;}"
        ".mode-button rect:focus,.competency-hit:focus{stroke:#cc0000;stroke-width:2;}"
        f"{hover_hide}" + "{display:none;}"
        f"{hover_show}"
        "svg[data-active] .competency-panel{display:none;}"
        f"{active_show}"
        "</style>"
    )

    rings = []
    for level in (0.25, 0.5, 0.75, 1.0):
        pts = []
        for index, _ in enumerate(dimensions):
            angle = -pi / 2 + 2 * pi * index / len(dimensions)
            pts.append(f"{cx + radius * level * cos(angle):.1f},{cy + radius * level * sin(angle):.1f}")
        rings.append(f'<polygon points="{" ".join(pts)}" fill="none" stroke="{PALETTE["line"]}" opacity=".74"/>')
    axis_parts = []
    label_positions = {
        "生命观念": (cx, cy - radius - 22, "middle"),
        "科学思维": (cx + radius - 8, cy - 22, "end"),
        "科学探究": (cx, cy + radius + 34, "middle"),
        "社会责任": (cx - radius + 8, cy - 22, "start"),
    }
    hit_parts = []
    for index, (key, label, value) in enumerate(dimensions):
        angle = -pi / 2 + 2 * pi * index / len(dimensions)
        axis_x, axis_y = cx + radius * cos(angle), cy + radius * sin(angle)
        fill = PALETTE["accent"] if label == strongest[1] else PALETTE["platinum"]
        axis_parts.append(f'<line x1="{cx}" y1="{cy}" x2="{axis_x:.1f}" y2="{axis_y:.1f}" stroke="{PALETTE["line"]}" />')
        axis_parts.append(f'<circle cx="{axis_x:.1f}" cy="{axis_y:.1f}" r="5" fill="{fill}" aria-hidden="true" />')
        activate = f"this.ownerSVGElement.setAttribute('data-active','{key}')"
        hit_parts.append(
            f'<circle class="competency-hit hit-{key}" tabindex="0" role="button" '
            f'onmouseenter="{activate}" onfocus="{activate}" onclick="{activate}" '
            f'aria-label="指向{_e(label)}" cx="{axis_x:.1f}" cy="{axis_y:.1f}" r="34" '
            f'fill="#ffffff" fill-opacity="0" stroke="none"/>'
        )

    def radar_layer(layer_class: str, values: Dict[str, float], max_value: float, labels: Dict[str, str], callout: str) -> str:
        points = []
        label_parts = []
        safe_max = max_value or 1
        for index, (_, label, _) in enumerate(dimensions):
            angle = -pi / 2 + 2 * pi * index / len(dimensions)
            value = values.get(label, 0)
            point_radius = radius * min(value / safe_max, 1)
            points.append(f"{cx + point_radius * cos(angle):.1f},{cy + point_radius * sin(angle):.1f}")
            label_x, label_y, anchor = label_positions[label]
            label_parts.append(
                f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" '
                f'font-size="14" font-weight="800" fill="{PALETTE["ink"]}" stroke="#fff" '
                f'stroke-width="4" paint-order="stroke">{_e(labels[label])}</text>'
            )
        return (
            f'<g class="{layer_class}">'
            f'<polygon points="{" ".join(points)}" fill="{PALETTE["accent"]}" fill-opacity="0.22" '
            f'stroke="{PALETTE["accent"]}" stroke-width="3.4" stroke-linejoin="round"/>'
            f'<circle cx="{cx}" cy="{cy}" r="4" fill="{PALETTE["accent"]}" aria-hidden="true" />'
            f'{"".join(label_parts)}'
            f'{_callout(callout, width - 36, 82, "end")}'
            "</g>"
        )

    coverage_values = {label: float(coverage_counts.get(label, 0)) for _, label, _ in dimensions}
    load_values = {label: value for _, label, value in dimensions}
    coverage_labels = {label: f"{label} {coverage_counts.get(label, 0)}题" for _, label, _ in dimensions}
    load_labels = {label: f"{label} {value:.0f}%" for _, label, value in dimensions}
    coverage_layer = radar_layer(
        "coverage-layer",
        coverage_values,
        float(max_coverage_questions),
        coverage_labels,
        f"覆盖最广：{strongest_coverage[1]} {coverage_counts.get(strongest_coverage[1], 0)}题",
    )
    load_layer = radar_layer(
        "load-layer",
        load_values,
        max_pct,
        load_labels,
        f"主导素养：{strongest[1]} {strongest[2]:.0f}%",
    )

    mode_buttons = (
        '<g class="mode-button mode-coverage" '
        'onclick="this.ownerSVGElement.setAttribute(\'data-mode\',\'coverage\')" '
        'onfocus="this.ownerSVGElement.setAttribute(\'data-mode\',\'coverage\')">'
        '<rect x="36" y="74" width="86" height="26" role="button" tabindex="0" aria-label="切换到覆盖触达" focusable="true" '
        'onclick="this.ownerSVGElement.setAttribute(\'data-mode\',\'coverage\')" '
        'onfocus="this.ownerSVGElement.setAttribute(\'data-mode\',\'coverage\')"/>'
        '<text x="79" y="92" text-anchor="middle" pointer-events="none">覆盖触达</text></g>'
        '<g class="mode-button mode-load" '
        'onclick="this.ownerSVGElement.setAttribute(\'data-mode\',\'load\')" '
        'onfocus="this.ownerSVGElement.setAttribute(\'data-mode\',\'load\')">'
        '<rect x="128" y="74" width="74" height="26" role="button" tabindex="0" aria-label="切换到主负荷" focusable="true" '
        'onclick="this.ownerSVGElement.setAttribute(\'data-mode\',\'load\')" '
        'onfocus="this.ownerSVGElement.setAttribute(\'data-mode\',\'load\')"/>'
        '<text x="165" y="92" text-anchor="middle" pointer-events="none">主负荷</text></g>'
        f'<text x="216" y="92" font-size="12" fill="{PALETTE["muted"]}">默认：覆盖触达</text>'
    )

    def panel_group(key: str, competency: str) -> str:
        pct = dim_map.get(competency, 0)
        rows = grouped.get(competency, [])[:4]
        is_strongest = competency == strongest[1]
        is_gap = any(str(row.get("competency")) == competency for row in gap_rows)
        accent = PALETTE["accent"] if is_strongest or is_gap else PALETTE["ink"]
        eyebrow = "默认：生命观念" if key == "life-concept" else f"指向：{competency}"
        coverage_q_count = coverage_counts.get(competency, 0)
        coverage_seu_count = int(coverage.get(competency, {}).get("seu_count", 0))
        total_score = sum(_num(row.get("score_contribution")) for row in rows)
        parts = [
            f'<g class="competency-panel panel-{key}">',
            f'<rect x="{panel_x}" y="{panel_y}" width="{panel_w}" height="{panel_h}" fill="#fff" stroke="{PALETTE["line"]}" stroke-width="1.2"/>',
            f'<text class="coverage-layer" x="{panel_x + 18}" y="{panel_y + 30}" font-size="18" font-weight="850" fill="{accent}">{_e(competency)} {coverage_q_count}题</text>',
            f'<text class="load-layer" x="{panel_x + 18}" y="{panel_y + 30}" font-size="18" font-weight="850" fill="{accent}">{_e(competency)} {pct:.0f}%</text>',
            f'<text x="{panel_x + panel_w - 18}" y="{panel_y + 30}" text-anchor="end" font-size="13" fill="{PALETTE["muted"]}">{_e(eyebrow)}</text>',
            f'<text class="coverage-layer" x="{panel_x + 18}" y="{panel_y + 57}" font-size="13" fill="{PALETTE["muted"]}">二级素养聚类 · 触达 {coverage_q_count}题 / {coverage_seu_count}采分点</text>',
            f'<text class="load-layer" x="{panel_x + 18}" y="{panel_y + 57}" font-size="13" fill="{PALETTE["muted"]}">二级素养聚类 · 主负荷 {total_score:g}分 / {pct:.0f}%</text>',
        ]
        max_score = max((_num(row.get("score_contribution")) for row in rows), default=1) or 1
        max_seu = max((int(_num(row.get("seu_count"), len(_items(row.get("question_ids"))))) for row in rows), default=1) or 1
        if rows:
            for row_index, row in enumerate(rows):
                row_y = panel_y + 88 + row_index * 44
                label = str(row.get("sub_competency") or "未细分")
                value = _num(row.get("score_contribution"))
                qids = _items(row.get("question_ids"))
                q_count = len(qids)
                seu_count = int(_num(row.get("seu_count"), q_count))
                coverage_bar_w = max(8, 152 * seu_count / max_seu)
                load_bar_w = max(8, 152 * value / max_score)
                fill = PALETTE["accent"] if row_index == 0 else PALETTE["watch"]
                parts.append(
                    f'<text x="{panel_x + 18}" y="{row_y}" font-size="15" font-weight="760" '
                    f'fill="{PALETTE["ink"]}">{_e(_truncate(label, 13))}</text>'
                )
                parts.append(f'<text class="coverage-layer" x="{panel_x + panel_w - 18}" y="{row_y}" text-anchor="end" font-size="12" fill="{PALETTE["muted"]}">触达 {q_count}题 / {seu_count}采分点</text>')
                parts.append(f'<text class="load-layer" x="{panel_x + panel_w - 18}" y="{row_y}" text-anchor="end" font-size="12" fill="{PALETTE["muted"]}">主负荷 {value:g}分</text>')
                parts.append(f'<rect x="{panel_x + 18}" y="{row_y + 12}" width="152" height="9" fill="{PALETTE["sand"]}" stroke="{PALETTE["line"]}"/>')
                parts.append(f'<rect class="coverage-layer" x="{panel_x + 18}" y="{row_y + 12}" width="{coverage_bar_w:.1f}" height="9" fill="{fill}"/>')
                parts.append(f'<rect class="load-layer" x="{panel_x + 18}" y="{row_y + 12}" width="{load_bar_w:.1f}" height="9" fill="{fill}"/>')
                parts.append(f'<text x="{panel_x + 184}" y="{row_y + 21}" font-size="12" font-weight="800" fill="{PALETTE["ink"]}">{_e(_truncate(_question_ids_label(qids), 8))}</text>')
        else:
            parts.append(f'<text x="{panel_x + 18}" y="{panel_y + 102}" font-size="14" fill="{PALETTE["muted"]}">未形成明确二级聚类</text>')
        if is_gap:
            parts.append(f'<text x="{panel_x + 18}" y="{panel_y + panel_h - 18}" font-size="13" font-weight="800" fill="{PALETTE["accent"]}">覆盖偏低，建议补充任务情境</text>')
        elif is_strongest:
            parts.append(f'<text x="{panel_x + 18}" y="{panel_y + panel_h - 18}" font-size="13" fill="{PALETTE["muted"]}">本卷主导素养，需核查高阶要求是否清晰。</text>')
        else:
            parts.append(f'<text x="{panel_x + 18}" y="{panel_y + panel_h - 18}" font-size="13" fill="{PALETTE["muted"]}">用于识别该类素养下的主要命题支点。</text>')
        parts.append("</g>")
        return "".join(parts)

    def mobile_card(key: str, competency: str) -> str:
        rows = grouped.get(competency, [])[:3]
        coverage_q_count = coverage_counts.get(competency, 0)
        coverage_seu_count = int(coverage.get(competency, {}).get("seu_count", 0))
        pct = dim_map.get(competency, 0)
        top_rows = []
        for row in rows:
            label = str(row.get("sub_competency") or "未细分")
            q_count = len(_items(row.get("question_ids")))
            seu_count = int(_num(row.get("seu_count"), q_count))
            top_rows.append(
                f'<li><span>{_e(_truncate(label, 12))}</span><b>{q_count}题 / {seu_count}采分点</b></li>'
            )
        if not top_rows:
            top_rows.append("<li><span>未形成明确二级聚类</span><b>待复核</b></li>")
        return (
            '<article class="chart-mobile-card chart-competency-mobile-card">'
            f'<div><strong>{_e(competency)}</strong><span>触达 {coverage_q_count}题</span></div>'
            f'<p>主负荷 {pct:.0f}%；二级聚类覆盖 {coverage_seu_count} 个采分点。</p>'
            f'<ul>{"".join(top_rows)}</ul>'
            f'<small>{"默认显示" if key == "life-concept" else "雷达指向"}：{_e(competency)}</small>'
            '</article>'
        )

    gap_text = "；".join(
        f'{row.get("status", "关注")}：{row.get("competency")}'
        for row in gap_rows[:4]
    ) or "暂无明显覆盖缺口"
    panels = "".join(panel_group(key, label) for key, label, _ in dimensions)
    body_parts = [
        style,
        _title("核心素养结构诊断", width),
        _axis_label("默认显示覆盖触达，切换查看主负荷；右侧保留二级聚类，不展开采分点明细。", 36, 64, "start"),
        mode_buttons,
        f'<rect x="34" y="116" width="300" height="286" fill="#fff" stroke="{PALETTE["line"]}" stroke-width="1.2"/>',
        _axis_label("一级素养雷达", cx, 108, "middle"),
        "".join(rings),
        "".join(axis_parts),
        coverage_layer,
        load_layer,
        "".join(hit_parts),
        f'<g class="competency-panels">{panels}</g>',
        f'<text x="36" y="424" font-size="13" font-weight="800" fill="{PALETTE["accent"]}">{_e(gap_text)}</text>',
        f'<rect x="36" y="434" width="648" height="24" fill="{PALETTE["sand"]}" stroke="{PALETTE["line"]}"/>',
        _note("口径：覆盖触达允许同一采分点可同时计入多个素养；主负荷按采分点分值守恒计算。", 52, 452, "start"),
    ]
    body = "".join(body_parts)
    mobile_list = (
        '<div class="chart-mobile-list chart-competency-mobile-list" aria-label="核心素养移动端二级聚类列表">'
        + "".join(mobile_card(key, label) for key, label, _ in dimensions)
        + "</div>"
    )
    return _svg("competency-distribution", width, height, body) + mobile_list


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
    rows = [("题目总数", total, PALETTE["blue"]), ("告警题", warning, PALETTE["watch"]), ("低置信度", low, PALETTE["accent"]), ("缺失元数据包", missing, PALETTE["risk"]), ("AI 调用", calls, PALETTE["teal"])]
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
    body.append(_note("口径：低置信与缺失元数据包用红色标识；AI 调用量只作为覆盖校验。", 190, height - 18, "start"))
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
        ("score_risk", "分值压力", 10),
        ("metadata_gap", "元数据缺口", 1),
        ("evidence_density", "证据密度", max(_num(row.get("evidence_density")) for row in items) or 1),
        ("difficulty", "难度", 10),
        ("quality_score", "质量", 5),
        ("seu_count", "采分点", max(_num(row.get("seu_count")) for row in items) or 1),
        ("du_count", "误区点", max(_num(row.get("du_count")) for row in items) or 1),
        ("max_trap_strength", "陷阱", 3),
    ]
    width, height = 1040, 168 + len(items) * 34
    left, top = 112, 122
    cell_w, cell_h = 98, 27
    body = [_title("重点压力题 × 难度因子热力图", width)]
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
        return _empty_chart("seu-competency-matrix", "采分点 × 知识点 × 素养矩阵")
    matrix: Dict[str, Dict[str, float]] = {}
    for row in items:
        knowledge = str(row.get("knowledge_point") or "未标注知识点")
        competency = str(row.get("competency") or "未标注素养")
        matrix.setdefault(knowledge, {})
        matrix[knowledge][competency] = matrix[knowledge].get(competency, 0) + _num(row.get("weighted_score"))
    knowledge_rows = sorted(matrix.items(), key=lambda item: -sum(item[1].values()))[:8]
    CORE_COMPETENCIES = ("生命观念", "科学思维", "科学探究", "社会责任")
    competencies = list(CORE_COMPETENCIES)
    max_value = max((values.get(c, 0) for _, values in knowledge_rows for c in competencies), default=1) or 1
    width, height = 920, 162 + len(knowledge_rows) * 44
    left, top = 210, 122
    cell_w, cell_h = 122, 31
    body = [_title("采分点 × 知识点 × 素养矩阵", width)]
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
    body.append(_note("口径：采分点分值按知识点与核心素养交叉聚合；红色为最大承载组合；空格表示本卷采分点未显性承载该素养。", left, height - 18, "start"))
    return _svg("seu-competency-matrix", width, height, "".join(body))


def render_du_trap_map(rows: Any) -> str:
    source_rows = [_dict(row) for row in _items(rows) if row]
    if not source_rows:
        return _empty_chart("du-trap-map", "学生误区负荷图")
    grouped: Dict[Any, Dict[str, Any]] = {}
    for row in source_rows:
        qid = row.get("question_id")
        item = grouped.setdefault(qid, {
            "question_id": qid,
            "count": 0,
            "strength_sum": 0.0,
            "max_strength": 0.0,
            "question_difficulty": _num(row.get("question_difficulty")),
            "question_pressure": _num(row.get("question_pressure")),
            "question_score": _num(row.get("question_score")),
            "examples": [],
        })
        strength = _num(row.get("trap_strength"))
        item["count"] += 1
        item["strength_sum"] += strength
        item["max_strength"] = max(item["max_strength"], strength)
        item["question_difficulty"] = max(item["question_difficulty"], _num(row.get("question_difficulty")))
        item["question_pressure"] = max(item["question_pressure"], _num(row.get("question_pressure")))
        item["question_score"] = max(item["question_score"], _num(row.get("question_score")))
        if len(item["examples"]) < 2:
            item["examples"].append(str(row.get("misconception") or row.get("knowledge_boundary") or "未标注误区"))
    items = []
    for item in grouped.values():
        avg_strength = item["strength_sum"] / max(item["count"], 1)
        load = (
            item["max_strength"] * 1.35
            + avg_strength * 0.65
            + min(item["count"], 6) * 0.45
            + _num(item.get("question_difficulty")) * 0.35
            + min(_num(item.get("question_score")), 16) * 0.08
        )
        item["avg_strength"] = round(avg_strength, 1)
        item["trap_load"] = round(load, 1)
        items.append(item)
    items = sorted(items, key=lambda row: (-_num(row.get("trap_load")), row.get("question_id") or 0))[:10]
    width, height = 780, 150 + len(items) * 58
    max_load = max(_num(row.get("trap_load")) for row in items) or 1
    min_load = min(_num(row.get("trap_load")) for row in items) if items else 0
    load_span = max(max_load - min_load, 0.1)
    body = [_title("学生误区负荷图", width)]
    body.append(_axis_label("按题目聚合误区数量、平均强度、最高强度和题目难度，服务讲评和命题修订", 84, 66, "start"))
    body.append(_baseline(94, 82, 354, 82))
    mobile_cards = []
    for index, row in enumerate(items):
        y = 106 + index * 58
        load = _num(row.get("trap_load"))
        bar_width = 130 + 140 * ((load - min_load) / load_span)
        max_strength = _num(row.get("max_strength"))
        color = PALETTE["accent"] if index < 3 else PALETTE["watch"] if max_strength >= 3 else PALETTE["platinum"]
        label = f"Q{row.get('question_id')}"
        text = "；".join(row.get("examples") or ["未标注误区"])
        details = (
            f'误区 {int(row.get("count", 0))} 个 · '
            f'均强 {row.get("avg_strength", 0)} · '
            f'难度 {float(_num(row.get("question_difficulty"))):.1f}'
        )
        body.append(_axis_label(label, 76, y + 18, "end"))
        body.append(f'<rect data-role="{"highlight" if index < 3 else "context"}" x="94" y="{y}" width="{bar_width:.1f}" height="24" rx="4" fill="{color}" />')
        body.append(f'<text x="374" y="{y + 17}" font-size="16" font-weight="850" fill="{color}">负荷 {load:.1f}</text>')
        body.append(f'<text x="468" y="{y + 17}" font-size="15" fill="{PALETTE["ink"]}">{_e(_truncate(text, 17))}</text>')
        body.append(f'<text x="374" y="{y + 39}" font-size="14" fill="{PALETTE["muted"]}">{_e(details)}</text>')
        mobile_cards.append(
            '<article class="chart-mobile-card">'
            f'<div><strong>{_e(label)}</strong><span>负荷 {load:.1f}</span></div>'
            f'<p>{_e(_truncate(text, 30))}</p>'
            f'<small>{_e(details)}</small>'
            '</article>'
        )
    top = items[0]
    body.append(_callout(f"首要讲评题：Q{top.get('question_id')}", width - 34, 66, "end"))
    body.append(_note("口径：条长按前十题相对负荷缩放；红色标出负荷前三题，文字第二行列出误区数、平均强度和题目难度。", 94, height - 18, "start"))
    mobile_list = (
        '<div class="chart-mobile-list chart-du-trap-mobile-list" aria-label="学生误区负荷图移动端列表">'
        + "".join(mobile_cards)
        + "</div>"
    )
    return _svg("du-trap-map", width, height, "".join(body)) + mobile_list


def render_portfolio_bubble(rows: Iterable[Dict[str, Any]]) -> str:
    items = [_dict(row) for row in rows]
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _qid_text(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return "Q?"
        return text if text.upper().startswith("Q") else f"Q{text}"

    def _qid_label(value: Any) -> str:
        text = _qid_text(value)
        return text[1:] if text.upper().startswith("Q") else text

    points = [row for row in items if _is_number(row.get("difficulty")) and _is_number(row.get("score"))]
    blocked_rows = [
        row
        for row in items
        if row.get("risk_level") == "data_gap" or not (_is_number(row.get("difficulty")) and _is_number(row.get("score")))
    ]
    blocked_ids: List[str] = []
    seen_blocked: set[str] = set()
    for row in blocked_rows:
        qid = _qid_text(row.get("question_id"))
        if qid not in seen_blocked:
            seen_blocked.add(qid)
            blocked_ids.append(qid)
    if not points:
        return _empty_chart("question-portfolio", "题目组合气泡图")
    width, height = 980, 470
    left, right, top, bottom = 82, 56, 78, 104
    plot_w, plot_h = width - left - right, height - top - bottom
    max_score = max(_num(row.get("score")) for row in points) or 1
    total_score = sum(_num(row.get("score")) for row in points) or len(points)
    avg_difficulty = sum(_num(row.get("difficulty")) * _num(row.get("score"), 1) for row in points) / total_score
    avg_pressure = sum(
        _num(row.get("pressure_index"), _num(row.get("score")) / max_score * 100) * _num(row.get("score"), 1)
        for row in points
    ) / total_score

    def _scaled_range(values: List[float], low: float, high: float, min_span: float, step: float) -> tuple[float, float]:
        """Keep absolute tick values while zooming away from empty canvas."""
        clean = [max(low, min(high, value)) for value in values if isinstance(value, (int, float))]
        if not clean:
            return low, high
        raw_min, raw_max = min(clean), max(clean)
        lo = max(low, math.floor((raw_min - step) / step) * step)
        hi = min(high, math.ceil((raw_max + step) / step) * step)
        span = hi - lo
        if span < min_span:
            center = (lo + hi) / 2
            lo = center - min_span / 2
            hi = center + min_span / 2
            if lo < low:
                hi += low - lo
                lo = low
            if hi > high:
                lo -= hi - high
                hi = high
        return max(low, lo), min(high, hi)

    difficulty_values = [_num(row.get("difficulty")) for row in points] + [avg_difficulty, 6.5, 7.5]
    pressure_values = [
        _num(row.get("pressure_index"), _num(row.get("score")) / max_score * 100)
        for row in points
    ] + [avg_pressure]
    x_min, x_max = _scaled_range(difficulty_values, 0, 10, 4.5, 0.5)
    y_min, y_max = _scaled_range(pressure_values, 0, 100, 35, 10)
    x_span = max(0.1, x_max - x_min)
    y_span = max(0.1, y_max - y_min)

    def _x_pos(value: float) -> float:
        return left + plot_w * (max(x_min, min(x_max, value)) - x_min) / x_span

    def _y_pos(value: float) -> float:
        return top + plot_h - plot_h * (max(y_min, min(y_max, value)) - y_min) / y_span

    def _fmt_tick(value: float) -> str:
        return str(int(value)) if abs(value - round(value)) < 1e-6 else f"{value:.1f}"

    def _ticks(lo: float, hi: float, count: int = 5) -> List[float]:
        if count <= 1:
            return [lo]
        return [lo + (hi - lo) * i / (count - 1) for i in range(count)]

    color_map = {"high": PALETTE["accent"], "medium": PALETTE["watch"], "low": PALETTE["platinum"], "data_gap": PALETTE["risk"]}
    body = [_title("题目组合气泡图：难度 × 压力指数 × 分值", width)]
    high_x = _x_pos(max(avg_difficulty, 7.5))
    high_y = _y_pos(avg_pressure)
    if high_x < width - right - 8 and high_y > top + 8:
        body.append(_highlight_rect(high_x, top, width - right - high_x, high_y - top, 0.06))
    body.append(_axis_label("高难高压复核区", left + plot_w - 10, top + 46, "end"))
    stable_x = _x_pos(min(avg_difficulty - 1.0, 5.5))
    stable_y = _y_pos(max(y_min, avg_pressure - 8))
    if stable_x > left + 8 and stable_y < height - bottom - 8:
        body.append(f'<rect x="{left}" y="{stable_y:.1f}" width="{stable_x - left:.1f}" height="{height - bottom - stable_y:.1f}" fill="{PALETTE["platinum"]}" fill-opacity="0.24"/>')
    body.append(_axis_label("基础稳定区", left + 10, height - bottom - 12, "start"))
    for value in reversed(_ticks(y_min, y_max, 6)):
        y = _y_pos(value)
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="{PALETTE["line"]}" />')
        body.append(_axis_label(_fmt_tick(value), left - 16, y + 5, "end"))
    for value in _ticks(x_min, x_max, 6):
        x = _x_pos(value)
        body.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height - bottom}" stroke="{PALETTE["line"]}" />')
        body.append(_axis_label(_fmt_tick(value), x, height - 58))
    difficulty_x = _x_pos(avg_difficulty)
    pressure_y = _y_pos(avg_pressure)
    body.append(_baseline(left, height - bottom, width - right, height - bottom))
    body.append(_baseline(left, top, left, height - bottom))
    body.append(_benchmark_line(difficulty_x, top, difficulty_x, height - bottom, f"平均难度 {avg_difficulty:.1f}", difficulty_x + 10, top + 22, "start"))
    body.append(_benchmark_line(left, pressure_y, width - right, pressure_y, f"平均压力 {avg_pressure:.1f}", left + 10, pressure_y - 12, "start"))
    body.append(_axis_label("难度", width / 2, height - 70))
    body.append(_axis_label("压力指数 / 气泡=分值", 28, top + 22, "start"))
    label_boxes: List[tuple[float, float, float, float]] = []

    def _label_box(label_x: float, label_y: float, label_text: str) -> tuple[float, float, float, float]:
        text_w = max(10.0, len(label_text) * 7.6)
        return (label_x - text_w / 2, label_y - 13, label_x + text_w / 2, label_y + 4)

    def _box_overlaps(box: tuple[float, float, float, float]) -> bool:
        return any(
            not (box[2] < placed[0] or box[0] > placed[2] or box[3] < placed[1] or box[1] > placed[3])
            for placed in label_boxes
        )

    for row in points:
        difficulty = max(0, min(10, _num(row.get("difficulty"))))
        score = _num(row.get("score"))
        pressure = max(0, min(100, _num(row.get("pressure_index"), score / max_score * 100)))
        x = _x_pos(difficulty)
        y = _y_pos(pressure)
        r = 7 + 9 * score / max_score
        color = color_map.get(row.get("risk_level"), PALETTE["watch"])
        role = "highlight" if row.get("risk_level") == "high" else "context"
        body.append(f'<circle data-role="{role}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}" fill-opacity="0.82" stroke="#fff" stroke-width="2" />')
        label_text = _qid_label(row.get("question_id"))
        candidates = [
            (0, 4, True),
            (0, -r - 8, False),
            (r + 18, 4, False),
            (-r - 18, 4, False),
            (r + 18, -r - 8, False),
            (-r - 18, -r - 8, False),
            (0, r + 18, False),
        ]
        label_x, label_y, inside = x, y + 4, True
        chosen_box = _label_box(label_x, label_y, label_text)
        for dx, dy, candidate_inside in candidates:
            candidate_x = min(width - right - 10, max(left + 10, x + dx))
            candidate_y = min(height - bottom - 8, max(top + 16, y + dy))
            candidate_box = _label_box(candidate_x, candidate_y, label_text)
            if not _box_overlaps(candidate_box):
                label_x, label_y, inside, chosen_box = candidate_x, candidate_y, candidate_inside, candidate_box
                break
        label_boxes.append(chosen_box)
        if not inside:
            body.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{label_x:.1f}" y2="{label_y - 5:.1f}" stroke="{PALETTE["line"]}" stroke-width="1"/>')
        text_fill = "#fff" if inside and row.get("risk_level") in {"high", "medium"} else PALETTE["ink"]
        stroke_attrs = "" if inside else ' stroke="#fff" stroke-width="3" paint-order="stroke"'
        body.append(f'<text data-role="bubble-label" x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="12" font-weight="850" fill="{text_fill}"{stroke_attrs}>{_e(label_text)}</text>')
    if blocked_ids:
        panel_w, panel_h = 258, 58
        panel_x, panel_y = left + 12, top + 54
        listed_ids = "、".join(blocked_ids[:6])
        if len(blocked_ids) > 6:
            listed_ids += f" 等{len(blocked_ids)}题"
        body.append(
            f'<g data-role="data-gap-panel">'
            f'<rect x="{panel_x}" y="{panel_y}" width="{panel_w}" height="{panel_h}" fill="#fff" stroke="{PALETTE["risk"]}" stroke-width="1.3" stroke-dasharray="5 4"/>'
            f'<text data-role="data-gap-label" x="{panel_x + 12}" y="{panel_y + 23}" font-size="14" font-weight="850" fill="{PALETTE["risk"]}">数据阻断：{_e(listed_ids)}</text>'
            f'<text x="{panel_x + 12}" y="{panel_y + 44}" font-size="13" fill="{PALETTE["muted"]}">不进坐标/均值，先补题干或分项数据</text>'
            f'</g>'
        )
    legend_x = width - 386
    body.append(f'<circle cx="{legend_x}" cy="{height - 32}" r="8" fill="{PALETTE["risk"]}" fill-opacity=".78"/>')
    body.append(_axis_label("高风险", legend_x + 20, height - 27, "start"))
    body.append(f'<circle cx="{legend_x + 92}" cy="{height - 32}" r="8" fill="{PALETTE["watch"]}" fill-opacity=".78"/>')
    body.append(_axis_label("关注", legend_x + 112, height - 27, "start"))
    body.append(f'<circle cx="{legend_x + 176}" cy="{height - 32}" r="8" fill="{PALETTE["positive"]}" fill-opacity=".78"/>')
    body.append(_axis_label("稳定", legend_x + 196, height - 27, "start"))
    body.append(f'<circle data-role="data-gap-legend" cx="{legend_x + 260}" cy="{height - 32}" r="8" fill="#fff" stroke="{PALETTE["risk"]}" stroke-width="2" stroke-dasharray="3 2"/>')
    body.append(_axis_label("数据阻断", legend_x + 280, height - 27, "start"))
    high_count = sum(1 for row in points if row.get("risk_level") == "high")
    data_gap_count = len(blocked_ids)
    body.append(_callout(f"坐标高风险 {high_count} 题 · 数据阻断 {data_gap_count} 题", width - 64, 68, "end"))
    body.append(_note("口径：气泡=分值；主导压力见明细；数据阻断不进坐标/均值。", left, height - 18, "start"))
    return _svg("question-portfolio", width, height, "".join(body))


def render_methodology_chart(methodology: Dict[str, Any]) -> str:
    counts = _dict(_dict(methodology.get("llm_call_summary")).get("purpose_counts"))
    rows = [(_status_label(key), _num(value)) for key, value in counts.items() if _num(value) > 0]
    if not rows:
        return _empty_chart("methodology-llm", "AI 调用结构图")
    rows = sorted(rows, key=lambda item: -item[1])
    width = 920
    row_h = 44
    height = 116 + len(rows) * row_h
    max_v = max(value for _, value in rows) or 1
    body = [_title("AI 调用结构图", width)]
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
    body.append(_note("口径：按调用目的聚合 AI 调用；红色为最大调用目的。", 300, height - 18, "start"))
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
