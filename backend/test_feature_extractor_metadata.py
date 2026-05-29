import json

import pytest

import feature_extractor
import prompt_loader
from feature_extractor import extract_big_question_features, extract_features, parse_features


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


def test_parse_features_recovers_nested_json_with_trailing_text():
    raw = json.dumps(_feature_payload(), ensure_ascii=False) + "\n模型备注：已完成。"

    result = parse_features(raw, include_status=True)

    assert result["_raw_core_count"] == 9
    assert result["working_memory"] == 4
    assert result["teacher_comment"] == "适合考查变量分析。"


def test_parse_features_salvages_fields_from_truncated_json():
    raw = """
    {
      "working_memory": 4,
      "working_memory_reason": "遗传方式+电泳结果+家系关系",
      "reasoning_steps": 5,
      "steps_detail": "判断遗传方式并结合电泳排除",
      "chain_coupling": 1,
      "coupling_reason": "选项独立判断",
      "trap_density": 2,
      "trap_reason": "电泳条带易错",
      "novelty": 2,
      "novelty_reason": "遗传题变式",
      "knowledge_breadth": 2,
      "breadth_reason": "遗传和检测",
      "bloom": 5,
      "bloom_reason": "评价选项证据",
      "info_density": 3,
      "density_reason": "图文信息较多",
      "representation_complexity": 2,
      "representation_reason": "系谱图和电泳图",
      "quality_score": 4,
      "quality_scientific": "无明显问题",
      "quality_normative": "图示信息充分",
      "quality_language": "表述清晰",
      "quality_context": "情境合理",
      "quality_sensitivity": "无舆情风险",
      "teacher_comment": "适合训练遗传证据推理。"
    """

    result = parse_features(raw, include_status=True)

    assert result["_raw_core_count"] == 9
    assert result["_parse_recovery"] == "field_salvage"
    assert result["representation_complexity"] == 2


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
async def test_extract_features_uses_visual_context_without_sending_images_to_deepseek(monkeypatch, tmp_path):
    monkeypatch.setattr(prompt_loader, "_PROMPTS_DIR", _prepare_prompt_dir(tmp_path))

    captured = {}

    async def fake_extract_visual_context(media_items, **kwargs):
        assert media_items[0]["base64"].startswith("iVBOR")
        return "Visual context extracted by Qwen Vision for DeepSeek review only:\nocr_text: curve labels", {
            "call_id": "biology-feature-visual-context",
            "question_id": None,
            "purpose": "image_inputs",
            "prompt_id": "biology.image_inputs.visual_context",
            "prompt_hash": "a" * 64,
            "provider": "qwen_vision",
            "model": "qwen3-vl-plus",
            "input_refs": {"media_count": 1, "media_types": ["image"]},
            "parsed_schema": "VisualContextResult",
            "confidence": 0.9,
            "validation_errors": [],
            "fallback_count": 0,
            "retry_count": 0,
            "metadata": {"used_as": "deepseek_text_prompt_context"},
        }

    async def fake_send_message(prompt, **kwargs):
        captured["prompt"] = prompt
        assert kwargs["purpose"] == "feature_extraction"
        return json.dumps(_feature_payload(), ensure_ascii=False)

    monkeypatch.setattr(feature_extractor, "extract_visual_context", fake_extract_visual_context)
    monkeypatch.setattr(feature_extractor, "send_message_gpt", fake_send_message)

    result = await extract_features(
        "图像题题干",
        question_type="实验题",
        subject="biology",
        media_items=[{"type": "image", "base64": "iVBORw0KGgoAAA"}],
    )

    assert "curve labels" in captured["prompt"]
    assert result["_llm_calls"][0]["purpose"] == "image_inputs"
    call = result["_llm_calls"][1]
    assert call["purpose"] == "feature_extraction"
    assert call["input_refs"]["media_count"] == 1
    assert call["metadata"]["visual_context_source"] == "qwen_vision"


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
        assert kwargs["purpose"] == "big_question_feature_extraction"
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
