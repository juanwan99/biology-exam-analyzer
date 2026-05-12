"""report_generator HTML 渲染层测试 — 验证 brief/full 模式 section 差异"""
import pytest
import sys
from unittest.mock import MagicMock

# Mock weasyprint（本地 Windows 无 GTK）
sys.modules['weasyprint'] = MagicMock()

from report_generator import (
    _render_html, _render_difficulty_section, _render_knowledge_section,
    _render_bloom_section, _render_competency_section,
    _render_questions_section, _render_recommendations_section,
)


@pytest.fixture
def sample_data():
    return {
        "exam_info": {"name": "测试卷", "total_questions": 2, "total_score": 10, "mode": "fast"},
        "metrics": {"avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
                    "difficulty_distribution": {"简单": 1, "中等": 1, "困难": 0},
                    "difficulty_distribution_by_score": {},
                    "bloom_distribution": {"应用": 0.6, "识记": 0.4}},
        "difficulty_curve": [],
        "difficulty_gradient": {"front": 3.0, "middle": 5.0, "back": 7.0, "gradient_type": "前易后难（递增）"},
        "knowledge": {
            "top_points": [{"name": "光合作用", "weighted_score": 6.0}],
            "textbook_distribution": {"必修1": {"weighted_score": 8.0, "percentage": 80.0},
                                      "必修2": {"weighted_score": 2.0, "percentage": 20.0}},
        },
        "competency": {"distribution": {}, "primary_distribution": {}},
        "feature_profile": {"avg_per_dimension": {"bloom": 3.0, "reasoning_steps": 4.0,
                            "knowledge_breadth": 2.0, "info_density": 2.0,
                            "novelty": 2.0, "representation_complexity": 1.0},
                           "top_difficulty_factors": ["bloom", "reasoning_steps", "knowledge_breadth"]},
        "questions": [
            {"id": 1, "total_score": 6, "difficulty": 3.0, "difficulty_label": "简单",
             "bloom": 2, "bloom_reason": "直接回忆",
             "cognitive_level": 3.3, "confidence": 0.85,
             "steps_detail": "单步回忆", "breadth_reason": "单知识点",
             "density_reason": "", "novelty_reason": "", "representation_reason": "",
             "knowledge_points": ["光合作用"], "detailed_analysis": "解题步骤...",
             "common_mistakes": ["错误1"],
             "primary_competency": "生命观念", "competency_level": "中",
             "competency_details": {}, "question_type": "single_choice",
             "score_distribution_by_difficulty": {},
             "quality_scientific": "准确", "quality_normative": "规范",
             "quality_language": "简洁", "quality_context": "合理",
             "teacher_comment": "本题考查光合作用基本概念。"},
            {"id": 2, "total_score": 4, "difficulty": 7.0, "difficulty_label": "困难",
             "bloom": 4, "bloom_reason": "需要分析",
             "cognitive_level": 6.7, "confidence": 0.9,
             "steps_detail": "多步推理", "breadth_reason": "跨章节",
             "density_reason": "信息量大", "novelty_reason": "新情境", "representation_reason": "图表分析",
             "knowledge_points": ["遗传学", "分子生物学"], "detailed_analysis": "需要综合分析...",
             "common_mistakes": ["混淆基因型"],
             "primary_competency": "科学思维", "competency_level": "高",
             "competency_details": {}, "question_type": "short_answer",
             "score_distribution_by_difficulty": {},
             "quality_scientific": "知识点准确", "quality_normative": "格式规范",
             "quality_language": "表述严谨", "quality_context": "情境真实",
             "teacher_comment": "需要综合遗传学和分子生物学知识。"},
        ],
    }


@pytest.fixture
def sample_insights():
    return {
        "overall_assessment": "本卷难度适中。",
        "recommendations": [
            {"category": "难度", "content": "建议增加过渡题", "priority": "high"},
            {"category": "知识", "content": "选修3不足", "priority": "medium"},
            {"category": "素养", "content": "探究不够", "priority": "low"},
            {"category": "Bloom", "content": "高阶偏少", "priority": "medium"},
        ],
        "difficulty_analysis": "难度梯度呈递增趋势。整体偏难。",
        "knowledge_analysis": "知识点集中在必修1。",
        "competency_analysis": "科学探究素养不足。",
        "bloom_analysis": "高阶思维占比偏低。",
        "question_comments": {
            "1": "本题考查光合作用基本概念。",
            "2": "需要综合遗传学和分子生物学知识。",
        },
    }


@pytest.fixture
def sample_charts():
    return {
        "curve": "data:image/png;base64,CURVE",
        "distribution": "data:image/png;base64,DIST",
        "competency_pie": "data:image/png;base64,PIE",
        "bloom": "data:image/png;base64,BLOOM",
        "gradient": "data:image/png;base64,GRAD",
        "radar": "data:image/png;base64,RADAR",
        "competency_bar": "data:image/png;base64,BAR",
        "knowledge_pie": "data:image/png;base64,KPIE",
    }


