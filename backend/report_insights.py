import asyncio
"""PDF 报告 LLM 分析层 — GPT 5.4 生成综合分析文本。

调用 1: 整卷综合分析（brief+full 共用）
调用 2: 逐题教师点评（仅 full）
GPT 失败直接 raise，不降级。
"""
import json
import re
from hashlib import sha256
from llm_client import send_message_gpt, get_last_llm_call_metadata as get_last_call_metadata
from logger import get_logger
from metadata_contracts import LLMCallRecord
from subject_config import get_subject_name, normalize_subject

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
    for key in ("provider_errors", "status", "operation", "model_policy", "usage"):
        if trace.get(key) is not None:
            metadata[key] = trace.get(key)
    return provider, model, fallback_count, metadata


def _call_record(*, call_id: str, purpose: str, prompt_id: str, prompt: str,
                 input_refs: dict, parsed_schema: str, confidence: float,
                 validation_errors: list = None, metadata: dict = None) -> dict:
    metadata = dict(metadata or {})
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
        metadata=metadata,
    )
    return call.model_dump()


def _parse_json_response(text: str) -> dict:
    """解析 Claude/GPT 返回的 JSON（容忍 markdown 包裹，兜底提取最外层 {}）。"""
    text = text.strip()
    # 去掉 ```json ... ``` 包裹
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if m:
        text = m.group(1).strip()
    # 若仍有多余前缀/后缀，提取最外层 { ... }
    if not text.startswith('{'):
        start = text.find('{')
        if start != -1:
            text = text[start:]
    if not text.endswith('}'):
        end = text.rfind('}')
        if end != -1:
            text = text[:end + 1]
    return json.loads(text)


def _data_subject(data: dict):
    """报告链 subject 真源在 exam_info.subject（report_data.aggregate_report_data 写入），顶层兜底。"""
    return (data.get("exam_info") or {}).get("subject") or data.get("subject")


def _build_overall_prompt(data: dict) -> str:
    """构建整卷综合分析 prompt。"""
    metrics = data["metrics"]
    diff_gradient = data["difficulty_gradient"]
    knowledge = data["knowledge"]
    competency = data["competency"]
    feature = data["feature_profile"]
    exam = data["exam_info"]
    metadata_quality = data.get("metadata_quality", {})

    diag = data.get("diagnostics", {})
    diag_section = ""
    if diag and diag.get("overall_rating") != "数据不足":
        diag_grad = diag.get("gradient", {})
        comp_bal = diag.get("competency_balance", {})
        spread = diag.get("difficulty_spread", {})
        diag_section = f"""
## 整卷质量诊断
- 难度梯度评级: {diag_grad.get('rating', 'N/A')}（偏差={diag_grad.get('deviation', 'N/A')}，理想分布={json.dumps(diag_grad.get('ideal', {}), ensure_ascii=False)}）
- 素养均衡度: {comp_bal.get('balance', 'N/A')}（方差={comp_bal.get('variance', 'N/A')}，缺失={comp_bal.get('missing', [])}）
- 难度离散度: {spread.get('spread_level', 'N/A')}（标准差={spread.get('difficulty_stdev', 'N/A')}，极差={spread.get('difficulty_range', 'N/A')}）
- 综合评价: {diag.get('overall_rating', 'N/A')}
"""

    metadata_section = ""
    if metadata_quality:
        metadata_section = f"""
## 元数据治理
- 低置信度题目: {metadata_quality.get('low_confidence_questions', [])}
- 元数据警告: {json.dumps(metadata_quality.get('warning_questions', []), ensure_ascii=False)}
- LLM 调用计数: {json.dumps(metadata_quality.get('llm_call_counts', {}), ensure_ascii=False)}
"""

    evidence_cards = _build_evidence_facts(data)
    evidence_section = "\n".join(
        f"- {fact.get('factText')}"
        for fact in evidence_cards
    )

    return f"""你是一名资深高中{get_subject_name(_data_subject(data))}教研员。请基于以下试卷分析数据，撰写专业的试卷质量评估。

## 试卷基本信息
- 名称: {exam["name"]}
- 题目数: {exam["total_questions"]}，总分: {exam["total_score"]}

## 整卷指标
- 平均难度（分值加权）: {metrics["avg_difficulty"]}（10分制）
- 平均认知层级（分值加权）: {metrics["avg_cognitive_level"]}（10分制）
- 难度分布: {json.dumps(metrics["difficulty_distribution"], ensure_ascii=False)}
- Bloom 认知层级分布（分值占比）: {json.dumps(metrics["bloom_distribution"], ensure_ascii=False)}

## 难度梯度
- 前段: {diff_gradient["front"]}，中段: {diff_gradient["middle"]}，后段: {diff_gradient["back"]}
- 梯度类型: {diff_gradient["gradient_type"]}

## 知识覆盖
- Top10 知识点: {json.dumps(knowledge["top_points"], ensure_ascii=False)}

## 6维特征均值
{json.dumps(feature["avg_per_dimension"], ensure_ascii=False)}
- 对难度贡献最大的3个维度: {feature["top_difficulty_factors"]}

## 素养分布
{json.dumps(competency["distribution"], ensure_ascii=False, default=str)}

{diag_section}
{metadata_section}
## 数据事实卡片
以下事实卡片均取自本卷分析数据。输出中的事实、数字和判断必须能被这些卡片直接支撑。
{evidence_section}

## 事实性要求
- 每句只包含一个主要事实；需要同时表达多个事实时，用短句拆开。
- 只使用上方数据中直接给出的数字、分布、题号和诊断结果。
- 优先使用上方数据事实卡片中的原句、数字和术语。
- 不要写“信度”“区分度”“质量良好”“有效区分”等未被上方数据直接证明的判断。
- 如果要写建议，必须先指出对应数据依据，例如“简单题0题”“科学探究10.6%”。
- 避免空泛评价，优先写可被上方数据逐句核对的事实句。

请输出严格 JSON（不要多余解释）：
{{
  "overall_assessment": "总评，150字内，概括试卷整体质量和突出特点",
  "recommendations": [
    {{"category": "类别", "content": "具体建议", "priority": "high|medium|low"}},
    ...5-8条
  ],
  "difficulty_analysis": "难度结构分析，含梯度评价和调整建议，200字内",
  "knowledge_analysis": "知识覆盖分析，指出薄弱章节和盲区，200字内",
  "competency_analysis": "素养覆盖分析，指出不足的素养维度，200字内",
  "bloom_analysis": "认知层级分析，高阶思维占比评价，150字内"
}}"""


