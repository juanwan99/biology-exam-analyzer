"""LLM 特征提取 — prompt 构建 + JSON 解析容错。

设计文档: docs/plans/2026-03-12-feature-difficulty-design.md §5
"""
import json
import re
import logging
from claude_client import send_message

logger = logging.getLogger(__name__)

# 各维度的合法范围 (min, max)
FEATURE_RANGES = {
    "bloom": (1, 6),
    "reasoning_steps": (1, 10),
    "knowledge_breadth": (1, 3),
    "info_density": (1, 3),
    "novelty": (1, 3),
    "question_type_factor": (1, 4),
}

# 解析失败时的默认值（各维度中位数）
DEFAULT_FEATURES = {
    "bloom": 3,
    "reasoning_steps": 4,
    "knowledge_breadth": 2,
    "info_density": 2,
    "novelty": 2,
    "question_type_factor": 1,
}


def build_feature_prompt(question_text: str, options: str = "", correct_answer: str = "") -> str:
    """构建特征提取 prompt。"""
    parts = [question_text]
    if options:
        parts.append(f"选项：{options}")
    if correct_answer:
        parts.append(f"正确答案：{correct_answer}")
    question_block = "\n".join(parts)

    return f"""你是一名资深高中生物教师。请分析这道题目的难度特征。

题目：
{question_block}

请输出以下 6 个维度的评分（严格 JSON，不要解释）：
{{
  "bloom": 1-6（1识记 2理解 3应用 4分析 5评价 6创造），
  "reasoning_steps": 正整数（从题目信息到答案的推理步数），
  "knowledge_breadth": 1-3（1单知识点 2跨考点 3跨模块），
  "info_density": 1-3（1低≤2条 2中3-5条 3高>5条或含图表），
  "novelty": 1-3（1教材原文 2变式 3全新情境），
  "question_type_factor": 1-4（1单选 2多选/填空 3简答 4实验设计）
}}"""


def parse_features(raw: str) -> dict:
    """从 LLM 原始输出解析 6 维特征，带容错和范围裁剪。

    解析策略：
    1. 直接 JSON 解析
    2. 从 markdown code block 提取
    3. 正则提取第一个 JSON object
    4. 全部失败 → 返回默认值
    """
    data = None

    if not isinstance(raw, str):
        logger.warning(f"特征解析输入非字符串: {type(raw)}")
        return dict(DEFAULT_FEATURES)

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

    # 策略 3: 第一个 JSON object
    if data is None:
        m = re.search(r'\{[^{}]*\}', raw)
        if m:
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError:
                pass

    # 全部失败
    if not isinstance(data, dict):
        logger.warning(f"特征解析失败，使用默认值。原始输出: {raw[:200]}")
        return dict(DEFAULT_FEATURES)

    # 补全缺失字段 + 范围裁剪
    result = {}
    for key, (lo, hi) in FEATURE_RANGES.items():
        val = data.get(key, DEFAULT_FEATURES[key])
        try:
            val = int(val)
        except (ValueError, TypeError):
            val = DEFAULT_FEATURES[key]
        result[key] = max(lo, min(hi, val))

    return result


async def extract_features(question_text: str, options: str = "",
                           correct_answer: str = "") -> dict:
    """调用 LLM 提取题目特征。

    Returns:
        dict: 6 维特征值
    """
    prompt = build_feature_prompt(question_text, options, correct_answer)
    try:
        raw = await send_message(
            prompt,
            model="claude-sonnet-4-5-20250929",
            max_tokens=256,
            temperature=0,
        )
        return parse_features(raw)
    except Exception as e:
        logger.error(f"特征提取 API 调用失败: {e}")
        return dict(DEFAULT_FEATURES)
