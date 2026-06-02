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
async def test_analyze_competency_normalizes_near_miss_weight_sum(monkeypatch, tmp_path):
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
        "生命观念": {"涉及": True, "具体维度": ["结构与功能观"], "权重": 0.4, "分析说明": "结构"},
        "科学思维": {"涉及": True, "具体维度": ["模型与建模"], "权重": 0.5, "分析说明": "模型"},
        "科学探究": {"涉及": False, "具体维度": [], "权重": 0.0, "分析说明": ""},
        "社会责任": {"涉及": False, "具体维度": [], "权重": 0.0, "分析说明": ""},
        "primary_competency": "科学思维",
        "competency_level": "高",
    }

    async def fake_llm_call(messages, **kwargs):
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(competency_analyzer, "llm_call", fake_llm_call)

    analyzer = CompetencyAnalyzer(library_path=str(library_path))
    result = await analyzer.analyze_competency({
        "id": 13,
        "content": "叶绿体蛋白转运",
        "knowledge_points": ["蛋白质转运"],
    })

    call = result["_llm_calls"][0]
    assert call["validation_errors"] == []
    assert call["metadata"]["weight_sum_normalized_from"] == 0.9
    assert abs(call["metadata"]["total_weight"] - 1.0) <= 0.01
    assert abs(
        result["生命观念"]["权重"]
        + result["科学思维"]["权重"]
        + result["科学探究"]["权重"]
        + result["社会责任"]["权重"]
        - 1.0
    ) <= 0.01


@pytest.mark.asyncio
async def test_analyze_competency_recovers_length_failure_with_compact_json(monkeypatch, tmp_path):
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
        "生命观念": {"涉及": True, "具体维度": ["稳态与平衡观"], "权重": 0.3, "分析说明": "理解调节机制"},
        "科学思维": {"涉及": True, "具体维度": ["演绎与推理"], "权重": 0.5, "分析说明": "分析实验结果"},
        "科学探究": {"涉及": True, "具体维度": ["得出结论"], "权重": 0.2, "分析说明": "根据数据判断"},
        "社会责任": {"涉及": False, "具体维度": [], "权重": 0.0, "分析说明": ""},
        "primary_competency": "科学思维",
        "competency_level": "高",
    }
    calls = []

    async def fake_llm_call(messages, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("openai_chat provider_incomplete_response: finish_reason=length")
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(competency_analyzer, "llm_call", fake_llm_call)
    monkeypatch.setattr(
        competency_analyzer,
        "get_last_call_metadata",
        lambda: {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "fallback_count": 0,
            "provider_errors": [],
            "status": "ok",
            "model_policy": "exam-review-deepseek-primary",
        },
        raising=False,
    )

    analyzer = CompetencyAnalyzer(library_path=str(library_path))
    result = await analyzer.analyze_competency({
        "id": 18,
        "content": "实验分析大题" * 200,
        "knowledge_points": ["稳态调节", "实验分析"],
    })

    assert len(calls) == 2
    assert calls[0]["max_tokens"] == 8192
    assert calls[1]["max_tokens"] == 4096
    assert result["primary_competency"] == "科学思维"
    call = result["_llm_calls"][0]
    assert call["provider"] == "deepseek"
    assert call["model"] == "deepseek-v4-pro"
    assert call["retry_count"] == 1
    assert call["metadata"]["recovery_mode"] == "compact_json"
    assert call["metadata"]["recovery_status"] == "ok"


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


@pytest.mark.asyncio
async def test_analyze_competency_sends_media_and_records_fallback(monkeypatch, tmp_path):
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
        "鐢熷懡瑙傚康": {"娑夊強": False, "鍏蜂綋缁村害": [], "鏉冮噸": 0.0, "鍒嗘瀽璇存槑": ""},
        "绉戝鎬濈淮": {"娑夊強": True, "鍏蜂綋缁村害": ["褰掔撼姒傛嫭"], "鏉冮噸": 0.6, "鍒嗘瀽璇存槑": "鍒嗘瀽鍥捐〃"},
        "绉戝鎺㈢┒": {"娑夊強": True, "鍏蜂綋缁村害": ["瀹為獙璁捐"], "鏉冮噸": 0.4, "鍒嗘瀽璇存槑": "璇嗗埆瀹為獙缁撴灉"},
        "绀句細璐ｄ换": {"娑夊強": False, "鍏蜂綋缁村害": [], "鏉冮噸": 0.0, "鍒嗘瀽璇存槑": ""},
        "primary_competency": "绉戝鎬濈淮",
        "competency_level": "楂?",
    }
    captured = {}

    async def fake_extract_visual_context(media_items, **kwargs):
        assert media_items[0]["base64"].startswith("iVBOR")
        return "Visual context extracted by Qwen Vision for DeepSeek review only:\nocr_text: chart labels", {
            "call_id": "question-18-competency-visual-context",
            "question_id": 18,
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

    async def fake_llm_call(messages, **kwargs):
        captured["messages"] = messages
        return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(competency_analyzer, "llm_call", fake_llm_call)
    monkeypatch.setattr(competency_analyzer, "extract_visual_context", fake_extract_visual_context)
    monkeypatch.setattr(
        competency_analyzer,
        "get_last_call_metadata",
        lambda: {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "fallback_count": 1,
            "provider_errors": [{"provider": "primary", "message": "timeout"}],
            "status": "ok",
        },
    )

    analyzer = CompetencyAnalyzer(library_path=str(library_path))
    result = await analyzer.analyze_competency({
        "id": 18,
        "content": "experiment chart item",
        "knowledge_points": ["experiment"],
        "media_items": [{"type": "image", "base64": "iVBORw0KGgoAAA"}],
    })

    content = captured["messages"][0]["content"]
    assert isinstance(content, str)
    assert "chart labels" in content
    assert "image_url" not in content
    assert result["_llm_calls"][0]["purpose"] == "image_inputs"
    call = result["_llm_calls"][1]
    assert call["fallback_count"] == 1
    assert call["provider"] == "deepseek"
    assert call["input_refs"]["media_count"] == 1
    assert call["metadata"]["visual_context_source"] == "qwen_vision"
    assert call["metadata"]["provider_errors"]
