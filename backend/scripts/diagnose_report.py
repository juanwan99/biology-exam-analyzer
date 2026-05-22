"""诊断最近一次分析的数据结构，定位 report_data 取值问题。"""
import sys
sys.path.insert(0, "/app")
import json
import glob
import os

# 1. 检查最近的报告
reports = sorted(glob.glob("/app/reports/*.pdf"), key=os.path.getmtime, reverse=True)
print(f"=== 最近报告: {reports[0] if reports else 'None'} ===\n")

# 2. 模拟一个题目的数据结构（从 analyze_auto 的返回推断）
# 检查 question 的 total_score 位置
print("=== 检查 total_score 路径 ===")
sample_q = {
    "id": 1,
    "content": "...",
    "analysis": {"total_score": 6, "knowledge_points": ["光合作用"]},
    "difficulty": {"final_difficulty": 5.0, "features": {"bloom": 3}},
}
print(f"q.get('total_score', 0) = {sample_q.get('total_score', 0)}")
print(f"q.get('analysis', {{}}).get('total_score', 0) = {sample_q.get('analysis', {}).get('total_score', 0)}")
print(f"结论: total_score 在 analysis 子字典中，report_data.py 取不到\n")

# 3. 检查 feature_extractor 的实际输出是否包含 quality 字段
print("=== 检查 feature_extractor 新字段 ===")
from feature_extractor import _QUALITY_KEYS, _REASON_KEYS
print(f"_QUALITY_KEYS = {_QUALITY_KEYS}")
print(f"_REASON_KEYS = {_REASON_KEYS}")

# 4. 检查 parse_features 是否正确提取 quality 字段
from feature_extractor import parse_features
test_raw = json.dumps({
    "bloom": 3, "reasoning_steps": 2, "knowledge_breadth": 1,
    "info_density": 1, "novelty": 1, "representation_complexity": 1,
    "question_type_factor": 1,
    "quality_scientific": "准确",
    "quality_normative": "规范",
    "quality_language": "简洁",
    "quality_context": "合理",
    "teacher_comment": "测试点评",
})
result = parse_features(test_raw)
for k in _QUALITY_KEYS:
    print(f"  {k}: '{result.get(k, 'MISSING')}'")

# 5. 检查 difficulty_pipeline 是否传递 features 中的 quality 字段
print("\n=== 检查 difficulty_pipeline 返回结构 ===")
from difficulty_pipeline import DifficultyPipeline
import asyncio

async def check_pipeline():
    from unittest.mock import AsyncMock, patch
    mock_features = {
        "bloom": 3, "reasoning_steps": 2, "knowledge_breadth": 1,
        "info_density": 1, "novelty": 1, "representation_complexity": 1,
        "question_type_factor": 1,
        "bloom_reason": "应用层",
        "quality_scientific": "准确", "teacher_comment": "测试",
    }
    with patch("difficulty_pipeline.extract_features", new_callable=AsyncMock, return_value=mock_features):
        pipeline = DifficultyPipeline()
        result = await pipeline.evaluate_with_refinement(
            question={"content": "test", "question_type": "选择题", "correct_answer": "A", "total_score": 6}
        )
    features = result.get("features", {})
    print(f"  features keys: {sorted(features.keys())}")
    print(f"  quality_scientific in features: {'quality_scientific' in features}")
    print(f"  teacher_comment in features: {'teacher_comment' in features}")

asyncio.get_event_loop().run_until_complete(check_pipeline())

# 6. 检查 report_data._extract_question_detail 的取值路径
print("\n=== 检查 _extract_question_detail 取值 ===")
from report_data import _extract_question_detail
detail = _extract_question_detail(sample_q)
print(f"  detail['total_score'] = {detail['total_score']}  (期望 6，实际取 q.total_score)")
print(f"  detail['quality_scientific'] = '{detail.get('quality_scientific', 'MISSING')}'")
print(f"  detail['teacher_comment'] = '{detail.get('teacher_comment', 'MISSING')}'")

# 带 quality 的完整题目
full_q = {
    "id": 1, "total_score": 6,
    "difficulty": {"final_difficulty": 5.0, "features": {
        "bloom": 3, "quality_scientific": "准确", "teacher_comment": "好题",
    }},
    "analysis": {"knowledge_points": ["光合作用"], "detailed_analysis": "...", "common_mistakes": []},
    "competency": {"primary_competency": "生命观念", "competency_level": "中"},
}
detail2 = _extract_question_detail(full_q)
print(f"\n  有 total_score 顶层: detail['total_score'] = {detail2['total_score']}")
print(f"  quality_scientific = '{detail2.get('quality_scientific', 'MISSING')}'")
print(f"  teacher_comment = '{detail2.get('teacher_comment', 'MISSING')}'")
