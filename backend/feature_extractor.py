"""LLM 特征提取 v3 — 难度预测模型（工作记忆 + 推理耦合 + 陷阱密度）。

设计文档: docs/plans/2026-03-28-difficulty-v3-design.md
v3 核心变化：bloom 降为报告标签，新增 working_memory/chain_coupling/trap_density。
"""
import json
import re
from hashlib import sha256
from llm_client import llm_call, send_message_gpt, get_last_llm_call_metadata as get_last_call_metadata
from llm_media import media_input_refs, messages_with_media
from metadata_contracts import LLMCallRecord
from prompt_loader import PromptLoader
from logger import get_logger
from vision_context import extract_visual_context

logger = get_logger()


def _llm_call_trace(metadata: dict | None = None) -> tuple[str, str, int, dict]:
    metadata = dict(metadata or {})
    try:
        trace = get_last_call_metadata() or {}
    except Exception:
        trace = {}
    provider = trace.get("provider") or "llm_client"
    model = trace.get("model") or "configured_provider_chain"
    fallback_count = int(trace.get("fallback_count") or 0)
    for key in ("provider_errors", "status", "operation", "fact_count", "grounding_score", "model_policy"):
        if trace.get(key) is not None:
            metadata[key] = trace.get(key)
    return provider, model, fallback_count, metadata

# === 评分维度（参与难度计算）===
SCORING_RANGES = {
    "working_memory": (1, 5),
    "reasoning_steps": (1, 10),
    "chain_coupling": (1, 3),
    "trap_density": (1, 3),
    "novelty": (1, 3),
    "knowledge_breadth": (1, 3),
}

# === 报告维度（不参与评分）===
REPORT_RANGES = {
    "bloom": (1, 6),
    "info_density": (1, 3),
    "representation_complexity": (1, 3),
}

# 合并：解析时全部提取
FEATURE_RANGES = {**SCORING_RANGES, **REPORT_RANGES}

# 解析失败时的默认值
DEFAULT_FEATURES = {
    "working_memory": 3,
    "reasoning_steps": 4,
    "chain_coupling": 2,
    "trap_density": 2,
    "novelty": 2,
    "knowledge_breadth": 2,
    "bloom": 3,
    "info_density": 2,
    "representation_complexity": 1,
}

# reason 字段
_REASON_KEYS = [
    "bloom_reason", "steps_detail", "breadth_reason",
    "density_reason", "novelty_reason", "representation_reason",
    "working_memory_reason", "coupling_reason", "trap_reason",
]

# 质量审查 + 教师点评字段
_QUALITY_KEYS = [
    "quality_scientific", "quality_normative", "quality_language",
    "quality_context", "quality_sensitivity", "teacher_comment",
]

# Bloom 中文标签
_BLOOM_LABELS = {"识记", "理解", "应用", "分析", "评价", "创造"}


def _input_refs(question_text: str, options: str, correct_answer: str,
                question_type: str, subject: str, media_items: list | None = None) -> dict:
    refs = {
        "subject": subject,
        "question_type": question_type,
        "question_text_length": len(question_text or ""),
        "options_length": len(options or ""),
        "has_correct_answer": bool(correct_answer),
    }
    refs.update(media_input_refs(media_items))
    return refs


async def _send_prompt(prompt: str, *, max_tokens: int, temperature: float,
                       purpose: str, media_items: list | None = None) -> str:
    if media_input_refs(media_items):
        return await llm_call(
            messages_with_media(prompt, media_items),
            max_tokens=max_tokens,
            temperature=temperature,
            purpose=purpose,
        )
    return await send_message_gpt(
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        purpose=purpose,
    )


def _attach_llm_call(payload: dict, *, call_id: str, purpose: str, prompt_id: str,
                     prompt: str, input_refs: dict, parsed_schema: str,
                     confidence: float, validation_errors: list = None,
                     retry_count: int = 0, metadata: dict = None,
                     existing_calls: list | None = None) -> dict:
    provider, model, fallback_count, metadata = _llm_call_trace(metadata)
    call = LLMCallRecord(
        call_id=call_id,
        purpose=purpose,
        prompt_id=prompt_id,
        prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
        provider=provider,
        model=model,
        input_refs=input_refs,
        parsed_schema=parsed_schema,
        confidence=confidence,
        validation_errors=validation_errors or [],
        fallback_count=fallback_count,
        retry_count=retry_count,
        metadata=metadata,
    )
    payload["_llm_calls"] = list(existing_calls or []) + [call.model_dump()]
    return payload


