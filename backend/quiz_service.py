"""
智能测验生成服务
基于向量检索和AI生成的混合策略
"""
import os
import random
import asyncio
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from logger import get_logger

logger = get_logger()


class QuizGeneratorService:
    """测验生成器服务"""

    def __init__(self):
        # 配置视觉模型 API
        self.api_key = os.environ.get("QWEN_API_KEY")
        self.api_base = os.environ.get("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.model_name = "qwen-vl-max"

        if self.api_key:
            self.enabled = True
        else:
            self.enabled = False

    async def generate_quiz(
        self,
        book_ids: List[str],
        question_types: Dict[str, int],
        difficulty: str = "medium",
        use_ai_generation: bool = False
    ) -> Dict[str, Any]:
        """
        生成测验

        Args:
            book_ids: 教材ID列表
            question_types: 题型数量配置 {"single_choice": 10, "multiple_choice": 5, ...}
            difficulty: 难度等级 (easy/medium/hard/mixed)
            use_ai_generation: 是否使用AI生成补充题目

        Returns:
            生成的测验数据
        """
        async with async_session() as session:
            questions = []

            # 题型映射
            type_map = {
                "single_choice": "单选题",
                "multiple_choice": "多选题",
                "fill_blank": "填空题",
                "short_answer": "简答题"
            }

            # 为每种题型生成题目
            for q_type_en, count in question_types.items():
                if count == 0:
                    continue

                q_type_cn = type_map.get(q_type_en)
                if not q_type_cn:
                    continue

                # 如果启用AI生成，优先使用AI生成全部题目
                if use_ai_generation and self.enabled:
                    # 使用AI生成所有题目
                    ai_questions = await self._generate_questions_with_ai(
                        session, book_ids, q_type_cn, count, difficulty
                    )
                    questions.extend(ai_questions)

                    # 如果AI生成不足，从题库补充
                    shortage = count - len(ai_questions)
                    if shortage > 0:
                        retrieved_questions = await self._retrieve_questions_from_bank(
                            session, book_ids, q_type_cn, shortage, difficulty
                        )
                        questions.extend(retrieved_questions)
                else:
                    # 未启用AI，仅从题库检索
                    retrieved_questions = await self._retrieve_questions_from_bank(
                        session, book_ids, q_type_cn, count, difficulty
                    )
                    questions.extend(retrieved_questions)

            # 获取教材名称
            book_names = await self._get_book_names(session, book_ids)

            # 构造返回数据
            quiz_data = {
                "questions": questions,
                "metadata": {
                    "books": book_names,
                    "difficulty": difficulty,
                    "total_questions": len(questions),
                    "generated_at": datetime.now().isoformat(),
                    "ai_generated_count": sum(1 for q in questions if q.get("source") == "AI生成")
                }
            }

            return quiz_data

    async def _retrieve_questions_from_bank(
        self,
        session: AsyncSession,
        book_ids: List[str],
        question_type: str,
        count: int,
        difficulty: str
    ) -> List[Dict[str, Any]]:
        """从题库检索题目（基于教材范围）"""

        # 根据难度设置难度范围
        difficulty_ranges = {
            "easy": (0.0, 0.4),
            "medium": (0.3, 0.7),
            "hard": (0.6, 1.0),
            "mixed": (0.0, 1.0)
        }
        min_diff, max_diff = difficulty_ranges.get(difficulty, (0.0, 1.0))

        # 查询题目
        # 注意: 这里需要通过source关联到教材，暂时先查询所有符合条件的题目
        result = await session.execute(
            text("""
                SELECT
                    eb.id,
                    eb.question_type,
                    eb.content,
                    eb.options,
                    eb.answer,
                    eb.explanation,
                    eb.difficulty_level,
                    es.name as source_name
                FROM exercise_bank eb
                LEFT JOIN exercise_sources es ON eb.source_id = es.id
                WHERE eb.question_type = :q_type
                  AND eb.difficulty_level BETWEEN :min_diff AND :max_diff
                ORDER BY RANDOM()
                LIMIT :limit
            """),
            {
                "q_type": question_type,
                "min_diff": min_diff,
                "max_diff": max_diff,
                "limit": count * 2  # 多取一些，后面筛选
            }
        )

        rows = result.fetchall()

        # 转换为字典格式
        questions = []
        for row in rows[:count]:  # 只取需要的数量
            q_dict = {
                "question_type": row.question_type,
                "content": row.content,
                "options": row.options if row.options else None,
                "answer": row.answer,
                "explanation": row.explanation or "",
                "difficulty_level": float(row.difficulty_level) if row.difficulty_level else 0.5,
                "source": row.source_name or "题库"
            }
            questions.append(q_dict)

        return questions

    async def _generate_questions_with_ai(
        self,
        session: AsyncSession,
        book_ids: List[str],
        question_type: str,
        count: int,
        difficulty: str
    ) -> List[Dict[str, Any]]:
        """使用AI生成题目（基于向量检索的教材内容）"""

        if not self.enabled:
            return []

        # 从向量库检索相关教材内容
        context = await self._retrieve_textbook_context(session, book_ids, limit=5)

        if not context:
            return []

        # 构造prompt
        prompt = self._build_generation_prompt(
            context, question_type, count, difficulty
        )

        import asyncio

        max_retries = 3
        retry_delay = 5  # 秒

        for attempt in range(max_retries):
            try:
                # 使用httpx调用API（支持自定义base_url）
                async with httpx.AsyncClient(timeout=120.0) as client:
                    # 构造OpenAI兼容的请求格式
                    response = await client.post(
                        f"{self.api_base}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model_name,
                            "messages": [
                                {"role": "user", "content": prompt}
                            ],
                            "temperature": 0.7,
                            "max_tokens": 4096
                        }
                    )
                    response.raise_for_status()
                    result = response.json()

                    # 提取生成的内容
                    ai_text = result["choices"][0]["message"]["content"]

                # 解析生成的题目
                questions = self._parse_ai_generated_questions(
                    ai_text, question_type
                )

                return questions[:count]

            except httpx.HTTPStatusError as e:
                if e.response.status_code in [429, 503] and attempt < max_retries - 1:
                    logger.warning(f"AI生成题目遇到{e.response.status_code}错误，{retry_delay}秒后重试 ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                    continue
                logger.error(f"AI生成题目失败: {e}")
                return []
            except Exception as e:
                logger.error(f"AI生成题目失败: {e}", exc_info=True)
                return []

        return []

    async def _retrieve_textbook_context(
        self,
        session: AsyncSession,
        book_ids: List[str],
        limit: int = 15
    ) -> str:
        """从向量库检索教材内容作为生成上下文"""

        # 随机从指定教材中抽取一些chunk作为上下文
        # 增加数量以提供更丰富的上下文
        result = await session.execute(
            text("""
                SELECT chunk_content
                FROM textbook_chunks
                WHERE book_id = ANY(:book_ids)
                ORDER BY RANDOM()
                LIMIT :limit
            """),
            {"book_ids": book_ids, "limit": limit}
        )

        rows = result.fetchall()
        context_parts = [row[0] for row in rows if row[0]]

        return "\n\n".join(context_parts)

    def _build_generation_prompt(
        self,
        context: str,
        question_type: str,
        count: int,
        difficulty: str
    ) -> str:
        """构造AI生成题目的prompt"""

        difficulty_desc = {
            "easy": "简单（基础概念和知识点理解）",
            "medium": "中等（知识应用和综合分析）",
            "hard": "困难（深度理解和创新思维）",
            "mixed": "混合难度"
        }

        # 根据题型定制prompt
        if question_type == "单选题":
            type_instruction = """
单选题要求:
- 题干清晰，问题明确
- 4个选项（A、B、C、D），只有1个正确答案
- 干扰项要有合理性，体现常见误区
- 答案要准确，解析要详细说明为何该选项正确，其他选项错误
"""
        elif question_type == "多选题":
            type_instruction = """
多选题要求:
- 题干清晰，说明"正确的是"或"错误的是"
- 4个选项（A、B、C、D），2-3个正确答案
- 答案格式如"AB"或"ACD"
- 解析要逐个分析每个选项的正误
"""
        elif question_type == "填空题":
            type_instruction = """
填空题要求:
- 题目中用"______"表示空白处
- 答案简洁准确，可以是单词、短语或简短句子
- 解析说明知识点和答题思路
"""
        else:  # 简答题
            type_instruction = """
简答题要求:
- 问题开放，需要完整表述
- 答案要点清晰，分条列出
- 解析提供答题思路和评分要点
"""

        prompt = f"""你是一位资深的高中生物教师，擅长根据教材内容命制高质量的考试题目。

请仔细阅读以下教材内容，并根据这些内容生成{count}道{question_type}。

【教材内容】
{context}

【命题要求】
1. 题目类型: {question_type}
2. 难度等级: {difficulty_desc.get(difficulty, '中等')}
3. 数量: {count}道
{type_instruction}
4. 题目必须严格基于上述教材内容，确保科学准确性
5. 题目要有一定的区分度和思维深度
6. 避免过于简单的记忆性题目
7. 解析要详细，帮助学生理解知识点

【输出格式】
请严格按照以下JSON格式输出，不要添加任何其他文字：
[
  {{
    "content": "题目内容",
    "options": {{"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"}},  // 仅选择题需要此字段
    "answer": "答案",  // 单选题如"A"，多选题如"AB"，填空题和简答题直接写答案
    "explanation": "详细解析"
  }}
]
"""
        return prompt

    def _parse_ai_generated_questions(
        self,
        ai_response: str,
        question_type: str
    ) -> List[Dict[str, Any]]:
        """解析AI生成的题目"""

        import json
        import re

        try:
            # 尝试提取JSON部分
            json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
            if json_match:
                questions_data = json.loads(json_match.group(0))
            else:
                questions_data = json.loads(ai_response)

            # 转换格式
            questions = []
            for q_data in questions_data:
                q_dict = {
                    "question_type": question_type,
                    "content": q_data.get("content", ""),
                    "options": q_data.get("options"),
                    "answer": q_data.get("answer", ""),
                    "explanation": q_data.get("explanation", ""),
                    "difficulty_level": 0.5,  # AI生成的默认中等难度
                    "source": "AI生成"
                }
                questions.append(q_dict)

            return questions

        except Exception as e:
            logger.error(f"解析AI生成题目失败: {e}")
            logger.debug(f"AI响应: {ai_response}")
            return []

    async def _get_book_names(
        self,
        session: AsyncSession,
        book_ids: List[str]
    ) -> List[str]:
        """获取教材名称"""

        book_map = {
            "bx1": "必修1",
            "bx2": "必修2",
            "xxbx1": "选择性必修1",
            "xxbx2": "选择性必修2",
            "xxbx3": "选择性必修3"
        }

        return [book_map.get(book_id, book_id) for book_id in book_ids]


# 创建全局服务实例
quiz_service = QuizGeneratorService()
