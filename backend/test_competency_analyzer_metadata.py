import json

import pytest

import competency_analyzer
from competency_analyzer import CompetencyAnalyzer


def test_extract_json_accepts_fenced_json_with_trailing_comma():
    assert competency_analyzer._extract_json('```json\n{"a": 1,}\n```') == {"a": 1}


@pytest.mark.asyncio
async def test_analyze_competency_attaches_llm_call_metadata(monkeypatch, tmp_path):
    library_path = tmp_path / "competency_library.json"
    library_path.write_text("{}", encoding="utf-8")

    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "competency_analysis_prompt.txt").write_text(
        "competency prompt {question_text} {knowledge_points}",
        encoding="utf-8",
    )
    monkeypatch.setattr(competency_analyzer, "PROMPT_DIR", prompt_dir)

    payload = {
        "生命观念": {"涉及": True, "具体维度": ["结构与功能观"], "权重": 0.2, "分析说明": "关联结构"},
        "科学思维": {"涉及": True, "具体维度": ["归纳概括"], "权重": 0.5, "分析说明": "分析变量"},
        "科学探究": {"涉及": True, "具体维度": ["实验设计"], "权重": 0.3, "分析说明": "设计实验"},
        "社会责任": {"涉及": False, "具体维度": [], "权重": 0.0, "分析说明": ""},
        "primary_competency": "科学思维",
        "competency_level": "高",
    }

    async def fake_llm_call(messages, **kwargs):
        assert "competency prompt" in messages[0]["content"]
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(competency_analyzer, "llm_call", fake_llm_call)

    analyzer = CompetencyAnalyzer(library_path=str(library_path))
    result = await analyzer.analyze_competency({
        "id": 9,
        "content": "分析酶活性实验变量",
        "knowledge_points": ["酶", "实验设计"],
    })

    call = result["_llm_calls"][0]
    assert call["call_id"] == "question-9-competency"
    assert call["question_id"] == 9
    assert call["purpose"] == "competency_analysis"
    assert call["prompt_id"] == "biology.competency_analysis"
    assert len(call["prompt_hash"]) == 64
    assert call["parsed_schema"] == "CompetencyResult"
    assert call["confidence"] == result["_extraction_confidence"]
    assert call["input_refs"]["knowledge_point_count"] == 2


@pytest.mark.asyncio
async def test_analyze_competency_failed_json_keeps_call_metadata(monkeypatch, tmp_path):
    library_path = tmp_path / "competency_library.json"
    library_path.write_text("{}", encoding="utf-8")

    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "competency_analysis_prompt.txt").write_text(
        "competency prompt {question_text} {knowledge_points}",
        encoding="utf-8",
    )
    monkeypatch.setattr(competency_analyzer, "PROMPT_DIR", prompt_dir)

    async def fake_llm_call(messages, **kwargs):
        return '{"invalid": }'

    monkeypatch.setattr(competency_analyzer, "llm_call", fake_llm_call)

    analyzer = CompetencyAnalyzer(library_path=str(library_path))
    result = await analyzer.analyze_competency({
        "id": 12,
        "content": "genetics item",
        "knowledge_points": ["genetics"],
    })

    assert "error" in result
    call = result["_llm_calls"][0]
    assert call["purpose"] == "competency_analysis"
    assert call["confidence"] == 0.0
    assert call["metadata"]["failure_type"] == "json_parse_failed"
    assert call["metadata"]["validation_errors"]
