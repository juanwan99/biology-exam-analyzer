"""PDF 报告 LLM 分析层 — GPT 5.4 生成综合分析文本。

调用 1: 整卷综合分析（brief+full 共用）
调用 2: 逐题教师点评（仅 full）
GPT 失败直接 raise，不降级。
"""
import json
import re
from hashlib import sha256
from llm_client import send_message_gpt
from logger import get_logger
from metadata_contracts import LLMCallRecord

logger = get_logger()


def _call_record(*, call_id: str, purpose: str, prompt_id: str, prompt: str,
                 input_refs: dict, parsed_schema: str, confidence: float,
                 validation_errors: list = None, metadata: dict = None) -> dict:
    call = LLMCallRecord(
        call_id=call_id,
        purpose=purpose,
        prompt_id=prompt_id,
        prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
        provider="llm_client",
        model="configured_provider_chain",
        input_refs=input_refs,
        parsed_schema=parsed_schema,
        confidence=confidence,
        validation_errors=validation_errors or [],
        metadata=metadata or {},
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

    return f"""你是一名资深高中生物教研员。请基于以下试卷分析数据，撰写专业的试卷质量评估。

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


def _build_comments_prompt(questions: list) -> str:
    """构建逐题教师点评 prompt。"""
    BLOOM_MAP = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}
    items = []
    for q in questions:
        items.append(
            f"题目{q['id']}（{q.get('total_score',0)}分，难度{q.get('difficulty',5):.1f}，"
            f"Bloom={BLOOM_MAP.get(q.get('bloom',3),'应用')}）：\n"
            f"  知识点: {', '.join(q.get('knowledge_points',[]))}\n"
            f"  素养: {q.get('primary_competency','')}\n"
            f"  解析摘要: {(q.get('detailed_analysis',''))[:100]}\n"
            f"  常见错误: {', '.join(q.get('common_mistakes',[])[:2])}"
        )

    return f"""你是一名资深高中生物教师。请为以下每道题写 2-3 句教师视角点评。
点评应包含：考查目的、难点归因、常见失分预警。

{chr(10).join(items)}

请输出严格 JSON：
{{
  "question_comments": {{
    "题号": "点评文本",
    ...
  }}
}}"""



def _build_teaching_prompt(data: dict) -> str:
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

    mistakes_text = chr(10).join(mistakes[:20])

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
    logger.info(f"[LLM分析] 开始生成 mode={mode}")

    try:
        llm_calls = []
        input_refs = {
            "mode": mode,
            "exam_name": data.get("exam_info", {}).get("name"),
            "question_count": len(data.get("questions", [])),
            "total_score": data.get("exam_info", {}).get("total_score"),
        }

        # 调用 1: 整卷综合分析
        overall_prompt = _build_overall_prompt(data)
        overall_text = await send_message_gpt(
            prompt=overall_prompt,
            max_tokens=2000,
            temperature=0.3,
        )
        result = _parse_json_response(overall_text)
        from llm_schemas import validate_llm_output, InsightsResult
        result, ext_conf, val_errors = validate_llm_output(result, InsightsResult, "整卷分析")
        if val_errors:
            logger.warning(f"[LLM分析] 整卷分析 schema 校验: {val_errors[:3]}")
        llm_calls.append(_call_record(
            call_id="report-overall-insights",
            purpose="report_insights",
            prompt_id="biology.report_insights",
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


        # 教学建议（错因归类 + 讲评提纲 + 补救练习）
        teaching_prompt = _build_teaching_prompt(data)
        try:
            teaching_text = await send_message_gpt(
                prompt=teaching_prompt,
                max_tokens=2048,
                temperature=0.3,
            )
            teaching = _parse_json_response(teaching_text)
            llm_calls.append(_call_record(
                call_id="report-teaching-suggestions",
                purpose="report_teaching_suggestions",
                prompt_id="biology.report_teaching_suggestions",
                prompt=teaching_prompt,
                input_refs=input_refs,
                parsed_schema="TeachingSuggestions",
                confidence=1.0,
                metadata={"response_length": len(teaching_text)},
            ))
            logger.info(f"[LLM分析] 教学建议生成完成")
        except Exception as e:
            logger.warning(f"[LLM分析] 教学建议生成失败: {e}")
            teaching = {"error_categories": [], "lecture_outline": [], "remedial_exercises": []}
            llm_calls.append(_call_record(
                call_id="report-teaching-suggestions",
                purpose="report_teaching_suggestions",
                prompt_id="biology.report_teaching_suggestions",
                prompt=teaching_prompt,
                input_refs=input_refs,
                parsed_schema="TeachingSuggestions",
                confidence=0.0,
                validation_errors=[str(e)],
                metadata={"fallback": "empty_teaching_suggestions"},
            ))

        result["teaching_suggestions"] = teaching
        result["_llm_calls"] = llm_calls

        return result

    except Exception as e:
        logger.error(f"[LLM分析] 失败，不使用静默降级: {e}", exc_info=True)
        raise RuntimeError("LLM 分析生成失败") from e


def _build_fallback_insights(data: dict) -> dict:
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