def _build_teaching_prompt(
    data: dict, *, compact: bool = False, ultra_compact: bool = False
) -> str:
    """构建教学建议 prompt（错因归类 + 讲评提纲 + 补救练习）。"""
    questions = data.get("questions", [])
    mistakes = []
    for q in questions:
        q_id = q.get("id", "?")
        cms = q.get("common_mistakes", [])
        if not cms:
            cms = q.get("analysis", {}).get("common_mistakes", [])
        kps = q.get("knowledge_points", [])
        if not kps:
            kps = q.get("analysis", {}).get("knowledge_points", [])
        for m in cms:
            kp_str = ",".join(kps[:2])
            mistakes.append(f"题{q_id}({kp_str}): {m}")

    diagnostics = data.get("diagnostics", {})
    gradient_info = diagnostics.get("gradient", {}).get("rating", "未知")
    balance_info = diagnostics.get("competency_balance", {}).get("balance", "未知")

    if ultra_compact:
        mistakes_text = "；".join(mistakes[:6]) or "无"
        return (
            f"你是高中{get_subject_name(_data_subject(data))}试卷讲评助手。只返回一个可解析JSON对象，"
            "不要Markdown、解释或JSON外文字。\n"
            f"依据：{mistakes_text}\n"
            f"诊断：难度梯度{gradient_info}，素养均衡度{balance_info}\n"
            "硬性限制：error_categories恰好1项，lecture_outline恰好2项，"
            "remedial_exercises恰好2项；每个字符串不超过12字，"
            "description不超过20字，related_questions最多3个整数；"
            "只能替换字段值，保留键名和数组长度。\n"
            'JSON模板：{"error_categories":[{"category":"审题不清",'
            '"description":"忽略限定条件","related_questions":[1],'
            '"frequency":"中"}],"lecture_outline":[{"topic":"限定词辨析",'
            '"duration_minutes":8,"key_points":["圈画条件"],'
            '"related_errors":["审题不清"]},{"topic":"证据推理",'
            '"duration_minutes":10,"key_points":["先证后结"],'
            '"related_errors":["审题不清"]}],"remedial_exercises":['
            '{"knowledge_point":"薄弱点","exercise_type":"选择题",'
            '"difficulty":"中等"},{"knowledge_point":"图表分析",'
            '"exercise_type":"非选择题","difficulty":"中等"}]}'
        )

    mistakes_text = chr(10).join(mistakes[:12 if compact else 20])

    if compact:
        return (
            "根据易错点生成极简教学建议，只返回JSON，不要解释。\n"
            f"易错点：\n{mistakes_text}\n"
            f"诊断：难度梯度{gradient_info}，素养均衡度{balance_info}\n"
            "JSON格式："
            '{"error_categories":[{"category":"概念混淆","description":"20字内",'
            '"related_questions":[1],"frequency":"高"}],'
            '"lecture_outline":[{"topic":"20字内","duration_minutes":10,'
            '"key_points":["12字内"],"related_errors":["概念混淆"]}],'
            '"remedial_exercises":[{"knowledge_point":"知识点",'
            '"exercise_type":"题型","difficulty":"中等"}]}'
            "\n限制：error_categories最多3项，lecture_outline最多4项，"
            "remedial_exercises最多4项，每个字符串尽量短，只输出JSON。"
        )

    return (
        "基于以下试卷易错点和诊断结果，生成教学建议，返回纯JSON：\n\n"
        f"易错点汇总：\n{mistakes_text}\n\n"
        f"试卷诊断：难度梯度{gradient_info}，素养均衡度{balance_info}\n\n"
        "返回格式：\n"
        "{\n"
        '    "error_categories": [\n'
        '        {"category": "错因类型名称", "description": "具体描述", "related_questions": [1,3,5], "frequency": "高/中/低"}\n'
        "    ],\n"
        '    "lecture_outline": [\n'
        '        {"topic": "讲评重点", "duration_minutes": 10, "key_points": ["要点1","要点2"], "related_errors": ["错因类型"]}\n'
        "    ],\n"
        '    "remedial_exercises": [\n'
        '        {"knowledge_point": "薄弱知识点", "exercise_type": "建议题型", "difficulty": "建议难度"}\n'
        "    ]\n"
        "}\n\n"
        "要求：\n"
        "1. 错因归类：按认知类型分类（概念混淆/推理错误/知识遗漏/审题不清），不按题号\n"
        "2. 讲评提纲：按教学逻辑排序，重点在前，每个重点标注时间\n"
        "3. 补救练习：针对薄弱知识点推荐练习方向\n"
        "4. 用中文，简洁实用"
    )


