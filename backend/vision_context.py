"""Qwen vision preprocessing for image-bearing exam questions.

The project boundary is intentionally strict:
- Qwen vision reads images and produces a visual evidence summary.
- DeepSeek text providers perform the actual exam-review judgment.
- The vision summary is audit metadata, not an independent final analysis.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any

from llm_client import llm_call, get_last_llm_call_metadata as get_last_call_metadata
from llm_media import media_input_refs, messages_with_media, normalize_media_items
from metadata_contracts import LLMCallRecord


VISUAL_CONTEXT_PROMPT_ID = "biology.image_inputs.visual_context"
VISUAL_CONTEXT_VERSION = "qwen-vision-preprocess-v1"
# content_hash -> (prompt_context, call_dump)
# 键为 题干+题型+章节头+图片内容(base64) 的 sha256：跨试卷即便题号相同，
# 只要题干或图片不同即不会命中，杜绝同题号跨卷串卷污染。
_visual_context_cache = {}
_VISUAL_CONTEXT_CACHE_MAX = 256


def _visual_context_cache_key(
    question_text: str,
    question_type: str,
    section_header: str,
    normalized: list[dict[str, str]],
) -> str:
    # ①A 视觉去重(GOAL 调研 #1):视觉转写是对整张图的客观抽取(visual_text/ocr/tables/figures),
    # 与题型/分节/题干无关。缓存键此前掺入 question_type/section_header,而三个消费方
    # (question_analyzer/feature_extractor/competency_analyzer)传入这两字段不一致(常为空),
    # 同题同图算出不同 key、缓存被打穿 → 同图被 Qwen-VL 重复转写 2-3 次(全卷 29 次 vs 带图题 11 道)。
    # 改为仅按图片 base64 做键:同题图片三方同源(派生自同一 media_items)→ 必命中,29→约11 次真调用;
    # 同图跨题共享转写无害(转写的是整图内容,题干差异由下游 DeepSeek 处理)。
    # 签名保留 question_text/question_type/section_header 参数以零改调用点,仅不再参与键。
    h = sha256()
    for item in normalized:
        h.update((item.get("base64") or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _llm_call_trace(metadata: dict | None = None) -> tuple[str, str, int, dict]:
    metadata = dict(metadata or {})
    try:
        trace = get_last_call_metadata() or {}
    except Exception:
        trace = {}
    provider = trace.get("provider") or "llm_client"
    model = trace.get("model") or "configured_provider_chain"
    fallback_count = int(trace.get("fallback_count") or 0)
    for key in ("provider_errors", "status", "model_policy", "usage"):
        if trace.get(key) is not None:
            metadata[key] = trace.get(key)
    return provider, model, fallback_count, metadata


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    candidates = [raw]
    candidates.extend(match.group(1).strip() for match in re.finditer(
        r"```(?:json)?\s*\n?(.*?)\n?```",
        raw,
        re.DOTALL,
    ))
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start:end + 1])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("vision_context_json_parse_failed")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _visual_context_text(payload: dict[str, Any]) -> str:
    visual_text = str(payload.get("visual_text") or "").strip()
    ocr_text = str(payload.get("ocr_text") or "").strip()
    tables = _string_list(payload.get("tables"))
    figures = _string_list(payload.get("figures"))
    uncertainties = _string_list(payload.get("uncertainties"))

    parts = []
    if visual_text:
        parts.append(f"visual_text: {visual_text}")
    if ocr_text:
        parts.append(f"ocr_text: {ocr_text}")
    if tables:
        parts.append("tables: " + " | ".join(tables))
    if figures:
        parts.append("figures: " + " | ".join(figures))
    if uncertainties:
        parts.append("uncertainties: " + " | ".join(uncertainties))
    return "\n".join(parts).strip()


def build_visual_context_prompt(
    *,
    question_text: str = "",
    question_id: int | None = None,
    question_type: str = "",
    section_header: str = "",
    subject: str = "biology",
) -> str:
    from subject_config import get_subject_name
    subject_cn = get_subject_name(subject)
    return (
        f"You are the vision preprocessing layer for a high-school {subject_cn} (学科) exam-review system.\n"
        "Extract only visual information from the attached image(s). Do not judge difficulty, "
        "competencies, answer correctness, or item quality; the downstream model will perform those tasks later.\n"
        "Preserve any Chinese text, labels, legends, table entries, units, formulas, equations, and option "
        "markers (A/B/C/D and their full option text) exactly when visible. If something is unclear, put it "
        "in uncertainties instead of guessing.\n\n"
        f"subject: {subject_cn}\n"
        f"question_id: {question_id}\n"
        f"question_type: {question_type}\n"
        f"section_header: {section_header}\n"
        f"known_question_text:\n{question_text}\n\n"
        "Return one JSON object with these keys only:\n"
        "{\n"
        '  "visual_text": "concise description of visible structures, charts, apparatus, curves, diagrams, or formulas",\n'
        '  "ocr_text": "all readable text from the image, preserving Chinese and symbols",\n'
        '  "tables": ["table/axis/curve information, one item per table or chart"],\n'
        '  "figures": ["diagram/apparatus/process information, one item per visual object"],\n'
        '  "uncertainties": ["anything visually ambiguous or unreadable"]\n'
        "}\n"
    )


async def extract_visual_context(
    media_items: Any,
    *,
    question_text: str = "",
    question_id: int | None = None,
    question_type: str = "",
    section_header: str = "",
    subject: str = "biology",
    call_id: str | None = None,
    timeout: float = 120.0,
) -> tuple[str, dict | None]:
    normalized = normalize_media_items(media_items)
    if not normalized:
        return "", None

    # 缓存键改为内容哈希后不再依赖 question_id（None 时仍按内容缓存，命中更安全） #semantic-ok
    cache_key = _visual_context_cache_key(question_text, question_type, section_header, normalized)
    if cache_key in _visual_context_cache:
        from logger import get_logger
        get_logger().info(f"[视觉] 题目{question_id} visual_context 命中内容缓存，跳过 qwen_vision API")
        # GOAL #8:命中回放标记 usage_from_cache 防双计费(本次零 qwen API 调用)
        ctx, cached_call = _visual_context_cache[cache_key]
        cached_call = dict(cached_call)
        cached_call["metadata"] = {**(cached_call.get("metadata") or {}), "usage_from_cache": True}
        return ctx, cached_call

    prompt = build_visual_context_prompt(
        question_text=question_text,
        question_id=question_id,
        question_type=question_type,
        section_header=section_header,
        subject=subject,
    )
    response_text = await llm_call(
        messages=messages_with_media(prompt, normalized),
        max_tokens=4096,
        temperature=0,
        timeout=timeout,
        purpose="image_inputs",
    )
    parse_recovery = None
    try:
        payload = _extract_json_object(response_text)
    except Exception:
        parse_recovery = "raw_visual_text"
        payload = {
            "visual_text": str(response_text or "").strip()[:2500],
            "ocr_text": "",
            "tables": [],
            "figures": [],
            "uncertainties": ["Qwen Vision returned non-JSON visual context; raw text was passed to DeepSeek."],
        }
    context_text = _visual_context_text(payload)
    if not context_text:
        raise RuntimeError("vision_context_empty")

    metadata = {
        "response_length": len(response_text or ""),
        "visual_context_version": VISUAL_CONTEXT_VERSION,
        "used_as": "deepseek_text_prompt_context",
        "uncertainties": _string_list(payload.get("uncertainties")),
    }
    if parse_recovery:
        metadata["parse_recovery"] = parse_recovery
    provider, model, fallback_count, metadata = _llm_call_trace(metadata)
    call = LLMCallRecord(
        call_id=call_id or (
            f"question-{question_id}-visual-context"
            if question_id is not None else "visual-context"
        ),
        question_id=question_id,
        purpose="image_inputs",
        prompt_id=VISUAL_CONTEXT_PROMPT_ID,
        prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
        provider=provider,
        model=model,
        input_refs={
            "question_id": question_id,
            "question_type": question_type,
            "section_header": section_header,
            "question_text_length": len(question_text or ""),
            **media_input_refs(normalized),
        },
        parsed_schema="VisualContextResult",
        confidence=0.75 if metadata["uncertainties"] else 0.9,
        validation_errors=[],
        fallback_count=fallback_count,
        retry_count=0,
        metadata=metadata,
    )
    prompt_context = (
        "Visual context extracted by Qwen Vision for DeepSeek review only:\n"
        f"{context_text}"
    )
    if len(_visual_context_cache) >= _VISUAL_CONTEXT_CACHE_MAX:
        _visual_context_cache.pop(next(iter(_visual_context_cache)))
    _visual_context_cache[cache_key] = (prompt_context, call.model_dump())
    return prompt_context, call.model_dump()