def build_feature_prompt(question_text: str, options: str = "",
                         correct_answer: str = "", question_type: str = "") -> str:
    """构建特征提取 prompt（v3: 难度预测 + 质量审查 + 教学点评）。"""
    parts = [question_text]
    if options:
        parts.append(f"选项：{options}")
    if correct_answer:
        parts.append(f"正确答案：{correct_answer}")
    question_block = "\n".join(parts)

    qtype_hint = f"\n题型：{question_type}" if question_type else ""

    return f"""你是一名资深高中生物命题审查专家。请从难度预测、命题质量、教学价值三个层面严格分析这道题目。

题目：
{question_block}{qtype_hint}

请输出严格 JSON（不要多余解释）：
{{
  "working_memory": 1-5（解题关键步骤中需同时在脑中保持的信息元素数量。1=直接匹配（读题→回忆→作答），2=单一比较（两个概念对比），3=多条件筛选（3-4个条件同时考虑），4=多要素联立（4-5个信息交叉推理），5=复杂系统推理（5+要素同时操控，如多基因+环境+系谱联合分析）），
  "working_memory_reason": "列出关键步骤需同时处理的具体信息元素(≤40字)",
  "reasoning_steps": 正整数（从题目信息到答案的最少认知操作数，不含读题/看选项），
  "steps_detail": "简述推理链(≤50字)",
  "chain_coupling": 1-3（推理链各步骤的依赖关系。1=独立：各步可单独完成，错一步不影响其他，2=部分依赖：部分步骤依赖前步结论但有独立分支，3=全链依赖：前一步错后续全错（如连续遗传推理、多步代谢通路）。重要：单选题/多选题的选项之间天然独立——判断A对错不依赖B的结论，因此选择题chain_coupling通常=1，极少数概念辨析题最多=2），
  "coupling_reason": "说明为什么是该耦合度(≤30字)",
  "trap_density": 1-3（看似正确但实际错误的推理路径或选项数量。1=低（0-1个有效干扰，答案一眼可见），2=中（2-3个选项/路径有迷惑性，需仔细排除），3=高（4+个看似合理的错误路径，或存在经典易混淆概念陷阱）），
  "trap_reason": "指出主要陷阱是什么(≤30字)",
  "novelty": 1-3（1教材原文/常见原题 2变式/改编 3全新情境/陌生素材），
  "novelty_reason": "一句话(≤20字)",
  "knowledge_breadth": 1-3（1单知识点 2跨考点 3跨模块），
  "breadth_reason": "一句话(≤20字)",
  "bloom": 1-6（该题所需的最高认知层级。注意：此字段仅用于教学报告，不影响难度评分），
  "bloom_distribution": {{"识记": 0, "理解": 0, "应用": 0, "分析": 0, "评价": 0, "创造": 0}}（各层级出现次数。选择题按选项计，非选择题按小问计），
  "bloom_reason": "描述最高层级对应的具体认知操作(≤30字)",
  "info_density": 1-3（1低≤2条 2中3-5条 3高>5条或含图表），
  "density_reason": "一句话(≤20字)",
  "representation_complexity": 1-3（1纯文字 2简单图表 3复杂系谱图/多图联读/装置图），
  "representation_reason": "一句话(≤20字)",
  "quality_score": 1-5（1=严重缺陷 2=明显问题 3=基本合格 4=较好 5=优秀。5分极少——大多数试题都有改进空间），
  "quality_scientific": "先指出问题，再给评价。检查：知识准确性、答案唯一性、有无歧义或事实错误。无问题写'无明显问题'(≤60字)",
  "quality_normative": "先指出问题，再给评价。检查：题干完整性、选项平行性、分值合理性、干扰项有效性。(≤60字)",
  "quality_language": "先指出问题，再给评价。检查：有无冗余/口语化/歧义/术语错误/表述过绝对。(≤60字)",
  "quality_context": "先指出问题，再给评价。检查：素材真实性、与考查内容关联度、背景知识门槛。(≤60字)",
  "quality_sensitivity": "先指出问题，再给评价。检查：是否涉及政治敏感话题、民族宗教争议、不当伦理情境（如人体实验、基因编辑争议性表述）、可能引发家长或社会舆论的内容。无问题写'无舆情风险'(≤60字)",
  "teacher_comment": "教师视角深度点评(≤150字)：考查目的、各小问难点归因、学生典型错误路径（具体写出学生会怎么错）、针对性教学建议"
}}

**working_memory 判例：**
- 1：直接回忆单一概念（"线粒体的功能是什么"）
- 2：两个概念比较（"有丝分裂和减数分裂的区别"）
- 3：3-4个条件同时筛选（"根据实验条件、自变量、因变量判断正确选项"）
- 4：4-5个信息交叉（"根据基因型+显隐性+连锁关系+杂交后代比例推导"）
- 5：5+要素系统推理（"多基因+多代系谱+电泳数据+概率计算联合分析"）

**chain_coupling 判例：**
- 1（独立）：选择题四个选项各自判断对错，错一个不影响其他。绝大多数单选/多选题=1
- 2（部分依赖）：先判断遗传方式再推基因型，但表现型分析独立；极少数概念辨析选择题需综合对比选项
- 3（全链依赖）：仅适用于非选择题。基因工程"设计引物→构建载体→转化→筛选→检测"；遗传系谱"判断显隐性→确定基因位置→推基因型→算概率"

**trap_density 判例：**
- 1：选择题只有1个有效干扰项，或填空题答案路径唯一
- 2：选择题2-3个选项都有一定迷惑性，或推理中存在1-2个常见误区
- 3：选择题所有选项都"看起来对"（如概念辨析题的细微差别），或推理中存在多个经典混淆点（如基因频率vs基因型频率、转录方向vs翻译方向）

**Bloom 判定规则（仅用于报告标签）：**
1. 选择题按选项、非选择题按小问独立判 bloom 层级
2. bloom 填最高层级，bloom_distribution 填各层级计数
3. bloom=5: "评价/论证/判断是否合理" bloom=6: "设计实验/提出方案"
"""


def build_compact_feature_retry_prompt(question_text: str, options: str = "",
                                       correct_answer: str = "",
                                       question_type: str = "",
                                       visual_context_text: str = "") -> str:
    parts = [question_text[:1800]]
    if options:
        parts.append(f"选项：{options[:800]}")
    if correct_answer:
        parts.append(f"正确答案：{correct_answer[:300]}")
    if visual_context_text:
        parts.append(f"视觉信息：{visual_context_text[:1200]}")
    question_block = "\n".join(parts)
    return f"""你是高中生物命题审查专家。上一次特征提取 JSON 不可解析，现在只做紧凑重试。
只返回一个合法 JSON 对象，不要 markdown，不要解释，不要省略号。

题目：
{question_block}
题型：{question_type or "unknown"}

必须输出这些键：
working_memory, working_memory_reason, reasoning_steps, steps_detail,
chain_coupling, coupling_reason, trap_density, trap_reason, novelty,
novelty_reason, knowledge_breadth, breadth_reason, bloom, bloom_distribution,
bloom_reason, info_density, density_reason, representation_complexity,
representation_reason, quality_score, quality_scientific, quality_normative,
quality_language, quality_context, quality_sensitivity, teacher_comment。

数值范围：
working_memory 1-5；reasoning_steps 1-10；chain_coupling 1-3；
trap_density 1-3；novelty 1-3；knowledge_breadth 1-3；bloom 1-6；
info_density 1-3；representation_complexity 1-3；quality_score 1-5。
所有 reason/quality 字段不超过 40 个汉字，teacher_comment 不超过 120 个汉字。
"""


def _decode_json_candidate(candidate: str):
    variants = [
        candidate,
        re.sub(r",\s*([}\]])", r"\1", candidate),
    ]
    decoder = json.JSONDecoder(strict=False)
    for variant in variants:
        text = str(variant or "").strip()
        if not text:
            continue
        try:
            return json.loads(text, strict=False)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            value, _ = decoder.raw_decode(text)
            return value
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def _json_object_candidates(text: str) -> list[str]:
    text = str(text or "").strip()
    candidates = [text]
    candidates.extend(match.group(1).strip() for match in re.finditer(
        r'```(?:json)?\s*\n?([\s\S]*?)\n?```',
        text,
        re.DOTALL,
    ))
    starts = [idx for idx, char in enumerate(text) if char == "{"]
    for start in starts:
        stack = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            char = text[idx]
            if escaped:
                escaped = False
                continue
            if char == "\\" and in_string:
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                stack += 1
            elif char == "}":
                stack -= 1
                if stack == 0:
                    candidates.append(text[start:idx + 1])
                    break
    seen = set()
    unique = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _json_string_value(raw_value: str) -> str:
    try:
        return json.loads(f'"{raw_value}"', strict=False)
    except Exception:
        return raw_value.replace('\\"', '"').replace("\\n", "\n").strip()


