"""
测验生成API路由
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional

from quiz_service import quiz_service
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


class QuestionTypesConfig(BaseModel):
    """题型配置"""
    single_choice: int = 0
    multiple_choice: int = 0
    fill_blank: int = 0
    short_answer: int = 0


class GenerateQuizRequest(BaseModel):
    """生成测验请求"""
    book_ids: List[str]
    question_types: QuestionTypesConfig
    difficulty: str = "medium"  # easy/medium/hard/mixed
    use_ai_generation: bool = False


@router.post("/generate")
async def generate_quiz(request: GenerateQuizRequest):
    """
    生成测验

    POST /api/quiz/generate
    {
        "book_ids": ["bx1", "bx2"],
        "question_types": {
            "single_choice": 10,
            "multiple_choice": 5,
            "fill_blank": 3,
            "short_answer": 2
        },
        "difficulty": "medium",
        "use_ai_generation": false
    }
    """
    try:
        # 验证输入
        if not request.book_ids:
            raise HTTPException(status_code=400, detail="请至少选择一本教材")

        total_questions = (
            request.question_types.single_choice +
            request.question_types.multiple_choice +
            request.question_types.fill_blank +
            request.question_types.short_answer
        )

        if total_questions == 0:
            raise HTTPException(status_code=400, detail="请至少设置一种题型的数量")

        if total_questions > 100:
            raise HTTPException(status_code=400, detail="题目总数不能超过100")

        # 验证difficulty
        if request.difficulty not in ["easy", "medium", "hard", "mixed"]:
            raise HTTPException(status_code=400, detail="无效的难度等级")

        # 生成测验
        quiz_data = await quiz_service.generate_quiz(
            book_ids=request.book_ids,
            question_types=request.question_types.dict(),
            difficulty=request.difficulty,
            use_ai_generation=request.use_ai_generation
        )

        return {
            "success": True,
            "data": quiz_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成测验失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")
