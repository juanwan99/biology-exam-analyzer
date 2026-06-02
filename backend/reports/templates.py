import html
from datetime import datetime
"""报告 HTML 模板渲染函数。"""

def _render_difficulty_section(data: dict, insights: dict, charts: dict, mode: str) -> str:
    """渲染难度分析 section"""
    html = '<h2>二、难度分析</h2>'
    html += f'<div class="chart"><img src="{charts["curve"]}" alt="难度曲线"></div>'
    html += f'<div class="chart"><img src="{charts["distribution"]}" alt="难度分布"></div>'

    if mode == "full":
        if "gradient" in charts:
            html += f'<div class="chart"><img src="{charts["gradient"]}" alt="难度梯度"></div>'
        if "radar" in charts:
            html += f'<div class="chart"><img src="{charts["radar"]}" alt="特征雷达"></div>'

    analysis = insights.get("difficulty_analysis", "")
    if analysis:
        if mode == "brief":
            # 精简档取首句
            first_sentence = analysis.split("。")[0] + "。" if "。" in analysis else analysis
            html += f'<div class="insight-box">{first_sentence}</div>'
        else:
            html += f'<div class="insight-box">{analysis}</div>'

    return html




def _render_knowledge_section(data: dict, insights: dict, charts: dict, mode: str) -> str:
    """渲染知识覆盖 section"""
    html = '<h2>三、知识覆盖</h2>'

    # Top10 知识点表
    top_points = data["knowledge"].get("top_points", [])
    if top_points:
        html += '<table><thead><tr><th>排名</th><th>知识点</th><th>分值权重</th></tr></thead><tbody>'
        for i, kp in enumerate(top_points[:10], 1):
            html += f'<tr><td>{i}</td><td>{kp.get("name", "")}</td><td>{kp.get("weighted_score", 0):.1f}</td></tr>'
        html += '</tbody></table>'

    # 教材饼图（brief+full 都渲染）
    if "knowledge_pie" in charts:
        html += f'<div class="chart"><img src="{charts["knowledge_pie"]}" alt="教材分布"></div>'

    # 教材章节明细表（full 模式）
    textbook = data["knowledge"].get("textbook_distribution", {})
    if textbook and mode == "full":
        html += '<table><thead><tr><th>教材册别</th><th>分值权重</th><th>占比</th></tr></thead><tbody>'
        for book, info in textbook.items():
            if isinstance(info, dict):
                score = info.get("weighted_score", 0)
                pct = info.get("percentage", 0)
                html += f'<tr><td>{book}</td><td>{score:.1f}</td><td>{pct:.1f}%</td></tr>'
        html += '</tbody></table>'

    analysis = insights.get("knowledge_analysis", "")
    if analysis:
        html += f'<div class="insight-box">{analysis}</div>'

    return html




def _render_bloom_section(data: dict, insights: dict, charts: dict, mode: str) -> str:
    """渲染 Bloom 认知层级 section"""
    html = '<h2>四、Bloom 认知层级</h2>'
    html += f'<div class="chart"><img src="{charts["bloom"]}" alt="Bloom分布"></div>'

    analysis = insights.get("bloom_analysis", "")
    if analysis:
        html += f'<div class="insight-box">{analysis}</div>'

    return html




def _render_competency_section(data: dict, insights: dict, charts: dict, mode: str) -> str:
    """渲染核心素养 section"""
    html = '<h2>五、核心素养</h2>'
    html += f'<div class="chart"><img src="{charts["competency_pie"]}" alt="素养分布"></div>'

    if mode == "full" and "competency_bar" in charts:
        html += f'<div class="chart"><img src="{charts["competency_bar"]}" alt="素养细分"></div>'

    analysis = insights.get("competency_analysis", "")
    if analysis:
        html += f'<div class="insight-box">{analysis}</div>'

    return html




