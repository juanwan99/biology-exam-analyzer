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
        生成难度分布直方图

        Args:
            questions_difficulty: 题目难度列表

        Returns:
            plotly Figure对象
        """
        logger.info(f"[图表2] 生成难度分布直方图")

        # 统计各难度等级数量
        easy_count = sum(1 for q in questions_difficulty if q["final_difficulty"] < 4)
        medium_count = sum(1 for q in questions_difficulty if 4 <= q["final_difficulty"] < 7)
        hard_count = sum(1 for q in questions_difficulty if q["final_difficulty"] >= 7)

        # 创建柱状图
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

        # 布局设置
        fig.update_layout(
            title={
                'text': '难度分布统计',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'family': 'SimHei'}
            },
            xaxis_title='难度等级',
            yaxis_title='题目数量',
            template='plotly_white',
            font=dict(family='SimHei', size=12),
            height=400
        )

        logger.info(f"[图表2] 难度分布: 简单{easy_count}题, 中等{medium_count}题, 困难{hard_count}题")
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

        # 提取数据
        competencies = list(competency_summary.keys())
        weights = [competency_summary[c]["总权重"] for c in competencies]
        percentages = [competency_summary[c]["占比"] * 100 for c in competencies]

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

        # 计算平均难度
        avg1 = sum(q["final_difficulty"] for q in part1) / len(part1) if part1 else 0
        avg2 = sum(q["final_difficulty"] for q in part2) / len(part2) if part2 else 0
        avg3 = sum(q["final_difficulty"] for q in part3) / len(part3) if part3 else 0

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

    def _fig_to_base64(self, fig: go.Figure) -> str:
        """将plotly图表转为base64编码的PNG"""
        img_bytes = fig.to_image(format="png", width=800, height=400, scale=2)
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"

    def generate_pdf_report(
        self,
        questions_analysis: List[Dict[str, Any]],
        competency_summary: Dict[str, Any],
        exam_info: Dict[str, str],
        output_path: str
    ) -> str:
        """
        生成完整的PDF评估报告

        Args:
            questions_analysis: 所有题目的分析结果
            competency_summary: 素养汇总统计
            exam_info: 试卷基本信息 {"name": "2025山东卷", "total": 25, "mode": "deep"}
            output_path: PDF输出路径

        Returns:
            PDF文件路径
        """
        logger.info(f"[PDF生成] 开始生成报告，题目数: {len(questions_analysis)}")

        # 提取难度数据
        questions_difficulty = [
            {
                "question_id": q.get("id", q.get("question_id", idx+1)),  # 兼容id和question_id两种字段
                "final_difficulty": q.get("difficulty", {}).get("final_difficulty", q.get("final_difficulty", q.get("base_difficulty", 5.0))),
                "difficulty_label": q.get("difficulty", {}).get("difficulty_label", q.get("difficulty_label", "中等")),
                "knowledge_complexity": q.get("difficulty", {}).get("knowledge_complexity", q.get("knowledge_complexity", 0)),
                "cognitive_level": q.get("difficulty", {}).get("cognitive_level", q.get("cognitive_level", 0)),
                "info_extraction": q.get("difficulty", {}).get("information_extraction", q.get("info_extraction", 0)),
                "reasoning_steps": q.get("difficulty", {}).get("reasoning_steps", q.get("reasoning_steps", 0))
            }
            for idx, q in enumerate(questions_analysis)
        ]

        # 生成所有图表
        logger.info("[PDF生成] 正在生成图表...")
        chart1 = self._fig_to_base64(self.generate_difficulty_curve(questions_difficulty))
        chart2 = self._fig_to_base64(self.generate_difficulty_distribution(questions_difficulty))
        chart3 = self._fig_to_base64(self.generate_dimension_radar(questions_difficulty[0]))  # 示例：第1题
        chart4 = self._fig_to_base64(self.generate_competency_pie(competency_summary))
        chart5 = self._fig_to_base64(self.generate_competency_bar(competency_summary))
        chart6 = self._fig_to_base64(self.generate_difficulty_gradient(questions_difficulty))

        # 计算统计数据
        avg_difficulty = sum(q["final_difficulty"] for q in questions_difficulty) / len(questions_difficulty)
        easy_count = sum(1 for q in questions_difficulty if q["final_difficulty"] < 4)
        medium_count = sum(1 for q in questions_difficulty if 4 <= q["final_difficulty"] < 7)
        hard_count = sum(1 for q in questions_difficulty if q["final_difficulty"] >= 7)

        # 生成HTML报告
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>生物试卷质量评估报告</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        body {{
            font-family: 'SimSun', 'Microsoft YaHei', sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            color: #2563eb;
            border-bottom: 3px solid #2563eb;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #1e40af;
            border-left: 4px solid #3b82f6;
            padding-left: 10px;
            margin-top: 30px;
        }}
        .info-box {{
            background: #f0f9ff;
            border: 1px solid #bfdbfe;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
        }}
        .info-item {{
            display: inline-block;
            margin-right: 30px;
            margin-bottom: 10px;
        }}
        .info-label {{
            font-weight: bold;
            color: #1e40af;
        }}
        .chart {{
            margin: 20px 0;
            text-align: center;
            page-break-inside: avoid;
        }}
        .chart img {{
            max-width: 100%;
            height: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #cbd5e1;
            padding: 10px;
            text-align: left;
        }}
        th {{
            background: #eff6ff;
            font-weight: bold;
            color: #1e40af;
        }}
        tr:nth-child(even) {{
            background: #f8fafc;
        }}
        .footer {{
            margin-top: 40px;
            text-align: center;
            color: #64748b;
            font-size: 12px;
            border-top: 1px solid #e2e8f0;
            padding-top: 20px;
        }}
        .difficulty-high {{ color: #dc2626; font-weight: bold; }}
        .difficulty-medium {{ color: #ea580c; }}
        .difficulty-low {{ color: #16a34a; }}
    </style>
</head>
<body>
    <h1>生物试卷质量评估报告</h1>

    <div class="info-box">
        <div class="info-item"><span class="info-label">试卷名称:</span> {exam_info.get("name", "未命名")}</div>
        <div class="info-item"><span class="info-label">题目总数:</span> {exam_info.get("total", len(questions_difficulty))}</div>
        <div class="info-item"><span class="info-label">评估模式:</span> {exam_info.get("mode", "fast")=="deep" and "深度模式🔬" or "快速模式🚄"}</div>
        <div class="info-item"><span class="info-label">生成时间:</span> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
    </div>

    <h2>一、试卷概览</h2>
    <div class="info-box">
        <div class="info-item"><span class="info-label">平均难度:</span> {avg_difficulty:.2f}/10</div>
        <div class="info-item"><span class="info-label">简单题:</span> <span class="difficulty-low">{easy_count}道</span></div>
        <div class="info-item"><span class="info-label">中等题:</span> <span class="difficulty-medium">{medium_count}道</span></div>
        <div class="info-item"><span class="info-label">困难题:</span> <span class="difficulty-high">{hard_count}道</span></div>
    </div>

    <h2>二、难度分析</h2>

    <div class="chart">
        <img src="{chart1}" alt="难度曲线图">
    </div>

    <div class="chart">
        <img src="{chart2}" alt="难度分布">
    </div>

    <div class="chart">
        <img src="{chart6}" alt="难度梯度">
    </div>

    <h2>三、核心素养分析</h2>

    <div class="chart">
        <img src="{chart4}" alt="素养覆盖">
    </div>

    <div class="chart">
        <img src="{chart5}" alt="素养细分">
    </div>

    <h2>四、题目详情</h2>
    <table>
        <thead>
            <tr>
                <th>题号</th>
                <th>难度系数</th>
                <th>难度等级</th>
                <th>知识复杂度</th>
                <th>认知层级</th>
                <th>信息提取</th>
                <th>推理步骤</th>
            </tr>
        </thead>
        <tbody>
"""

        # 添加题目详情
        for q in questions_difficulty:
            difficulty_class = "difficulty-low"
            if q["final_difficulty"] >= 7:
                difficulty_class = "difficulty-high"
            elif q["final_difficulty"] >= 4:
                difficulty_class = "difficulty-medium"

            html_content += f"""
            <tr>
                <td>{q["question_id"]}</td>
                <td class="{difficulty_class}">{q["final_difficulty"]:.2f}</td>
                <td>{q["difficulty_label"]}</td>
                <td>{q["knowledge_complexity"]:.1f}</td>
                <td>{q["cognitive_level"]:.1f}</td>
                <td>{q["info_extraction"]:.1f}</td>
                <td>{q["reasoning_steps"]:.1f}</td>
            </tr>
"""

        html_content += """
        </tbody>
    </table>

    <h2>五、评估建议</h2>
    <div class="info-box">
"""

        # 生成建议
        if avg_difficulty >= 7:
            html_content += "<p>✅ <strong>整体难度偏高</strong>，适合选拔性考试，建议适当增加基础题。</p>"
        elif avg_difficulty >= 5:
            html_content += "<p>✅ <strong>难度适中</strong>，符合常规考试要求。</p>"
        else:
            html_content += "<p>✅ <strong>整体难度偏低</strong>，适合日常测验，建议增加挑战性题目。</p>"

        if hard_count > len(questions_difficulty) * 0.4:
            html_content += "<p>⚠️ 困难题占比过高，可能影响学生自信心。</p>"

        # 素养建议
        for comp, data in competency_summary.items():
            if data["占比"] < 0.1:
                html_content += f"<p>⚠️ <strong>{comp}</strong>覆盖不足（{data['占比']*100:.1f}%），建议增加相关题目。</p>"

        html_content += """
    </div>

    <div class="footer">
        <p>本报告由 生物试卷智能分析系统 自动生成</p>
        <p>基于《普通高中生物学课程标准（2017年版2020修订）》</p>
    </div>
</body>
</html>
"""

        # 生成PDF
        logger.info("[PDF生成] HTML生成完成，开始转换为PDF...")
        HTML(string=html_content).write_pdf(output_path)
        logger.info(f"[PDF生成] 报告生成成功: {output_path}")

        return output_path


# 测试代码
if __name__ == "__main__":
    print("可视化报告生成器模块加载成功")
    print("6个图表函数已就绪:")
    print("  1. generate_difficulty_curve() - 难度曲线图")
    print("  2. generate_difficulty_distribution() - 难度分布直方图")
    print("  3. generate_dimension_radar() - 维度雷达图")
    print("  4. generate_competency_pie() - 素养覆盖饼图")
    print("  5. generate_competency_bar() - 素养细分柱状图")
    print("  6. generate_difficulty_gradient() - 难度梯度评估")
    print("  7. generate_pdf_report() - 生成完整PDF报告 ⭐")
