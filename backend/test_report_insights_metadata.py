import json

import pytest

import report_insights
from report_insights import generate_insights


def _report_data():
    return {
        "exam_info": {"name": "测试卷", "total_questions": 1, "total_score": 2},
        "metrics": {
            "avg_difficulty": 5.0,
            "avg_cognitive_level": 4.0,
            "difficulty_distribution": {"中等": 1},
            "bloom_distribution": {"分析": 1},
        },
        "difficulty_gradient": {
            "front": 4.0,
            "middle": 5.0,
            "back": 6.0,
            "gradient_type": "递增",
        },
        "knowledge": {"top_points": ["酶"]},
        "competency": {"distribution": {"科学思维": 1}},
        "feature_profile": {
            "avg_per_dimension": {"working_memory": 3},
            "top_difficulty_factors": ["working_memory"],
        },
        "diagnostics": {},
        "questions": [
            {
                "id": 1,
                "total_score": 2,
                "difficulty": 5.0,
                "bloom": 4,
                "knowledge_points": ["酶"],
                "primary_competency": "科学思维",
                "detailed_analysis": "分析实验变量",
                "common_mistakes": ["混淆自变量"],
            }
        ],
    }


@pytest.mark.asyncio
async def test_generate_insights_attaches_report_llm_call_metadata(monkeypatch):
    responses = [
        {
            "overall_assessment": "整体质量稳定。",
            "recommendations": [
                {"category": "难度结构", "content": "保持梯度。", "priority": "medium"}
            ],
            "difficulty_analysis": "难度适中。",
            "knowledge_analysis": "覆盖酶相关知识。",
            "competency_analysis": "突出科学思维。",
            "bloom_analysis": "分析层级为主。",
        },
        {
            "error_categories": [],
            "lecture_outline": [],
            "remedial_exercises": [],
        },
    ]
    prompts = []

    async def fake_send_message(prompt, **kwargs):
        prompts.append(prompt)
        return json.dumps(responses[len(prompts) - 1], ensure_ascii=False)

    monkeypatch.setattr(report_insights, "send_message_gpt", fake_send_message)

    result = await generate_insights(_report_data(), mode="brief", grounding_enabled=False)

    assert len(prompts) == 2
    assert result["_llm_calls"][0]["purpose"] == "report_insights"
    assert result["_llm_calls"][0]["prompt_id"] == "biology.report_insights"
    assert result["_llm_calls"][0]["parsed_schema"] == "InsightsResult"
    assert result["_llm_calls"][0]["confidence"] == 1.0
    calls_by_purpose = {call["purpose"]: call for call in result["_llm_calls"]}
    teaching_call = calls_by_purpose["report_teaching_suggestions"]
    assert teaching_call["prompt_id"] == "biology.report_teaching_suggestions"
    assert teaching_call["parsed_schema"] == "TeachingSuggestions"
    assert len(teaching_call["prompt_hash"]) == 64
