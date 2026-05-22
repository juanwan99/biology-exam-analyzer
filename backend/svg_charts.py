"""纯 Python SVG 图表生成模块。

每个函数接收数据，返回合法 XML 的 SVG 字符串（<svg>...</svg>）。
无外部依赖，仅用 math 标准库。供报告 HTML 内联使用。
"""
import math
from typing import Dict, List

# ── 公共常量 ──────────────────────────────────────────────────────

_FONT = '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'

# 与 exam-analysis-v3.html 配色对齐
_BLUE = "#2563eb"
_GREEN = "#059669"
_RED = "#dc2626"
_ORANGE = "#d97706"
_PURPLE = "#7c3aed"
_GRID = "#dde1ea"
_BG_FILL = "rgba(37,99,235,0.2)"
_TEXT = "#1e293b"
_TEXT_MUTED = "#64748b"

# 雷达图各维度归一化范围（与 rule_scorer._RANGES 一致）
_RADAR_RANGES: Dict[str, int] = {
    "信息负荷": 5,   # working_memory 1-5
    "推理步数": 10,  # reasoning_steps 1-10
    "推理耦合": 3,   # chain_coupling 1-3
    "陷阱密度": 3,   # trap_density 1-3
    "情境新颖": 3,   # novelty 1-3
    "知识跨度": 3,   # knowledge_breadth 1-3
}