def _render_questions_section(data: dict, insights: dict, mode: str) -> str:
    """渲染逐题详情 section"""
    BLOOM_MAP = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}
    questions = data["questions"]
    comments = insights.get("question_comments", {})

    html = '<h2>七、逐题详情</h2>'

    if mode == "brief":
        # 精简表格
        html += '<table><thead><tr><th>题号</th><th>分值</th><th>难度</th><th>Bloom</th><th>知识点</th><th>主素养</th></tr></thead><tbody>'
        for q in questions:
            diff_class = "difficulty-low"
            if q["difficulty"] >= 7:
                diff_class = "difficulty-high"
            elif q["difficulty"] >= 4:
                diff_class = "difficulty-medium"
            kps = ", ".join(q.get("knowledge_points", [])[:3])
            bloom_label = BLOOM_MAP.get(q.get("bloom", 3), "应用")
            html += (f'<tr><td>{q["id"]}</td><td>{q["total_score"]}</td>'
                     f'<td class="{diff_class}">{q["difficulty"]:.1f}</td>'
                     f'<td>{bloom_label}</td><td>{kps}</td>'
                     f'<td>{q.get("primary_competency", "")}</td></tr>')
        html += '</tbody></table>'
    else:
        # 完整卡片
        for q in questions:
            diff_class = "difficulty-low"
            if q["difficulty"] >= 7:
                diff_class = "difficulty-high"
            elif q["difficulty"] >= 4:
                diff_class = "difficulty-medium"
            bloom_label = BLOOM_MAP.get(q.get("bloom", 3), "应用")
            kps = ", ".join(q.get("knowledge_points", []))
            mistakes = ", ".join(q.get("common_mistakes", [])[:3])

            qs = q.get("quality_score")
            qs_text = ""
            if qs is not None:
                qs_labels = {1: "严重缺陷", 2: "需修改", 3: "基本合格", 4: "较好", 5: "优秀"}
                qs_colors = {1: "#dc2626", 2: "#ea580c", 3: "#ca8a04", 4: "#16a34a", 5: "#16a34a"}
                qs_text = f' | <span style="color:{qs_colors.get(qs, "#333")}">质量: {qs}/5 {qs_labels.get(qs, "")}</span>'

            html += f'''<div class="question-card">
<h4>题目 {q["id"]}（{q["total_score"]}分）</h4>
<div class="meta">
难度: <span class="{diff_class}">{q["difficulty"]:.1f} {q["difficulty_label"]}</span> |
Bloom: {bloom_label} | 素养: {q.get("primary_competency", "")} ({q.get("competency_level", "")}){qs_text}
</div>
<p><strong>知识点:</strong> {kps}</p>'''

            if q.get("detailed_analysis"):
                html += f'<p><strong>解析:</strong> {q["detailed_analysis"][:200]}</p>'
            if mistakes:
                html += f'<p><strong>常见错误:</strong> {mistakes}</p>'

            # 7 维 reason（CR-02 修复：full 模式展示特征分析理由）
            reasons = []
            if q.get("bloom_reason"):
                reasons.append(f"Bloom层级: {q['bloom_reason']}")
            if q.get("steps_detail"):
                reasons.append(f"推理步数: {q['steps_detail']}")
            if q.get("breadth_reason"):
                reasons.append(f"知识跨度: {q['breadth_reason']}")
            if q.get("density_reason"):
                reasons.append(f"信息密度: {q['density_reason']}")
            if q.get("novelty_reason"):
                reasons.append(f"情境新颖度: {q['novelty_reason']}")
            if q.get("representation_reason"):
                reasons.append(f"表征复杂度: {q['representation_reason']}")
            if reasons:
                html += '<p><strong>特征分析:</strong></p><ul>'
                for r in reasons:
                    html += f'<li style="font-size:12px;color:#475569">{r}</li>'
                html += '</ul>'

            # 命题质量审查（v3: 从 feature_extractor 合并）
            quality_items = []
            if q.get("quality_scientific"):
                quality_items.append(f"科学性: {q['quality_scientific']}")
            if q.get("quality_normative"):
                quality_items.append(f"规范性: {q['quality_normative']}")
            if q.get("quality_language"):
                quality_items.append(f"语言表述: {q['quality_language']}")
            if q.get("quality_context"):
                quality_items.append(f"情境设计: {q['quality_context']}")
            if quality_items:
                html += '<p><strong>命题质量:</strong></p><ul>'
                for qi in quality_items:
                    html += f'<li style="font-size:12px;color:#475569">{qi}</li>'
                html += '</ul>'

            # 教师点评（v3: 从 feature_extractor 合并，替代原 report_insights 逐题点评）
            comment = q.get("teacher_comment", "") or comments.get(str(q["id"]), "")
            if comment:
                html += f'<div class="comment"><strong>教师点评:</strong> {comment}</div>'

            html += '</div>'

    return html




