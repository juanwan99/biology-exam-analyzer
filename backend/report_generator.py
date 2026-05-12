"""
可视化报告生成器
使用 plotly 生成交互式图表，导出为 PDF 报告
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
        fig.add_hrect(y0=0, y1=4, fillcolor="green", opacity=0.1, line_width=0,
                      annotation_text="简单", annotation_position="top left")
        fig.add_hrect(y0=4, y1=7, fillcolor="yellow", opacity=0.1, line_width=0,
                      annotation_text="中等", annotation_position="top left")
        fig.add_hrect(y0=7, y1=10, fillcolor="red", opacity=0.1, line_width=0,
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

        has_score_distribution = any("score_distribution_by_difficulty" in q for q in questions_difficulty)

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
                    x=['简单 (0-4.5)', '中等 (4.5-7.5)', '困难 (7.5-10)'],
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
            easy_count = sum(1 for q in questions_difficulty if q.get("final_difficulty", 5.0) < 4)
            medium_count = sum(1 for q in questions_difficulty if 4 <= q.get("final_difficulty", 5.0) < 7)
            hard_count = sum(1 for q in questions_difficulty if q.get("final_difficulty", 5.0) >= 7)

            logger.warning(f"[图表2] 未找到score_distribution_by_difficulty，使用题目数量统计")
            logger.info(f"[图表2] 难度分布（题数）: 简单{easy_count}题, 中等{medium_count}题, 困难{hard_count}题")

            fig = go.Figure(data=[
                go.Bar(
                    x=['简单 (0-4)', '中等 (4-7)', '困难 (7-10)'],
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
</style>"""


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