def _salvage_feature_fields(raw: str) -> dict | None:
    text = str(raw or "")
    data = {}
    for key in FEATURE_RANGES:
        match = re.search(
            rf'"{re.escape(key)}"\s*:\s*("(?P<quoted>(?:\\.|[^"\\])*)"|(?P<number>-?\d+(?:\.\d+)?))',
            text,
            re.DOTALL,
        )
        if not match:
            continue
        if match.group("number") is not None:
            try:
                data[key] = int(float(match.group("number")))
            except ValueError:
                continue
        else:
            data[key] = _json_string_value(match.group("quoted"))

    for key in _REASON_KEYS + _QUALITY_KEYS:
        match = re.search(
            rf'"{re.escape(key)}"\s*:\s*"((?:\\.|[^"\\])*)"',
            text,
            re.DOTALL,
        )
        if match:
            data[key] = _json_string_value(match.group(1))

    match = re.search(r'"quality_score"\s*:\s*(-?\d+(?:\.\d+)?)', text)
    if match:
        try:
            data["quality_score"] = int(float(match.group(1)))
        except ValueError:
            pass

    bloom_pos = text.find('"bloom_distribution"')
    if bloom_pos != -1:
        object_start = text.find("{", bloom_pos)
        if object_start != -1:
            bloom_value = _decode_json_candidate(text[object_start:])
            if isinstance(bloom_value, dict):
                data["bloom_distribution"] = bloom_value

    core_count = len([key for key in FEATURE_RANGES if key in data])
    return data if core_count >= 4 else None


def parse_features(raw: str, include_status: bool = False) -> dict:
    """从 LLM 原始输出解析特征，带容错和范围裁剪。"""
    data = None
    parse_recovery = None

    if not isinstance(raw, str):
        logger.warning(f"特征解析输入非字符串: {type(raw)}")
        defaults = dict(DEFAULT_FEATURES)
        if include_status:
            defaults["_feature_failed"] = True
            defaults["_feature_status"] = "failed"
        return defaults

    for index, candidate in enumerate(_json_object_candidates(raw)):
        decoded = _decode_json_candidate(candidate)
        if isinstance(decoded, dict):
            data = decoded
            parse_recovery = None if index == 0 else "json_candidate"
            break

    # 截断检测
    if data is None and raw.count('{') > raw.count('}'):
        logger.warning(f"[特征提取] 疑似截断：{{ 数={raw.count('{')}, }} 数={raw.count('}')}, 原始长度={len(raw)}")
        last_brace = raw.rfind('}')
        if last_brace > 0:
            try:
                candidate = raw[:last_brace + 1]
                candidate = re.sub(r',\s*"[^"]*":\s*"?[^"{}]*$', '', candidate)
                if not candidate.endswith('}'):
                    candidate += '}'
                data = json.loads(candidate, strict=False)
                parse_recovery = "truncated_json_repair"
                logger.info(f"[特征提取] 截断修复成功，恢复了 {len(data)} 个字段")
            except (json.JSONDecodeError, Exception):
                pass

    if data is None:
        data = _salvage_feature_fields(raw)
        if isinstance(data, dict):
            parse_recovery = "field_salvage"
            logger.warning(
                f"[特征提取] 使用字段级恢复解析 JSON，核心字段={len([k for k in FEATURE_RANGES if k in data])}"
            )

    # 全部失败
    if not isinstance(data, dict):
        logger.warning(f"特征解析失败，使用默认值。原始输出: {raw[:200]}")
        defaults = dict(DEFAULT_FEATURES)
        if include_status:
            defaults["_feature_failed"] = True
            defaults["_feature_status"] = "failed"
        return defaults

    # 补全缺失字段 + 范围裁剪
    # 记录 LLM 实际返回的核心维度 key（在默认填充前）
    raw_core_keys = {k for k in FEATURE_RANGES if k in data}
    raw_core_count = len(raw_core_keys)

    result = {}
    for key, (lo, hi) in FEATURE_RANGES.items():
        val = data.get(key, DEFAULT_FEATURES[key])
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = DEFAULT_FEATURES[key]
        result[key] = max(lo, min(hi, val))

    result["_raw_core_count"] = raw_core_count
    if parse_recovery:
        result["_parse_recovery"] = parse_recovery

    # 保留 reason 字段
    for reason_key in _REASON_KEYS:
        if reason_key in data:
            result[reason_key] = str(data[reason_key])[:50]

    # bloom_distribution
    bloom_dist = data.get("bloom_distribution")
    if isinstance(bloom_dist, dict):
        cleaned = {}
        for label, count in bloom_dist.items():
            if label in _BLOOM_LABELS:
                try:
                    cleaned[label] = max(0, int(count))
                except (ValueError, TypeError):
                    pass
        if sum(cleaned.values()) > 0:
            result["bloom_distribution"] = cleaned

    # quality_score
    qs = data.get("quality_score")
    if qs is not None:
        try:
            result["quality_score"] = max(1, min(5, int(qs)))
        except (ValueError, TypeError):
            pass

    # 质量审查 + 教师点评
    missing_quality = []
    for qkey in _QUALITY_KEYS:
        if qkey in data:
            limit = 400 if qkey == "teacher_comment" else 120
            result[qkey] = str(data[qkey])[:limit]
        else:
            missing_quality.append(qkey)
    if missing_quality:
        logger.warning(f"[特征提取] 质量字段缺失: {missing_quality}")

    return result


