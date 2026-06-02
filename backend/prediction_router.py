"""
分数预估系统API路由

提供历史数据管理和分数预估的API端点
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from prediction_service import PredictionService
from logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/api/prediction", tags=["分数预估"])


# ============ Pydantic Models ============

class QuestionScoreInput(BaseModel):
    """单个题目的得分输入"""
    question_number: int = Field(..., description="题号")
    question_score: float = Field(..., description="该题满分")
    actual_average: float = Field(..., description="实际平均分")
    absolute_difficulty: Optional[float] = Field(None, description="绝对难度 (0-10)")
    knowledge_complexity: Optional[float] = Field(None, description="知识复杂度")
    cognitive_level: Optional[float] = Field(None, description="认知层级")
    knowledge_points: Optional[List[str]] = Field(default=[], description="知识点列表")
    textbook_chapter: Optional[str] = Field(None, description="教材章节")
    question_type: Optional[str] = Field(None, description="题型")
    question_content: Optional[str] = Field(None, description="题目内容摘要")


class ExamHistoryCreate(BaseModel):
    """创建历史考试记录请求"""
    name: str = Field(..., description="考试名称")
    grade: str = Field(..., description="年级（高一/高二/高三）")
    total_score: float = Field(..., description="试卷总分")
    questions: List[QuestionScoreInput] = Field(..., description="题目列表")
    exam_date: Optional[str] = Field(None, description="考试日期 (YYYY-MM-DD)")
    student_count: Optional[int] = Field(None, description="参考人数")
    source_file: Optional[str] = Field(None, description="原始文件路径")


class QuestionForPrediction(BaseModel):
    """用于预估的题目数据"""
    id: Optional[int] = None
    total_score: float = Field(..., description="题目满分")
    difficulty: Dict = Field(..., description="难度数据，需包含 final_difficulty")
    analysis: Optional[Dict] = Field(default={}, description="分析数据，可包含 knowledge_points")


class PredictExamRequest(BaseModel):
    """预估试卷分数请求"""
    questions: List[QuestionForPrediction] = Field(..., description="题目列表")
    total_score: float = Field(..., description="试卷总分")
    grade: str = Field(..., description="年级")
    exam_name: Optional[str] = Field(None, description="考试名称")
    save_prediction: bool = Field(True, description="是否保存预估记录")


class FeedbackRequest(BaseModel):
    """考后反馈请求"""
    prediction_id: int = Field(..., description="预估记录ID")
    actual_average: float = Field(..., description="实际平均分")


# ============ API Endpoints ============

@router.post("/history")
async def create_exam_history(
    request: ExamHistoryCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    上传历史试卷数据

    上传包含实际得分率的历史考试数据，用于训练预估模型
    """
    service = PredictionService(db)

    try:
        exam = await service.create_exam_history(
            name=request.name,
            grade=request.grade,
            total_score=request.total_score,
            questions=[q.model_dump() for q in request.questions],
            exam_date=request.exam_date,
            student_count=request.student_count,
            source_file=request.source_file
        )

        return {
            "success": True,
            "data": {
                "id": exam.id,
                "name": exam.name,
                "grade": exam.grade,
                "total_score": float(exam.total_score),
                "average_score": float(exam.average_score) if exam.average_score else None,
                "score_rate": float(exam.score_rate) if exam.score_rate else None,
                "question_count": len(request.questions)
            },
            "message": "历史数据上传成功，映射模型已更新"
        }
    except Exception as e:
        logger.exception(f"创建历史记录失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/history")
async def list_exam_history(
    grade: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """
    列出历史考试记录

    支持按年级筛选
    """
    service = PredictionService(db)

    try:
        result = await service.list_exam_history(
            grade=grade,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            "data": result['items'],
            "total": result['total']
        }
    except Exception as e:
        logger.exception(f"获取历史记录列表失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/history/{exam_id}")
async def get_exam_history(
    exam_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    获取单份历史数据详情

    包含每道题的详细信息
    """
    service = PredictionService(db)

    try:
        exam = await service.get_exam_history(exam_id)
        if not exam:
            raise HTTPException(status_code=404, detail="历史记录不存在")

        return {
            "success": True,
            "data": {
                "id": exam.id,
                "name": exam.name,
                "exam_date": exam.exam_date.strftime('%Y-%m-%d') if exam.exam_date else None,
                "grade": exam.grade,
                "student_count": exam.student_count,
                "total_score": float(exam.total_score),
                "average_score": float(exam.average_score) if exam.average_score else None,
                "score_rate": float(exam.score_rate) if exam.score_rate else None,
                "difficulty_avg": float(exam.difficulty_avg) if exam.difficulty_avg else None,
                "source_file": exam.source_file,
                "created_at": exam.created_at.isoformat() if exam.created_at else None,
                "questions": [
                    {
                        "id": qp.id,
                        "question_number": qp.question_number,
                        "question_score": float(qp.question_score),
                        "actual_average": float(qp.actual_average) if qp.actual_average else None,
                        "score_rate": float(qp.score_rate) if qp.score_rate else None,
                        "absolute_difficulty": float(qp.absolute_difficulty) if qp.absolute_difficulty else None,
                        "knowledge_complexity": float(qp.knowledge_complexity) if qp.knowledge_complexity else None,
                        "cognitive_level": float(qp.cognitive_level) if qp.cognitive_level else None,
                        "knowledge_points": qp.knowledge_points or [],
                        "textbook_chapter": qp.textbook_chapter,
                        "question_type": qp.question_type,
                        "question_content": qp.question_content
                    }
                    for qp in exam.question_performances
                ]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"获取历史记录详情失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/history/{exam_id}")
async def delete_exam_history(
    exam_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    删除历史考试记录

    删除后会自动重建映射模型
    """
    service = PredictionService(db)

    try:
        success = await service.delete_exam_history(exam_id)
        if not success:
            raise HTTPException(status_code=404, detail="历史记录不存在")

        return {
            "success": True,
            "message": "历史记录已删除，映射模型已更新"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"删除历史记录失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/predict")
async def predict_exam_score(
    request: PredictExamRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    预估新试卷分数

    基于历史数据预估新试卷的平均分和置信区间
    """
    service = PredictionService(db)

    try:
        result = await service.predict_exam_score(
            questions=[q.model_dump() for q in request.questions],
            total_score=request.total_score,
            grade=request.grade,
            exam_name=request.exam_name,
            save_prediction=request.save_prediction
        )

        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.exception(f"分数预估失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    提交考后反馈

    提交实际平均分，用于评估预估准确度
    """
    service = PredictionService(db)

    try:
        result = await service.submit_feedback(
            prediction_id=request.prediction_id,
            actual_average=request.actual_average
        )

        if not result:
            raise HTTPException(status_code=404, detail="预估记录不存在")

        return {
            "success": True,
            "data": result,
            "message": "反馈提交成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"提交反馈失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/stats")
async def get_coverage_stats(
    db: AsyncSession = Depends(get_db)
):
    """
    获取数据覆盖统计

    返回映射覆盖率、历史数据量、预估准确度等统计信息
    """
    service = PredictionService(db)

    try:
        stats = await service.get_coverage_stats()

        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.exception(f"获取统计数据失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/rebuild-mapping")
async def rebuild_mapping(
    grade: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    手动重建映射模型

    可指定年级，不指定则重建所有年级
    """
    service = PredictionService(db)

    try:
        stats = await service.mapper.build_mapping_from_history(grade)

        return {
            "success": True,
            "data": stats,
            "message": f"映射重建完成" + (f" (年级: {grade})" if grade else " (所有年级)")
        }
    except Exception as e:
        logger.exception(f"重建映射失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
