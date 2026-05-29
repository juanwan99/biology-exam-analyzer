import json

import pytest

import vision_context


@pytest.mark.asyncio
async def test_extract_visual_context_records_qwen_vision_call(monkeypatch):
    async def fake_llm_call(**kwargs):
        content = kwargs["messages"][0]["content"]
        assert kwargs["purpose"] == "image_inputs"
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
        return json.dumps({
            "visual_text": "装置图显示光照变量",
            "ocr_text": "甲 乙",
            "tables": [],
            "figures": ["甲组有光照，乙组遮光"],
            "uncertainties": [],
        }, ensure_ascii=False)

    monkeypatch.setattr(vision_context, "llm_call", fake_llm_call)
    monkeypatch.setattr(
        vision_context,
        "get_last_call_metadata",
        lambda: {
            "provider": "qwen_vision",
            "model": "qwen3-vl-plus",
            "fallback_count": 0,
            "status": "ok",
            "model_policy": "exam-review-qwen-vision",
        },
    )

    text, call = await vision_context.extract_visual_context(
        [{"type": "image", "base64": "iVBORw0KGgoAAA"}],
        question_text="观察实验装置图",
        question_id=6,
        question_type="experiment",
    )

    assert "光照变量" in text
    assert call["purpose"] == "image_inputs"
    assert call["provider"] == "qwen_vision"
    assert call["model"] == "qwen3-vl-plus"
    assert call["input_refs"]["media_count"] == 1
    assert call["metadata"]["used_as"] == "deepseek_text_prompt_context"


@pytest.mark.asyncio
async def test_extract_visual_context_recovers_non_json_text(monkeypatch):
    async def fake_llm_call(**kwargs):
        return "图中包含两条曲线：甲组上升，乙组下降。坐标轴为处理时间和相对含量。"

    monkeypatch.setattr(vision_context, "llm_call", fake_llm_call)
    monkeypatch.setattr(
        vision_context,
        "get_last_call_metadata",
        lambda: {
            "provider": "qwen_vision",
            "model": "qwen3-vl-plus",
            "fallback_count": 0,
            "status": "ok",
            "model_policy": "exam-review-qwen-vision",
        },
    )

    text, call = await vision_context.extract_visual_context(
        [{"type": "image", "base64": "iVBORw0KGgoAAA"}],
        question_text="观察曲线图",
        question_id=21,
        question_type="short_answer",
    )

    assert "甲组上升" in text
    assert call["provider"] == "qwen_vision"
    assert call["metadata"]["parse_recovery"] == "raw_visual_text"
    assert call["validation_errors"] == []
