"""PDF 报告 LLM 分析层 — GPT 5.4 生成综合分析文本。

调用 1: 整卷综合分析（brief+full 共用）
调用 2: 逐题教师点评（仅 full）
GPT 失败直接 raise，不降级。
"""
import json
import re
from llm_client import send_message_gpt
from logger import get_logger

logger = get_logger()


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
        # 调用 1: 整卷综合分析
        overall_text = await send_message_gpt(
            prompt=_build_overall_prompt(data),
            max_tokens=2000,
            temperature=0.3,
        )
        result = _parse_json_response(overall_text)
        from llm_schemas import validate_llm_output, InsightsResult
        result, ext_conf, val_errors = validate_llm_output(result, InsightsResult, "整卷分析")
        if val_errors:
            logger.warning(f"[LLM分析] 整卷分析 schema 校验: {val_errors[:3]}")
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
            logger.info(f"[LLM分析] 教学建议生成完成")
        except Exception as e:
            logger.warning(f"[LLM分析] 教学建议生成失败: {e}")
            teaching = {"error_categories": [], "lecture_outline": [], "remedial_exercises": []}

        result["teaching_suggestions"] = teaching

        return result

    except Exception as e:
        logger.error(f"[LLM分析] 失败，使用数据降级模板: {e}", exc_info=True)
        return _build_fallback_insights(data)


def _build_fallback_insights(data: dict) -> dict:
    """基于 rdata 数值生成降级分析（无 LLM）。"""
    metrics = data.get("metrics", {})
    avg_diff = metrics.get("avg_difficulty", 0)
    avg_cog = metrics.get("avg_cognitive_level", 0)
    dist = metrics.get("difficulty_distribution", {})
    bloom = metrics.get("bloom_distribution", {})
    gradient = data.get("difficulty_gradient", {})
    diag = data.get("diagnostics", {})
    knowledge = data.get("knowledge", {})
    competency = data.get("competency", {})

    diff_label = "偏易" if avg_diff < 4 else ("偏难" if avg_diff > 7 else "适中")
    overall_rating = diag.get("overall_rating", "")
    rating_text = f"整卷质量评价为「{overall_rating}」。" if overall_rating and overall_rating != "数据不足" else ""

    overall = (
        f"本卷共{data.get('exam_info', {}).get('total_questions', '?')}题，"
        f"总分{data.get('exam_info', {}).get('total_score', '?')}分。"
        f"分值加权平均难度{avg_diff:.1f}（{diff_label}），"
        f"平均认知层级{avg_cog:.1f}。"
        f"难度分布：简单{dist.get('简单', 0)}题、中等{dist.get('中等', 0)}题、困难{dist.get('困难', 0)}题。"
        f"{rating_text}"
    )

    grad_type = gradient.get("gradient_type", "")
    diff_analysis = (
        f"难度梯度类型为「{grad_type}」（前段{gradient.get('front', 0)}、"
        f"中段{gradient.get('middle', 0)}、后段{gradient.get('back', 0)}）。"
    )
    if diag.get("gradient", {}).get("rating"):
        diff_analysis += f"梯度评级：{diag['gradient']['rating']}（偏差{diag['gradient'].get('deviation', '?')}）。"

    top_kps = [kp.get("name", "") for kp in knowledge.get("top_points", [])[:5]]
    know_analysis = f"高频知识点：{'、'.join(top_kps)}。" if top_kps else "知识点数据不足。"

    comp_dist = competency.get("distribution", {})
    comp_bal = diag.get("competency_balance", {})
    balance_text = comp_bal.get("balance", "未知")
    comp_analysis = f"素养均衡度：{balance_text}。"
    if comp_bal.get("missing"):
        comp_analysis += f"缺失维度：{'、'.join(comp_bal['missing'])}。"

    high_order = sum(bloom.get(k, 0) for k in ["分析", "评价", "创造"])
    bloom_analysis = f"高阶思维（分析+评价+创造）占比{high_order*100:.1f}%。"

    recs = []
    if avg_diff > 7:
        recs.append({"category": "难度", "content": "整卷偏难，建议增加基础题占比。", "priority": "high"})
    elif avg_diff < 3.5:
        recs.append({"category": "难度", "content": "整卷偏易，建议增加中等及以上难度题目。", "priority": "high"})
    if comp_bal.get("missing"):
        recs.append({"category": "素养", "content": f"缺失{'、'.join(comp_bal['missing'])}相关题目，建议补充。", "priority": "high"})
    if high_order < 0.2:
        recs.append({"category": "认知", "content": "高阶思维题目占比偏低，建议增加分析、评价类题目。", "priority": "medium"})
    if not recs:
        recs.append({"category": "综合", "content": "各项指标基本达标，建议参考详细数据进一步优化。", "priority": "low"})

    return {
        "overall_assessment": overall,
        "recommendations": recs,
        "difficulty_analysis": diff_analysis,
        "knowledge_analysis": know_analysis,
        "competency_analysis": comp_analysis,
        "bloom_analysis": bloom_analysis,
        "question_comments": {},
        "teaching_suggestions": {"error_categories": [], "lecture_outline": [], "remedial_exercises": []},
    }
