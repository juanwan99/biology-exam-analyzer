import pytest

import difficulty_pipeline
from difficulty_pipeline import DifficultyPipeline


def _call(call_id, purpose, schema):
    return {
        "call_id": call_id,
        "purpose": purpose,
        "prompt_id": f"biology.{purpose}",
        "prompt_hash": "a" * 64,
        "provider": "llm_client",
        "model": "configured_provider_chain",
        "input_refs": {},
        "parsed_schema": schema,
        "confidence": 0.9,
        "validation_errors": [],
        "fallback_count": 0,
        "retry_count": 0,
        "metadata": {},
    }


@pytest.mark.asyncio
async def test_big_question_difficulty_preserves_feature_llm_call_metadata(monkeypatch):
    async def fake_extract_big_question_features(*args, **kwargs):
        return {
            "subquestions": [
                {
                    "id": 1,
                    "points": 10,
                    "working_memory": 3,
                    "reasoning_steps": 4,
                    "trap_density": 2,
                    "novelty": 2,
                    "knowledge_breadth": 2,
                    "brief": "analysis",
                }
            ],
            "dependencies": [],
            "global_features": {
                "shared_context_load": 2,
                "global_method_novelty": 2,
            },
            "report": {},
            "_llm_calls": [
                _call("big-question-call", "big_question_feature_extraction", "BigQuestionFeatureResult")
            ],
        }

    monkeypatch.setattr(
        difficulty_pipeline,
        "extract_big_question_features",
        fake_extract_big_question_features,
    )

    result = await DifficultyPipeline()._evaluate_single(
        {"id": 18, "content": "big question", "total_score": 10, "subject": "biology"}
    )

    assert result["features"]["_llm_calls"][0]["purpose"] == "big_question_feature_extraction"


@pytest.mark.asyncio
async def test_big_question_emits_aggregated_cognitive_load(monkeypatch):
    # RC3 字段分离 ENTRY：大题输出专属 aggregated_cognitive_load 字段
    async def fake_extract_big_question_features(*args, **kwargs):
        return {
            "subquestions": [
                {"id": 1, "points": 6, "working_memory": 3, "reasoning_steps": 5,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "a"},
                {"id": 2, "points": 6, "working_memory": 4, "reasoning_steps": 6,
                 "trap_density": 3, "novelty": 3, "knowledge_breadth": 3, "brief": "b"},
            ],
            "dependencies": [{"from": 1, "to": 2, "strength": "strong"}],
            "global_features": {"shared_context_load": 2, "global_method_novelty": 2},
            "report": {},
        }

    monkeypatch.setattr(
        difficulty_pipeline,
        "extract_big_question_features",
        fake_extract_big_question_features,
    )

    result = await DifficultyPipeline()._evaluate_single(
        {"id": 20, "content": "big question", "total_score": 12, "subject": "biology"}
    )
    feats = result["features"]
    eff = feats["_big_question"]["effective_steps"]
    # 新字段 = round(effective_steps)，诚实命名的聚合认知负荷
    assert feats["aggregated_cognitive_load"] == round(eff)
    # 过渡期 reasoning_steps 仍等于同一聚合值（保证内部读取点数值不变）
    assert feats["reasoning_steps"] == round(eff)


@pytest.mark.asyncio
async def test_small_question_has_no_aggregated_cognitive_load(monkeypatch):
    # RC3 字段分离 COUNTER：小题不产出 aggregated_cognitive_load
    async def fake_extract_features(*args, **kwargs):
        return {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 1,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "_feature_status": "ok",
        }

    monkeypatch.setattr(
        difficulty_pipeline,
        "extract_features",
        fake_extract_features,
    )

    result = await DifficultyPipeline()._evaluate_single(
        {"id": 5, "content": "small question", "total_score": 4, "subject": "biology"}
    )
    feats = result["features"]
    assert "aggregated_cognitive_load" not in feats
    assert feats["reasoning_steps"] == 4