def _build_evidence_facts(data: dict) -> list[dict]:
    facts = []

    def add_fact(source: str, text: str, **attrs) -> None:
        text = str(text or "").strip()
        if not text:
            return
        if len(text) > 1200:
            text = text[:1197] + "..."
        facts.append({
            "factText": text,
            "attributes": {"source": source, **attrs},
        })

    def compact_json(value) -> str:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))

    def pct(value) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if 0 <= number <= 1:
            number *= 100
        return f"{number:.1f}%"

    def number_text(value) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        return f"{number:.3f}".rstrip("0").rstrip(".")

    exam_info = data.get("exam_info") or {}
    if exam_info:
        add_fact(
            "report.data_card.exam_info",
            "exam_info: "
            f"名称={exam_info.get('name')}; "
            f"题目数={exam_info.get('total_questions')}; "
            f"总分={exam_info.get('total_score')}; "
            f"模式={exam_info.get('mode')}",
        )

    metrics = data.get("metrics", {}) or {}
    gradient = data.get("difficulty_gradient") or {}
    diagnostics = data.get("diagnostics") or {}
    gradient_diag = diagnostics.get("gradient") or {}
    spread_diag = diagnostics.get("difficulty_spread") or {}
    competency_diag = diagnostics.get("competency_balance") or {}
    if metrics or diagnostics:
        add_fact(
            "report.data_card.overall",
            "overall_evidence: "
            f"题目数={exam_info.get('total_questions')}；"
            f"总分={exam_info.get('total_score')}；"
            f"综合评价={diagnostics.get('overall_rating')}；"
            f"平均难度={metrics.get('avg_difficulty')}；"
            f"平均认知层级={metrics.get('avg_cognitive_level')}；"
            f"难度离散度={spread_diag.get('spread_level')}；"
            f"素养均衡度={competency_diag.get('balance')}。",
        )
    curve = data.get("difficulty_curve") or []
    top_difficulty = []
    if isinstance(curve, list):
        top_difficulty = [
            {
                "id": item.get("id") or item.get("question_id"),
                "difficulty": item.get("difficulty"),
                "score": item.get("total_score"),
            }
            for item in sorted(
                [row for row in curve if isinstance(row, dict)],
                key=lambda row: float(row.get("difficulty") or 0),
                reverse=True,
            )[:10]
        ]
    diff_distribution = metrics.get("difficulty_distribution") or {}
    diff_by_score = metrics.get("difficulty_distribution_by_score") or {}
    by_score_text = "、".join(
        f"{name}{pct((item or {}).get('percentage'))}"
        for name, item in diff_by_score.items()
        if isinstance(item, dict)
    )
    simple_count = diff_distribution.get("简单", 0)
    medium_count = diff_distribution.get("中等", 0)
    hard_count = diff_distribution.get("困难", 0)
    score_share_parts = []
    for name in ("简单", "中等", "困难"):
        score_item = diff_by_score.get(name)
        if isinstance(score_item, dict):
            score_share_parts.append(f"{name}题分值占比为{pct(score_item.get('percentage'))}。")
    top_difficulty_text = "、".join(
        f"Q{item.get('id')} 难度{item.get('difficulty')} 分值{item.get('score')}"
        for item in top_difficulty
        if item.get("id")
    )
    add_fact(
        "report.data_card.difficulty_distribution_detail",
        "difficulty_distribution_detail: "
        f"简单题为{simple_count}题。"
        f"中等题为{medium_count}题。"
        f"困难题为{hard_count}题。"
        f"{''.join(score_share_parts)}",
    )
    add_fact(
        "report.data_card.difficulty",
        "difficulty_evidence: "
        f"avg_difficulty={metrics.get('avg_difficulty')}，"
        f"难度分布为简单{simple_count}题、"
        f"中等{medium_count}题、"
        f"困难{hard_count}题；"
        f"按分值占比为{by_score_text}；"
        f"difficulty_gradient=前段{gradient.get('front')}、"
        f"中段{gradient.get('middle')}、后段{gradient.get('back')}，"
        f"类型={gradient.get('gradient_type')}；"
        f"难度梯度评级={gradient_diag.get('rating')}，"
        f"偏差值={gradient_diag.get('deviation')}，"
        f"理想分布={compact_json(gradient_diag.get('ideal') or {})}；"
        f"难度离散度={spread_diag.get('spread_level')}，"
        f"标准差={spread_diag.get('difficulty_stdev')}，"
        f"极差={spread_diag.get('difficulty_range')}；"
        f"高难题={top_difficulty_text}。",
    )
    bloom_distribution = metrics.get("bloom_distribution") or {}
    high_order = sum(
        float(bloom_distribution.get(key) or 0)
        for key in ("分析", "评价", "创造")
    )
    bloom_rank = sorted(
        bloom_distribution.items(),
        key=lambda item: float(item[1] or 0),
        reverse=True,
    )
    bloom_highest = bloom_rank[0][0] if bloom_rank else ""
    bloom_lowest = bloom_rank[-1][0] if bloom_rank else ""
    add_fact(
        "report.data_card.bloom",
        "bloom_evidence: "
        f"avg_cognitive_level={metrics.get('avg_cognitive_level')}；"
        f"识记层级占比为{number_text(bloom_distribution.get('识记', 0))}（{pct(bloom_distribution.get('识记', 0))}）；"
        f"理解层级占比为{number_text(bloom_distribution.get('理解', 0))}（{pct(bloom_distribution.get('理解', 0))}）；"
        f"应用层级占比为{number_text(bloom_distribution.get('应用', 0))}（{pct(bloom_distribution.get('应用', 0))}）；"
        f"分析层级占比为{number_text(bloom_distribution.get('分析', 0))}（{pct(bloom_distribution.get('分析', 0))}）；"
        f"评价层级占比为{number_text(bloom_distribution.get('评价', 0))}（{pct(bloom_distribution.get('评价', 0))}）；"
        f"创造层级占比为{number_text(bloom_distribution.get('创造', 0))}（{pct(bloom_distribution.get('创造', 0))}）；"
        f"bloom_distribution_raw={compact_json(bloom_distribution)}；"
        f"高阶思维占比={pct(high_order)}；"
        f"{bloom_highest}层级占比最高；{bloom_lowest}层级占比最低。",
    )

    if bloom_lowest:
        add_fact(
            "report.data_card.bloom_extremes",
            "bloom_extreme_evidence: "
            f"\u9ad8\u9636\u601d\u7ef4\u5360\u6bd4={pct(high_order)}; "
            f"{bloom_lowest}\u5c42\u7ea7\u5360\u6bd4\u6700\u4f4e\uff0c\u4e3a{pct(bloom_distribution.get(bloom_lowest, 0))}\u3002",
        )

    knowledge = data.get("knowledge") or {}
    top_points = []
    for point in (knowledge.get("top_points") or [])[:12]:
        if isinstance(point, dict):
            top_points.append({
                "name": point.get("name"),
                "weighted_score": point.get("weighted_score"),
                "question_count": point.get("question_count") or point.get("count"),
            })
    textbook_distribution = knowledge.get("textbook_distribution") or {}
    top_points_text = "、".join(
        f"{item.get('name')} 加权{item.get('weighted_score')}"
        for item in top_points
        if item.get("name")
    )
    knowledge_rank_labels = (
        "最高权重知识点",
        "第二高权重知识点",
        "第三高权重知识点",
        "第四高权重知识点",
        "第五高权重知识点",
        "第六高权重知识点",
    )
    knowledge_detail_parts = []
    for index, item in enumerate(top_points[:6]):
        name = item.get("name")
        if not name:
            continue
        rank_label = knowledge_rank_labels[index] if index < len(knowledge_rank_labels) else f"第{index + 1}高权重知识点"
        score = item.get("weighted_score")
        count = item.get("question_count")
        knowledge_detail_parts.append(f"{rank_label}为{name}")
        if score is not None:
            knowledge_detail_parts.append(f"{name}加权分值为{score}")
        if count is not None:
            knowledge_detail_parts.append(f"{name}涉及题数为{count}")
    textbook_text = "、".join(
        f"{name} {pct((value or {}).get('percentage'))}"
        for name, value in textbook_distribution.items()
        if isinstance(value, dict)
    )
    textbook_rank = []
    for name, value in textbook_distribution.items():
        if not isinstance(value, dict):
            continue
        try:
            textbook_rank.append((name, float(value.get("percentage") or 0)))
        except (TypeError, ValueError):
            continue

    add_fact(
        "report.data_card.knowledge",
        "knowledge_evidence: "
        f"top_points={top_points_text}；"
        f"textbook_distribution={textbook_text}。",
    )
    if knowledge_detail_parts:
        if textbook_rank:
            lowest_textbook, lowest_textbook_value = min(textbook_rank, key=lambda item: item[1])
            add_fact(
                "report.data_card.knowledge_extremes",
                "knowledge_extreme_evidence: "
                f"{lowest_textbook}\u5360\u6bd4\u6700\u4f4e\uff0c\u4e3a{pct(lowest_textbook_value)}\u3002",
            )
        add_fact(
            "report.data_card.knowledge_detail",
            "knowledge_detail_evidence: " + "；".join(knowledge_detail_parts) + "。",
        )

    competency = data.get("competency") or {}
    comp_distribution = competency.get("distribution") or {}
    comp_text_parts = []
    subtype_parts = []
    primary_distribution = competency.get("primary_distribution") or {}
    comp_rank = []
    for name, value in comp_distribution.items():
        if not isinstance(value, dict):
            continue
        if "占比" not in value and "ratio" not in value:
            continue
        ratio = value.get("占比") or value.get("ratio")
        try:
            comp_rank.append((name, float(ratio or 0)))
        except (TypeError, ValueError):
            pass
        comp_text_parts.append(
            f"{name}占比为{number_text(ratio)}（{pct(ratio)}）"
        )
        subtypes = value.get("细分") or {}
        if isinstance(subtypes, dict) and subtypes:
            subtype_parts.extend(
                f"{name}中{sub}包含{count}题"
                for sub, count in subtypes.items()
            )
    missing_competency = competency_diag.get("missing") or []
    missing_text = "空" if not missing_competency else "、".join(map(str, missing_competency))
    primary_parts = [
        f"主要素养分布中{name}为{count}题"
        for name, count in primary_distribution.items()
    ]
    comp_rank.sort(key=lambda item: item[1], reverse=True)
    comp_extreme_text = ""
    if comp_rank:
        highest_name, highest_ratio = comp_rank[0]
        lowest_name, lowest_ratio = comp_rank[-1]
        comp_extreme_text = (
            f"{highest_name}占比最高，为{pct(highest_ratio)}；"
            f"{lowest_name}占比最低，为{pct(lowest_ratio)}；"
        )
    add_fact(
        "report.data_card.competency",
        "competency_evidence: "
        f"素养均衡度={competency_diag.get('balance')}；"
        f"方差={competency_diag.get('variance')}；"
        f"缺失素养={missing_text}；"
        f"{comp_extreme_text}"
        f"{'；'.join(comp_text_parts)}；"
        f"{'；'.join(primary_parts)}；"
        f"{'；'.join(subtype_parts)}。",
    )

    zero_primary = []
    for name, count in primary_distribution.items():
        try:
            if float(count or 0) == 0:
                zero_primary.append(name)
        except (TypeError, ValueError):
            continue
    if zero_primary:
        add_fact(
            "report.data_card.competency_primary_gaps",
            "competency_primary_gap_evidence: "
            + "\uff1b".join(
                f"\u4e3b\u8981\u7d20\u517b\u4e2d{name}\u4e3a0\u9898"
                for name in zero_primary
            )
            + "\u3002",
        )
    zero_primary_text = "\u3001".join(map(str, zero_primary)) if zero_primary else "\u65e0"
    add_fact(
        "report.data_card.competency_primary_gap_summary",
        f"competency_primary_gap_summary: \u4e3b\u8981\u7d20\u517b\u4e3a0\u9898\u7684\u7ef4\u5ea6\u4e3a{zero_primary_text}\u3002",
    )

    feature_profile = data.get("feature_profile") or {}
    avg_dims = feature_profile.get("avg_per_dimension") or {}
    avg_dims_text = ", ".join(
        f"{name}={value}" for name, value in avg_dims.items()
    )
    factor_aliases = {
        "bloom": "\u8ba4\u77e5\u5c42\u7ea7",
        "reasoning_steps": "\u63a8\u7406\u6b65\u9aa4",
        "knowledge_breadth": "\u77e5\u8bc6\u5e7f\u5ea6",
        "working_memory": "\u5de5\u4f5c\u8bb0\u5fc6",
        "info_density": "\u4fe1\u606f\u5bc6\u5ea6",
        "representation_complexity": "\u8868\u5f81\u590d\u6742\u5ea6",
        "trap_density": "\u9677\u9631\u5bc6\u5ea6",
        "novelty": "\u60c5\u5883\u65b0\u9896\u5ea6",
        "chain_coupling": "\u94fe\u5f0f\u8026\u5408",
    }
    top_factors = feature_profile.get("top_difficulty_factors") or []
    top_factor_alias_text = ", ".join(
        f"{factor_aliases.get(str(factor), str(factor))}({factor})"
        for factor in top_factors
    )
    top_factor_names_text = "、".join(
        factor_aliases.get(str(factor), str(factor))
        for factor in top_factors
    )
    add_fact(
        "report.data_card.feature_profile",
        "feature_profile_evidence: "
        f"avg_per_dimension={avg_dims_text}；"
        f"对难度贡献最大的维度包含{top_factor_names_text}；"
        f"top_difficulty_factors={compact_json(top_factors)}; "
        f"top_difficulty_factor_aliases={top_factor_alias_text}",
    )

    add_fact(
        "report.data_card.summary",
        "summary_evidence: "
        f"exam_name={exam_info.get('name')}; "
        f"question_count={exam_info.get('total_questions')}; "
        f"total_score={exam_info.get('total_score')}; "
        f"avg_difficulty={metrics.get('avg_difficulty')}; "
        f"avg_cognitive_level={metrics.get('avg_cognitive_level')}; "
        f"high_order_share={pct(high_order)}; "
        f"top_difficulty_factors={compact_json(feature_profile.get('top_difficulty_factors') or [])}; "
        f"difficulty_gradient_back={gradient.get('back')}; "
        f"difficulty_gradient_type={gradient.get('gradient_type')}",
    )

    add_fact(
        "report.data_card.recommendation_basis",
        "recommendation_basis: "
        f"difficulty_distribution={compact_json(diff_distribution)}; "
        f"difficulty_distribution_by_score={by_score_text}; "
        f"hard_questions={top_difficulty_text}; "
        f"primary_distribution={compact_json(primary_distribution)}; "
        f"competency_distribution={' | '.join(comp_text_parts)}; "
        f"bloom_lowest={bloom_lowest}; "
        f"bloom_distribution={compact_json(bloom_distribution)}; "
        f"textbook_distribution={textbook_text}",
    )

    def _distribution_value_by_label(mapping: dict, labels: tuple[str, ...], field: str | None = None):
        if not isinstance(mapping, dict):
            return None
        lowered_labels = tuple(label.lower() for label in labels)
        for name, value in mapping.items():
            name_text = str(name).lower()
            if not any(label in name_text for label in lowered_labels):
                continue
            if field and isinstance(value, dict):
                return value.get(field)
            return value
        return None

    def _float_or(value, default: float | None = None) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    hard_score_share = _distribution_value_by_label(
        diff_by_score,
        ("\u56f0\u96be", "hard"),
        "percentage",
    )
    easy_score_share = _distribution_value_by_label(
        diff_by_score,
        ("\u7b80\u5355", "easy"),
        "percentage",
    )
    hard_count = _distribution_value_by_label(
        diff_distribution,
        ("\u56f0\u96be", "hard"),
    )
    easy_count = _distribution_value_by_label(
        diff_distribution,
        ("\u7b80\u5355", "easy"),
    )
    zero_primary = [
        str(name)
        for name, count in primary_distribution.items()
        if _float_or(count, None) == 0
    ]
    low_textbook = [
        str(name)
        for name, value in textbook_distribution.items()
        if isinstance(value, dict)
        and _float_or(value.get("percentage"), 1.0) < 0.15
    ]
    add_fact(
        "report.data_card.recommendation_policy",
        "recommendation_policy: "
        f"hard_score_share={pct(hard_score_share)}; "
        f"hard_count={hard_count}; "
        f"easy_score_share={pct(easy_score_share)}; "
        f"easy_count={easy_count}; "
        f"zero_primary_competencies={compact_json(zero_primary)}; "
        f"bloom_lowest={bloom_lowest}; "
        f"low_textbook_modules={compact_json(low_textbook)}; "
        "\u82e5\u56f0\u96be\u9898\u5206\u503c\u5360\u6bd4\u9ad8\u4e8e55%\uff0c"
        "\u5efa\u8bae\u964d\u4f4e\u56f0\u96be\u9898\u6bd4\u4f8b\u6216\u589e\u52a0\u4f4e\u95e8\u69db\u9898; "
        "\u82e5\u7b80\u5355\u9898\u4e0d\u8db32\u9898\u6216\u7b80\u5355\u9898\u5206\u503c\u5360\u6bd4\u4f4e\u4e8e10%\uff0c"
        "\u5efa\u8bae\u589e\u52a0\u7b80\u5355\u9898\u6216\u57fa\u7840\u9898; "
        "\u82e5\u67d0\u4e00\u4e3b\u8981\u7d20\u517b\u4e3a0\u9898\uff0c"
        "\u5efa\u8bae\u589e\u52a0\u4ee5\u8be5\u7d20\u517b\u4e3a\u4e3b\u7684\u9898\u76ee; "
        "\u82e5\u67d0\u8ba4\u77e5\u5c42\u7ea7\u5360\u6bd4\u6700\u4f4e\uff0c"
        "\u5efa\u8bae\u590d\u6838\u662f\u5426\u9700\u8981\u8865\u5145\u8be5\u5c42\u7ea7; "
        "\u82e5\u67d0\u6559\u6750\u6a21\u5757\u5360\u6bd4\u4f4e\u4e8e15%\uff0c"
        "\u5efa\u8bae\u6839\u636e\u8bfe\u7a0b\u8981\u6c42\u590d\u6838\u8986\u76d6\u662f\u5426\u8db3\u591f\u3002",
    )

    if diagnostics:
        add_fact(
            "report.data_card.diagnostics",
            "diagnostics_evidence: "
            f"overall_rating={diagnostics.get('overall_rating')}；"
            f"gradient_rating={gradient_diag.get('rating')}，"
            f"deviation={gradient_diag.get('deviation')}；"
            f"competency_balance={competency_diag.get('balance')}；"
            f"difficulty_spread={spread_diag.get('spread_level')}，"
            f"stdev={spread_diag.get('difficulty_stdev')}。",
        )

    metadata_quality = data.get("metadata_quality") or {}
    if metadata_quality:
        add_fact(
            "report.data_card.metadata_quality",
            "metadata_quality_evidence: "
            f"blocked_questions={compact_json(metadata_quality.get('blocked_questions') or [])}; "
            f"warning_questions={compact_json(metadata_quality.get('warning_questions') or [])}; "
            f"evidence_gap_questions={compact_json(metadata_quality.get('evidence_gap_questions') or [])}; "
            f"score_issue_questions={compact_json(metadata_quality.get('score_issue_questions') or [])}; "
            f"failure_events={compact_json(metadata_quality.get('failure_events') or [])}",
        )

    return facts


