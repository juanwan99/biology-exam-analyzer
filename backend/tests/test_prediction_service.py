"""整卷分数预估：个别题难度未评估 / 分值缺失时不拖垮整卷。"""
from unittest.mock import AsyncMock

import pytest

from prediction_service import PredictionService, _question_score


def _service():
    svc = PredictionService.__new__(PredictionService)
    svc.db = None
    svc.mapper = AsyncMock()
    svc.mapper.predict_rate = AsyncMock(side_effect=lambda difficulty, **kw: (1 - difficulty / 10, 0.4, 0.8))
    svc._check_knowledge_point_coverage = AsyncMock(return_value=False)
    svc._get_global_sample_count = AsyncMock(return_value=0)
    return svc


def test_question_score_prefers_question_level_and_skips_invalid():
    assert _question_score({"total_score": 12, "analysis": {"total_score": 10}}) == 12
    assert _question_score({"total_score": 0, "analysis": {"total_score": 10}}) == 10
    assert _question_score({"total_score": None, "analysis": {"total_score": None}}) == 0
    assert _question_score({"analysis": None}) == 0


@pytest.mark.asyncio
async def test_unevaluated_difficulty_uses_paper_mean():
    questions = [
        {"id": 1, "total_score": 2, "difficulty": {"final_difficulty": 4.0}, "analysis": {"knowledge_points": []}},
        {"id": 2, "total_score": 2, "difficulty": {"final_difficulty": 6.0}, "analysis": {"knowledge_points": []}},
        {"id": 3, "total_score": 12, "difficulty": {"final_difficulty": None, "difficulty_label": "未评估"},
         "analysis": {"total_score": None, "knowledge_points": None}},
    ]
    result = await _service().predict_exam_score(questions, total_score=16, grade="高三", save_prediction=False)
    assert result["predicted_average"] is not None
    per = {p["question_id"]: p for p in result["per_question_predictions"]}
    assert per[3]["difficulty"] == 5.0
    assert per[3]["question_score"] == 12
    assert any("第3题难度未评估" in w for w in result["warnings"])
