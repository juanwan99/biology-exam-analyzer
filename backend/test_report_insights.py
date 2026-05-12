"""report_insights LLM 分析层测试（mock GPT 调用）"""
import pytest
import json
from unittest.mock import patch, AsyncMock

MOCK_OVERALL_RESPONSE = json.dumps({
    "overall_assessment": "本卷难度适中，知识覆盖较全面。",
    "recommendations": [
        {"category": "难度结构", "content": "建议增加过渡题", "priority": "high"},
        {"category": "知识覆盖", "content": "选修3覆盖不足", "priority": "medium"},
    ],
    "difficulty_analysis": "难度梯度呈递增趋势...",
    "knowledge_analysis": "知识点集中在必修1...",
    "competency_analysis": "科学探究素养覆盖不足...",
    "bloom_analysis": "高阶思维占比偏低...",
})

MOCK_COMMENTS_RESPONSE = json.dumps({
    "question_comments": {
        "1": "本题考查光合作用基本概念，属于识记层级。",
        "2": "本题需要分析系谱图推导基因型。",
    }
})


@pytest.fixture
def sample_report_data():
    return {
        "exam_info": {"name": "测试卷", "total_questions": 2, "total_score": 10, "mode": "fast"},
        "metrics": {"avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
                    "difficulty_distribution": {"简单": 1, "中等": 1, "困难": 0},
                    "difficulty_distribution_by_score": {},
                    "bloom_distribution": {"应用": 0.6, "识记": 0.4}},
        "difficulty_curve": [],
        "difficulty_gradient": {"front": 3.0, "middle": 5.0, "back": 7.0, "gradient_type": "前易后难（递增）"},
        "knowledge": {"top_points": [{"name": "光合作用", "weighted_score": 6.0}],
                      "textbook_distribution": {}},
        "competency": {"distribution": {}, "primary_distribution": {}},
        "feature_profile": {"avg_per_dimension": {"bloom": 3.0, "reasoning_steps": 4.0,
                            "knowledge_breadth": 2.0, "info_density": 2.0,
                            "novelty": 2.0, "representation_complexity": 1.0},
                           "top_difficulty_factors": ["bloom", "reasoning_steps", "knowledge_breadth"]},
        "questions": [
            {"id": 1, "total_score": 6, "difficulty": 3.0, "bloom": 2,
             "knowledge_points": ["光合作用"], "primary_competency": "生命观念",
             "detailed_analysis": "步骤1...", "common_mistakes": ["错误1"]},
            {"id": 2, "total_score": 4, "difficulty": 7.0, "bloom": 4,
             "knowledge_points": ["遗传学"], "primary_competency": "科学思维",
             "detailed_analysis": "步骤1...", "common_mistakes": ["错误1"]},
        ],
    }


@pytest.mark.asyncio
class TestGenerateInsights:

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_brief_mode_one_call(self, mock_gpt, sample_report_data):
        """精简档只调用 1 次 GPT"""
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE
        from report_insights import generate_insights
        result = await generate_insights(sample_report_data, mode="brief")
        assert mock_gpt.call_count == 1
        assert "overall_assessment" in result
        assert len(result["recommendations"]) >= 1

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_full_mode_one_call_with_comments_from_data(self, mock_gpt, sample_report_data):
        """完整档只调用 1 次 GPT（逐题点评从 report_data 复用）"""
        mock_gpt.return_value = MOCK_OVERALL_RESPONSE
        # 模拟 teacher_comment 已在 feature_extractor 中提取
        sample_report_data["questions"][0]["teacher_comment"] = "本题考查光合作用基本概念。"
        sample_report_data["questions"][1]["teacher_comment"] = "需要综合分析系谱图。"
        from report_insights import generate_insights
        result = await generate_insights(sample_report_data, mode="full")
        assert mock_gpt.call_count == 1  # 只调用 1 次
        assert "question_comments" in result
        assert "1" in result["question_comments"]

    @patch("report_insights.send_message_gpt", new_callable=AsyncMock)
    async def test_gpt_failure_raises(self, mock_gpt, sample_report_data):
        """GPT 失败直接抛异常，不降级"""
        mock_gpt.side_effect = RuntimeError("API 超时")
        from report_insights import generate_insights
        with pytest.raises(RuntimeError, match="LLM 分析生成失败"):
            await generate_insights(sample_report_data, mode="brief")
