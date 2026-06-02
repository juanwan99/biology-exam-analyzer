# -*- coding: utf-8 -*-
"""
工具函数模块

从 main.py 提取的通用辅助函数。
"""
from typing import Dict, Any

from logger import get_logger

logger = get_logger()


def infer_question_type(question: Dict[str, Any]) -> str:
    """
    推断题目类型（统一的题型推断逻辑）

    Args:
        question: 题目数据，包含 question_type 和 _section_header 字段

    Returns:
        推断后的题型：single_choice/multiple_choice/fill_blank/short_answer/unknown
    """
    question_type = question.get("question_type", "unknown")
    section_header = question.get("_section_header", "")
    q_id = question.get("id", "?")

    # 如果已有明确题型，直接返回
    if question_type != "unknown":
        return question_type

    # 根据分节标题推断
    if section_header:
        if any(kw in section_header for kw in ["单选", "单项选择", "只有一项", "只有一个选项"]):
            logger.info(f"[题型推断] 题目{q_id} 根据分节标题推断为 single_choice")
            return "single_choice"
        elif any(kw in section_header for kw in ["多选", "不定项", "多项", "一项或多项", "一个或多个选项"]):
            logger.info(f"[题型推断] 题目{q_id} 根据分节标题推断为 multiple_choice")
            return "multiple_choice"
        elif "填空" in section_header:
            logger.info(f"[题型推断] 题目{q_id} 根据分节标题推断为 fill_blank")
            return "fill_blank"
        elif any(kw in section_header for kw in ["非选择题", "简答", "实验"]):
            logger.info(f"[题型推断] 题目{q_id} 根据分节标题推断为 short_answer")
            return "short_answer"

    return "unknown"
