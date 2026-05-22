import json

import pytest

import question_analyzer
from question_analyzer import QuestionAnalyzer


@pytest.mark.asyncio
async def test_split_questions_attaches_llm_call_metadata(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "split_prompt.txt").write_text("split prompt", encoding="utf-8")
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    async def fake_llm_call(**kwargs):
        content = kwargs["messages"][0]["content"]
        assert "split prompt" in content[0]["text"]
        assert "Word text" in content[0]["text"]
        return json.dumps([
            {"id": 1, "content": "第一题", "image_indices": [0]},
            {"id": 2, "content": "第二题", "image_indices": [0]},
        ], ensure_ascii=False)

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    result = await QuestionAnalyzer().split_questions([b"image-bytes"], extracted_text="Word text")

    assert len(result) == 2
    for question in result:
        call = question["_llm_calls"][0]
        assert call["call_id"] == "exam-split-questions"
        assert call["purpose"] == "split_questions"
        assert call["prompt_id"] == "biology.split_questions"
        assert len(call["prompt_hash"]) == 64
        assert call["parsed_schema"] == "SplitQuestionList"
        assert call["confidence"] == 1.0
        assert call["input_refs"]["image_count"] == 1
        assert call["input_refs"]["extracted_text_length"] == 9
        assert call["metadata"]["question_count"] == 2
