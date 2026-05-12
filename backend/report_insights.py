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
    gradient = data["difficulty_gradient"]
    knowledge = data["knowledge"]
    competency = data["competency"]
    feature = data["feature_profile"]
    exam = data["exam_info"]

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
- 前段: {gradient["front"]}，中段: {gradient["middle"]}，后段: {gradient["back"]}
- 梯度类型: {gradient["gradient_type"]}

## 知识覆盖
- Top10 知识点: {json.dumps(knowledge["top_points"], ensure_ascii=False)}

## 6维特征均值
{json.dumps(feature["avg_per_dimension"], ensure_ascii=False)}
- 对难度贡献最大的3个维度: {feature["top_difficulty_factors"]}

## 素养分布
{json.dumps(competency["distribution"], ensure_ascii=False, default=str)}

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
        logger.info(f"[LLM分析] 整卷分析完成，{len(result.get('recommendations',[]))} 条建议")

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

        return result

    except Exception as e:
        logger.error(f"[LLM分析] 失败: {e}", exc_info=True)
        raise RuntimeError(f"LLM 分析生成失败: {e}") from e