async def _extract_features_uncached(question_text: str, options: str = "",
                           correct_answer: str = "",
                           question_type: str = "",
                           subject: str = "biology",
                           media_items: list | None = None) -> dict:
    """调用 LLM 提取题目特征（v3: 难度预测维度 + 报告维度 + 质量审查）。"""
    # 尝试从 PromptLoader 加载学科专用 prompt
    loader = PromptLoader(subject)
    if loader.exists("feature_extractor"):
        parts = [question_text]
        if options:
            parts.append(f"选项：{options}")
        if correct_answer:
            parts.append(f"正确答案：{correct_answer}")
        question_block = "\n".join(parts)
        qtype_hint = f"\n题型：{question_type}" if question_type else ""
        prompt = loader.load("feature_extractor",
                            question_block=question_block, qtype_hint=qtype_hint)
    else:
        prompt = build_feature_prompt(question_text, options, correct_answer, question_type)
    visual_call_record = None
    visual_context_text = ""
    prompt_for_llm = prompt
    try:
        if media_input_refs(media_items):
            visual_context_text, visual_call_record = await extract_visual_context(
                media_items,
                question_text=question_text,
                question_type=question_type,
                call_id=f"{subject}-feature-visual-context",
            )
            prompt_for_llm = "\n\n".join([prompt, visual_context_text])

        raw = await _send_prompt(
            prompt_for_llm,
            max_tokens=8192,
            temperature=0,
            purpose="feature_extraction",
            media_items=None,
        )
        selected_raw = raw
        selected_prompt = prompt_for_llm
        retry_count = 0
        result = parse_features(raw, include_status=True)

        # 核心字段不足时用短 prompt 再试一次；DeepSeek 仍是唯一文本主审。
        raw_core = result.get("_raw_core_count", 0)
        if raw_core < 6:
            logger.warning(f"[特征提取] raw_core={raw_core} 不足，触发紧凑重试（raw前100: {raw[:100]}）")
            try:
                retry_count = 1
                retry_prompt = build_compact_feature_retry_prompt(
                    question_text,
                    options,
                    correct_answer,
                    question_type,
                    visual_context_text if visual_call_record else "",
                )
                raw2 = await _send_prompt(
                    retry_prompt,
                    max_tokens=4096,
                    temperature=0,
                    purpose="feature_extraction",
                    media_items=None,
                )
                result2 = parse_features(raw2, include_status=True)
                if result2.get("_raw_core_count", 0) > raw_core:
                    result = result2
                    selected_raw = raw2
                    selected_prompt = retry_prompt
                    logger.info(f"[特征提取] 重试成功 raw_core={result2.get('_raw_core_count', 0)}")
                else:
                    logger.warning(f"[特征提取] 重试后 raw_core 仍不足: {result2.get('_raw_core_count', 0)}")
            except Exception as retry_err:
                logger.warning(f"[特征提取] 重试失败: {retry_err}")

        # Schema 校验 + 一致性检查
        from llm_schemas import validate_llm_output, FeatureResult, check_consistency
        validated, ext_conf, val_errors = validate_llm_output(result, FeatureResult, "特征提取")
        for k, v in validated.items():
            if k in result or k in FEATURE_RANGES:
                result[k] = v

        consistency_score, consistency_flags = check_consistency(result)
        result["_extraction_confidence"] = ext_conf
        result["_consistency_confidence"] = consistency_score
        if val_errors:
            result["_validation_errors"] = val_errors
        if consistency_flags:
            result["_consistency_flags"] = consistency_flags

        # 完整性评分
        completeness = len([k for k in FEATURE_RANGES if k in result])
        completeness += len([k for k in _REASON_KEYS if k in result])
        completeness += len([k for k in _QUALITY_KEYS if k in result])
        completeness += (1 if "bloom_distribution" in result else 0)
        completeness += (1 if "quality_score" in result else 0)

        raw_core_count = result.get("_raw_core_count", 0)

        if raw_core_count >= 6 and completeness >= 18:
            result["_feature_status"] = "ok"
            logger.info(f"[特征提取] 完整度={completeness}/29, raw_core={raw_core_count}, "
                        f"ext_conf={ext_conf}, consistency={consistency_score}")
        elif raw_core_count >= 4:
            result["_feature_status"] = "partial"
            logger.warning(f"[特征提取] 部分可用 raw_core={raw_core_count}/6, completeness={completeness}/29")
        else:
            result["_feature_status"] = "failed"
            result["_feature_failed"] = True
            logger.error(f"[特征提取] 不可用 raw_core={raw_core_count}/6, completeness={completeness}/29, 原始长度={len(raw)}")

        return _attach_llm_call(
            result,
            call_id=f"{subject}-feature-extraction",
            purpose="feature_extraction",
            prompt_id=f"{subject}.feature_extraction",
            prompt=selected_prompt,
            input_refs=_input_refs(question_text, options, correct_answer, question_type, subject, media_items),
            parsed_schema="FeatureResult",
            confidence=ext_conf,
            validation_errors=val_errors,
            retry_count=retry_count,
            existing_calls=[visual_call_record] if visual_call_record else None,
            metadata={
                "response_length": len(selected_raw),
                "feature_status": result.get("_feature_status"),
                "raw_core_count": raw_core_count,
                "parse_recovery": result.get("_parse_recovery"),
                **({"recovery_status": "ok"} if retry_count and result.get("_feature_status") == "ok" else {}),
                **({"visual_context_source": "qwen_vision"} if visual_call_record else {}),
            },
        )
    except Exception as e:
        logger.error(f"特征提取 API 调用失败: {e}")
        try:
            retry_prompt = build_compact_feature_retry_prompt(
                question_text,
                options,
                correct_answer,
                question_type,
                visual_context_text if visual_call_record else "",
            )
            raw_retry = await _send_prompt(
                retry_prompt,
                max_tokens=4096,
                temperature=0,
                purpose="feature_extraction",
                media_items=None,
            )
            result = parse_features(raw_retry, include_status=True)

            from llm_schemas import validate_llm_output, FeatureResult, check_consistency
            validated, ext_conf, val_errors = validate_llm_output(result, FeatureResult, "特征提取API失败重试")
            for k, v in validated.items():
                if k in result or k in FEATURE_RANGES:
                    result[k] = v

            consistency_score, consistency_flags = check_consistency(result)
            result["_extraction_confidence"] = ext_conf
            result["_consistency_confidence"] = consistency_score
            if val_errors:
                result["_validation_errors"] = val_errors
            if consistency_flags:
                result["_consistency_flags"] = consistency_flags

            completeness = len([k for k in FEATURE_RANGES if k in result])
            completeness += len([k for k in _REASON_KEYS if k in result])
            completeness += len([k for k in _QUALITY_KEYS if k in result])
            completeness += (1 if "bloom_distribution" in result else 0)
            completeness += (1 if "quality_score" in result else 0)
            raw_core_count = result.get("_raw_core_count", 0)
            if raw_core_count >= 6 and completeness >= 18:
                result["_feature_status"] = "ok"
                logger.info(f"[特征提取] API失败后紧凑重试成功 raw_core={raw_core_count}")
            elif raw_core_count >= 4:
                result["_feature_status"] = "partial"
                logger.warning(f"[特征提取] API失败后紧凑重试部分可用 raw_core={raw_core_count}/6")
            else:
                raise RuntimeError(f"compact retry incomplete raw_core={raw_core_count}")

            return _attach_llm_call(
                result,
                call_id=f"{subject}-feature-extraction",
                purpose="feature_extraction",
                prompt_id=f"{subject}.feature_extraction",
                prompt=retry_prompt,
                input_refs=_input_refs(question_text, options, correct_answer, question_type, subject, media_items),
                parsed_schema="FeatureResult",
                confidence=ext_conf,
                validation_errors=val_errors,
                retry_count=1,
                existing_calls=[visual_call_record] if visual_call_record else None,
                metadata={
                    "response_length": len(raw_retry),
                    "feature_status": result.get("_feature_status"),
                    "raw_core_count": raw_core_count,
                    "parse_recovery": result.get("_parse_recovery"),
                    "recovery_mode": "api_failure_compact_retry",
                    "recovery_status": "ok" if result.get("_feature_status") == "ok" else "partial",
                    "original_error": str(e)[:200],
                    **({"visual_context_source": "qwen_vision"} if visual_call_record else {}),
                },
            )
        except Exception as retry_err:
            retry_error_text = str(retry_err)
            logger.warning(f"[特征提取] API失败后的紧凑重试失败: {retry_error_text}")
        result = dict(DEFAULT_FEATURES)
        result["_feature_failed"] = True
        result["_feature_status"] = "failed"
        result["_extraction_confidence"] = 0.0
        result["_consistency_confidence"] = 0.0
        result["_validation_errors"] = [
            f"API失败: {str(e)}",
            f"compact_retry_failed: {retry_error_text}",
        ]
        return _attach_llm_call(
            result,
            call_id=f"{subject}-feature-extraction",
            purpose="feature_extraction",
            prompt_id=f"{subject}.feature_extraction",
            prompt=prompt,
            input_refs=_input_refs(question_text, options, correct_answer, question_type, subject, media_items),
            parsed_schema="FeatureResult",
            confidence=0.0,
            validation_errors=result["_validation_errors"],
            retry_count=1,
            existing_calls=[visual_call_record] if visual_call_record else None,
            metadata={
                "feature_status": "failed",
                "recovery_mode": "api_failure_compact_retry_failed",
                "recovery_status": "failed",
            },
        )