def _esc(text: str) -> str:
    """XML 实体转义。"""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 雷达图（6 维难度因子）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_radar_chart(dimensions: dict, size: int = 200, title: str = "") -> str:
    """6 维雷达图 SVG。

    Args:
        dimensions: {"信息负荷": 3, "推理步数": 5, ...} 值为原始分（非归一化）。
                    缺失的维度用 0 补齐。
        size: SVG 宽高（正方形）。
        title: 可选标题（显示在顶部）。
    Returns:
        SVG 字符串。
    """
    dim_names = list(_RADAR_RANGES.keys())
    n = len(dim_names)
    cx, cy = size / 2, size / 2
    # 留出标签空间
    radius = size * 0.32
    title_offset = 18 if title else 0
    svg_h = size + title_offset

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{size}" height="{svg_h}" '
                 f'viewBox="0 0 {size} {svg_h}" '
                 f'font-family=\'{_FONT}\'>')

    # 标题
    if title:
        parts.append(f'<text x="{cx}" y="14" text-anchor="middle" '
                     f'font-size="12" font-weight="600" fill="{_TEXT}">'
                     f'{_esc(title)}</text>')

    g_offset = title_offset
    parts.append(f'<g transform="translate(0,{g_offset})">')

    # 背景网格（3 层同心六边形: 0.33, 0.67, 1.0）
    for level in (0.33, 0.67, 1.0):
        r = radius * level
        pts = []
        for i in range(n):
            angle = math.pi / 2 + 2 * math.pi * i / n
            px = cx + r * math.cos(angle)
            py = cy - r * math.sin(angle)
            pts.append(f"{px:.1f},{py:.1f}")
        parts.append(f'<polygon points="{" ".join(pts)}" '
                     f'fill="none" stroke="{_GRID}" stroke-width="1"/>')

    # 轴线
    for i in range(n):
        angle = math.pi / 2 + 2 * math.pi * i / n
        ex = cx + radius * math.cos(angle)
        ey = cy - radius * math.sin(angle)
        parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" '
                     f'x2="{ex:.1f}" y2="{ey:.1f}" '
                     f'stroke="{_GRID}" stroke-width="0.8"/>')

    # 数据多边形
    data_pts = []
    for i, name in enumerate(dim_names):
        raw = dimensions.get(name, 0)
        max_val = _RADAR_RANGES[name]
        normed = max(0.0, min(1.0, raw / max_val)) if max_val > 0 else 0
        angle = math.pi / 2 + 2 * math.pi * i / n
        px = cx + radius * normed * math.cos(angle)
        py = cy - radius * normed * math.sin(angle)
        data_pts.append((px, py))

    poly = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in data_pts)
    parts.append(f'<polygon points="{poly}" '
                 f'fill="{_BG_FILL}" stroke="{_BLUE}" stroke-width="1.5"/>')

    # 数据点
    for px, py in data_pts:
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.5" '
                     f'fill="{_BLUE}"/>')

    # 轴端标签 + 数值
    for i, name in enumerate(dim_names):
        raw = dimensions.get(name, 0)
        angle = math.pi / 2 + 2 * math.pi * i / n
        label_r = radius + 20
        lx = cx + label_r * math.cos(angle)
        ly = cy - label_r * math.sin(angle)
        anchor = "middle"
        if abs(math.cos(angle)) > 0.3:
            anchor = "start" if math.cos(angle) > 0 else "end"
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" '
                     f'text-anchor="{anchor}" font-size="10" fill="{_TEXT}">'
                     f'{_esc(name)}</text>')
        parts.append(f'<text x="{lx:.1f}" y="{ly + 12:.1f}" '
                     f'text-anchor="{anchor}" font-size="9" fill="{_TEXT_MUTED}">'
                     f'{raw}</text>')

    parts.append('</g>')
    parts.append('</svg>')
    return "\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 热力图（知识模块 x 认知层次）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_heatmap(rows: list, cols: list, values: list,
                   title: str = "", width: int = 600) -> str:
    """热力图 SVG。

    Args:
        rows: 行标签（知识模块名列表）。
        cols: 列标签（认知层次列表）。
        values: 2D list, values[i][j] 对应 rows[i] x cols[j] 的分值。
        title: 标题。
        width: SVG 宽度。
    Returns:
        SVG 字符串。
    """
    if not rows or not cols:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="40"></svg>'

    row_label_w = 130
    col_header_h = 36
    cell_h = 28
    title_h = 24 if title else 0
    # 额外一行一列用于合计
    n_rows = len(rows) + 1
    n_cols = len(cols) + 1
    cell_w = (width - row_label_w) / n_cols
    svg_h = title_h + col_header_h + cell_h * n_rows + 4

    # 计算合计 + 全局最大值
    row_sums = [sum(r) for r in values]
    col_sums = [sum(values[i][j] for i in range(len(rows))) for j in range(len(cols))]
    grand_total = sum(row_sums)
    flat = [v for row in values for v in row]
    max_val = max(flat) if flat else 1

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{width}" height="{svg_h:.0f}" '
                 f'font-family=\'{_FONT}\'>')

    if title:
        parts.append(f'<text x="{width / 2}" y="16" text-anchor="middle" '
                     f'font-size="13" font-weight="600" fill="{_TEXT}">'
                     f'{_esc(title)}</text>')

    y_base = title_h

    # 列标题
    for j, col in enumerate(cols):
        x = row_label_w + j * cell_w + cell_w / 2
        parts.append(f'<text x="{x:.1f}" y="{y_base + 22}" text-anchor="middle" '
                     f'font-size="10" fill="{_TEXT}">{_esc(col)}</text>')
    # 合计列标题
    x_total = row_label_w + len(cols) * cell_w + cell_w / 2
    parts.append(f'<text x="{x_total:.1f}" y="{y_base + 22}" text-anchor="middle" '
                 f'font-size="10" font-weight="600" fill="{_TEXT}">合计</text>')

    y_base += col_header_h

    # 数据行
    for i, row_label in enumerate(rows):
        y = y_base + i * cell_h
        # 行标签
        parts.append(f'<text x="{row_label_w - 6}" y="{y + cell_h / 2 + 4}" '
                     f'text-anchor="end" font-size="10" fill="{_TEXT}">'
                     f'{_esc(row_label)}</text>')
        for j in range(len(cols)):
            v = values[i][j] if i < len(values) and j < len(values[i]) else 0
            x = row_label_w + j * cell_w
            intensity = v / max_val if max_val > 0 else 0
            r_c = int(255 - intensity * (255 - 37))
            g_c = int(255 - intensity * (255 - 99))
            b_c = int(255 - intensity * (255 - 235))
            fill = f"rgb({r_c},{g_c},{b_c})"
            parts.append(f'<rect x="{x:.1f}" y="{y}" '
                         f'width="{cell_w:.1f}" height="{cell_h}" '
                         f'fill="{fill}" stroke="white" stroke-width="1"/>')
            text_color = "white" if intensity > 0.6 else _TEXT
            display = str(v) if v > 0 else "—"
            parts.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + cell_h / 2 + 4}" '
                         f'text-anchor="middle" font-size="10" fill="{text_color}">'
                         f'{display}</text>')
        # 行合计
        x = row_label_w + len(cols) * cell_w
        parts.append(f'<rect x="{x:.1f}" y="{y}" '
                     f'width="{cell_w:.1f}" height="{cell_h}" '
                     f'fill="#f1f5f9" stroke="white" stroke-width="1"/>')
        parts.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + cell_h / 2 + 4}" '
                     f'text-anchor="middle" font-size="10" font-weight="600" '
                     f'fill="{_TEXT}">{row_sums[i]}</text>')

    # 合计行
    y = y_base + len(rows) * cell_h
    parts.append(f'<text x="{row_label_w - 6}" y="{y + cell_h / 2 + 4}" '
                 f'text-anchor="end" font-size="10" font-weight="600" fill="{_TEXT}">'
                 f'合计</text>')
    for j in range(len(cols)):
        x = row_label_w + j * cell_w
        parts.append(f'<rect x="{x:.1f}" y="{y}" '
                     f'width="{cell_w:.1f}" height="{cell_h}" '
                     f'fill="#f1f5f9" stroke="white" stroke-width="1"/>')
        parts.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + cell_h / 2 + 4}" '
                     f'text-anchor="middle" font-size="10" font-weight="600" '
                     f'fill="{_TEXT}">{col_sums[j]}</text>')
    # 右下角总计
    x = row_label_w + len(cols) * cell_w
    parts.append(f'<rect x="{x:.1f}" y="{y}" '
                 f'width="{cell_w:.1f}" height="{cell_h}" '
                 f'fill="#e2e8f0" stroke="white" stroke-width="1"/>')
    parts.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + cell_h / 2 + 4}" '
                 f'text-anchor="middle" font-size="11" font-weight="700" '
                 f'fill="{_TEXT}">{grand_total}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 水平条形图（质量评分）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_horizontal_bars(items: list, max_val: float = 100,
                           width: int = 500, title: str = "") -> str:
    """水平条形图 SVG。

    Args:
        items: [{"label": "第1题", "value": 85, "color": "#059669"}, ...]
               color 可选，缺省用 _BLUE。
        max_val: 最大值（归一化基准）。
        width: SVG 宽度。
        title: 标题。
    Returns:
        SVG 字符串。
    """
    if not items:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="40"></svg>'

    label_w = 80
    bar_area = width - label_w - 50  # 右侧留数值空间
    bar_h = 20
    gap = 6
    title_h = 24 if title else 0
    svg_h = title_h + len(items) * (bar_h + gap) + 4

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{width}" height="{svg_h:.0f}" '
                 f'font-family=\'{_FONT}\'>')

    if title:
        parts.append(f'<text x="{width / 2}" y="16" text-anchor="middle" '
                     f'font-size="13" font-weight="600" fill="{_TEXT}">'
                     f'{_esc(title)}</text>')

    for idx, item in enumerate(items):
        y = title_h + idx * (bar_h + gap)
        label = item.get("label", "")
        value = item.get("value", 0)
        color = item.get("color", _BLUE)
        bar_w = (value / max_val * bar_area) if max_val > 0 else 0
        bar_w = max(0, min(bar_area, bar_w))

        # 标签
        parts.append(f'<text x="{label_w - 6}" y="{y + bar_h / 2 + 4}" '
                     f'text-anchor="end" font-size="11" fill="{_TEXT}">'
                     f'{_esc(label)}</text>')
        # 背景轨道
        parts.append(f'<rect x="{label_w}" y="{y}" '
                     f'width="{bar_area}" height="{bar_h}" rx="3" '
                     f'fill="#f1f5f9"/>')
        # 数据条
        if bar_w > 0:
            parts.append(f'<rect x="{label_w}" y="{y}" '
                         f'width="{bar_w:.1f}" height="{bar_h}" rx="3" '
                         f'fill="{_esc(color)}"/>')
        # 数值
        parts.append(f'<text x="{label_w + bar_area + 6}" y="{y + bar_h / 2 + 4}" '
                     f'font-size="11" fill="{_TEXT_MUTED}">'
                     f'{value}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 折线+散点图（难度曲线）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_line_scatter(points: list, width: int = 600, height: int = 200,
                        title: str = "") -> str:
    """折线+散点图 SVG。

    Args:
        points: [{"x": 1, "y": 3.5, "label": "Q1", "size": 2}, ...]
                x=题号, y=难度(0-10), size=分值（控制点大小，可选）。
        width, height: SVG 尺寸。
        title: 标题。
    Returns:
        SVG 字符串。
    """
    if not points:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{width}" height="{height}"></svg>')

    pad_left = 40
    pad_right = 20
    pad_top = 30 if title else 14
    pad_bottom = 30
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    x_vals = [p["x"] for p in points]
    x_min, x_max = min(x_vals), max(x_vals)
    y_min, y_max = 0, 10  # 难度固定 0-10

    def tx(x):
        if x_max == x_min:
            return pad_left + plot_w / 2
        return pad_left + (x - x_min) / (x_max - x_min) * plot_w

    def ty(y):
        return pad_top + (1 - (y - y_min) / (y_max - y_min)) * plot_h

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{width}" height="{height}" '
                 f'font-family=\'{_FONT}\'>')

    if title:
        parts.append(f'<text x="{width / 2}" y="16" text-anchor="middle" '
                     f'font-size="13" font-weight="600" fill="{_TEXT}">'
                     f'{_esc(title)}</text>')

    # Y 轴刻度
    for yv in range(0, 11, 2):
        sy = ty(yv)
        parts.append(f'<line x1="{pad_left}" y1="{sy:.1f}" '
                     f'x2="{pad_left + plot_w}" y2="{sy:.1f}" '
                     f'stroke="{_GRID}" stroke-width="0.5"/>')
        parts.append(f'<text x="{pad_left - 6}" y="{sy + 3:.1f}" '
                     f'text-anchor="end" font-size="9" fill="{_TEXT_MUTED}">'
                     f'{yv}</text>')

    # 参考线: 3.5（简单/中等分界）和 6.5（中等/困难分界）
    for ref_y, ref_label, ref_color in [
        (3.5, "简单/中等", _GREEN),
        (6.5, "中等/困难", _RED),
    ]:
        ry = ty(ref_y)
        parts.append(f'<line x1="{pad_left}" y1="{ry:.1f}" '
                     f'x2="{pad_left + plot_w}" y2="{ry:.1f}" '
                     f'stroke="{ref_color}" stroke-width="1" '
                     f'stroke-dasharray="4,3" opacity="0.6"/>')
        parts.append(f'<text x="{pad_left + plot_w + 2}" y="{ry + 3:.1f}" '
                     f'font-size="8" fill="{ref_color}">{ref_label}</text>')

    # 折线
    if len(points) > 1:
        line_pts = " ".join(f"{tx(p['x']):.1f},{ty(p['y']):.1f}" for p in points)
        parts.append(f'<polyline points="{line_pts}" '
                     f'fill="none" stroke="{_BLUE}" stroke-width="1.5" '
                     f'stroke-linejoin="round"/>')

    # 散点
    for p in points:
        px = tx(p["x"])
        py = ty(p["y"])
        base_r = 3
        size_factor = p.get("size", 2)
        r = base_r + size_factor * 0.6
        r = max(2, min(10, r))
        parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.1f}" '
                     f'fill="{_BLUE}" opacity="0.7"/>')
        # 题号标签（在点下方）
        label = p.get("label", "")
        if label:
            parts.append(f'<text x="{px:.1f}" y="{py + r + 10:.1f}" '
                         f'text-anchor="middle" font-size="8" fill="{_TEXT_MUTED}">'
                         f'{_esc(label)}</text>')

    # X 轴标签
    parts.append(f'<text x="{pad_left + plot_w / 2}" y="{height - 4}" '
                 f'text-anchor="middle" font-size="9" fill="{_TEXT_MUTED}">'
                 f'题号</text>')

    parts.append('</svg>')
    return "\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 环形图（素养占比）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_donut_chart(slices: list, size: int = 180, title: str = "") -> str:
    """环形图 SVG。

    Args:
        slices: [{"label": "科学思维", "value": 0.36, "color": "#2563eb"}, ...]
                value 是 0-1 的占比，合计应为 1.0。
        size: SVG 宽高。
        title: 中心文字（为空则显示总百分比）。
    Returns:
        SVG 字符串。
    """
    if not slices:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"></svg>'

    cx, cy = size / 2, size / 2
    outer_r = size * 0.38
    inner_r = outer_r * 0.55
    label_r = outer_r + 16

    # 默认颜色循环
    default_colors = [_BLUE, _GREEN, _RED, _ORANGE, _PURPLE, "#6366f1", "#0891b2"]

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{size}" height="{size}" '
                 f'font-family=\'{_FONT}\'>')

    total = sum(s.get("value", 0) for s in slices)
    if total <= 0:
        parts.append('</svg>')
        return "\n".join(parts)

    angle = -math.pi / 2  # 从 12 点钟方向开始

    for idx, s in enumerate(slices):
        value = s.get("value", 0)
        if value <= 0:
            continue
        frac = value / total
        sweep = frac * 2 * math.pi
        color = s.get("color", default_colors[idx % len(default_colors)])
        label = s.get("label", "")

        end_angle = angle + sweep

        # F-004 修复：单扇区 100% 时 SVG arc 起终点重合会渲染为空
        if frac >= 0.9999:
            mid_r = (outer_r + inner_r) / 2
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{mid_r:.2f}" fill="none" '
                         f'stroke="{_esc(color)}" stroke-width="{outer_r - inner_r:.2f}"/>')
        else:
            x1_o = cx + outer_r * math.cos(angle)
            y1_o = cy + outer_r * math.sin(angle)
            x1_i = cx + inner_r * math.cos(angle)
            y1_i = cy + inner_r * math.sin(angle)

            x2_o = cx + outer_r * math.cos(end_angle)
            y2_o = cy + outer_r * math.sin(end_angle)
            x2_i = cx + inner_r * math.cos(end_angle)
            y2_i = cy + inner_r * math.sin(end_angle)

            large_arc = 1 if sweep > math.pi else 0

            d = (f"M {x1_o:.2f} {y1_o:.2f} "
                 f"A {outer_r:.2f} {outer_r:.2f} 0 {large_arc} 1 {x2_o:.2f} {y2_o:.2f} "
                 f"L {x2_i:.2f} {y2_i:.2f} "
                 f"A {inner_r:.2f} {inner_r:.2f} 0 {large_arc} 0 {x1_i:.2f} {y1_i:.2f} "
                 f"Z")
            parts.append(f'<path d="{d}" fill="{_esc(color)}" stroke="white" stroke-width="1.5"/>')

        # 标签（弧中点方向）
        mid_angle = angle + sweep / 2
        lx = cx + label_r * math.cos(mid_angle)
        ly = cy + label_r * math.sin(mid_angle)
        anchor = "start" if math.cos(mid_angle) >= 0 else "end"
        pct_text = f"{frac * 100:.0f}%"
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
                     f'font-size="9" fill="{_TEXT}">'
                     f'{_esc(label)} {pct_text}</text>')

        angle = end_angle

    # 中心文字
    center_text = title if title else ""
    if center_text:
        parts.append(f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" '
                     f'font-size="11" font-weight="600" fill="{_TEXT}">'
                     f'{_esc(center_text)}</text>')

    parts.append('</svg>')
    return "\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. 分组柱状图（选项难度对比）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_grouped_bars(groups: list, width: int = 300, height: int = 150,
                        title: str = "") -> str:
    """分组柱状图 SVG（用于选项难度对比）。

    Args:
        groups: [{"label": "A", "value": 6.0, "color": "#dc2626"}, ...]
        width, height: SVG 尺寸。
        title: 标题。
    Returns:
        SVG 字符串。
    """
    if not groups:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{width}" height="{height}"></svg>')

    pad_left = 30
    pad_right = 10
    pad_top = 28 if title else 12
    pad_bottom = 28
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    values = [g.get("value", 0) for g in groups]
    max_val = max(values) if values else 1
    if max_val <= 0:
        max_val = 1

    n = len(groups)
    bar_gap = 6
    bar_w = (plot_w - bar_gap * (n + 1)) / n if n > 0 else plot_w
    bar_w = min(bar_w, 40)  # 最大宽度上限
    total_bars_w = n * bar_w + (n - 1) * bar_gap
    x_offset = pad_left + (plot_w - total_bars_w) / 2

    parts: List[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{width}" height="{height}" '
                 f'font-family=\'{_FONT}\'>')

    if title:
        parts.append(f'<text x="{width / 2}" y="18" text-anchor="middle" '
                     f'font-size="12" font-weight="600" fill="{_TEXT}">'
                     f'{_esc(title)}</text>')

    # 基线
    base_y = pad_top + plot_h
    parts.append(f'<line x1="{pad_left}" y1="{base_y}" '
                 f'x2="{pad_left + plot_w}" y2="{base_y}" '
                 f'stroke="{_GRID}" stroke-width="1"/>')

    # Y 轴参考线
    for frac in (0.25, 0.5, 0.75, 1.0):
        gy = base_y - frac * plot_h
        parts.append(f'<line x1="{pad_left}" y1="{gy:.1f}" '
                     f'x2="{pad_left + plot_w}" y2="{gy:.1f}" '
                     f'stroke="{_GRID}" stroke-width="0.5" stroke-dasharray="3,3"/>')

    for idx, g in enumerate(groups):
        val = g.get("value", 0)
        color = g.get("color", _BLUE)
        label = g.get("label", "")
        bx = x_offset + idx * (bar_w + bar_gap)
        bh = (val / max_val) * plot_h if max_val > 0 else 0
        bh = max(0, bh)
        by = base_y - bh

        # 柱
        if bh > 0:
            parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" '
                         f'width="{bar_w:.1f}" height="{bh:.1f}" rx="2" '
                         f'fill="{_esc(color)}"/>')

        # 数值（柱顶）
        parts.append(f'<text x="{bx + bar_w / 2:.1f}" y="{by - 4:.1f}" '
                     f'text-anchor="middle" font-size="9" fill="{_TEXT_MUTED}">'
                     f'{val}</text>')

        # 标签（基线下方）
        parts.append(f'<text x="{bx + bar_w / 2:.1f}" y="{base_y + 16}" '
                     f'text-anchor="middle" font-size="10" fill="{_TEXT}">'
                     f'{_esc(label)}</text>')

    parts.append('</svg>')
    return "\n".join(parts)
