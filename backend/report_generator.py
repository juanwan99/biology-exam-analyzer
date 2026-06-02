"""
可视化报告生成器
使用 plotly 生成交互式图表，导出为 PDF 报告。
SVG 图表（svg_charts 模块）在可用时优先内联，兼容 WeasyPrint。
"""
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict, Any
import json
from datetime import datetime
from pathlib import Path
import base64
from io import BytesIO
from weasyprint import HTML, CSS
from logger import get_logger

try:
    from svg_charts import (render_radar_chart, render_heatmap, render_horizontal_bars,
                            render_line_scatter, render_donut_chart, render_grouped_bars)
    HAS_SVG_CHARTS = True
except ImportError:
    HAS_SVG_CHARTS = False

logger = get_logger()


class ReportGenerator:
    """可视化报告生成器"""

    def __init__(self):
        """初始化报告生成器"""
        logger.info("报告生成器初始化完成")

    def generate_difficulty_curve(
        self,
        questions_difficulty: List[Dict[str, Any]]
    ) -> go.Figure:
        """
        生成难度曲线图（折线图）

        Args:
            questions_difficulty: [
                {"question_id": 1, "final_difficulty": 6.5, "difficulty_label": "中等"},
                ...
            ]

        Returns:
            plotly Figure对象
        """
        logger.info(f"[图表1] 生成难度曲线图，题目数: {len(questions_difficulty)}")

        # 提取数据
        question_ids = [q["question_id"] for q in questions_difficulty]
        difficulties = [q["final_difficulty"] for q in questions_difficulty]
        labels = [q["difficulty_label"] for q in questions_difficulty]

        # 创建折线图
        fig = go.Figure()

        # 添加折线
        fig.add_trace(go.Scatter(
            x=question_ids,
            y=difficulties,
            mode='lines+markers',
            name='难度系数',
            line=dict(color='#3b82f6', width=2),
            marker=dict(size=8, color=difficulties, colorscale='RdYlGn_r', showscale=True,
                       colorbar=dict(title="难度")),
            text=labels,
            hovertemplate='<b>题目 %{x}</b><br>难度: %{y:.2f}<br>%{text}<extra></extra>'
        ))

        # 添加难度区间背景
        fig.add_hrect(y0=0, y1=3.5, fillcolor="green", opacity=0.1, line_width=0,
                      annotation_text="简单", annotation_position="top left")
        fig.add_hrect(y0=3.5, y1=6.5, fillcolor="yellow", opacity=0.1, line_width=0,
                      annotation_text="中等", annotation_position="top left")
        fig.add_hrect(y0=6.5, y1=10, fillcolor="red", opacity=0.1, line_width=0,
                      annotation_text="困难", annotation_position="top left")

        # 布局设置
        fig.update_layout(
            title={
                'text': '试卷难度曲线',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'SimHei'}
            },
            xaxis_title='题号',
            yaxis_title='难度系数（0-10）',
            yaxis=dict(range=[0, 10]),
            hovermode='x unified',
            template='plotly_white',
            font=dict(family='SimHei', size=12),
            height=400
        )

        logger.info("[图表1] 难度曲线图生成完成")
        return fig

    def generate_difficulty_distribution(
        self,
        questions_difficulty: List[Dict[str, Any]]
    ) -> go.Figure:
        """
        生成难度分布直方图（基于分值）

        Args:
            questions_difficulty: 题目难度列表（包含score_distribution_by_difficulty字段）

        Returns:
            plotly Figure对象
        """
        logger.info(f"[图表2] 生成难度分布直方图")

        # 统计各难度等级分值（优先使用分值分配，回退到题数统计）
        easy_score = 0.0
        medium_score = 0.0
        hard_score = 0.0

        has_score_distribution = any(q.get("score_distribution_by_difficulty") for q in questions_difficulty)

        if has_score_distribution:
            # 基于分值分配
            for q in questions_difficulty:
                score_dist = q.get("score_distribution_by_difficulty", {})
                easy_score += score_dist.get("简单", 0.0)
                medium_score += score_dist.get("中等", 0.0)
                hard_score += score_dist.get("困难", 0.0)

            total_score = easy_score + medium_score + hard_score
            logger.info(f"[图表2] 难度分布（分值）: 简单{easy_score}分, 中等{medium_score}分, 困难{hard_score}分, 总计{total_score}分")

            # 创建柱状图（显示分值）
            fig = go.Figure(data=[
                go.Bar(
                    x=['简单 (0-3.5)', '中等 (3.5-6.5)', '困难 (6.5-10)'],
                    y=[easy_score, medium_score, hard_score],
                    text=[f"{easy_score:.1f}分<br>({easy_score/total_score*100:.1f}%)" if total_score > 0 else f"{easy_score:.1f}分",
                          f"{medium_score:.1f}分<br>({medium_score/total_score*100:.1f}%)" if total_score > 0 else f"{medium_score:.1f}分",
                          f"{hard_score:.1f}分<br>({hard_score/total_score*100:.1f}%)" if total_score > 0 else f"{hard_score:.1f}分"],
                    textposition='auto',
                    marker=dict(color=['#22c55e', '#eab308', '#ef4444']),
                    hovertemplate='<b>%{x}</b><br>分值: %{y:.1f}分<extra></extra>'
                )
            ])

            yaxis_title = '分值（分）'
        else:
            # 回退：基于题目数量
            easy_count = sum(1 for q in questions_difficulty if q.get("final_difficulty", 5.0) <= 3.5)
            medium_count = sum(1 for q in questions_difficulty if 3.5 < q.get("final_difficulty", 5.0) <= 6.5)
            hard_count = sum(1 for q in questions_difficulty if q.get("final_difficulty", 5.0) > 6.5)

            logger.warning(f"[图表2] 未找到score_distribution_by_difficulty，使用题目数量统计")
            logger.info(f"[图表2] 难度分布（题数）: 简单{easy_count}题, 中等{medium_count}题, 困难{hard_count}题")

            fig = go.Figure(data=[
                go.Bar(
                    x=['简单 (0-3.5)', '中等 (3.5-6.5)', '困难 (6.5-10)'],
                    y=[easy_count, medium_count, hard_count],
                    text=[easy_count, medium_count, hard_count],
                    textposition='auto',
                    marker=dict(color=['#22c55e', '#eab308', '#ef4444']),
                    hovertemplate='<b>%{x}</b><br>题目数: %{y}<extra></extra>'
                )
            ])

            yaxis_title = '题目数量'

        # 布局设置
        fig.update_layout(
            title={
                'text': '难度分布统计',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'SimHei'}
            },
            xaxis_title='难度等级',
            yaxis_title=yaxis_title,
            template='plotly_white',
            font=dict(family='SimHei', size=12),
            height=400
        )

        return fig

    def generate_dimension_radar(
        self,
        question_difficulty: Dict[str, Any]
    ) -> go.Figure:
        """
        生成单道题目的难度维度雷达图

        Args:
            question_difficulty: {
                "question_id": 7,
                "knowledge_complexity": 7.0,
                "cognitive_level": 8.0,
                "info_extraction": 7.0,
                "reasoning_steps": 4.0
            }

        Returns:
            plotly Figure对象
        """
        logger.info(f"[图表3] 生成题目 {question_difficulty.get('question_id')} 的维度雷达图")

        # 提取数据
        categories = ['知识复杂度', '认知层级', '信息提取', '推理步骤']
        values = [
            question_difficulty.get("knowledge_complexity", 0),
            question_difficulty.get("cognitive_level", 0),
            question_difficulty.get("info_extraction", 0),
            question_difficulty.get("reasoning_steps", 0)
        ]

        # 闭合雷达图
        values_closed = values + [values[0]]
        categories_closed = categories + [categories[0]]

        # 创建雷达图
        fig = go.Figure()

        fig.add_trace(go.Scatterpolar(
            r=values_closed,
            theta=categories_closed,
            fill='toself',
            name=f'题目 {question_difficulty.get("question_id")}',
            line=dict(color='#3b82f6', width=2),
            fillcolor='rgba(59, 130, 246, 0.3)',
            hovertemplate='<b>%{theta}</b><br>分数: %{r:.2f}<extra></extra>'
        ))

        # 布局设置
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 10],
                    tickfont=dict(size=10)
                )
            ),
            title={
                'text': f'题目 {question_difficulty.get("question_id")} 难度维度分析',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 18, 'family': 'SimHei'}
            },
            font=dict(family='SimHei', size=12),
            height=400,
            showlegend=False
        )

        return fig

    def generate_competency_pie(
        self,
        competency_summary: Dict[str, Any]
    ) -> go.Figure:
        """
        生成核心素养覆盖饼图

        Args:
            competency_summary: {
                "生命观念": {"总权重": 4.8, "占比": 0.32},
                "科学思维": {"总权重": 7.5, "占比": 0.50},
                "科学探究": {"总权重": 1.8, "占比": 0.12},
                "社会责任": {"总权重": 0.9, "占比": 0.06}
            }

        Returns:
            plotly Figure对象
        """
        logger.info(f"[图表4] 生成核心素养覆盖饼图")

        # 过滤出真正的素养（排除primary_distribution等）
        valid_competencies = ["生命观念", "科学思维", "科学探究", "社会责任"]
        competencies = [c for c in valid_competencies if c in competency_summary and isinstance(competency_summary[c], dict)]

        # 提取数据，增加错误处理
        weights = []
        percentages = []
        for c in competencies:
            comp_data = competency_summary[c]
            if isinstance(comp_data, dict):
                weights.append(comp_data.get("总权重", 0))
                percentages.append(comp_data.get("占比", 0) * 100)
            else:
                weights.append(0)
                percentages.append(0)

        # 创建饼图
        fig = go.Figure(data=[go.Pie(
            labels=competencies,
            values=weights,
            text=[f"{p:.1f}%" for p in percentages],
            textposition='inside',
            textfont=dict(size=14, color='white'),
            marker=dict(colors=['#3b82f6', '#10b981', '#f59e0b', '#ef4444']),
            hovertemplate='<b>%{label}</b><br>权重: %{value:.2f}<br>占比: %{percent}<extra></extra>'
        )])

        # 布局设置
        fig.update_layout(
            title={
                'text': '核心素养覆盖分布',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'SimHei'}
            },
            font=dict(family='SimHei', size=12),
            height=400,
            showlegend=True
        )

        logger.info(f"[图表4] 素养分布: {dict(zip(competencies, percentages))}")
        return fig

    def generate_competency_bar(
        self,
        competency_summary: Dict[str, Any]
    ) -> go.Figure:
        """
        生成核心素养细分柱状图

        Args:
            competency_summary: {
                "生命观念": {
                    "细分": {"结构与功能观": 5, "稳态与平衡观": 3, ...}
                },
                ...
            }

        Returns:
            plotly Figure对象
        """
        logger.info(f"[图表5] 生成核心素养细分柱状图")

        # 提取所有细分维度
        all_dimensions = []
        all_counts = []
        all_colors = []

        color_map = {
            "生命观念": '#3b82f6',
            "科学思维": '#10b981',
            "科学探究": '#f59e0b',
            "社会责任": '#ef4444'
        }

        for comp, data in competency_summary.items():
            sub_dims = data.get("细分", {})
            for dim, count in sub_dims.items():
                all_dimensions.append(f"{comp}-{dim}")
                all_counts.append(count)
                all_colors.append(color_map.get(comp, '#6b7280'))

        # 创建柱状图
        fig = go.Figure(data=[
            go.Bar(
                x=all_dimensions,
                y=all_counts,
                text=all_counts,
                textposition='auto',
                marker=dict(color=all_colors),
                hovertemplate='<b>%{x}</b><br>题目数: %{y}<extra></extra>'
            )
        ])

        # 布局设置
        fig.update_layout(
            title={
                'text': '核心素养细分维度分布',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'SimHei'}
            },
            xaxis_title='素养维度',
            yaxis_title='题目数量',
            xaxis=dict(tickangle=-45),
            template='plotly_white',
            font=dict(family='SimHei', size=12),
            height=500
        )

        return fig

    def generate_difficulty_gradient(
        self,
        questions_difficulty: List[Dict[str, Any]]
    ) -> go.Figure:
        """
        生成试卷难度梯度评估条形图

        分析试卷前、中、后三段的平均难度

        Args:
            questions_difficulty: 题目难度列表

        Returns:
            plotly Figure对象
        """
        logger.info(f"[图表6] 生成难度梯度评估")

        total = len(questions_difficulty)
        part_size = total // 3

        # 分三段
        part1 = questions_difficulty[:part_size]
        part2 = questions_difficulty[part_size:part_size*2]
        part3 = questions_difficulty[part_size*2:]

        # 计算平均难度（分值加权，fallback 简单平均）
        def _weighted_avg(part):
            w = sum(q.get("total_score", 0) for q in part)
            if w > 0:
                return sum(q["final_difficulty"] * q.get("total_score", 0) for q in part) / w
            return sum(q["final_difficulty"] for q in part) / len(part) if part else 0

        avg1 = _weighted_avg(part1)
        avg2 = _weighted_avg(part2)
        avg3 = _weighted_avg(part3)

        # 创建条形图
        fig = go.Figure(data=[
            go.Bar(
                x=['前段 (1-8题)', '中段 (9-16题)', '后段 (17-25题)'],
                y=[avg1, avg2, avg3],
                text=[f"{avg1:.2f}", f"{avg2:.2f}", f"{avg3:.2f}"],
                textposition='auto',
                marker=dict(color=[avg1, avg2, avg3], colorscale='RdYlGn_r', showscale=True,
                           colorbar=dict(title="难度")),
                hovertemplate='<b>%{x}</b><br>平均难度: %{y:.2f}<extra></extra>'
            )
        ])

        # 判断难度梯度类型
        if avg3 > avg2 > avg1:
            gradient_type = "前易后难（递增）"
        elif avg1 > avg2 > avg3:
            gradient_type = "前难后易（递减）"
        elif abs(avg1 - avg2) < 0.5 and abs(avg2 - avg3) < 0.5:
            gradient_type = "难度均衡"
        else:
            gradient_type = "难度波动较大"

        # 布局设置
        fig.update_layout(
            title={
                'text': f'试卷难度梯度分析 - {gradient_type}',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'SimHei'}
            },
            xaxis_title='试卷段落',
            yaxis_title='平均难度',
            yaxis=dict(range=[0, 10]),
            template='plotly_white',
            font=dict(family='SimHei', size=12),
            height=400
        )

        logger.info(f"[图表6] 难度梯度: {gradient_type}, 前{avg1:.2f} 中{avg2:.2f} 后{avg3:.2f}")
        return fig

    def generate_knowledge_pie(self, textbook_distribution: Dict[str, Any]) -> go.Figure:
        """生成教材知识点分布饼图"""
        labels = []
        values = []
        for book, info in textbook_distribution.items():
            if isinstance(info, dict) and info.get("weighted_score", 0) > 0:
                labels.append(book)
                values.append(info["weighted_score"])
        if not labels:
            labels = ["无数据"]
            values = [1]
        fig = go.Figure(data=[go.Pie(
            labels=labels, values=values,
            textposition='inside', textfont=dict(size=12),
            marker=dict(colors=['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']),
            hovertemplate='<b>%{label}</b><br>分值: %{value:.1f}<br>占比: %{percent}<extra></extra>'
        )])
        fig.update_layout(
            title={'text': '教材知识点分值分布', 'x': 0.5,
                   'font': {'size': 18, 'family': 'SimHei'}},
            font=dict(family='SimHei', size=12), height=400, showlegend=True,
        )
        return fig

    def generate_feature_radar(self, avg_per_dimension: Dict[str, float]) -> go.Figure:
        """生成 6 维特征雷达图"""
        DIM_LABELS = {
            "bloom": "Bloom层级", "reasoning_steps": "推理步数",
            "knowledge_breadth": "知识跨度", "info_density": "信息密度",
            "novelty": "情境新颖度", "representation_complexity": "表征复杂度",
        }
        DIM_MAX = {
            "bloom": 6, "reasoning_steps": 10, "knowledge_breadth": 3,
            "info_density": 3, "novelty": 3, "representation_complexity": 3,
        }
        labels = [DIM_LABELS[d] for d in avg_per_dimension if d in DIM_LABELS]
        values = [avg_per_dimension[d] / DIM_MAX.get(d, 1) * 100
                  for d in avg_per_dimension if d in DIM_LABELS]
        values.append(values[0])  # 闭合
        labels.append(labels[0])

        fig = go.Figure(data=go.Scatterpolar(
            r=values, theta=labels, fill='toself',
            line=dict(color='#2d5a3d', width=2),
            fillcolor='rgba(45,90,61,0.15)',
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
            title={'text': '试卷难度特征画像（6维）', 'x': 0.5, 'font': {'size': 18, 'family': 'SimHei'}},
            font=dict(family='SimHei', size=12), height=450, showlegend=False,
        )
        return fig

    def generate_bloom_chart(self, bloom_distribution: Dict[str, float]) -> go.Figure:
        """生成 Bloom 认知层级分布柱状图"""
        BLOOM_COLORS = ['#a3c4bc', '#5a9a6d', '#10b981', '#2d5a3d', '#f59e0b', '#ef4444']
        labels = list(bloom_distribution.keys())
        values = [round(v * 100, 1) for v in bloom_distribution.values()]

        fig = go.Figure(data=[go.Bar(
            x=labels, y=values,
            text=[f"{v}%" for v in values], textposition='auto',
            marker=dict(color=BLOOM_COLORS[:len(labels)]),
        )])
        fig.update_layout(
            title={'text': 'Bloom 认知层级分布（分值加权）', 'x': 0.5,
                   'font': {'size': 18, 'family': 'SimHei'}},
            xaxis_title='认知层级', yaxis_title='分值占比 (%)',
            yaxis=dict(range=[0, 100]),
            template='plotly_white', font=dict(family='SimHei', size=12), height=400,
        )
        return fig

    def _fig_to_base64(self, fig: go.Figure) -> str:
        """将plotly图表转为base64编码的PNG"""
        img_bytes = fig.to_image(format="png", width=800, height=400, scale=2)
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"



# ============ 模块级 PDF 生成入口 ============

def generate_pdf_report(
    report_data: Dict,
    insights: Dict,
    mode: str = "brief",
    output_path: str = "",
) -> str:
    """生成 PDF 报告（模块级函数）。

    Args:
        report_data: aggregate_report_data() 输出
        insights: generate_insights() 输出
        mode: "brief" 或 "full"
        output_path: PDF 输出路径
    """
    rg = ReportGenerator()
    logger.info(f"[PDF生成] mode={mode}, 题目数={report_data['exam_info']['total_questions']}")

    # 提取图表所需数据（PR-02 修复：包含 score_distribution_by_difficulty）
    questions_difficulty = [
        {
            "question_id": q["id"],
            "final_difficulty": q["difficulty"],
            "difficulty_label": q["difficulty_label"],
            "total_score": q["total_score"],
            "score_distribution_by_difficulty": q.get("score_distribution_by_difficulty", {}),
        }
        for q in report_data["questions"]
    ]

    # 生成图表
    charts = {}
    charts["curve"] = rg._fig_to_base64(rg.generate_difficulty_curve(questions_difficulty))
    charts["distribution"] = rg._fig_to_base64(rg.generate_difficulty_distribution(questions_difficulty))
    charts["competency_pie"] = rg._fig_to_base64(rg.generate_competency_pie(
        report_data["competency"]["distribution"]))
    charts["bloom"] = rg._fig_to_base64(rg.generate_bloom_chart(
        report_data["metrics"]["bloom_distribution"]))
    textbook_dist = report_data["knowledge"].get("textbook_distribution", {})
    if textbook_dist:
        charts["knowledge_pie"] = rg._fig_to_base64(rg.generate_knowledge_pie(textbook_dist))

    if mode == "full":
        charts["gradient"] = rg._fig_to_base64(rg.generate_difficulty_gradient(questions_difficulty))
        charts["radar"] = rg._fig_to_base64(rg.generate_feature_radar(
            report_data["feature_profile"]["avg_per_dimension"]))
        charts["competency_bar"] = rg._fig_to_base64(rg.generate_competency_bar(
            report_data["competency"]["distribution"]))

    # 组装 HTML
    html = _render_html(report_data, insights, charts, mode)

    # HTML → PDF
    HTML(string=html).write_pdf(output_path)
    logger.info(f"[PDF生成] 完成: {output_path}")
    return output_path


# ============ HTML 模板渲染 ============

def _get_report_css() -> str:
    """A4 排版 CSS 样式"""
    return """<style>
@page { size: A4; margin: 2cm; }
body { font-family: 'SimSun', 'Microsoft YaHei', sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; }
h1 { text-align: center; color: #2563eb; border-bottom: 3px solid #2563eb; padding-bottom: 10px; margin-bottom: 30px; }
h2 { color: #1e40af; border-left: 4px solid #3b82f6; padding-left: 10px; margin-top: 30px; page-break-after: avoid; }
.cover { text-align: center; padding: 60px 0 40px; }
.cover h1 { font-size: 28px; margin-bottom: 20px; }
.cover .subtitle { font-size: 20px; color: #475569; margin: 10px 0; }
.cover p { color: #64748b; margin: 5px 0; }
.metrics-grid { display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0; }
.metric-card { flex: 1; min-width: 140px; background: #f0f9ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 15px; text-align: center; }
.metric-value { font-size: 28px; font-weight: bold; color: #1e40af; }
.metric-label { font-size: 12px; color: #64748b; margin-top: 5px; }
.insight-box { background: #fefce8; border-left: 4px solid #eab308; padding: 12px 16px; margin: 15px 0; border-radius: 0 8px 8px 0; }
.chart { margin: 20px 0; text-align: center; page-break-inside: avoid; }
.chart img { max-width: 100%; height: auto; }
table { width: 100%; border-collapse: collapse; margin: 20px 0; page-break-inside: auto; }
th, td { border: 1px solid #cbd5e1; padding: 8px 10px; text-align: left; font-size: 13px; }
th { background: #eff6ff; font-weight: bold; color: #1e40af; }
tr:nth-child(even) { background: #f8fafc; }
tr { page-break-inside: avoid; }
.question-card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 15px 0; page-break-inside: avoid; }
.question-card h4 { color: #1e40af; margin: 0 0 10px; }
.question-card .meta { color: #64748b; font-size: 12px; margin-bottom: 8px; }
.question-card .comment { background: #f0fdf4; border-left: 3px solid #22c55e; padding: 8px 12px; margin-top: 10px; font-style: italic; }
.rec-item { border-left: 3px solid #3b82f6; padding: 8px 12px; margin: 10px 0; }
.rec-item.high { border-left-color: #ef4444; }
.rec-item.medium { border-left-color: #f59e0b; }
.rec-item.low { border-left-color: #22c55e; }
.rec-category { font-weight: bold; color: #1e40af; font-size: 13px; }
.difficulty-high { color: #dc2626; font-weight: bold; }
.difficulty-medium { color: #ea580c; }
.difficulty-low { color: #16a34a; }
.footer { margin-top: 40px; text-align: center; color: #64748b; font-size: 11px; border-top: 1px solid #e2e8f0; padding-top: 20px; }
.chart-container { margin: 12px 0; text-align: center; }
.chart-inline { display: inline-block; vertical-align: top; margin: 8px; }
.seu-table { width: 100%; border-collapse: collapse; font-size: 0.85em; margin: 8px 0; }
.seu-table th { background: #f0f2f6; padding: 6px 8px; text-align: left; border: 1px solid #dde1ea; }
.seu-table td { padding: 6px 8px; border: 1px solid #dde1ea; }
.diagnostics { margin: 8px 0; }
.trap-item { padding: 4px 8px; margin: 2px 0; border-radius: 4px; font-size: 0.85em; }
.trap-item.high { background: #fee2e2; color: #dc2626; }
.trap-item.med { background: #fef3c7; color: #d97706; }
.trap-option { font-weight: 700; margin-right: 8px; }
.fg-summary { background: #eff6ff; border-left: 3px solid #2563eb; padding: 8px 12px; margin: 12px 0; font-size: 0.85em; border-radius: 0 6px 6px 0; }
</style>"""


def _render_difficulty_section(data: dict, insights: dict, charts: dict, mode: str) -> str:
    """渲染难度分析 section"""
    html = '<h2>二、难度分析</h2>'

    # SVG 难度折线+散点图（优先，内联不依赖外部图片）
    if HAS_SVG_CHARTS and data.get("difficulty_curve"):
        points = [{"x": p["question_id"], "y": p["difficulty"],
                   "label": f"Q{p['question_id']}", "size": p.get("total_score", 2)}
                  for p in data["difficulty_curve"]]
        line_svg = render_line_scatter(points, width=700, height=200, title="难度曲线")
        html += f'<div class="chart-container">{line_svg}</div>'
    else:
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

    # 未映射率提示
    unmapped = data["knowledge"].get("unmapped_count", 0)
    total_kp = data["knowledge"].get("total_knowledge_points", 0)
    if unmapped > 0 and total_kp > 0:
        unmapped_pct = round(unmapped / total_kp * 100, 1)
        color = "#dc2626" if unmapped_pct > 30 else "#ca8a04"
        html += f'<p style="color:{color};font-size:0.9em">知识点映射覆盖率：{total_kp - unmapped}/{total_kp}（{unmapped}个未映射，{unmapped_pct}%）</p>'

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

    # SVG 环形图（优先）
    comp_dist = data.get("competency", {}).get("distribution", {})
    if HAS_SVG_CHARTS and comp_dist:
        comp_colors = {"生命观念": "#7c3aed", "科学思维": "#2563eb",
                       "科学探究": "#0891b2", "社会责任": "#db2777"}
        valid_competencies = ["生命观念", "科学思维", "科学探究", "社会责任"]
        slices = []
        for name in valid_competencies:
            entry = comp_dist.get(name)
            if isinstance(entry, dict):
                pct = entry.get("占比", 0)
                if pct > 0:
                    slices.append({"label": name, "value": pct,
                                   "color": comp_colors.get(name, "#6b7385")})
        if slices:
            donut_svg = render_donut_chart(slices, size=200, title="素养分布")
            html += f'<div class="chart-container">{donut_svg}</div>'
        else:
            html += f'<div class="chart"><img src="{charts["competency_pie"]}" alt="素养分布"></div>'
    else:
        html += f'<div class="chart"><img src="{charts["competency_pie"]}" alt="素养分布"></div>'

    if mode == "full" and "competency_bar" in charts:
        html += f'<div class="chart"><img src="{charts["competency_bar"]}" alt="素养细分"></div>'

    # SEU 级素养分布（如果有且与题级不同）
    seu_pd = data.get("competency", {}).get("seu_primary_distribution", {})
    if seu_pd and any(v > 0 for v in seu_pd.values()):
        q_pd = data.get("competency", {}).get("primary_distribution", {})
        html += '<div style="margin-top:12px"><p><strong>采分单元级素养分布：</strong></p>'
        html += '<table><tr><th>维度</th><th>题级 primary</th><th>SEU级 primary</th></tr>'
        for dim in ["生命观念", "科学思维", "科学探究", "社会责任"]:
            q_val = q_pd.get(dim, 0)
            s_val = seu_pd.get(dim, 0)
            highlight = ' style="color:#0891b2;font-weight:bold"' if s_val > 0 and q_val == 0 else ''
            html += f'<tr><td>{dim}</td><td>{q_val}</td><td{highlight}>{s_val}</td></tr>'
        html += '</table></div>'

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

            qtype_label = q.get("question_type", "")
            qtype_display = f" · {qtype_label}" if qtype_label and qtype_label != "unknown" else ""
            html += f'''<div class="question-card">
<h4>题目 {q["id"]}（{q["total_score"]}分{qtype_display}）</h4>
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

            # 特征状态提示
            feat_status = q.get("feature_status", "ok")
            if feat_status == "partial":
                html += '<p style="color:#ca8a04;font-size:0.85em">⚠ 部分特征数据（核心维度可用，质量审查缺失）</p>'
            elif feat_status == "failed":
                html += '<p style="color:#dc2626;font-size:0.85em">⚠ 特征提取未成功，难度评估可能不准确</p>'

            # SVG 单题雷达图（6 维难度因子）
            if HAS_SVG_CHARTS and q.get("features"):
                feats = q["features"]
                dims = {
                    "信息负荷": feats.get("working_memory", 2),
                    "推理步数": feats.get("reasoning_steps", 3),
                    "推理耦合": feats.get("chain_coupling", 1),
                    "陷阱密度": feats.get("trap_density", 1),
                    "情境新颖": feats.get("novelty", 1),
                    "知识跨度": feats.get("knowledge_breadth", 1),
                }
                q_radar = render_radar_chart(dims, size=160)
                html += f'<div class="chart-inline">{q_radar}</div>'

            # 诊断高亮（细粒度干扰项）
            if q.get("diagnostic_highlights"):
                html += '<div class="diagnostics">'
                for dh in q["diagnostic_highlights"]:
                    strength_class = "high" if dh.get("trap_strength", 0) >= 3 else "med"
                    html += f'<div class="trap-item {strength_class}">'
                    html += f'<span class="trap-option">{dh.get("option", "?")}</span>'
                    html += f'<span class="trap-desc">{dh.get("misconception", "")}</span>'
                    html += '</div>'
                html += '</div>'

            # SEU 知识点拆分表
            if q.get("seu_knowledge_breakdown"):
                bloom_labels = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}
                html += '<table class="seu-table"><tr><th>采分点</th><th>分值占比</th><th>知识点</th><th>认知</th><th>素养</th></tr>'
                for seu in q["seu_knowledge_breakdown"]:
                    kps = ", ".join(kl.get("knowledge_point", "") for kl in seu.get("knowledge_links", []))
                    bl = bloom_labels.get(seu.get("bloom_level", 3), "应用")
                    pct = f"{seu.get('score_share', 0) * 100:.0f}%"
                    html += f'<tr><td>{seu.get("label", "")}</td><td>{pct}</td><td>{kps}</td><td>{bl}</td><td>{seu.get("competency", "")}</td></tr>'
                html += '</table>'

            # 命题质量审查（v3: 从 feature_extractor 合并）
            quality_items = []
            for qk, ql in [("quality_scientific", "科学性"), ("quality_normative", "规范性"),
                            ("quality_language", "语言表述"), ("quality_context", "情境设计")]:
                qv = q.get(qk, "")
                if qv and "无明显问题" not in qv and "无问题" not in qv:
                    quality_items.append(f"{ql}: {qv}")
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


def _render_diagnostics_summary(data: dict) -> str:
    """渲染整卷质量诊断摘要（来自 exam_diagnostics）。"""
    diag = data.get("diagnostics", {})
    if not diag or diag.get("overall_rating") == "数据不足":
        return ""

    overall = diag.get("overall_rating", "N/A")
    grad = diag.get("gradient", {})
    bal = diag.get("competency_balance", {})
    spread = diag.get("difficulty_spread", {})

    rating_colors = {"优秀": "#16a34a", "良好": "#2563eb", "一般": "#ca8a04", "待改进": "#dc2626"}
    color = rating_colors.get(overall, "#333")

    html = f'''<div style="background:#f0f9ff;border:1px solid #bfdbfe;border-radius:8px;padding:16px;margin:16px 0">
<h3 style="margin:0 0 12px;color:#1e40af">整卷质量诊断</h3>
<div class="metrics-grid">
<div class="metric-card"><div class="metric-value" style="color:{color}">{overall}</div><div class="metric-label">综合评价</div></div>
<div class="metric-card"><div class="metric-value">{grad.get("rating", "N/A")}</div><div class="metric-label">难度梯度</div></div>
<div class="metric-card"><div class="metric-value">{bal.get("balance", "N/A")}</div><div class="metric-label">素养均衡</div></div>
<div class="metric-card"><div class="metric-value">{spread.get("spread_level", "N/A")}</div><div class="metric-label">难度离散度</div></div>
</div>'''

    if grad.get("actual") and grad.get("ideal"):
        html += '<table><thead><tr><th>难度等级</th><th>实际占比</th><th>理想占比</th><th>偏差</th></tr></thead><tbody>'
        for level in ["简单", "中等", "困难"]:
            actual = grad["actual"].get(level, 0)
            ideal = grad["ideal"].get(level, 0)
            diff = actual - ideal
            diff_color = "#dc2626" if abs(diff) > 0.15 else ("#ca8a04" if abs(diff) > 0.05 else "#16a34a")
            html += f'<tr><td>{level}</td><td>{actual*100:.0f}%</td><td>{ideal*100:.0f}%</td><td style="color:{diff_color}">{diff:+.0%}</td></tr>'
        html += '</tbody></table>'

    if bal.get("missing"):
        html += f'<p style="color:#dc2626"><strong>素养缺失：</strong>{"、".join(bal["missing"])}</p>'

    alloc = diag.get("allocation_reliability", {})
    if alloc.get("rating"):
        r = alloc["rating"]
        r_color = {"高": "#16a34a", "中": "#ca8a04", "低": "#dc2626"}.get(r, "#333")
        html += f'<p><strong>分值归因可靠性：</strong><span style="color:{r_color}">{r}</span>'
        html += f'（共 {alloc.get("total_seus", 0)} 个采分单元，推断占比 {alloc.get("inferred_pct", 0):.1f}%）</p>'
        lc = alloc.get("low_confidence_seus", [])
        if lc:
            labels = [f'Q{s.get("question_id", "?")}-{s.get("seu_id", "?")}({s.get("confidence", 0):.0%})' for s in lc[:3]]
            html += f'<p style="color:#6b7280;font-size:0.9em">低置信度单元：{"、".join(labels)}</p>'

    html += '</div>'
    return html


def _render_quality_overview_section(data: dict) -> str:
    """渲染命题质量总览 section — 整卷诊断 + 逐题质量问题。"""
    questions = data["questions"]

    critical = []
    improve = []
    good = []
    no_score = []

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
    html += _render_diagnostics_summary(data)

    # SVG 质量评分条形图
    if HAS_SVG_CHARTS and questions:
        bar_items = []
        for q in questions:
            qs = q.get("quality_score")
            if qs:
                score_val = qs * 20  # 1-5 -> 20-100
                color = "#059669" if score_val >= 80 else "#d97706" if score_val >= 60 else "#dc2626"
                bar_items.append({"label": f"Q{q.get('id', '?')}", "value": score_val, "color": color})
        if bar_items:
            bars_svg = render_horizontal_bars(bar_items, max_val=100, width=600, title="命题质量评分")
            html += f'<div class="chart-container">{bars_svg}</div>'

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



def _render_specification_table(data: dict, mode: str) -> str:
    """渲染双向细目表：知识点(行) x Bloom层级(列) → 分值"""
    BLOOM_COLS = ["识记", "理解", "应用", "分析", "评价", "创造"]
    BLOOM_MAP = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}
    table = {}  # {kp: {bloom: score}}
    for q in data.get("questions", []):
        fg = q.get("fine_grained") or q.get("_fine_grained") or {}
        if not fg:
            a = q.get("analysis") if isinstance(q, dict) else {}
            if isinstance(a, dict):
                fg = a.get("_fine_grained", {})
        q_score = q.get("total_score", 0) or 1
        for seu in (fg.get("scoring_units") or []):
            bloom = BLOOM_MAP.get(seu.get("bloom_level", 3), "应用")
            seu_score = q_score * seu.get("score_share", 0)
            for kl in seu.get("knowledge_links", []):
                kp = kl.get("knowledge_point", kl.get("point", ""))
                if not kp:
                    continue
                score = seu_score * kl.get("share", 1.0)
                if kp not in table:
                    table[kp] = {}
                table[kp][bloom] = round(table[kp].get(bloom, 0) + score, 2)
    if not table:
        return ""
    # Sort by total score desc
    sorted_kps = sorted(table.items(), key=lambda x: sum(x[1].values()), reverse=True)
    html = '<h2 style="page-break-before:always">附、双向细目表（知识点 × 认知层级）</h2>'
    html += '<table style="width:100%;border-collapse:collapse;font-size:11px;margin-top:10px">'
    html += '<tr style="background:#1e293b;color:white"><th style="padding:6px;text-align:left">知识点</th>'
    for col in BLOOM_COLS:
        html += f'<th style="padding:6px;text-align:center;min-width:45px">{col}</th>'
    html += '<th style="padding:6px;text-align:center">合计</th></tr>'
    col_totals = {c: 0 for c in BLOOM_COLS}
    for i, (kp, scores) in enumerate(sorted_kps[:30]):
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        row_total = sum(scores.values())
        html += f'<tr style="background:{bg}"><td style="padding:4px 6px;border-bottom:1px solid #e2e8f0">{kp[:25]}</td>'
        for col in BLOOM_COLS:
            v = scores.get(col, 0)
            col_totals[col] += v
            cell = f"{v:.1f}" if v > 0 else ""
            html += f'<td style="padding:4px;text-align:center;border-bottom:1px solid #e2e8f0">{cell}</td>'
        html += f'<td style="padding:4px;text-align:center;border-bottom:1px solid #e2e8f0;font-weight:600">{row_total:.1f}</td></tr>'
    # Total row
    grand = sum(col_totals.values())
    html += '<tr style="background:#f1f5f9;font-weight:600"><td style="padding:6px">合计</td>'
    for col in BLOOM_COLS:
        html += f'<td style="padding:4px;text-align:center">{col_totals[col]:.1f}</td>'
    html += f'<td style="padding:4px;text-align:center">{grand:.1f}</td></tr>'
    html += '</table>'
    if len(sorted_kps) > 30:
        html += f'<p style="font-size:11px;color:#94a3b8">（仅展示分值最高的 30 项，共 {len(sorted_kps)} 项）</p>'
    return html


def _render_recommendations_section(insights: dict, mode: str) -> str:
    """渲染综合建议 section"""
    html = '<h2>八、综合建议</h2>'
    recs = insights.get("recommendations", [])

    if mode == "brief":
        recs = recs[:3]

    for rec in recs:
        if isinstance(rec, str):
            html += f'<div class="rec-item medium"><span class="rec-category">[建议]</span> {rec}</div>'
        elif isinstance(rec, dict):
            priority = rec.get("priority", "medium")
            html += f'''<div class="rec-item {priority}">
<span class="rec-category">[{rec.get("category", "建议")}]</span> {rec.get("content", "")}
</div>'''

    return html


def _render_metadata_quality_summary(data: dict) -> str:
    """Render metadata governance quality signals."""
    quality = data.get("metadata_quality") or {}
    if not quality:
        return ""

    low = quality.get("low_confidence_questions", [])
    warnings = quality.get("warning_questions", [])
    call_counts = quality.get("llm_call_counts", {})
    missing = quality.get("missing_envelope_questions", [])

    low_text = "、".join(f"Q{qid}" for qid in low) if low else "无"
    missing_text = "、".join(f"Q{qid}" for qid in missing) if missing else "无"
    warning_items = []
    for item in warnings[:5]:
        if not isinstance(item, dict):
            continue
        warning_items.append(
            f"Q{item.get('id', '?')}: {', '.join(str(w) for w in item.get('warnings', []))}"
        )
    warning_text = "；".join(warning_items) if warning_items else "无"
    calls_text = "，".join(f"{k}: {v}" for k, v in sorted(call_counts.items())) if call_counts else "无"

    return f'''<div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;padding:14px;margin:14px 0">
<h3 style="margin:0 0 8px;color:#334155">元数据治理</h3>
<p><strong>低置信度题目：</strong>{low_text}</p>
<p><strong>元数据警告：</strong>{warning_text}</p>
<p><strong>缺失 Envelope：</strong>{missing_text}</p>
<p style="font-size:12px;color:#64748b"><strong>LLM 调用计数：</strong>{calls_text}</p>
</div>'''


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
    section1 += _render_metadata_quality_summary(data)

    # SVG 6 维全卷均值雷达图
    fp = data.get("feature_profile", {})
    avg_dims = fp.get("avg_per_dimension", {})
    has_valid_features = avg_dims and any(v > 0 for v in avg_dims.values())
    if HAS_SVG_CHARTS and has_valid_features:
        _DIM_MAP = {
            "bloom": "认知层级",
            "reasoning_steps": "推理步数",
            "knowledge_breadth": "知识跨度",
            "info_density": "信息负荷",
            "novelty": "情境新颖",
            "representation_complexity": "表征复杂度",
        }
        radar_dims: Dict[str, float] = {}
        for eng_key, val in avg_dims.items():
            cn = _DIM_MAP.get(eng_key)
            if cn:
                radar_dims[cn] = max(radar_dims.get(cn, 0), val)
        if radar_dims:
            radar_svg = render_radar_chart(radar_dims, size=220, title="难度因子全卷均值")
            section1 += f'<div class="chart-container">{radar_svg}</div>'
    elif not has_valid_features:
        section1 += '<p style="color:#ca8a04">⚠ 特征提取未成功，难度因子雷达图暂不可用</p>'

    # 细粒度汇总
    fgs = data.get("fine_grained_summary", {})
    if fgs.get("total_seus", 0) > 0:
        section1 += '<div class="fg-summary">'
        section1 += f'<p>细粒度分析：共识别 {fgs["total_seus"]} 个采分证据单元、{fgs["total_dus"]} 个诊断干扰单元</p>'
        section1 += f'<p>分析置信度：{fgs["avg_allocation_confidence"]:.0%}'
        if fgs.get("inferred_score_pct", 0) > 0:
            section1 += f' | 推断分配占比：{fgs["inferred_score_pct"]:.1f}%'
        section1 += '</p></div>'

    sections = [css, cover, section1]
    sections.append(_render_difficulty_section(data, insights, charts, mode))
    sections.append(_render_knowledge_section(data, insights, charts, mode))
    sections.append(_render_bloom_section(data, insights, charts, mode))
    sections.append(_render_competency_section(data, insights, charts, mode))
    sections.append(_render_quality_overview_section(data))
    sections.append(_render_questions_section(data, insights, mode))
    sections.append(_render_specification_table(data, mode))
    sections.append(_render_recommendations_section(insights, mode))

    # Footer
    sections.append('''<div class="footer">
<p>本报告由 生物试卷智能分析系统 自动生成</p>
<p>基于《普通高中生物学课程标准（2017年版2020修订）》</p>
</div>''')

    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>试卷评估报告</title></head><body>{"".join(sections)}</body></html>'''