class TestRenderHtml:

    def test_brief_contains_all_sections(self, sample_data, sample_insights, sample_charts):
        """brief 模式包含全部 7 个 section"""
        html = _render_html(sample_data, sample_insights, sample_charts, "brief")
        assert "一、试卷总评" in html
        assert "二、难度分析" in html
        assert "三、知识覆盖" in html
        assert "四、Bloom 认知层级" in html
        assert "五、核心素养" in html
        assert "六、命题质量总览" in html
        assert "七、逐题详情" in html
        assert "八、综合建议" in html

    def test_brief_has_table_not_cards(self, sample_data, sample_insights, sample_charts):
        """brief 模式逐题用精简表格，不用卡片"""
        html = _render_questions_section(sample_data, sample_insights, "brief")
        assert '<div class="question-card">' not in html
        assert "<table>" in html

    def test_full_has_cards_with_comments(self, sample_data, sample_insights, sample_charts):
        """full 模式用卡片并包含 GPT 教师点评"""
        html = _render_html(sample_data, sample_insights, sample_charts, "full")
        assert "question-card" in html
        assert "教师点评" in html
        assert "本题考查光合作用" in html

    def test_full_has_7dim_reasons(self, sample_data, sample_insights, sample_charts):
        """full 模式逐题卡片包含全部 reason 字段（CR-02）"""
        html = _render_html(sample_data, sample_insights, sample_charts, "full")
        assert "特征分析" in html
        assert "需要分析" in html  # bloom_reason of q2
        assert "多步推理" in html  # steps_detail of q2
        assert "跨章节" in html    # breadth_reason of q2
        assert "信息量大" in html  # density_reason of q2
        assert "新情境" in html    # novelty_reason of q2
        assert "图表分析" in html  # representation_reason of q2

    def test_brief_recommendations_top3(self, sample_data, sample_insights, sample_charts):
        """brief 模式只展示 top 3 建议"""
        html = _render_recommendations_section(sample_insights, "brief")
        assert "建议增加过渡题" in html
        assert "选修3不足" in html
        assert "探究不够" in html
        assert "高阶偏少" not in html  # 第 4 条不展示

    def test_full_recommendations_all(self, sample_data, sample_insights, sample_charts):
        """full 模式展示全部建议"""
        html = _render_recommendations_section(sample_insights, "full")
        assert "高阶偏少" in html  # 第 4 条也展示


    def test_full_has_quality_review(self, sample_data, sample_insights, sample_charts):
        """full 模式逐题卡片包含命题质量审查"""
        html = _render_html(sample_data, sample_insights, sample_charts, "full")
        assert "命题质量" in html
        assert "科学性" in html
        assert "规范性" in html
        assert "语言表述" in html

    def test_full_teacher_comment_from_data(self, sample_data, sample_insights, sample_charts):
        """full 模式教师点评来自 report_data（不依赖 insights.question_comments）"""
        # 清除 insights 中的 question_comments
        insights_no_comments = {k: v for k, v in sample_insights.items() if k != "question_comments"}
        html = _render_html(sample_data, insights_no_comments, sample_charts, "full")
        assert "本题考查光合作用基本概念" in html  # from q1.teacher_comment


class TestRenderKnowledgeSection:

    def test_knowledge_pie_rendered(self, sample_data, sample_insights, sample_charts):
        """知识覆盖 section 渲染教材饼图（CR-01）"""
        html = _render_knowledge_section(sample_data, sample_insights, sample_charts, "brief")
        assert "KPIE" in html  # knowledge_pie chart

    def test_full_has_textbook_table(self, sample_data, sample_insights, sample_charts):
        """full 模式有教材章节明细表"""
        html = _render_knowledge_section(sample_data, sample_insights, sample_charts, "full")
        assert "必修1" in html
        assert "80.0%" in html

    def test_brief_no_textbook_table(self, sample_data, sample_insights, sample_charts):
        """brief 模式没有教材章节明细表"""
        html = _render_knowledge_section(sample_data, sample_insights, sample_charts, "brief")
        assert "80.0%" not in html


class TestRenderDifficultySection:

    def test_brief_no_gradient_chart(self, sample_data, sample_insights, sample_charts):
        """brief 模式不展示梯度图和雷达图"""
        html = _render_difficulty_section(sample_data, sample_insights, sample_charts, "brief")
        assert "GRAD" not in html
        assert "RADAR" not in html

    def test_full_has_gradient_and_radar(self, sample_data, sample_insights, sample_charts):
        """full 模式展示梯度图和雷达图"""
        html = _render_difficulty_section(sample_data, sample_insights, sample_charts, "full")
        assert "GRAD" in html
        assert "RADAR" in html

    def test_brief_difficulty_analysis_first_sentence(self, sample_data, sample_insights, sample_charts):
        """brief 模式只展示难度分析首句"""
        html = _render_difficulty_section(sample_data, sample_insights, sample_charts, "brief")
        assert "难度梯度呈递增趋势。" in html
        assert "整体偏难" not in html
