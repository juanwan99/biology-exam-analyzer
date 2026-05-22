import json

import pytest

import feature_extractor
import prompt_loader
from feature_extractor import extract_big_question_features, extract_features


def _prepare_prompt_dir(tmp_path):
    prompt_dir = tmp_path / "prompts" / "biology"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "feature_extractor.txt").write_text(
        "feature prompt {question_block} {qtype_hint}",
        encoding="utf-8",
    )
    (prompt_dir / "big_question_extractor.txt").write_text(
        "big prompt {question_block} {qtype_hint}",
        encoding="utf-8",
    )
    return tmp_path / "prompts"


def _feature_payload():
    return {
        "working_memory": 4,
        "working_memory_reason": "需同时处理实验组和对照组",
        "reasoning_steps": 5,
        "steps_detail": "读题后判断变量并排除干扰",
        "chain_coupling": 2,
        "coupling_reason": "部分结论依赖前一步",
        "trap_density": 2,
        "trap_reason": "变量和结果易混",
        "novelty": 2,
        "novelty_reason": "常见实验变式",
        "knowledge_breadth": 2,
        "breadth_reason": "实验设计和代谢",
        "bloom": 4,
        "bloom_distribution": {"分析": 1},
        "bloom_reason": "分析实验变量",
        "info_density": 2,
        "density_reason": "信息中等",
        "representation_complexity": 1,
        "representation_reason": "纯文字",
        "quality_score": 4,
        "quality_scientific": "无明显问题",
        "quality_normative": "选项较规范",
        "quality_language": "表述清晰",
        "quality_context": "情境贴合教材",
        "quality_sensitivity": "无舆情风险",
        "teacher_comment": "适合考查变量分析。",
    }


@pytest.mark.asyncio
async def test_extract_features_attaches_llm_call_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(prompt_loader, "_PROMPTS_DIR", _prepare_prompt_dir(tmp_path))

    async def fake_send_message(prompt, **kwargs):
        assert "feature prompt" in prompt
        return json.dumps(_feature_payload(), ensure_ascii=False)

    monkeypatch.setattr(feature_extractor, "send_message_gpt", fake_send_message)

    result = await extract_features(
        "酶活性实验题干",
        options="A.正确 B.错误",
        correct_answer="A",
        question_type="单选题",
        subject="biology",
    )

    assert result["_feature_status"] == "ok"
    assert result["_llm_calls"][0]["purpose"] == "feature_extraction"
    assert result["_llm_calls"][0]["prompt_id"] == "biology.feature_extraction"
    assert len(result["_llm_calls"][0]["prompt_hash"]) == 64
    assert result["_llm_calls"][0]["provider"] == "llm_client"
    assert result["_llm_calls"][0]["model"] == "configured_provider_chain"
    assert result["_llm_calls"][0]["parsed_schema"] == "FeatureResult"
    assert result["_llm_calls"][0]["confidence"] == result["_extraction_confidence"]
    assert result["_llm_calls"][0]["input_refs"]["question_type"] == "单选题"


@pytest.mark.asyncio
async def test_extract_big_question_features_attaches_llm_call_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(prompt_loader, "_PROMPTS_DIR", _prepare_prompt_dir(tmp_path))

    payload = {
        "subquestions": [
            {
                "id": 1,
                "points": 4,
                "working_memory": 3,
                "reasoning_steps": 4,
                "trap_density": 2,
                "novelty": 2,
                "knowledge_breadth": 2,
                "brief": "判断变量",
            }
        ],
        "dependencies": [],
        "global_features": {
            "shared_context_load": 2,
            "global_method_novelty": 1,
        },
        "bloom": 4,
        "info_density": 2,
        "representation_complexity": 1,
        "quality_score": 4,
    }

    async def fake_send_message(prompt, **kwargs):
        assert "big prompt" in prompt
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(feature_extractor, "send_message_gpt", fake_send_message)

    result = await extract_big_question_features(
        "实验设计大题",
        correct_answer="参考答案",
        question_type="非选择题",
        subject="biology",
    )

    assert result is not None
    assert result["_llm_calls"][0]["purpose"] == "big_question_feature_extraction"
    assert result["_llm_calls"][0]["prompt_id"] == "biology.big_question_feature_extraction"
    assert len(result["_llm_calls"][0]["prompt_hash"]) == 64
    assert result["_llm_calls"][0]["parsed_schema"] == "BigQuestionFeatureResult"
    assert result["_llm_calls"][0]["input_refs"]["question_type"] == "非选择题"