def _render_diagnostics_section(data: dict, charts: dict) -> str:
    """渲染整卷质量诊断 section"""
    diag = data.get("diagnostics", {})
    if not diag:
        return ""
    html = '<div class="section"><h2>整卷质量诊断</h2>'

    # 综合评价
    overall = diag.get("overall_rating", "未知")
    css_map = {"优秀": "rating-excellent", "良好": "rating-good",
               "一般": "rating-fair", "待改进": "rating-poor"}
    css_class = css_map.get(overall, "")
    html += f'<p>综合评价：<span class="{css_class}">{overall}</span></p>'

    # 素养雷达图
    if "competency_radar" in charts:
        html += f'<div class="chart"><img src="{charts["competency_radar"]}" alt="素养雷达"></div>'

    # 题型分布饼图
    if "type_distribution" in charts:
        html += f'<div class="chart"><img src="{charts["type_distribution"]}" alt="题型分布"></div>'

    # 知识点热力图
    if "knowledge_heatmap" in charts:
        html += f'<div class="chart"><img src="{charts["knowledge_heatmap"]}" alt="知识点热力图"></div>'

    # 难度梯度
    gradient = diag.get("gradient", {})
    if gradient.get("rating"):
        html += f'<div class="diagnosis-card"><h4>难度梯度</h4><p>评价: {gradient["rating"]}</p>'
        actual = gradient.get("actual", {})
        html += f'<p>实际分布: 简单{actual.get("简单",0):.0%} / 中等{actual.get("中等",0):.0%} / 困难{actual.get("困难",0):.0%}</p></div>'

    # 素养均衡
    balance = diag.get("competency_balance", {})
    if balance.get("balance"):
        html += f'<div class="diagnosis-card"><h4>素养均衡度</h4><p>{balance["balance"]}</p></div>'

    # 难度离散度
    disc = diag.get("difficulty_spread", {})
    if disc.get("spread_level"):
        html += f'<div class="diagnosis-card"><h4>难度离散度</h4><p>{disc["spread_level"]}（标准差: {disc.get("difficulty_stdev", 0):.2f}）</p></div>'

    html += '</div>'
    return html


def _render_quality_overview_section(data: dict) -> str:
    """渲染命题质量总览 section — 按严重程度汇总所有题的质量问题。"""
    questions = data["questions"]

    # 分类：硬伤（score 1-2）、待改进（score 3）、良好（score 4-5）、未评估
    critical = []   # 硬伤
    improve = []    # 待改进
    good = []       # 良好
    no_score = []   # 未评估

    for q in questions:
        qs = q.get("quality_score")
        qid = q["id"]
        issues = []
        for key, label in [("quality_scientific", "科学性"), ("quality_normative", "规范性"),
                           ("quality_language", "语言"), ("quality_context", "情境")]:
            text = q.get(key, "")
            if text and "无明显问题" not in text and "无问题" not in text:
                issues.append(f"{label}: {text}")

        entry = {"id": qid, "score": qs, "issues": issues}
        if qs is None:
            no_score.append(entry)
        elif qs <= 2:
            critical.append(entry)
        elif qs == 3:
            improve.append(entry)
        else:
            good.append(entry)

    # 统计
    total = len(questions)
    avg_score = sum(q.get("quality_score", 0) for q in questions if q.get("quality_score")) / max(1, sum(1 for q in questions if q.get("quality_score")))

    html = '<h2>六、命题质量总览</h2>'

    # 总评卡片
    html += f'''<div class="metrics-grid">
<div class="metric-card"><div class="metric-value" style="color:#dc2626">{len(critical)}</div><div class="metric-label">硬伤（必须修改）</div></div>
<div class="metric-card"><div class="metric-value" style="color:#ca8a04">{len(improve)}</div><div class="metric-label">待改进</div></div>
<div class="metric-card"><div class="metric-value" style="color:#16a34a">{len(good)}</div><div class="metric-label">良好</div></div>
<div class="metric-card"><div class="metric-value">{avg_score:.1f}/5</div><div class="metric-label">平均质量评分</div></div>
</div>'''

    # 硬伤列表（红色高亮）
    if critical:
        html += '<h3 style="color:#dc2626;margin-top:20px">⚠ 硬伤（quality_score ≤ 2，必须修改）</h3>'
        for entry in critical:
            html += f'<div class="rec-item high"><strong>题目 {entry["id"]}</strong>（评分 {entry["score"]}/5）'
            if entry["issues"]:
                html += '<ul style="margin:5px 0">'
                for issue in entry["issues"]:
                    html += f'<li style="font-size:12px">{issue}</li>'
                html += '</ul>'
            html += '</div>'

    # 待改进列表（黄色）
    if improve:
        html += '<h3 style="color:#ca8a04;margin-top:20px">△ 待改进（quality_score = 3，建议修改）</h3>'
        for entry in improve:
            html += f'<div class="rec-item medium"><strong>题目 {entry["id"]}</strong>（评分 {entry["score"]}/5）'
            if entry["issues"]:
                html += '<ul style="margin:5px 0">'
                for issue in entry["issues"]:
                    html += f'<li style="font-size:12px">{issue}</li>'
                html += '</ul>'
            html += '</div>'

    # 良好的只列题号
    if good:
        good_ids = ", ".join(str(e["id"]) for e in good)
        html += f'<p style="color:#16a34a;margin-top:15px"><strong>✓ 质量良好：</strong>题目 {good_ids}</p>'

    if no_score:
        no_ids = ", ".join(str(e["id"]) for e in no_score)
        html += f'<p style="color:#94a3b8;margin-top:10px"><strong>未评估：</strong>题目 {no_ids}（特征提取不完整）</p>'

    return html




