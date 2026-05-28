import json

import pytest

import question_analyzer
from question_analyzer import QuestionAnalyzer


def test_normalize_fine_grained_accepts_du_su_alias_fields():
    data = {
        "scoring_units": [
            {
                "seu_id": "seu_1",
                "label": "infer mechanism",
                "score_share": 1.0,
                "allocation_source": "inferred",
                "allocation_confidence": 0.8,
                "knowledge_links": [{"knowledge_point": "gene expression", "share": 1.0}],
                "bloom_level": 4,
                "competency_weights": {
                    "生命观念": 0.4,
                    "科学思维": 0.5,
                    "科学探究": 0.1,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 8.0,
                "reasoning_brief": "use evidence",
            }
        ],
        "diagnostic_units": [
            {
                "du_id": "DU_1",
                "label": "ignore N-terminal signal",
                "trap_strength": 3,
                "if_selected_means": "missed protein localization cue",
            }
        ],
        "stimulus_units": [
            {
                "su_id": "SU_1",
                "label": "fusion protein stem",
                "type": "text",
                "complexity": "high",
                "is_core": True,
            }
        ],
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    from llm_schemas import FineGrainedResult

    result = FineGrainedResult(**normalized)
    assert result.diagnostic_units[0].option_or_trap == "ignore N-terminal signal"
    assert result.diagnostic_units[0].misconception == "ignore N-terminal signal"
    assert result.diagnostic_units[0].if_selected_means == ["missed protein localization cue"]
    assert result.stimulus_units[0].description == "fusion protein stem"
    assert result.stimulus_units[0].stimulus_type == "text"
    assert result.stimulus_units[0].complexity == 3
    assert "label_to_option_or_trap" in notes


@pytest.mark.asyncio
async def test_analyze_question_attaches_llm_call_record(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt.txt").write_text(
        "Analyze {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    async def fake_llm_call(**kwargs):
        return json.dumps({
            "knowledge_points": ["cell membrane"],
            "detailed_analysis": "Use membrane structure to select the answer.",
            "difficulty": "medium",
            "common_mistakes": ["confuse phospholipid and protein roles"],
            "answer": "C",
            "total_score": 2,
            "bloom_level": 3,
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    result = await QuestionAnalyzer().analyze_question(
        question_text="Which statement about cell membrane is correct?",
        question_images=[],
        question_id=7,
        question_type="single_choice",
        section_header="single choice, 2 points each",
    )

    assert result["answer"] == "C"
    assert result["_analysis_version"] == "v1"
    call = result["_llm_calls"][0]
    assert call["call_id"] == "question-7-analysis"
    assert call["question_id"] == 7
    assert call["purpose"] == "question_analysis"
    assert call["prompt_id"] == "biology.question_analysis.v1"
    assert len(call["prompt_hash"]) == 64
    assert call["provider"] == "llm_client"
    assert call["model"] == "configured_provider_chain"
    assert call["parsed_schema"] == "AnalysisResult"
    assert call["confidence"] == result["_extraction_confidence"]
    assert call["input_refs"]["question_type"] == "single_choice"
    assert call["input_refs"]["image_count"] == 0


@pytest.mark.asyncio
async def test_analyze_question_records_actual_provider_model_metadata(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt.txt").write_text(
        "Analyze {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    async def fake_llm_call(**kwargs):
        return json.dumps({
            "knowledge_points": ["gene regulation"],
            "detailed_analysis": "Use the experiment context to infer the answer.",
            "difficulty": "hard",
            "common_mistakes": ["ignore control group"],
            "answer": "reference",
            "total_score": 12,
            "bloom_level": 4,
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)
    monkeypatch.setattr(
        question_analyzer,
        "get_last_call_metadata",
        lambda: {
            "provider": "native_sdk",
            "model": "primary-pro",
            "fallback_count": 1,
            "provider_errors": [{"provider": "deepseek", "error": "timeout"}],
        },
        raising=False,
    )

    result = await QuestionAnalyzer().analyze_question(
        question_text="Analyze the experiment result.",
        question_images=[],
        question_id=18,
        question_type="short_answer",
        section_header="non-choice, 12 points",
    )

    call = result["_llm_calls"][0]
    assert call["provider"] == "native_sdk"
    assert call["model"] == "primary-pro"
    assert call["fallback_count"] == 1
    assert call["metadata"]["provider_errors"][0]["provider"] == "deepseek"


@pytest.mark.asyncio
async def test_analyze_question_injects_ranked_evidence_context_when_enabled(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt.txt").write_text(
        "Analyze {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    seen = {}

    class FakeEvidenceContextProvider:
        async def build_question_context(self, **kwargs):
            seen["context_kwargs"] = kwargs
            return {
                "context_text": "【审题证据上下文】\n1. 评分细则与采分点闭合：检查小问、采分点和分值边界。",
                "metadata": {
                    "provider": "evidence_service",
                    "operation": "rank",
                    "record_ids": ["rubric-closure"],
                    "ranked_count": 1,
                    "candidate_count": 6,
                },
            }

    async def fake_llm_call(**kwargs):
        seen["prompt"] = kwargs["messages"][0]["content"][0]["text"]
        return json.dumps({
            "knowledge_points": ["genetic experiment"],
            "detailed_analysis": "Use evidence context and stem to judge genotype.",
            "difficulty": "medium",
            "common_mistakes": ["ignore scoring boundary"],
            "answer": "reference answer",
            "total_score": 12,
            "bloom_level": 4,
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    result = await QuestionAnalyzer().analyze_question(
        question_text="Analyze a genetic experiment and infer parent genotype.",
        question_images=[],
        question_id=18,
        question_type="short_answer",
        section_header="non-choice, 12 points",
        evidence_context_provider=FakeEvidenceContextProvider(),
        evidence_ranking_enabled=True,
    )

    assert "审题证据上下文" in seen["prompt"]
    assert "题目内容" in seen["prompt"]
    assert seen["prompt"].index("审题证据上下文") < seen["prompt"].index("题目内容")
    assert seen["context_kwargs"]["question_id"] == 18
    call = result["_llm_calls"][0]
    assert call["metadata"]["evidence_context"]["record_ids"] == ["rubric-closure"]
    assert call["metadata"]["evidence_context"]["operation"] == "rank"


@pytest.mark.asyncio
async def test_analyze_question_does_not_call_evidence_ranking_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("EVIDENCE_RANKING_ENABLED", raising=False)
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt.txt").write_text(
        "Analyze {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    class FailingEvidenceContextProvider:
        async def build_question_context(self, **kwargs):
            raise AssertionError("ranking should be disabled by default")

    async def fake_llm_call(**kwargs):
        return json.dumps({
            "knowledge_points": ["cell respiration"],
            "detailed_analysis": "Analyze the stem directly.",
            "difficulty": "medium",
            "common_mistakes": [],
            "answer": "A",
            "total_score": 2,
            "bloom_level": 3,
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    result = await QuestionAnalyzer().analyze_question(
        question_text="Which statement is correct?",
        question_images=[],
        question_id=1,
        question_type="single_choice",
        section_header="choice",
        evidence_context_provider=FailingEvidenceContextProvider(),
    )

    assert result["answer"] == "A"
    assert "evidence_context" not in result["_llm_calls"][0]["metadata"]


@pytest.mark.asyncio
async def test_analyze_question_fails_closed_when_evidence_ranking_fails(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt.txt").write_text(
        "Analyze {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    class FailingEvidenceContextProvider:
        async def build_question_context(self, **kwargs):
            raise RuntimeError("ranking quota denied")

    async def fake_llm_call(**kwargs):
        raise AssertionError("LLM should not be called when ranking fails")

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    with pytest.raises(RuntimeError, match="ranking quota denied"):
        await QuestionAnalyzer().analyze_question(
            question_text="Analyze a genetic experiment.",
            question_images=[],
            question_id=18,
            question_type="short_answer",
            section_header="non-choice, 12 points",
            evidence_context_provider=FailingEvidenceContextProvider(),
            evidence_ranking_enabled=True,
        )


@pytest.mark.asyncio
async def test_long_short_answer_uses_extended_timeout(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt.txt").write_text(
        "Analyze {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    seen = {}

    async def fake_llm_call(**kwargs):
        seen["timeout"] = kwargs["timeout"]
        return json.dumps({
            "knowledge_points": ["gene expression"],
            "detailed_analysis": "Long constructed response.",
            "difficulty": "hard",
            "common_mistakes": [],
            "answer": "reference",
            "total_score": 14,
            "bloom_level": 5,
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    await QuestionAnalyzer().analyze_question(
        question_text="long stem " * 80,
        question_images=[],
        question_id=21,
        question_type="short_answer",
        section_header="non-choice",
    )

    assert seen["timeout"] == 240.0


@pytest.mark.asyncio
async def test_invalid_v2_json_uses_compact_retry_with_metadata(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt_v2.txt").write_text(
        "Analyze {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    calls = []

    async def fake_llm_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return '{"scoring_units": [{"seu_id": "seu_1"'
        if len(calls) == 3:
            return json.dumps({
                "diagnostic_units": [
                    {
                        "du_id": "du_1",
                        "option_or_trap": "trap_1",
                        "distractor_type": "misconception",
                        "misconception": "ignore molecular evidence",
                        "trap_strength": 3,
                        "knowledge_boundary": "gene expression evidence must support the mechanism",
                        "if_selected_means": ["cannot connect evidence to mechanism"],
                    }
                ],
                "stimulus_units": [
                    {
                        "su_id": "su_1",
                        "stimulus_type": "text",
                        "complexity": 2,
                        "is_core": True,
                        "description": "molecular evidence stem",
                    }
                ],
            })
        return json.dumps({
            "scoring_units": [
                {
                    "seu_id": "seu_1",
                    "label": "explain gene expression evidence",
                    "score_share": 1.0,
                    "allocation_source": "inferred",
                    "allocation_confidence": "high",
                    "knowledge_links": [
                        {"kp_id": "gene expression", "share": 1.0}
                    ],
                    "bloom_level": "分析",
                    "competency_weights": {
                        "生命观念": 0.4,
                        "科学思维": 0.4,
                        "科学探究": 0.2,
                        "社会责任": 0.0,
                    },
                    "difficulty_estimate": "Hard",
                    "reasoning_brief": "connect evidence to mechanism",
                }
            ],
            "diagnostic_units": [],
            "stimulus_units": [],
            "answer": {"text": "reference answer"},
            "total_score": 14,
            "detailed_analysis": "Use evidence to infer the biological mechanism.",
            "difficulty": "困难",
            "knowledge_points": ["gene expression"],
            "common_mistakes": ["ignore evidence"],
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    async def fake_extract_visual_context(media_items, **kwargs):
        assert media_items[0]["base64"].startswith("iVBOR")
        return "Visual context extracted by Qwen Vision for DeepSeek review only:\nocr_text: figure labels", {
            "call_id": "question-21-visual-context",
            "question_id": 21,
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

    monkeypatch.setattr(question_analyzer, "extract_visual_context", fake_extract_visual_context)

    png_bytes = b"\x89PNG\r\n\x1a\nfake"

    result = await QuestionAnalyzer().analyze_question(
        question_text="long constructed response",
        question_images=[png_bytes],
        question_id=21,
        question_type="short_answer",
        section_header="non-choice",
    )

    assert len(calls) == 3
    for llm_call_kwargs in calls:
        content = llm_call_kwargs["messages"][0]["content"]
        assert isinstance(content, list)
        assert len(content) == 1
        assert "figure labels" in content[0]["text"]
    assert result["_analysis_version"] == "v2_json_repair"
    assert result["_fine_grained"]["scoring_units"]
    assert result["_fine_grained"]["diagnostic_units"]
    assert result["_fine_grained"]["stimulus_units"]
    assert result["_llm_calls"][0]["purpose"] == "image_inputs"
    call = result["_llm_calls"][1]
    assert call["call_id"] == "question-21-analysis-repair"
    assert call["purpose"] == "question_analysis"
    assert call["prompt_id"] == "biology.question_analysis.v2.json_repair"
    assert call["input_refs"]["media_count"] == 1
    assert call["input_refs"]["media_types"] == ["image"]
    assert call["retry_count"] == 1
    assert "initial_parse_error" in call["metadata"]
    assert call["metadata"]["initial_response_length"] > 0
    assert call["metadata"]["normalization_notes"]
    assert call["metadata"]["visual_context_source"] == "qwen_vision"
    evidence_call = result["_llm_calls"][2]
    assert evidence_call["call_id"] == "question-21-evidence-retry"
    assert evidence_call["prompt_id"] == "biology.question_analysis.v2.evidence_retry"
    assert evidence_call["input_refs"]["media_count"] == 1
    assert evidence_call["input_refs"]["media_types"] == ["image"]
    assert evidence_call["metadata"]["diagnostic_units_count"] == 1
    assert evidence_call["metadata"]["stimulus_units_count"] == 1
    seu = result["_fine_grained"]["scoring_units"][0]
    assert seu["knowledge_links"][0]["knowledge_point"] == "gene expression"
    assert seu["bloom_level"] == 4
    assert seu["difficulty_estimate"] == 8.0
    assert result["answer"] == '{"text": "reference answer"}'
