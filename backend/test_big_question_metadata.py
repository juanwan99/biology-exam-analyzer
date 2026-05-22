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