# ── 大题结构化特征提取 v3.1 ────────────────────────────────────

def build_big_question_prompt(question_text: str, options: str = "",
                              correct_answer: str = "",
                              question_type: str = "") -> str:
    """构建大题结构化特征提取 prompt（v3.2: score_share 替代 absolute points）。"""
    parts = [question_text]
    if options:
        parts.append(f"选项：{options}")
    if correct_answer:
        parts.append(f"正确答案/参考答案：{correct_answer}")
    question_block = "\n".join(parts)
    qtype_hint = f"\n题型：{question_type}" if question_type else ""

    return f"""你是一名资深高中生物命题审查专家。这是一道非选择题（大题），请按小问拆分分析。

题目：
{question_block}{qtype_hint}

请只输出严格 JSON（不要多余解释）。必须二选一：

成功时输出：
{{
  "status": "ok",
  "data": {{
  "subquestions": [
    {{
      "id": 1,
      "score_share": 该小问占总分的比例(0.0-1.0的浮点数，所有小问之和=1.0),
      "working_memory": 1-5（该小问解题时需同时在脑中保持的信息元素数），
      "reasoning_steps": 正整数（该小问最少认知操作数），
      "trap_density": 1-3（看似正确但实际错误的推理路径或答题方向数。选择题：有效干扰选项数。非选择题：需排除的错误假设/机制/解释的数量。例如蛋白不在上清需排除2+原因(包涵体/未分泌/降解)→trap>=2；PCR引物方向判断需从多个引物中选配→trap>=2），
      "novelty": 1-3（知识/方法新颖度），
      "knowledge_breadth": 1-3（跨知识模块程度），
      "brief": "核心任务(<=20字)"
    }}
  ],
  "dependencies": [
    {{
      "from": 源小问id,
      "to": 目标小问id,
      "strength": "weak"或"strong",
      "reason": "依赖内容(<=30字)"
    }}
  ],
  "global_features": {{
    "shared_context_load": 1-3（跨问保持负担。1=各问独立 2=共享背景 3=围绕复杂系统），
    "shared_context_reason": "<=20字",
    "global_method_novelty": 1-3（教材外方法。1=全教材内 2=部分外 3=核心方法外），
    "method_novelty_reason": "<=20字"
  }},
  "bloom": 1-6, "bloom_distribution": {{}}, "bloom_reason": "<=30字",
  "info_density": 1-3, "density_reason": "<=20字",
  "representation_complexity": 1-3, "representation_reason": "<=20字",
  "quality_score": 1-5,
  "quality_scientific": "<=60字", "quality_normative": "<=60字",
  "quality_language": "<=60字", "quality_context": "<=60字",
  "quality_sensitivity": "<=60字", "teacher_comment": "<=150字"
  }}
}}

失败时输出：
{{
  "status": "failed",
  "failure_type": "cannot_identify_subquestions|insufficient_stem|non_big_question|schema_uncertain",
  "reason": "说明无法可靠结构化的原因(<=80字)"
}}

**结构化硬约束：**
- subquestions 必须对应题面可见小问，不得为了凑数拆分或合并。
- 每个小问的 score_share 是该小问占总分的比例，所有小问的 score_share 之和必须等于 1.0。
- 如果无法确定各小问的分值比例，按小问数量均分（如 3 小问各 0.33）。
- 如果无法识别小问或题干证据不足，输出 status=failed，不要猜测。
- dependencies 的 from/to 只能引用 subquestions 中存在的 id。

**dependencies 判定规则（关键！）：**
- "strong"：前一问的结论/产物是后一问的前提。不知道前问答案就无法做后问。
- "weak"：前一问的背景知识有助于后问理解，但不知道前问答案也能部分作答
- 无关的小问之间不加 dependency

**global_method_novelty 判例：**
- 1：所有方法在高中教材中有明确介绍
- 2：部分方法需要迁移应用
- 3：核心方法在教材中完全没有（如 In-Fusion 克隆、CRISPR）

**难度构念补充：**
- reasoning_steps 只计最少认知操作数，不按填空数量累计。
- trap_density 只计真实可混淆路径，不按采分点数量累计。
- 三引物PCR鉴定插入方向、GFP/融合蛋白定位、复杂载体构建、CRISPR、In-Fusion 等属于高级分子工具；若它们是核心解法，global_method_novelty 应为 3。
- 引物方向/序列位置/融合蛋白/插入方向判断通常 representation_complexity 不低于 3；多个候选引物或方向判断 trap_density 通常不低于 2。
"""


_SQ_RANGES = {
    "working_memory": (1, 5),
    "reasoning_steps": (1, 10),
    "trap_density": (1, 3),
    "novelty": (1, 3),
    "knowledge_breadth": (1, 3),
}

_ADVANCED_BIO_METHOD_TERMS = (
    "三引物pcr",
    "插入方向",
    "gfp",
    "融合蛋白",
    "融合基因",
    "亚细胞定位",
    "定位失败",
    "引物设计",
    "酶切位点",
    "crispr",
    "in-fusion",
    "载体构建",
    "基因编辑",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in terms)


def _apply_biology_method_floors(result: dict, question_text: str,
                                 subject: str) -> dict:
    """Protect advanced biotech constructs from being scored as routine blanks."""
    if subject != "biology" or not isinstance(result, dict):
        return result
    lowered = (question_text or "").lower()
    matches = [term for term in _ADVANCED_BIO_METHOD_TERMS if term in lowered]
    if len(matches) < 2:
        return result

    global_features = result.setdefault("global_features", {})
    if int(global_features.get("global_method_novelty", 1) or 1) < 3:
        global_features["global_method_novelty"] = 3
        global_features["method_novelty_reason"] = "复杂分子工具"

    report = result.setdefault("report", {})
    if _contains_any(lowered, ("三引物pcr", "引物设计", "插入方向", "酶切位点")):
        report["representation_complexity"] = max(
            int(report.get("representation_complexity", 1) or 1),
            3,
        )

    for sq in result.get("subquestions", []):
        brief = str(sq.get("brief", "")).lower()
        if _contains_any(brief, ("三引物", "pcr", "插入方向")):
            sq["novelty"] = max(int(sq.get("novelty", 1) or 1), 3)
            sq["trap_density"] = max(int(sq.get("trap_density", 1) or 1), 2)
            sq["reasoning_steps"] = max(int(sq.get("reasoning_steps", 1) or 1), 4)
        elif _contains_any(brief, ("融合", "载体", "定位失败", "引物设计")):
            sq["novelty"] = max(int(sq.get("novelty", 1) or 1), 2)
            sq["reasoning_steps"] = max(int(sq.get("reasoning_steps", 1) or 1), 3)
    return result