async def generate_insights(data: dict, mode: str = "brief") -> dict:
    """生成 LLM 综合分析。

    Args:
        data: aggregate_report_data() 的输出
        mode: "brief" 或 "full"

    Returns:
        InsightsResult dict

    Raises:
        RuntimeError: GPT 调用失败
    """
    _subj = normalize_subject(_data_subject(data))
    logger.info(f"[LLM分析] 开始生成 mode={mode} subject={_subj}")

    try:
        llm_calls = []
        input_refs = {
            "mode": mode,
            "exam_name": data.get("exam_info", {}).get("name"),
            "question_count": len(data.get("questions", [])),
            "total_score": data.get("exam_info", {}).get("total_score"),
        }

        # 调用 1+2: 整卷综合分析 & 教学建议 并行
        overall_prompt = _build_overall_prompt(data)
        teaching_prompt = _build_teaching_prompt(data)

        async def _run_overall():
            # 改动C：综合分析板块级降级保护。成功 → (text, False)；失败 → (None, True) 不 raise。
            try:
                text = await send_message_gpt(
                    prompt=overall_prompt,
                    max_tokens=64000,
                    temperature=0.0,
                    purpose="report_insights",
                )
                return text, False
            except Exception as overall_error:
                logger.warning(f"[LLM分析] 综合分析生成失败，板块降级: {overall_error}")
                return None, True

        async def _run_teaching():
            try:
                return await send_message_gpt(
                    prompt=teaching_prompt,
                    max_tokens=64000,
                    temperature=0.0,
                    purpose="report_teaching_suggestions",
                ), teaching_prompt, 0, "none"
            except Exception as first_error:
                logger.warning(f"[LLM分析] 教学建议生成失败，触发短格式重试: {first_error}")
                for retry_count, (retry_label, retry_prompt, retry_max_tokens) in enumerate(
                    (
                        ("compact", _build_teaching_prompt(data, compact=True), 64000),
                        ("ultra_compact", _build_teaching_prompt(data, ultra_compact=True), 64000),
                    ),
                    start=1,
                ):
                    try:
                        text = await send_message_gpt(
                            prompt=retry_prompt,
                            max_tokens=retry_max_tokens,
                            temperature=0.0,
                            purpose="report_teaching_suggestions",
                        )
                        return text, retry_prompt, retry_count, retry_label
                    except Exception as retry_error:
                        logger.warning(f"[LLM分析] 教学建议短格式重试失败 ({retry_label}): {retry_error}")
                # 改动C：教学建议三级重试全失败 → 板块降级（不 raise）。strategy="degraded" 供上层识别。
                logger.warning("[LLM分析] 教学建议三级重试全失败，板块降级")
                return None, teaching_prompt, retry_count, "degraded"

        (overall_text, overall_degraded), teaching_result = await asyncio.gather(
            _run_overall(), _run_teaching())
        teaching_text, teaching_prompt_used, teaching_retry_count, teaching_retry_strategy = teaching_result
        teaching_degraded = teaching_text is None or teaching_retry_strategy == "degraded"

        from llm_schemas import validate_llm_output, InsightsResult

        # 改动C fail-closed 护栏：综合分析与教学建议均降级 → 疑似 provider 整体不可用，
        # 不出空壳报告（这是 generate_insights 唯一保留的整篇失败）。
        if overall_degraded and teaching_degraded:
            raise RuntimeError(
                "LLM 分析生成失败: 综合分析与教学建议均不可用（疑似 provider 整体不可用），"
                "fail-closed 不出空壳报告"
            )

        degraded_sections = []

        # ── 综合分析（overall）──
        if overall_degraded:
            # 占位 result：各项统计数据由 report_data 提供、不受影响；仅 LLM 文本缺失。
            result = {
                "overall_assessment": "本次综合分析因模型暂时不可用未能生成，下列各项统计数据不受影响。",
                "recommendations": [],
                "difficulty_analysis": "",
                "knowledge_analysis": "",
                "competency_analysis": "",
                "bloom_analysis": "",
            }
            ext_conf, val_errors = 0.0, []
            degraded_sections.append("report_insights")
            # 降级 call 不走 _call_record（避免 contextvar provider_errors 泄漏被审计二次毙）
            llm_calls.append({
                "call_id": "report-overall-insights",
                "purpose": "report_insights",
                "prompt_id": f"{_subj}.report_insights",
                "prompt_hash": "degraded",
                "provider": "n/a",
                "model": "n/a",
                "input_refs": input_refs,
                "parsed_schema": "InsightsResult",
                "confidence": 0.0,
                "metadata": {"degraded": True, "reason": "provider_unavailable"},
            })
            logger.warning("[LLM分析] 综合分析板块降级，使用占位文案")
        else:
            result = _parse_json_response(overall_text)
            result, ext_conf, val_errors = validate_llm_output(result, InsightsResult, "整卷分析")
            if val_errors:
                logger.warning(f"[LLM分析] 整卷分析 schema 校验: {val_errors[:3]}")
            llm_calls.append(_call_record(
                call_id="report-overall-insights",
                purpose="report_insights",
                prompt_id=f"{_subj}.report_insights",
                prompt=overall_prompt,
                input_refs=input_refs,
                parsed_schema="InsightsResult",
                confidence=ext_conf,
                validation_errors=val_errors,
                metadata={"response_length": len(overall_text)},
            ))
            logger.info(f"[LLM分析] 整卷分析完成，{len(result.get('recommendations',[]))} 条建议 (confidence={ext_conf})")

        # 逐题点评和质量审查已移入 feature_extractor（v3 合并优化）
        # 从 report_data 的 questions 中提取 teacher_comment
        if mode == "full":
            question_comments = {}
            for q in data.get("questions", []):
                comment = q.get("teacher_comment", "")
                if comment:
                    question_comments[str(q["id"])] = comment
            if question_comments:
                result["question_comments"] = question_comments
                logger.info(f"[LLM分析] 逐题点评从特征提取复用，{len(question_comments)} 题")

        # ── 教学建议（teaching）──
        empty_teaching = {"error_categories": [], "lecture_outline": [], "remedial_exercises": []}
        if teaching_degraded:
            teaching = dict(empty_teaching)
            degraded_sections.append("report_teaching_suggestions")
            llm_calls.append({
                "call_id": "report-teaching-suggestions",
                "purpose": "report_teaching_suggestions",
                "prompt_id": f"{_subj}.report_teaching_suggestions",
                "prompt_hash": "degraded",
                "provider": "n/a",
                "model": "n/a",
                "input_refs": input_refs,
                "parsed_schema": "TeachingSuggestions",
                "confidence": 0.0,
                "metadata": {"degraded": True, "reason": "provider_unavailable"},
            })
            logger.warning("[LLM分析] 教学建议板块降级，使用占位空结构")
        else:
            # 教学建议已在上方并行获取，这里只解析结果；非法 JSON 也兜底为空结构（不 raise）
            try:
                teaching = _parse_json_response(teaching_text)
            except Exception as parse_error:
                logger.warning(f"[LLM分析] 教学建议解析失败，兜底空结构: {parse_error}")
                teaching = dict(empty_teaching)
                degraded_sections.append("report_teaching_suggestions")
            llm_calls.append(_call_record(
                call_id="report-teaching-suggestions",
                purpose="report_teaching_suggestions",
                prompt_id=f"{_subj}.report_teaching_suggestions",
                prompt=teaching_prompt_used,
                input_refs=input_refs,
                parsed_schema="TeachingSuggestions",
                confidence=1.0,
                metadata={
                    "response_length": len(teaching_text),
                    "retry_count": teaching_retry_count,
                    "compact_retry": teaching_retry_count > 0,
                    "retry_strategy": teaching_retry_strategy,
                },
            ))
            logger.info(f"[LLM分析] 教学建议生成完成")

        result["teaching_suggestions"] = teaching
        result["_llm_calls"] = llm_calls
        if degraded_sections:
            result.setdefault("_degraded_sections", []).extend(degraded_sections)

        return result

    except RuntimeError:
        # 改动C fail-closed 护栏抛出的 RuntimeError（两板块全降级）原样上抛，避免消息双重包裹
        logger.error("[LLM分析] fail-closed：综合分析与教学建议均不可用，整篇失败", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"[LLM分析] 失败，不使用静默降级: {e}", exc_info=True)
        raise RuntimeError(f"LLM 分析生成失败: {e}") from e