def _render_recommendations_section(insights: dict, mode: str) -> str:
    """渲染综合建议 section"""
    html = '<h2>八、综合建议</h2>'
    recs = insights.get("recommendations", [])

    if mode == "brief":
        recs = recs[:3]  # 精简档 top 3

    for rec in recs:
        priority = rec.get("priority", "medium")
        html += f'''<div class="rec-item {priority}">
<span class="rec-category">[{rec.get("category", "")}]</span> {rec.get("content", "")}
</div>'''

    return html




def _render_html(data: dict, insights: dict, charts: dict, mode: str) -> str:
    """组装完整 HTML 报告。"""
    exam = data["exam_info"]
    metrics = data["metrics"]

    css = _get_report_css()

    # 封面
    cover = f'''<div class="cover">
<h1>生物试卷质量评估报告</h1>
<p class="subtitle">{exam["name"]}</p>
<p>题目总数: {exam["total_questions"]} | 总分: {exam["total_score"]}分 |
模式: {"深度" if exam["mode"]=="deep" else "快速"} |
档位: {"完整版" if mode=="full" else "精简版"}</p>
<p>生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
</div>'''

    # 一、试卷总评
    section1 = f'''<h2>一、试卷总评</h2>
<div class="metrics-grid">
<div class="metric-card"><div class="metric-value">{metrics["avg_difficulty"]:.2f}</div><div class="metric-label">平均难度（分值加权）</div></div>
<div class="metric-card"><div class="metric-value">{metrics["avg_cognitive_level"]:.2f}</div><div class="metric-label">平均认知层级</div></div>
<div class="metric-card"><div class="metric-value">{exam["total_score"]}</div><div class="metric-label">总分</div></div>
<div class="metric-card"><div class="metric-value">{exam["total_questions"]}</div><div class="metric-label">题目数</div></div>
</div>
<div class="insight-box">{insights.get("overall_assessment", "")}</div>'''

    sections = [css, cover, section1]
    sections.append(_render_difficulty_section(data, insights, charts, mode))
    sections.append(_render_knowledge_section(data, insights, charts, mode))
    sections.append(_render_bloom_section(data, insights, charts, mode))
    sections.append(_render_competency_section(data, insights, charts, mode))
    sections.append(_render_diagnostics_section(data, charts))
    sections.append(_render_quality_overview_section(data))
    sections.append(_render_questions_section(data, insights, mode))
    sections.append(_render_recommendations_section(insights, mode))

    # Footer
    sections.append('''<div class="footer">
<p>本报告由 生物试卷智能分析系统 自动生成</p>
<p>基于《普通高中生物学课程标准（2017年版2020修订）》</p>
</div>''')

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>试卷评估报告</title></head><body>{"".join(sections)}</body></html>'''