def _derive_points_from_score_shares(shares: list[float],
                                     total_score: float | None) -> tuple[list[int] | None, list[float] | None, str | None]:
    try:
        expected_total = int(round(float(total_score or 0)))
    except (ValueError, TypeError):
        expected_total = 0
    if expected_total <= 0:
        return None, None, "score_share_requires_total_score"
    if len(shares) > expected_total:
        return None, None, "score_share_points_impossible"

    share_sum = sum(shares)
    if share_sum <= 0:
        return None, None, "score_share_sum_mismatch"
    if abs(share_sum - 1.0) > 0.1:
        return None, None, "score_share_sum_mismatch"

    normalized = [share / share_sum for share in shares]
    extra_total = expected_total - len(shares)
    raw_extra = [share * extra_total for share in normalized]
    extra = [int(value) for value in raw_extra]
    remainder = extra_total - sum(extra)
    order = sorted(
        range(len(shares)),
        key=lambda idx: raw_extra[idx] - extra[idx],
        reverse=True,
    )
    for idx in order[:remainder]:
        extra[idx] += 1
    return [1 + value for value in extra], normalized, None


def _dependency_graph_has_cycle(valid_ids: set, dependencies: list[dict]) -> bool:
    adj = {item_id: [] for item_id in valid_ids}
    in_degree = {item_id: 0 for item_id in valid_ids}
    for dep in dependencies:
        fr = dep.get("from")
        to = dep.get("to")
        if fr in adj and to in adj:
            adj[fr].append(to)
            in_degree[to] += 1

    queue = [item_id for item_id in valid_ids if in_degree[item_id] == 0]
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for nxt in adj[node]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)
    return visited < len(valid_ids)


