import json

import pytest

import question_analyzer
from question_analyzer import QuestionAnalyzer


@pytest.mark.asyncio
async def test_analyze_question_recovers_length_failures_with_minimal_json(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt_v2.txt").write_text(
        "Return a full fine-grained JSON object for {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    purposes = []
    calls = []

    async def fake_llm_call(**kwargs):
        purposes.append(kwargs.get("purpose"))
        calls.append(kwargs)
        if len(purposes) <= 4:
            raise RuntimeError("openai_chat provider_incomplete_response: finish_reason=length")
        return json.dumps({
            "knowledge_points": ["gene editing"],
            "detailed_analysis": "Use the experimental design to infer the result.",
            "difficulty": "困难",
            "common_mistakes": ["ignore control group"],
            "answer": "reference answer",
            "total_score": 12,
            "bloom_level": 4,
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)
    monkeypatch.setattr(
        question_analyzer,
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

    result = await QuestionAnalyzer().analyze_question(
        question_text="Short biology item",
        question_images=[],
        question_id=21,
        question_type="single_choice",
        section_header="single choice, 2 points",
    )

    assert purposes[:3] == [
        "question_analysis",
        "question_analysis_retry",
        "question_analysis_retry",
    ]
    assert purposes[3:] == [
        "question_analysis_retry",
        "question_analysis_retry",
        "missing_evidence_repair",
    ]
    assert calls[1]["max_tokens"] <= 8192
    assert calls[1]["timeout"] <= 220
    assert calls[2]["max_tokens"] <= 4096
    assert calls[2]["timeout"] <= 180
    assert calls[3]["max_tokens"] <= 2048
    assert calls[3]["timeout"] <= 140
    assert calls[4]["max_tokens"] <= 3072
    assert calls[4]["timeout"] <= 180
    assert result["_analysis_version"] == "v1_length_recovery"
    assert result["answer"] == "reference answer"
    call = result["_llm_calls"][0]
    assert call["provider"] == "deepseek"
    assert call["model"] == "deepseek-v4-pro"
    assert call["retry_count"] == 4
    assert call["metadata"]["recovery_mode"] == "minimal_json"


@pytest.mark.asyncio
async def test_compact_v2_retry_marks_successful_recovery(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt_v2.txt").write_text(
        "Return a full fine-grained JSON object for {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    calls = []

    async def fake_llm_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("openai_chat provider_incomplete_response: finish_reason=length")
        return json.dumps({
            "scoring_units": [
                {
                    "seu_id": "seu_1",
                    "label": "analyze evidence chain",
                    "score_share": 1.0,
                    "allocation_source": "inferred",
                    "allocation_confidence": 0.8,
                    "knowledge_links": [
                        {"knowledge_point": "gene expression", "share": 1.0}
                    ],
                    "bloom_level": 4,
                    "competency_weights": {
                        "生命观念": 0.2,
                        "科学思维": 0.6,
                        "科学探究": 0.2,
                        "社会责任": 0.0,
                    },
                    "difficulty_estimate": 8.0,
                    "reasoning_brief": "connect evidence to mechanism",
                }
            ],
            "diagnostic_units": [
                {
                    "du_id": "du_1",
                    "option_or_trap": "trap_1",
                    "distractor_type": "misconception",
                    "misconception": "ignore evidence",
                    "trap_strength": 3,
                    "knowledge_boundary": "evidence must support mechanism",
                    "if_selected_means": ["weak evidence chain"],
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
            "answer": "reference answer",
            "total_score": 14,
            "detailed_analysis": "Use evidence to infer the biological mechanism.",
            "difficulty": "困难",
            "knowledge_points": ["gene expression"],
            "common_mistakes": ["ignore evidence"],
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)
    monkeypatch.setattr(
        question_analyzer,
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

    result = await QuestionAnalyzer().analyze_question(
        question_text="Long constructed response " * 100,
        question_images=[],
        question_id=21,
        question_type="short_answer",
        section_header="non-choice, 14 points",
    )

    assert len(calls) == 2
    assert result["_analysis_version"] == "v2_compact_retry"
    call = result["_llm_calls"][0]
    assert call["purpose"] == "question_analysis"
    assert call["prompt_id"] == "biology.question_analysis.v2.compact_retry"
    assert call["retry_count"] == 1
    assert call["metadata"]["recovery_mode"] == "compact_v2"
    assert call["metadata"]["recovery_status"] == "ok"


@pytest.mark.asyncio
async def test_analyze_question_uses_skeletal_retry_for_big_non_choice_after_micro_length_failure(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt_v2.txt").write_text(
        "Return a full fine-grained JSON object for {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    calls = []

    async def fake_llm_call(**kwargs):
        calls.append(kwargs)
        if len(calls) <= 4:
            raise RuntimeError("openai_chat provider_incomplete_response: finish_reason=length")
        return json.dumps({
            "kp": ["突变类型辨析", "基因表达与性状的关系", "表观遗传"],
            "diff": "困难",
            "bloom": 5,
            "labels": ["遗传判断", "电泳证据", "机制评价"],
            "trap": "证据混淆",
            "stimulus": "系谱电泳",
            "answer": "",
            "analysis": "综合证据判断",
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)
    monkeypatch.setattr(
        question_analyzer,
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

    result = await QuestionAnalyzer().analyze_question(
        question_text="脆性X综合征系谱与电泳图综合判断 " * 100,
        question_images=[],
        question_id=21,
        question_type="short_answer",
        section_header="non-choice, 14 points",
    )

    assert [call["purpose"] for call in calls] == [
        "question_analysis",
        "question_analysis_retry",
        "question_analysis_retry",
        "question_analysis_retry",
        "question_analysis_retry",
    ]
    assert calls[4]["max_tokens"] <= 1536
    assert result["_analysis_version"] == "v2_skeletal_fine_grained_retry"
    assert result["total_score"] == 14
    assert len(result["_fine_grained"]["scoring_units"]) == 3
    assert len(result["_fine_grained"]["diagnostic_units"]) == 1
    assert len(result["_fine_grained"]["stimulus_units"]) == 1
    assert result["knowledge_points"][0] == "基因突变"
    call = result["_llm_calls"][0]
    assert call["prompt_id"] == "biology.question_analysis.v2.skeletal_fine_grained_retry"
    assert call["retry_count"] == 4
    assert call["metadata"]["recovery_mode"] == "llm_guided_skeletal_fine_grained"


@pytest.mark.asyncio
async def test_analyze_question_uses_skeletal_retry_for_media_choice_after_micro_length_failure(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt_v2.txt").write_text(
        "Return a full fine-grained JSON object for {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    calls = []

    async def fake_llm_call(**kwargs):
        calls.append(kwargs)
        if len(calls) <= 4:
            raise RuntimeError("openai_chat provider_incomplete_response: finish_reason=length")
        return json.dumps({
            "kp": ["突变类型辨析", "不完全外显与遗传咨询", "电泳结果分析"],
            "diff": "困难",
            "bloom": 4,
            "labels": ["系谱判断", "电泳证据", "外显分析"],
            "trap": "图文错配",
            "stimulus": "系谱电泳",
            "answer": "B",
            "analysis": "图文证据联合判断",
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)
    monkeypatch.setattr(
        question_analyzer,
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

    async def fake_extract_visual_context(media_items, **kwargs):
        return "Visual context extracted by Qwen Vision for DeepSeek review only:\n系谱图和电泳图", {
            "call_id": "question-16-visual-context",
            "question_id": 16,
            "purpose": "image_inputs",
            "prompt_id": "biology.image_inputs.visual_context",
            "prompt_hash": "b" * 64,
            "provider": "qwen_vision",
            "model": "qwen3-vl-plus",
            "input_refs": {"media_count": 1, "media_types": ["image"]},
            "parsed_schema": "VisualContextResult",
            "confidence": 0.85,
            "validation_errors": [],
            "fallback_count": 0,
            "retry_count": 0,
            "metadata": {"used_as": "deepseek_text_prompt_context"},
        }

    monkeypatch.setattr(question_analyzer, "extract_visual_context", fake_extract_visual_context)

    result = await QuestionAnalyzer().analyze_question(
        question_text="脆性X综合征CGG重复扩增，结合家系图和电泳图判断选项正误。" * 8,
        question_images=[b"\x89PNG\r\n\x1a\nfake"],
        question_id=16,
        question_type="multiple_choice",
        section_header="multiple choice, 4 points each",
    )

    assert [call["purpose"] for call in calls] == [
        "question_analysis",
        "question_analysis_retry",
        "question_analysis_retry",
        "question_analysis_retry",
        "question_analysis_retry",
    ]
    assert result["_analysis_version"] == "v2_skeletal_fine_grained_retry"
    assert result["total_score"] == 4
    assert result["_llm_calls"][0]["purpose"] == "image_inputs"
    call = result["_llm_calls"][1]
    assert call["prompt_id"] == "biology.question_analysis.v2.skeletal_fine_grained_retry"
    assert call["metadata"]["recovery_mode"] == "llm_guided_skeletal_fine_grained"
    assert call["metadata"]["visual_context_source"] == "qwen_vision"


@pytest.mark.asyncio
async def test_analyze_question_recovers_compact_length_failure_with_ultra_compact_json(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt_v2.txt").write_text(
        "Return a full fine-grained JSON object for {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    calls = []

    async def fake_llm_call(**kwargs):
        calls.append(kwargs)
        if len(calls) <= 2:
            raise RuntimeError("openai_chat provider_incomplete_response: finish_reason=length")
        return json.dumps({
            "scoring_units": [
                {
                    "seu_id": "seu_1",
                    "label": "定位基因",
                    "score_share": 0.34,
                    "allocation_source": "inferred",
                    "allocation_confidence": 0.7,
                    "knowledge_links": [{"knowledge_point": "基因工程", "share": 1.0}],
                    "bloom_level": 4,
                    "competency_weights": {"生命观念": 0.2, "科学思维": 0.5, "科学探究": 0.3, "社会责任": 0.0},
                    "difficulty_estimate": 8.0,
                    "reasoning_brief": "证据定位",
                },
                {
                    "seu_id": "seu_2",
                    "label": "解释调控",
                    "score_share": 0.33,
                    "allocation_source": "inferred",
                    "allocation_confidence": 0.7,
                    "knowledge_links": [{"knowledge_point": "基因表达调控", "share": 1.0}],
                    "bloom_level": 4,
                    "competency_weights": {"生命观念": 0.2, "科学思维": 0.5, "科学探究": 0.3, "社会责任": 0.0},
                    "difficulty_estimate": 8.4,
                    "reasoning_brief": "调控推理",
                },
                {
                    "seu_id": "seu_3",
                    "label": "方案评价",
                    "score_share": 0.33,
                    "allocation_source": "inferred",
                    "allocation_confidence": 0.7,
                    "knowledge_links": [{"knowledge_point": "代谢工程", "share": 1.0}],
                    "bloom_level": 5,
                    "competency_weights": {"生命观念": 0.1, "科学思维": 0.5, "科学探究": 0.4, "社会责任": 0.0},
                    "difficulty_estimate": 8.8,
                    "reasoning_brief": "方案评价",
                },
            ],
            "diagnostic_units": [
                {
                    "du_id": "du_1",
                    "option_or_trap": "trap_1",
                    "distractor_type": "misconception",
                    "misconception": "忽略启动子",
                    "trap_strength": 3,
                    "knowledge_boundary": "表达调控",
                    "if_selected_means": ["未识别调控层级"],
                },
                {
                    "du_id": "du_2",
                    "option_or_trap": "trap_2",
                    "distractor_type": "reading_trap",
                    "misconception": "混淆产物",
                    "trap_strength": 2,
                    "knowledge_boundary": "代谢途径",
                    "if_selected_means": ["材料转化不足"],
                },
            ],
            "stimulus_units": [
                {
                    "su_id": "su_1",
                    "stimulus_type": "text",
                    "complexity": 3,
                    "is_core": True,
                    "description": "代谢工程材料",
                }
            ],
            "answer": "参考答案",
            "total_score": 14,
            "detailed_analysis": "结合材料推断基因表达与代谢调控。",
            "difficulty": "困难",
            "knowledge_points": ["基因工程", "基因表达调控", "代谢工程"],
            "common_mistakes": ["忽略启动子", "混淆代谢产物"],
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    result = await QuestionAnalyzer().analyze_question(
        question_text="番茄红素合成与基因工程调控材料题 " * 80,
        question_images=[],
        question_id=21,
        question_type="short_answer",
        section_header="non-choice, 14 points",
    )

    assert [call["purpose"] for call in calls] == [
        "question_analysis",
        "question_analysis_retry",
        "question_analysis_retry",
    ]
    assert calls[2]["max_tokens"] <= 4096
    assert "Question content" in calls[2]["messages"][0]["content"][0]["text"]
    assert result["_analysis_version"] == "v2_ultra_compact_retry"
    assert len(result["_fine_grained"]["scoring_units"]) == 3
    assert len(result["_fine_grained"]["diagnostic_units"]) == 2
    assert len(result["_fine_grained"]["stimulus_units"]) == 1
    call = result["_llm_calls"][0]
    assert call["prompt_id"] == "biology.question_analysis.v2.ultra_compact_retry"
    assert call["retry_count"] == 2
    assert call["metadata"]["recovery_mode"] == "ultra_compact_v2"
    assert call["metadata"]["recovery_status"] == "ok"


@pytest.mark.asyncio
async def test_analyze_question_recovers_ultra_length_failure_with_micro_compact_json(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt_v2.txt").write_text(
        "Return a full fine-grained JSON object for {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    calls = []

    async def fake_llm_call(**kwargs):
        calls.append(kwargs)
        if len(calls) <= 3:
            raise RuntimeError("openai_chat provider_incomplete_response: finish_reason=length")
        return json.dumps({
            "scoring_units": [
                {
                    "seu_id": "s1",
                    "label": "引物设计",
                    "score_share": 0.34,
                    "allocation_source": "inferred",
                    "allocation_confidence": 0.7,
                    "knowledge_links": [{"knowledge_point": "PCR技术扩增目的基因", "share": 1.0}],
                    "bloom_level": 4,
                    "competency_weights": {"生命观念": 0.1, "科学思维": 0.6, "科学探究": 0.3, "社会责任": 0.0},
                    "difficulty_estimate": 8,
                    "reasoning_brief": "定位证据",
                },
                {
                    "seu_id": "s2",
                    "label": "载体构建",
                    "score_share": 0.33,
                    "allocation_source": "inferred",
                    "allocation_confidence": 0.7,
                    "knowledge_links": [{"knowledge_point": "基因表达载体构建", "share": 1.0}],
                    "bloom_level": 4,
                    "competency_weights": {"生命观念": 0.1, "科学思维": 0.6, "科学探究": 0.3, "社会责任": 0.0},
                    "difficulty_estimate": 8,
                    "reasoning_brief": "构建推理",
                },
                {
                    "seu_id": "s3",
                    "label": "表达调控",
                    "score_share": 0.33,
                    "allocation_source": "inferred",
                    "allocation_confidence": 0.7,
                    "knowledge_links": [{"knowledge_point": "基因表达调控", "share": 1.0}],
                    "bloom_level": 5,
                    "competency_weights": {"生命观念": 0.1, "科学思维": 0.6, "科学探究": 0.3, "社会责任": 0.0},
                    "difficulty_estimate": 8,
                    "reasoning_brief": "综合判断",
                },
            ],
            "diagnostic_units": [
                {
                    "du_id": "d1",
                    "option_or_trap": "trap",
                    "distractor_type": "reading_trap",
                    "misconception": "忽略同源臂",
                    "trap_strength": 3,
                    "knowledge_boundary": "引物边界",
                    "if_selected_means": ["证据遗漏"],
                }
            ],
            "stimulus_units": [
                {"su_id": "u1", "stimulus_type": "text", "complexity": 3, "is_core": True, "description": "基因工程材料"}
            ],
            "answer": "",
            "total_score": 14,
            "detailed_analysis": "综合材料判断。",
            "difficulty": "困难",
            "knowledge_points": ["PCR技术扩增目的基因", "基因表达载体构建", "基因表达调控"],
            "common_mistakes": ["忽略证据"],
        })

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    result = await QuestionAnalyzer().analyze_question(
        question_text="番茄红素合成与基因工程调控材料题 " * 120,
        question_images=[],
        question_id=21,
        question_type="short_answer",
        section_header="non-choice, 14 points",
    )

    assert [call["purpose"] for call in calls] == [
        "question_analysis",
        "question_analysis_retry",
        "question_analysis_retry",
        "question_analysis_retry",
    ]
    assert calls[3]["max_tokens"] <= 2048
    assert result["_analysis_version"] == "v2_micro_compact_retry"
    assert len(result["_fine_grained"]["scoring_units"]) == 3
    assert len(result["_fine_grained"]["diagnostic_units"]) == 1
    assert len(result["_fine_grained"]["stimulus_units"]) == 1
    call = result["_llm_calls"][0]
    assert call["prompt_id"] == "biology.question_analysis.v2.micro_compact_retry"
    assert call["retry_count"] == 3
    assert call["metadata"]["recovery_mode"] == "micro_compact_v2"


@pytest.mark.asyncio
async def test_analyze_question_degrades_when_all_length_retries_fail(monkeypatch, tmp_path):
    prompt_dir = tmp_path / "prompts"
    prompt_dir.mkdir()
    (prompt_dir / "analysis_prompt_v2.txt").write_text(
        "Return a full fine-grained JSON object for {question_type}; section={section_header}",
        encoding="utf-8",
    )
    monkeypatch.setattr(question_analyzer, "PROMPT_DIR", prompt_dir)

    calls = []

    async def fake_llm_call(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("openai_chat provider_incomplete_response: finish_reason=length")

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    result = await QuestionAnalyzer().analyze_question(
        question_text="CGG重复扩增导致遗传病的多选题",
        question_images=[],
        question_id=16,
        question_type="multiple_choice",
        section_header="二、选择题：本题共4小题，每小题4分，共16分。",
    )

    assert [call["purpose"] for call in calls] == [
        "question_analysis",
        "question_analysis_retry",
        "question_analysis_retry",
        "question_analysis_retry",
        "question_analysis_retry",
    ]
    assert result["_analysis_version"] == "v1_length_recovery_deterministic"
    assert result["total_score"] == 4.0
    assert result["knowledge_points"] == ["基因突变"]
    assert result["_llm_calls"][0]["retry_count"] == 5
    assert result["_llm_calls"][0]["metadata"]["recovery_mode"] == "deterministic_length_fallback"


def test_normalize_fine_grained_accepts_du_su_alias_fields():
    data = {
        "scoring_units": [
            {
                "seu_id": "seu_1",
                "label": "infer mechanism",
                "score_share": 1.0,
                "allocation_source": "inferred",
                "allocation_confidence": 0.8,
                "knowledge_links": [{"k_id": "KP1", "share": 1.0}],
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
                "stu_id": "SU_1",
                "label": "fusion protein stem",
                "type": "text",
                "complexity": "high",
                "is_core": True,
            }
        ],
        "difficulty": 8.0,
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    from llm_schemas import FineGrainedResult

    result = FineGrainedResult(**normalized)
    assert result.difficulty == "困难"
    assert result.scoring_units[0].knowledge_links[0].knowledge_point == "infer mechanism"
    assert result.diagnostic_units[0].option_or_trap == "ignore N-terminal signal"
    assert result.diagnostic_units[0].misconception == "ignore N-terminal signal"
    assert result.diagnostic_units[0].if_selected_means == ["missed protein localization cue"]
    assert result.stimulus_units[0].su_id == "SU_1"
    assert result.stimulus_units[0].description == "fusion protein stem"
    assert result.stimulus_units[0].stimulus_type == "text"
    assert result.stimulus_units[0].complexity == 3
    assert "label_to_option_or_trap" in notes
    assert "seu_label_to_knowledge_point" in notes
    assert "stu_id_to_su_id" in notes
    assert "difficulty_number_to_label" in notes


def test_normalize_fine_grained_accepts_q16_compact_aliases():
    data = {
        "scoring_units": [
            {
                "score_share": 0.34,
                "knowledge_point": "基因突变",
                "allocation_source": "inferred",
                "allocation_confidence": 0.7,
                "bloom_level": "分析",
                "competency_weights": {
                    "生命观念": 0.2,
                    "科学思维": 0.6,
                    "科学探究": 0.2,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": "Hard",
            },
            {
                "score_share": 0.33,
                "kp": "遗传病",
                "allocation_source": "inferred",
                "allocation_confidence": 0.7,
                "bloom_level": 4,
                "competency_weights": {
                    "生命观念": 0.2,
                    "科学思维": 0.6,
                    "科学探究": 0.2,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 8,
            },
            {
                "score_share": 0.33,
                "label": "电泳证据",
                "allocation_source": "inferred",
                "allocation_confidence": 0.7,
                "bloom_level": 4,
                "competency_weights": {
                    "生命观念": 0.2,
                    "科学思维": 0.6,
                    "科学探究": 0.2,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 8,
            },
        ],
        "diagnostic_units": [
            {
                "diagnostic_id": "diag_01",
                "trap": "A",
                "type": "reading_trap",
                "misunderstanding": "误判突变类型",
                "if_selected_means": "混淆基因突变与染色体变异",
            }
        ],
        "stimulus_units": [
            {
                "id": "pedigree",
                "type": "pedigree",
                "complexity": "high",
                "is_core": True,
            }
        ],
        "answer": "B",
        "total_score": 4,
        "detailed_analysis": "图文证据联合判断。",
        "difficulty": "困难",
        "knowledge_points": [
            {"kp_id": "kp1", "point": "基因突变"},
            {"kp_id": "kp2", "point": "遗传病"},
        ],
        "common_mistakes": ["误读电泳图"],
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    from llm_schemas import FineGrainedResult

    result = FineGrainedResult(**normalized)
    assert result.knowledge_points == ["基因突变", "遗传病"]
    assert result.scoring_units[0].seu_id == "seu_1"
    assert result.scoring_units[0].label == "基因突变"
    assert result.scoring_units[0].knowledge_links[0].knowledge_point == "基因突变"
    assert result.scoring_units[1].knowledge_links[0].knowledge_point == "遗传病"
    assert result.scoring_units[2].knowledge_links[0].knowledge_point == "电泳证据"
    assert result.diagnostic_units[0].du_id == "diag_01"
    assert result.diagnostic_units[0].distractor_type == "reading_trap"
    assert result.diagnostic_units[0].misconception == "误判突变类型"
    assert result.stimulus_units[0].su_id == "pedigree"
    assert "knowledge_points_dicts_to_strings" in notes
    assert "seu_id_defaulted" in notes
    assert "seu_knowledge_point_to_links" in notes
    assert "diagnostic_id_to_du_id" in notes


def test_normalize_fine_grained_accepts_micro_compact_strings_and_difficulty_object():
    data = {
        "scoring_units": [
            {
                "seu_id": "seu_1",
                "label": "引物方向判断",
                "score_share": 0.5,
                "allocation_source": "inferred",
                "allocation_confidence": 0.8,
                "knowledge_links": [{"knowledge_point": "PCR技术扩增目的基因", "share": 1.0}],
                "bloom_level": 5,
                "competency_weights": {
                    "生命观念": 0.1,
                    "科学思维": 0.6,
                    "科学探究": 0.3,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 8.4,
                "reasoning_brief": "依据序列方向定位扩增区间",
            },
            {
                "seu_id": "seu_2",
                "label": "实验流程评价",
                "score_share": 0.5,
                "allocation_source": "inferred",
                "allocation_confidence": 0.8,
                "knowledge_links": [{"knowledge_point": "基因工程的基本操作程序", "share": 1.0}],
                "bloom_level": 5,
                "competency_weights": {
                    "生命观念": 0.1,
                    "科学思维": 0.5,
                    "科学探究": 0.4,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": "中等偏难",
                "reasoning_brief": "综合流程信息作答",
            },
        ],
        "diagnostic_units": [
            "混淆引物方向",
            {"t": "读错序列方向", "m": "把5到3方向看反", "means": "扩增区间判断错误", "trap_strength": "强"},
        ],
        "stimulus_units": [
            "序列图和实验流程",
            {"s": "实验流程图", "kind": "流程图", "complexity": "高"},
        ],
        "answer": "参考答案",
        "total_score": 14,
        "detailed_analysis": "综合序列图与实验流程判断。",
        "difficulty": {"label": ["困难"]},
        "knowledge_points": ["PCR技术扩增目的基因", "基因工程的基本操作程序"],
        "common_mistakes": "混淆引物方向",
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    from llm_schemas import FineGrainedResult

    result = FineGrainedResult(**normalized)
    assert result.difficulty == "困难"
    assert result.scoring_units[1].difficulty_estimate == 6.8
    assert len(result.diagnostic_units) == 2
    assert result.diagnostic_units[0].misconception == "混淆引物方向"
    assert result.diagnostic_units[1].option_or_trap == "读错序列方向"
    assert result.diagnostic_units[1].misconception == "把5到3方向看反"
    assert result.diagnostic_units[1].if_selected_means == ["扩增区间判断错误"]
    assert result.diagnostic_units[1].trap_strength == 3
    assert len(result.stimulus_units) == 2
    assert result.stimulus_units[0].description == "序列图和实验流程"
    assert result.stimulus_units[0].is_core is True
    assert result.stimulus_units[1].su_id == "实验流程图"
    assert result.stimulus_units[1].stimulus_type == "flowchart"
    assert result.stimulus_units[1].complexity == 3
    assert result.common_mistakes == ["混淆引物方向"]
    assert "diagnostic_units_strings_to_dicts" in notes
    assert "stimulus_units_strings_to_dicts" in notes
    assert "difficulty_object_to_label" in notes


def test_normalize_fine_grained_replaces_placeholder_kp_links():
    data = {
        "scoring_units": [
            {
                "seu_id": "seu_1",
                "label": "动态突变",
                "score_share": 0.5,
                "allocation_source": "inferred",
                "allocation_confidence": 0.7,
                "knowledge_links": [{"knowledge_point": "KP1", "share": 1.0}],
                "bloom_level": 4,
                "competency_weights": {
                    "生命观念": 0.2,
                    "科学思维": 0.6,
                    "科学探究": 0.2,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 8.0,
                "reasoning_brief": "判断CGG重复",
            },
            {
                "seu_id": "seu_2",
                "label": "电泳证据",
                "score_share": 0.5,
                "allocation_source": "inferred",
                "allocation_confidence": 0.7,
                "knowledge_links": [{"knowledge_point": "KP2", "share": 1.0}],
                "bloom_level": 4,
                "competency_weights": {
                    "生命观念": 0.2,
                    "科学思维": 0.6,
                    "科学探究": 0.2,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 8.0,
                "reasoning_brief": "解读条带",
            },
        ],
        "diagnostic_units": [
            {
                "du_id": "du_1",
                "option_or_trap": "trap",
                "distractor_type": "reading_trap",
                "misconception": "忽略条带",
                "trap_strength": 2,
                "knowledge_boundary": "电泳证据",
                "if_selected_means": ["证据误读"],
            }
        ],
        "stimulus_units": [
            {
                "su_id": "su_1",
                "stimulus_type": "image",
                "complexity": 3,
                "is_core": True,
                "description": "系谱电泳图",
            }
        ],
        "answer": "B",
        "total_score": 4,
        "detailed_analysis": "图文证据联合判断。",
        "difficulty": "困难",
        "knowledge_points": [
            {"id": "KP1", "name": "动态突变与前突变传递"},
            {"id": "KP2", "name": "电泳结果分析"},
        ],
        "common_mistakes": ["误读条带"],
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    assert normalized["knowledge_points"] == ["动态突变与前突变传递", "电泳结果分析"]
    assert normalized["scoring_units"][0]["knowledge_links"][0]["knowledge_point"] == "动态突变与前突变传递"
    assert normalized["scoring_units"][1]["knowledge_links"][0]["knowledge_point"] == "电泳结果分析"
    assert "placeholder_knowledge_point_replaced" in notes


def test_normalize_fine_grained_repairs_generic_option_knowledge_labels():
    data = {
        "scoring_units": [
            {
                "seu_id": "seu_1",
                "label": "判断选项A错误",
                "score_share": 0.5,
                "allocation_source": "inferred",
                "allocation_confidence": 0.8,
                "knowledge_links": [{"knowledge_point": "判断选项A错误", "share": 1.0}],
                "bloom_level": 4,
                "competency_weights": {
                    "生命观念": 0.2,
                    "科学思维": 0.8,
                    "科学探究": 0.0,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 6.0,
                "reasoning_brief": "CGG重复扩展属于基因突变",
            },
            {
                "seu_id": "seu_2",
                "label": "判断选项B正确",
                "score_share": 0.5,
                "allocation_source": "inferred",
                "allocation_confidence": 0.8,
                "knowledge_links": [{"knowledge_point": "判断选项B正确", "share": 1.0}],
                "bloom_level": 4,
                "competency_weights": {
                    "生命观念": 0.2,
                    "科学思维": 0.8,
                    "科学探究": 0.0,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 6.0,
                "reasoning_brief": "甲基化抑制F基因表达",
            },
        ],
        "diagnostic_units": [],
        "stimulus_units": [],
        "answer": "BC",
        "total_score": 4,
        "knowledge_points": ["基因突变", "表观遗传"],
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    points = [
        unit["knowledge_links"][0]["knowledge_point"]
        for unit in normalized["scoring_units"]
    ]
    assert points == ["CGG重复扩展属于基因突变", "甲基化抑制F基因表达"]
    assert "placeholder_knowledge_point_replaced" in notes


def test_normalize_fine_grained_accepts_common_mistakes_string():
    data = {
        "scoring_units": [
            {
                "seu_id": "seu_1",
                "label": "引物设计",
                "score_share": 1.0,
                "allocation_source": "inferred",
                "allocation_confidence": 0.7,
                "knowledge_links": [{"knowledge_point": "PCR技术扩增目的基因", "share": 1.0}],
                "bloom_level": 4,
                "competency_weights": {
                    "生命观念": 0.1,
                    "科学思维": 0.6,
                    "科学探究": 0.3,
                    "社会责任": 0.0,
                },
                "difficulty_estimate": 8.0,
                "reasoning_brief": "定位证据",
            }
        ],
        "diagnostic_units": [
            {
                "du_id": "du_1",
                "option_or_trap": "trap",
                "distractor_type": "reading_trap",
                "misconception": "混淆黏性末端作用",
                "trap_strength": 2,
                "knowledge_boundary": "限制酶",
                "if_selected_means": ["误判连接方式"],
            }
        ],
        "stimulus_units": [
            {
                "su_id": "su_1",
                "stimulus_type": "text",
                "complexity": 3,
                "is_core": True,
                "description": "基因工程材料",
            }
        ],
        "answer": "",
        "total_score": 14,
        "detailed_analysis": "综合材料判断。",
        "difficulty": "困难",
        "knowledge_points": ["PCR技术扩增目的基因"],
        "common_mistakes": "混淆黏性末端作用",
    }

    normalized, notes = QuestionAnalyzer._normalize_fine_grained_result(data)

    from llm_schemas import FineGrainedResult

    result = FineGrainedResult(**normalized)
    assert result.common_mistakes == ["混淆黏性末端作用"]
    assert "common_mistakes_string_to_list" in notes


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
            "provider": "qwen_text",
            "model": "qwen-plus",
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
    assert call["provider"] == "qwen_text"
    assert call["model"] == "qwen-plus"
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


def test_big_question_blank_stimulus_units_needs_evidence_repair():
    payload = {
        "total_score": 14,
        "_fine_grained": {
            "diagnostic_units": [
                {
                    "du_id": "du_1",
                    "option_or_trap": "trap",
                    "distractor_type": "reading_trap",
                    "misconception": "忽略材料证据",
                    "trap_strength": 2,
                    "knowledge_boundary": "材料解读",
                    "if_selected_means": ["证据链断裂"],
                }
            ],
            "stimulus_units": [
                {
                    "su_id": "su_1",
                    "stimulus_type": "text",
                    "complexity": 3,
                    "is_core": True,
                    "description": "",
                }
            ],
        },
    }

    assert QuestionAnalyzer._needs_evidence_units(payload, "short_answer") is True


@pytest.mark.asyncio
async def test_missing_evidence_retry_fills_blank_stimulus_units_deterministically(monkeypatch):
    async def fake_llm_call(**kwargs):
        raise RuntimeError("repair model timeout")

    monkeypatch.setattr(question_analyzer, "llm_call", fake_llm_call)

    payload = {
        "total_score": 14,
        "_fine_grained": {
            "scoring_units": [
                {
                    "seu_id": "seu_1",
                    "label": "综合证据",
                    "score_share": 1.0,
                    "allocation_source": "inferred",
                    "allocation_confidence": 0.7,
                    "knowledge_links": [{"knowledge_point": "基因工程", "share": 1.0}],
                    "bloom_level": 4,
                    "competency_weights": {
                        "生命观念": 0.2,
                        "科学思维": 0.5,
                        "科学探究": 0.3,
                        "社会责任": 0.0,
                    },
                    "difficulty_estimate": 8.0,
                    "reasoning_brief": "结合材料推断",
                }
            ],
            "diagnostic_units": [
                {
                    "du_id": "du_1",
                    "option_or_trap": "trap",
                    "distractor_type": "reading_trap",
                    "misconception": "忽略材料证据",
                    "trap_strength": 2,
                    "knowledge_boundary": "材料解读",
                    "if_selected_means": ["证据链断裂"],
                }
            ],
            "stimulus_units": [
                {
                    "su_id": "su_1",
                    "stimulus_type": "text",
                    "complexity": 3,
                    "is_core": True,
                    "description": "",
                }
            ],
        },
        "_llm_calls": [],
    }

    repaired = await QuestionAnalyzer()._retry_missing_evidence_units(
        analysis_payload=payload,
        question_id=21,
        question_type="short_answer",
        section_header="non-choice, 14 points",
        question_text="番茄红素合成与基因工程调控材料题，要求结合图表证据分析。",
        timeout=240.0,
        question_media_items=[],
        visual_context_text="",
    )

    stimulus_units = repaired["_fine_grained"]["stimulus_units"]
    assert stimulus_units[0]["description"]
    assert stimulus_units[0]["is_core"] is True
    assert repaired["stimulus_units"] == stimulus_units
    evidence_call = repaired["_llm_calls"][0]
    assert evidence_call["purpose"] == "missing_evidence_repair"
    assert "stimulus_units_deterministic_repair" in evidence_call["validation_errors"]
    assert evidence_call["metadata"]["stimulus_units_count"] == 1