def _build_fallback_insights(data: dict) -> dict:
    raise RuntimeError("legacy report-insights fallback is disabled; use LLM output or fail closed")
    """数据驱动的降级建议（不依赖 LLM）"""
    recs = []
    metrics = data.get("metrics", {})
    knowledge = data.get("knowledge", {})
    competency = data.get("competency", {})
    questions = data.get("questions", [])

    # 难度分布建议
    diff_dist = metrics.get("difficulty_distribution", {})
    total_q = sum(diff_dist.values()) if diff_dist else 0
    if total_q > 0:
        hard_pct = diff_dist.get("困难", 0) / total_q * 100
        easy_pct = diff_dist.get("简单", 0) / total_q * 100
        if hard_pct > 50:
            recs.append({"priority": "high", "category": "难度结构",
                        "content": f"困难题占比 {hard_pct:.0f}%，偏高。建议适当降低 2-3 道中等以上难度题的综合性或信息量。"})
        elif easy_pct > 40:
            recs.append({"priority": "medium", "category": "难度结构",
                        "content": f"简单题占比 {easy_pct:.0f}%，区分度可能不足。建议增加情境化命题以提升思维考查深度。"})

    # 教材覆盖建议
    tb_dist = knowledge.get("textbook_distribution", {})
    if tb_dist:
        for tb_name, tb_data in tb_dist.items():
            if isinstance(tb_data, dict):
                pct = tb_data.get("percentage", 0)
                if pct < 5 and tb_data.get("weighted_score", 0) > 0:
                    recs.append({"priority": "medium", "category": "知识覆盖",
                                "content": f"{tb_name} 占比仅 {pct:.1f}%，覆盖不足。建议增加该模块相关试题。"})
                elif pct == 0:
                    recs.append({"priority": "low", "category": "知识覆盖",
                                "content": f"{tb_name} 未涉及。如非刻意取舍，建议补充该模块基础题目。"})

    # 素养均衡建议
    primary_dist = competency.get("primary_distribution", {})
    if isinstance(primary_dist, dict):
        for comp_name in ["科学探究", "社会责任"]:
            if primary_dist.get(comp_name, 0) == 0:
                recs.append({"priority": "medium", "category": "素养覆盖",
                            "content": f"核心素养 '{comp_name}' 在题目主素养维度缺失。虽然 SEU 加权分析显示有涉及，但建议增设以该素养为主考目标的题目。"})

    # 特征提取失败建议
    failed = sum(1 for q in questions if isinstance(q, dict) and
                 isinstance(q.get("feature_status"), str) and q["feature_status"] == "failed")
    if failed > 0:
        recs.append({"priority": "low", "category": "分析质量",
                    "content": f"{failed} 道题的特征提取未完成，相关质量评分缺失。建议检查这些题目是否包含复杂图表或特殊格式。"})

    if not recs:
        recs.append({"priority": "low", "category": "总评",
                    "content": "各项指标基本均衡，建议对照课程标准做进一步的覆盖度分析。"})

    # 整体评价
    avg_diff = metrics.get("avg_difficulty", 0)
    overall = f"本卷共 {total_q} 题，分值加权平均难度 {avg_diff:.2f}。"
    if avg_diff > 7:
        overall += "整体偏难，适合用于选拔性考试或一模摸底。"
    elif avg_diff > 5:
        overall += "难度适中，适合阶段性检测。"
    else:
        overall += "整体偏易，适合基础巩固练习。"

    return {
        "overall_assessment": overall,
        "recommendations": recs,
        "difficulty_analysis": "",
        "knowledge_analysis": "",
        "bloom_analysis": "",
        "competency_analysis": "",
    }