def parse_big_question_features(raw: str, total_score: float | None = None,
                                detailed: bool = False) -> dict | None:
    """解析大题结构化 JSON。

    默认返回兼容旧接口的 payload/None；detailed=True 时返回带 failure_type
    的结构化结果，供上游显式失败而不是生成看似正常的回退数据。
    """

    raw_length = len(raw) if isinstance(raw, str) else 0

    def fail(failure_type: str, errors: list[str]) -> dict | None:
        if detailed:
            return {
                "ok": False,
                "data": None,
                "failure_type": failure_type,
                "errors": errors,
                "raw_length": raw_length,
            }
        return None

    def success(payload: dict) -> dict:
        if detailed:
            return {
                "ok": True,
                "data": payload,
                "failure_type": None,
                "errors": [],
                "raw_length": raw_length,
            }
        return payload

    if not isinstance(raw, str):
        return fail("non_string_response", ["LLM response is not a string"])

    data = None
    # 策略 1: 直接解析
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, TypeError):
        pass
    # 策略 2: code block
    if data is None:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    # 策略 3: 嵌套提取
    if data is None:
        depth = 0
        start = raw.find('{')
        if start >= 0:
            for i in range(start, len(raw)):
                if raw[i] == '{':
                    depth += 1
                elif raw[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            data = json.loads(raw[start:i + 1])
                        except json.JSONDecodeError:
                            pass
                        break
    # 策略 4: 截断修复（与 parse_features 一致）。detailed 路径供难度
    # pipeline 消费，不能把截断片段修成看似完整的结构化结果。
    if data is None and raw.count('{') > raw.count('}'):
        if detailed:
            logger.warning(
                f"[大题解析] JSON 疑似截断，原始长度={len(raw)}")
            return fail("json_truncated", ["JSON appears truncated"])
        logger.warning(f"[大题解析] 疑似截断：{{ 数={raw.count('{')}, }} 数={raw.count('}')}, 原始长度={len(raw)}")
        last_brace = raw.rfind('}')
        if last_brace > 0:
            try:
                candidate = raw[:last_brace + 1]
                candidate = re.sub(r',\s*"[^"]*":\s*"?[^"{}]*$', '', candidate)
                if not candidate.endswith('}'):
                    candidate += '}'
                data = json.loads(candidate)
                logger.info(f"[大题解析] 截断修复成功，恢复了 {len(data)} 个字段")
            except json.JSONDecodeError:
                pass

    if not isinstance(data, dict):
        logger.warning(f"[大题解析] JSON 解析失败，原始长度={len(raw)}")
        return fail("json_parse_failed", ["JSON parse failed"])

    if data.get("status") == "failed":
        failure_type = str(data.get("failure_type") or "model_reported_failure")
        reason = str(data.get("reason") or data.get("message") or failure_type)
        logger.warning(f"[大题解析] 模型报告失败: {failure_type}: {reason}")
        return fail(failure_type, [reason])

    if data.get("status") == "ok":
        wrapped = data.get("data")
        if not isinstance(wrapped, dict):
            return fail("invalid_wrapper_schema", ["status=ok requires object field data"])
        data = wrapped

    # subquestions
    sqs_raw = data.get("subquestions", [])
    if not isinstance(sqs_raw, list) or len(sqs_raw) == 0:
        logger.warning("[大题解析] subquestions 缺失或为空")
        return fail("missing_subquestions", ["subquestions is missing or empty"])

    subquestions = []
    invalid_schema_errors = []
    score_share_mode = any(
        isinstance(sq, dict) and "score_share" in sq
        for sq in sqs_raw
    )
    score_shares = []
    for sq in sqs_raw:
        if not isinstance(sq, dict):
            invalid_schema_errors.append("subquestion item is not an object")
            continue
        item_errors = []
        if "id" not in sq and detailed:
            item_errors.append("missing id")
        raw_id = sq.get("id", len(subquestions) + 1)
        try:
            sq_id = int(raw_id)
        except (ValueError, TypeError):
            item_errors.append(f"invalid id: {raw_id}")
            if detailed:
                invalid_schema_errors.extend(item_errors)
                continue
            sq_id = len(subquestions) + 1
        score_share = None
        points = None
        if score_share_mode:
            if "score_share" not in sq and detailed:
                item_errors.append(f"missing score_share for subquestion {raw_id}")
            raw_share = sq.get("score_share", 0)
            try:
                score_share = float(raw_share)
                if score_share < 0:
                    raise ValueError("negative score_share")
            except (ValueError, TypeError):
                item_errors.append(f"invalid score_share for subquestion {raw_id}: {raw_share}")
                if detailed:
                    invalid_schema_errors.extend(item_errors)
                    continue
                score_share = 0.0
        else:
            if "points" not in sq and detailed:
                item_errors.append(f"missing points for subquestion {raw_id}")
            raw_points = sq.get("points", 2)
            try:
                points = max(1, int(float(raw_points)))
            except (ValueError, TypeError):
                item_errors.append(f"invalid points for subquestion {raw_id}: {raw_points}")
                if detailed:
                    invalid_schema_errors.extend(item_errors)
                    continue
                points = 2
        cleaned_values = {}
        for key, (lo, hi) in _SQ_RANGES.items():
            if key not in sq and detailed:
                item_errors.append(f"missing {key} for subquestion {raw_id}")
            val = sq.get(key, 2)
            try:
                val = int(val)
            except (ValueError, TypeError):
                item_errors.append(f"invalid {key} for subquestion {raw_id}: {val}")
                if detailed:
                    continue
                val = 2
            cleaned_values[key] = max(lo, min(hi, val))
        if detailed and item_errors:
            invalid_schema_errors.extend(item_errors)
            continue
        cleaned = {
            "id": sq_id,
            "brief": str(sq.get("brief", ""))[:20],
        }
        if score_share_mode:
            cleaned["score_share"] = score_share
            score_shares.append(score_share)
        else:
            cleaned["points"] = points
        cleaned.update(cleaned_values)
        subquestions.append(cleaned)
    if not subquestions:
        return fail("invalid_subquestion_schema",
                    invalid_schema_errors or ["no valid subquestions"])
    if detailed and invalid_schema_errors:
        return fail("invalid_subquestion_schema", invalid_schema_errors)

    allocation_source = "inferred" if score_share_mode else "explicit"
    if score_share_mode:
        derived_points, normalized_shares, share_failure = _derive_points_from_score_shares(
            score_shares,
            total_score,
        )
        if share_failure:
            return fail(
                share_failure,
                [f"score_share_sum={sum(score_shares):.3f}, total_score={total_score}"],
            )
        for sq, points, share in zip(subquestions, derived_points, normalized_shares):
            sq["points"] = points
            sq["score_share"] = round(share, 6)

    ids = [sq["id"] for sq in subquestions]
    if len(set(ids)) != len(ids):
        return fail("duplicate_subquestion_ids", ["subquestion ids must be unique"])

    if total_score is not None and not score_share_mode:
        try:
            expected_total = float(total_score)
        except (ValueError, TypeError):
            expected_total = 0
        if expected_total > 0:
            points_sum = sum(float(sq["points"]) for sq in subquestions)
            if abs(points_sum - expected_total) / expected_total > 0.2:
                return fail(
                    "points_sum_mismatch",
                    [f"points_sum={points_sum:g}, total_score={expected_total:g}"],
                )

    # dependencies
    deps_raw = data.get("dependencies", [])
    dependencies = []
    dropped_deps = 0
    valid_ids = {sq["id"] for sq in subquestions}
    if isinstance(deps_raw, list):
        for dep in deps_raw:
            if not isinstance(dep, dict):
                continue
            fr, to = dep.get("from"), dep.get("to")
            strength = dep.get("strength", "weak")
            if fr in valid_ids and to in valid_ids and strength in ("weak", "strong"):
                dependencies.append({
                    "from": fr, "to": to, "strength": strength,
                    "reason": str(dep.get("reason", ""))[:30],
                })
            else:
                dropped_deps += 1
    if dropped_deps > 0:
        logger.warning(f"[大题解析] 丢弃 {dropped_deps} 条无效依赖（ID 不存在或 strength 非法）")
        if dropped_deps >= len(deps_raw) and len(deps_raw) > 0:
            logger.warning("[大题解析] 所有依赖均无效，视为依赖图矛盾，返回结构化失败")
            return fail("invalid_dependency_ids", ["all dependency ids are invalid"])
    if dependencies and _dependency_graph_has_cycle(valid_ids, dependencies):
        logger.warning("[大题解析] 依赖图存在环，返回结构化失败")
        return fail("dependency_cycle", ["dependency graph contains a cycle"])

    # global_features
    gf_raw = data.get("global_features", {})
    if isinstance(gf_raw, dict):
        try:
            scl = max(1, min(3, int(gf_raw.get("shared_context_load", 1))))
        except (ValueError, TypeError):
            scl = 1
        try:
            gmn = max(1, min(3, int(gf_raw.get("global_method_novelty", 1))))
        except (ValueError, TypeError):
            gmn = 1
    else:
        scl, gmn = 1, 1
    global_features = {"shared_context_load": scl, "global_method_novelty": gmn}

    # report fields
    report = {}
    for key in ["bloom", "info_density", "representation_complexity"]:
        val = data.get(key)
        if val is not None:
            lo, hi = REPORT_RANGES.get(key, (1, 6))
            try:
                report[key] = max(lo, min(hi, int(val)))
            except (ValueError, TypeError):
                pass
    for reason_key in _REASON_KEYS:
        if reason_key in data:
            report[reason_key] = str(data[reason_key])[:50]
    bloom_dist = data.get("bloom_distribution")
    if isinstance(bloom_dist, dict):
        cleaned_bd = {}
        for label, count in bloom_dist.items():
            if label in _BLOOM_LABELS:
                try:
                    cleaned_bd[label] = max(0, int(count))
                except (ValueError, TypeError):
                    pass
        if sum(cleaned_bd.values()) > 0:
            report["bloom_distribution"] = cleaned_bd
    qs = data.get("quality_score")
    if qs is not None:
        try:
            report["quality_score"] = max(1, min(5, int(qs)))
        except (ValueError, TypeError):
            pass
    for qkey in _QUALITY_KEYS:
        if qkey in data:
            limit = 400 if qkey == "teacher_comment" else 120
            report[qkey] = str(data[qkey])[:limit]

    result = {
        "subquestions": subquestions,
        "dependencies": dependencies,
        "global_features": global_features,
        "report": report,
        "allocation_source": allocation_source,
    }
    if dropped_deps > 0:
        result["_dropped_deps"] = dropped_deps
    return success(result)


def _big_question_failure_payload(*, failure_type: str, errors: list[str],
                                  prompt: str, question_text: str, options: str,
                                  correct_answer: str, question_type: str,
                                  subject: str, status: str,
                                  response_length: int = 0,
                                  media_items: list | None = None) -> dict:
    payload = {
        "_big_question_failed": True,
        "failure_type": failure_type,
        "errors": errors,
    }
    return _attach_llm_call(
        payload,
        call_id=f"{subject}-big-question-feature-extraction",
        purpose="big_question_feature_extraction",
        prompt_id=f"{subject}.big_question_feature_extraction",
        prompt=prompt,
        input_refs=_input_refs(question_text, options, correct_answer, question_type, subject, media_items),
        parsed_schema="BigQuestionFeatureResult",
        confidence=0.0,
        validation_errors=errors,
        metadata={
            "status": status,
            "failure_type": failure_type,
            "response_length": response_length,
        },
    )


async def _extract_big_question_features_uncached(question_text: str, options: str = "",
                                        correct_answer: str = "",
                                        question_type: str = "",
                                        subject: str = "biology",
                                        total_score: float | None = None,
                                        return_failure: bool = False,
                                        media_items: list | None = None) -> dict | None:
    """调用 LLM 提取大题结构化特征。

    return_failure=True 时返回结构化失败 payload，避免上游把解析失败
    当成普通缺省值继续评分。
    """
    loader = PromptLoader(subject)
    if loader.exists("big_question_extractor"):
        parts = [question_text]
        if options:
            parts.append(f"选项：{options}")
        if correct_answer:
            parts.append(f"正确答案/参考答案：{correct_answer}")
        question_block = "\n".join(parts)
        qtype_hint = f"\n题型：{question_type}" if question_type else ""
        prompt = loader.load("big_question_extractor",
                            question_block=question_block, qtype_hint=qtype_hint)
    else:
        prompt = build_big_question_prompt(question_text, options, correct_answer, question_type)
    try:
        visual_call_record = None
        prompt_for_llm = prompt
        if media_input_refs(media_items):
            visual_context_text, visual_call_record = await extract_visual_context(
                media_items,
                question_text=question_text,
                question_type=question_type,
                call_id=f"{subject}-big-question-visual-context",
            )
            prompt_for_llm = "\n\n".join([prompt, visual_context_text])

        raw = await _send_prompt(
            prompt_for_llm,
            max_tokens=16000,
            temperature=0,
            purpose="big_question_feature_extraction",
            media_items=None,
        )
        parsed = parse_big_question_features(raw, total_score=total_score, detailed=True)
        retry_count = 0
        if not parsed["ok"]:
            failure_type = parsed["failure_type"] or "big_question_structure_failed"
            if failure_type in {"points_sum_mismatch", "score_share_sum_mismatch"}:
                logger.warning(f"[大题提取] {failure_type}，按同一结构化合同重试一次")
                retry_count = 1
                raw_retry = await _send_prompt(
                    prompt_for_llm,
                    max_tokens=16000,
                    temperature=0,
                    purpose="big_question_feature_extraction",
                    media_items=None,
                )
                parsed_retry = parse_big_question_features(
                    raw_retry,
                    total_score=total_score,
                    detailed=True,
                )
                if parsed_retry["ok"]:
                    raw = raw_retry
                    parsed = parsed_retry
                else:
                    raw = raw_retry
                    parsed = parsed_retry
                    failure_type = parsed["failure_type"] or failure_type
            errors = parsed.get("errors") or [failure_type]
            if not parsed["ok"]:
                status = "parse_failed" if failure_type == "json_parse_failed" else "validation_failed"
                if failure_type in {
                    "cannot_identify_subquestions", "points_unknown",
                    "insufficient_stem", "non_big_question", "schema_uncertain",
                    "model_reported_failure",
                }:
                    status = "model_failed"
                logger.warning(
                    f"[大题提取] 结构化解析失败: {failure_type}, 原始长度={len(raw)}")
                if return_failure:
                    return _big_question_failure_payload(
                        failure_type=failure_type,
                        errors=errors,
                        prompt=prompt,
                        question_text=question_text,
                        options=options,
                        correct_answer=correct_answer,
                        question_type=question_type,
                        subject=subject,
                        status=status,
                        response_length=len(raw),
                        media_items=media_items,
                    )
                return None

        result = parsed["data"]
        result = _apply_biology_method_floors(result, question_text, subject)
        result = _attach_llm_call(
            result,
            call_id=f"{subject}-big-question-feature-extraction",
            purpose="big_question_feature_extraction",
            prompt_id=f"{subject}.big_question_feature_extraction",
            prompt=prompt_for_llm,
            input_refs=_input_refs(question_text, options, correct_answer, question_type, subject, media_items),
            parsed_schema="BigQuestionFeatureResult",
            confidence=1.0,
            retry_count=retry_count,
            existing_calls=[visual_call_record] if visual_call_record else None,
            metadata={
                "status": "ok",
                "response_length": len(raw),
                "subquestion_count": len(result.get("subquestions", [])),
                "dependency_count": len(result.get("dependencies", [])),
                **({"visual_context_source": "qwen_vision"} if visual_call_record else {}),
            },
        )
        logger.info(f"[大题提取] 成功: {len(result['subquestions'])}小问, "
                    f"{len(result['dependencies'])}依赖")
        return result
    except Exception as e:
        logger.error(f"[大题提取] API 调用失败: {e}")
        if return_failure:
            return _big_question_failure_payload(
                failure_type="provider_failed",
                errors=[str(e)],
                prompt=prompt,
                question_text=question_text,
                options=options,
                correct_answer=correct_answer,
                question_type=question_type,
                subject=subject,
                status="provider_failed",
                media_items=media_items,
            )
        return None



async def extract_features(question_text: str, options: str = "",
                           correct_answer: str = "",
                           question_type: str = "",
                           subject: str = "biology",
                           media_items: list | None = None) -> dict:
    """RC1: 同卷特征缓存包装。同题（内容指纹相同）复用首次特征，消除 DeepSeek 跨跑漂移、
    保证同卷重跑难度可复现；缓存命中零 LLM 调用、零额外 token。
    实际提取逻辑见 _extract_features_uncached。"""
    import feature_cache
    cached = feature_cache.get(question_text, options, correct_answer, question_type, subject)
    if cached is not None:
        logger.info(f"[特征缓存] 命中，复用特征（零 LLM 调用）: {question_text[:30]}...")
        return cached
    result = await _extract_features_uncached(
        question_text, options, correct_answer, question_type, subject, media_items)
    if isinstance(result, dict) and result.get("_feature_status") in ("ok", "partial"):
        feature_cache.set(question_text, options, correct_answer, question_type, subject, result)
    return result


async def extract_big_question_features(question_text: str, options: str = "",
                                        correct_answer: str = "",
                                        question_type: str = "",
                                        subject: str = "biology",
                                        total_score: float | None = None,
                                        return_failure: bool = False,
                                        media_items: list | None = None) -> dict | None:
    """RC1: 同卷大题特征缓存包装（补齐 Task2，原仅覆盖小题）。
    实测 seed 对 deepseek-v4-pro 大题无效（同输入两次结构不同），故大题复现必须靠缓存：
    同题（内容指纹相同）复用首次结构化特征 → 同卷重跑大题难度可复现、零额外 LLM/token。
    用 bigq:: 命名空间与小题缓存隔离；仅缓存成功结果。实际提取见 _extract_big_question_features_uncached。"""
    import feature_cache
    cache_subject = "bigq::" + subject
    cached = feature_cache.get(question_text, options, correct_answer, question_type, cache_subject)
    if cached is not None:
        logger.info(f"[大题特征缓存] 命中，复用结构化特征（零 LLM 调用）: {question_text[:30]}...")
        return cached
    result = await _extract_big_question_features_uncached(
        question_text, options, correct_answer, question_type, subject,
        total_score, return_failure, media_items)
    if (isinstance(result, dict) and not result.get("_big_question_failed")
            and result.get("subquestions")):
        feature_cache.set(question_text, options, correct_answer, question_type, cache_subject, result)
    return result
