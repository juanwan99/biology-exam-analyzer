"""
题库管理API路由
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Header, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_, Integer, cast, text, delete
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
import os

from database import get_db
from models import ExerciseBank, ExerciseSource
from logger import get_logger
from auth_router import require_auth, log_operation

logger = get_logger()

router = APIRouter(prefix="/api/exercises", tags=["题库管理"])


# ============ Pydantic Models ============

class ExerciseListResponse(BaseModel):
    """题目列表响应"""
    items: List[Dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


class ExerciseFilterParams(BaseModel):
    """题目筛选参数"""
    question_type: Optional[str] = None
    year: Optional[int] = None
    source_type: Optional[str] = None
    difficulty_min: Optional[float] = None
    difficulty_max: Optional[float] = None
    tags: Optional[List[str]] = None
    keyword: Optional[str] = None


class SourceListResponse(BaseModel):
    """来源列表响应"""
    items: List[Dict[str, Any]]
    total: int


class ExerciseCreate(BaseModel):
    """创建题目请求"""
    question_type: str = Field(..., description="题型")
    content: str = Field(..., description="题目内容")
    options: Optional[Dict[str, str]] = Field(None, description="选项")
    answer: str = Field(..., description="答案")
    explanation: Optional[str] = Field(None, description="解析")
    difficulty_level: Optional[float] = Field(None, ge=0, le=1, description="难度")
    tags: Optional[List[str]] = Field(None, description="标签")
    source_id: Optional[int] = Field(None, description="来源ID")
    year: Optional[int] = Field(None, description="年份")
    exam_source: Optional[str] = Field(None, description="考试来源")
    question_number: Optional[int] = Field(None, description="题号")


class ExerciseUpdate(BaseModel):
    """更新题目请求"""
    question_type: Optional[str] = None
    content: Optional[str] = None
    options: Optional[Dict[str, str]] = None
    answer: Optional[str] = None
    explanation: Optional[str] = None
    difficulty_level: Optional[float] = Field(None, ge=0, le=1)
    tags: Optional[List[str]] = None
    source_id: Optional[int] = None
    year: Optional[int] = None
    exam_source: Optional[str] = None
    question_number: Optional[int] = None


class SourceCreate(BaseModel):
    """创建来源请求"""
    name: str = Field(..., description="来源名称")
    source_type: str = Field(..., description="来源类型（高考/模拟/教辅）")
    year: Optional[int] = Field(None, description="年份")
    region: Optional[str] = Field(None, description="地区")
    description: Optional[str] = Field(None, description="描述")


class SourceUpdate(BaseModel):
    """更新来源请求"""
    name: Optional[str] = None
    source_type: Optional[str] = None
    year: Optional[int] = None
    region: Optional[str] = None
    description: Optional[str] = None


# ============ API Endpoints ============

@router.get("/list", response_model=ExerciseListResponse)
async def list_exercises(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    question_type: Optional[str] = Query(None, description="题型筛选"),
    year: Optional[int] = Query(None, description="年份筛选"),
    source_type: Optional[str] = Query(None, description="来源类型"),
    difficulty_min: Optional[float] = Query(None, ge=0, le=1, description="最低难度"),
    difficulty_max: Optional[float] = Query(None, ge=0, le=1, description="最高难度"),
    tag: Optional[str] = Query(None, description="标签筛选"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    db: AsyncSession = Depends(get_db)
):
    """
    获取题目列表（分页）

    支持多维度筛选：
    - question_type: 题型（单选题/多选题/填空题/简答题）
    - year: 年份
    - source_type: 来源类型（高考/模拟/教辅）
    - difficulty_min/max: 难度范围（0-1）
    - tag: 标签
    - keyword: 关键词（搜索题目内容）
    """
    logger.info(f"[题库] 查询列表: page={page}, page_size={page_size}")

    try:
        # 构建基础查询
        query = select(ExerciseBank).options(joinedload(ExerciseBank.source))
        count_query = select(func.count(ExerciseBank.id))

        # 应用筛选条件
        filters = []

        if question_type:
            filters.append(ExerciseBank.question_type == question_type)

        if year:
            # 使用 PostgreSQL 的 JSON 操作符 ->>
            filters.append(text(f"competency_scores->>'year' = '{year}'"))

        if difficulty_min is not None:
            filters.append(ExerciseBank.difficulty_level >= difficulty_min)

        if difficulty_max is not None:
            filters.append(ExerciseBank.difficulty_level <= difficulty_max)

        if tag:
            filters.append(ExerciseBank.tags.any(tag))

        if keyword:
            filters.append(ExerciseBank.content.ilike(f"%{keyword}%"))

        if source_type:
            # 需要 join 来源表
            query = query.join(ExerciseSource)
            count_query = count_query.join(ExerciseSource)
            filters.append(ExerciseSource.source_type == source_type)

        # 应用所有筛选条件
        if filters:
            query = query.filter(and_(*filters))
            count_query = count_query.filter(and_(*filters))

        # 获取总数
        result = await db.execute(count_query)
        total = result.scalar()

        # 分页
        offset = (page - 1) * page_size
        query = query.order_by(ExerciseBank.id.desc()).offset(offset).limit(page_size)

        result = await db.execute(query)
        exercises = result.scalars().unique().all()

        # 格式化响应
        items = []
        for ex in exercises:
            # 从 competency_scores 中提取额外信息
            extra = ex.competency_scores or {}
            items.append({
                "id": ex.id,
                "question_type": ex.question_type,
                "content": ex.content,
                "options": ex.options,
                "answer": ex.answer,
                "explanation": ex.explanation,
                "difficulty_level": float(ex.difficulty_level) if ex.difficulty_level else None,
                "tags": ex.tags or [],
                "year": extra.get("year"),
                "exam_source": extra.get("exam_source"),
                "question_number": extra.get("question_number"),
                "images": extra.get("images", []),
                "table_html": extra.get("table_html"),
                "source_name": ex.source.name if ex.source else None,
                "source_type": ex.source.source_type if ex.source else None,
                "created_at": ex.created_at.isoformat() if ex.created_at else None
            })

        total_pages = (total + page_size - 1) // page_size

        logger.info(f"[题库] 返回 {len(items)} 道题，共 {total} 道")

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }

    except Exception as e:
        logger.error(f"[题库] 查询失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.get("/detail/{exercise_id}")
async def get_exercise_detail(
    exercise_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取题目详情"""
    logger.info(f"[题库] 获取详情: id={exercise_id}")

    try:
        result = await db.execute(
            select(ExerciseBank)
            .options(joinedload(ExerciseBank.source))
            .filter(ExerciseBank.id == exercise_id)
        )
        exercise = result.scalar_one_or_none()

        if not exercise:
            raise HTTPException(404, detail="题目不存在")

        extra = exercise.competency_scores or {}

        return {
            "id": exercise.id,
            "question_type": exercise.question_type,
            "content": exercise.content,
            "options": exercise.options,
            "answer": exercise.answer,
            "explanation": exercise.explanation,
            "difficulty_level": float(exercise.difficulty_level) if exercise.difficulty_level else None,
            "tags": exercise.tags or [],
            "year": extra.get("year"),
            "exam_source": extra.get("exam_source"),
            "question_number": extra.get("question_number"),
            "images": extra.get("images", []),
            "table_index": extra.get("table_index"),
            "table_html": extra.get("table_html"),
            "table_markdown": extra.get("table_markdown"),
            "source": {
                "id": exercise.source.id,
                "name": exercise.source.name,
                "source_type": exercise.source.source_type,
                "year": exercise.source.year,
                "region": exercise.source.region
            } if exercise.source else None,
            "usage_count": exercise.usage_count,
            "created_at": exercise.created_at.isoformat() if exercise.created_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[题库] 获取详情失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.get("/sources")
async def list_sources(
    db: AsyncSession = Depends(get_db)
):
    """获取所有题目来源列表"""
    logger.info("[题库] 获取来源列表")

    try:
        result = await db.execute(
            select(
                ExerciseSource,
                func.count(ExerciseBank.id).label("exercise_count")
            )
            .outerjoin(ExerciseBank)
            .group_by(ExerciseSource.id)
            .order_by(ExerciseSource.year.desc(), ExerciseSource.name)
        )

        sources = result.all()

        items = []
        for source, count in sources:
            items.append({
                "id": source.id,
                "name": source.name,
                "source_type": source.source_type,
                "year": source.year,
                "region": source.region,
                "description": source.description,
                "exercise_count": count
            })

        return {
            "items": items,
            "total": len(items)
        }

    except Exception as e:
        logger.error(f"[题库] 获取来源列表失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.get("/statistics")
async def get_statistics(
    db: AsyncSession = Depends(get_db)
):
    """获取题库统计信息"""
    logger.info("[题库] 获取统计信息")

    try:
        # 总题数
        result = await db.execute(select(func.count(ExerciseBank.id)))
        total_count = result.scalar()

        # 按题型统计
        result = await db.execute(
            select(
                ExerciseBank.question_type,
                func.count(ExerciseBank.id)
            ).group_by(ExerciseBank.question_type)
        )
        type_distribution = {row[0]: row[1] for row in result.all()}

        # 按年份统计（使用原生SQL提取JSON字段）
        result = await db.execute(
            text("""
                SELECT competency_scores->>'year' as year, COUNT(*) as count
                FROM exercise_bank
                WHERE competency_scores->>'year' IS NOT NULL
                GROUP BY competency_scores->>'year'
                ORDER BY competency_scores->>'year' DESC
            """)
        )
        year_distribution = {int(row[0]): row[1] for row in result.all() if row[0]}

        # 来源数量
        result = await db.execute(select(func.count(ExerciseSource.id)))
        source_count = result.scalar()

        # 标签统计（取前20个常用标签）
        result = await db.execute(
            select(func.unnest(ExerciseBank.tags).label("tag"))
        )
        all_tags = [row[0] for row in result.all() if row[0]]
        tag_counts = {}
        for tag in all_tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]

        return {
            "total_count": total_count,
            "source_count": source_count,
            "type_distribution": type_distribution,
            "year_distribution": year_distribution,
            "top_tags": [{"name": t[0], "count": t[1]} for t in top_tags]
        }

    except Exception as e:
        logger.error(f"[题库] 获取统计信息失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.get("/random")
async def get_random_exercises(
    count: int = Query(5, ge=1, le=50, description="随机题目数量"),
    question_type: Optional[str] = Query(None, description="题型筛选"),
    db: AsyncSession = Depends(get_db)
):
    """随机获取题目（用于练习功能）"""
    logger.info(f"[题库] 随机获取 {count} 道题")

    try:
        query = select(ExerciseBank).options(joinedload(ExerciseBank.source))

        if question_type:
            query = query.filter(ExerciseBank.question_type == question_type)

        # 随机排序
        query = query.order_by(func.random()).limit(count)

        result = await db.execute(query)
        exercises = result.scalars().unique().all()

        items = []
        for ex in exercises:
            extra = ex.competency_scores or {}
            items.append({
                "id": ex.id,
                "question_type": ex.question_type,
                "content": ex.content,
                "options": ex.options,
                "answer": ex.answer,
                "explanation": ex.explanation,
                "difficulty_level": float(ex.difficulty_level) if ex.difficulty_level else None,
                "tags": ex.tags or [],
                "year": extra.get("year"),
                "exam_source": extra.get("exam_source"),
                "images": extra.get("images", []),
                "source_name": ex.source.name if ex.source else None
            })

        return {"items": items, "count": len(items)}

    except Exception as e:
        logger.error(f"[题库] 随机获取失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


# ============ CRUD Endpoints (Admin) ============

@router.post("/create")
async def create_exercise(
    request: Request,
    data: ExerciseCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """创建新题目（需要登录）"""
    logger.info(f"[题库] {user['username']} 创建题目: {data.question_type}")

    try:
        # 构建 competency_scores 存储额外信息
        competency_scores = {}
        if data.year:
            competency_scores["year"] = data.year
        if data.exam_source:
            competency_scores["exam_source"] = data.exam_source
        if data.question_number:
            competency_scores["question_number"] = data.question_number

        exercise = ExerciseBank(
            question_type=data.question_type,
            content=data.content,
            options=data.options,
            answer=data.answer,
            explanation=data.explanation,
            difficulty_level=data.difficulty_level,
            tags=data.tags or [],
            source_id=data.source_id,
            competency_scores=competency_scores if competency_scores else None
        )

        db.add(exercise)
        await db.commit()
        await db.refresh(exercise)

        # 记录操作日志
        await log_operation(
            db, user, "create", "exercise",
            target_id=exercise.id,
            target_name=data.content[:50] + "..." if len(data.content) > 50 else data.content,
            new_value={"question_type": data.question_type, "content": data.content[:100]},
            ip_address=request.client.host if request.client else None
        )

        logger.info(f"[题库] 创建成功: id={exercise.id}")
        return {"success": True, "id": exercise.id, "message": "题目创建成功"}

    except Exception as e:
        await db.rollback()
        logger.error(f"[题库] 创建失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.put("/update/{exercise_id}")
async def update_exercise(
    exercise_id: int,
    request: Request,
    data: ExerciseUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """更新题目（需要登录）"""
    logger.info(f"[题库] {user['username']} 更新题目: id={exercise_id}")

    try:
        result = await db.execute(
            select(ExerciseBank).filter(ExerciseBank.id == exercise_id)
        )
        exercise = result.scalar_one_or_none()

        if not exercise:
            raise HTTPException(404, detail="题目不存在")

        # 保存旧值
        old_value = {
            "question_type": exercise.question_type,
            "content": exercise.content[:100] if exercise.content else None,
            "answer": exercise.answer
        }

        # 更新字段
        update_data = data.model_dump(exclude_unset=True)

        # 处理 competency_scores 中的额外字段
        extra_fields = ["year", "exam_source", "question_number"]
        competency_updates = {}
        for field in extra_fields:
            if field in update_data:
                competency_updates[field] = update_data.pop(field)

        if competency_updates:
            current_scores = exercise.competency_scores or {}
            current_scores.update(competency_updates)
            exercise.competency_scores = current_scores

        # 更新其他字段
        for key, value in update_data.items():
            if hasattr(exercise, key):
                setattr(exercise, key, value)

        await db.commit()

        # 记录操作日志
        await log_operation(
            db, user, "update", "exercise",
            target_id=exercise_id,
            target_name=exercise.content[:50] + "..." if exercise.content and len(exercise.content) > 50 else exercise.content,
            old_value=old_value,
            new_value=data.model_dump(exclude_unset=True),
            ip_address=request.client.host if request.client else None
        )

        logger.info(f"[题库] 更新成功: id={exercise_id}")
        return {"success": True, "message": "题目更新成功"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[题库] 更新失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.delete("/delete/{exercise_id}")
async def delete_exercise(
    exercise_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """删除题目（需要登录）"""
    logger.info(f"[题库] {user['username']} 删除题目: id={exercise_id}")

    try:
        result = await db.execute(
            select(ExerciseBank).filter(ExerciseBank.id == exercise_id)
        )
        exercise = result.scalar_one_or_none()

        if not exercise:
            raise HTTPException(404, detail="题目不存在")

        target_name = exercise.content[:50] + "..." if exercise.content and len(exercise.content) > 50 else exercise.content
        old_value = {"question_type": exercise.question_type, "content": exercise.content[:100] if exercise.content else None}

        await db.delete(exercise)
        await db.commit()

        # 记录操作日志
        await log_operation(
            db, user, "delete", "exercise",
            target_id=exercise_id,
            target_name=target_name,
            old_value=old_value,
            ip_address=request.client.host if request.client else None
        )

        logger.info(f"[题库] 删除成功: id={exercise_id}")
        return {"success": True, "message": "题目删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[题库] 删除失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.post("/batch-delete")
async def batch_delete_exercises(
    request: Request,
    ids: List[int],
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """批量删除题目（需要登录）"""
    logger.info(f"[题库] {user['username']} 批量删除: {len(ids)} 道题")

    try:
        # 先获取题目信息用于日志
        result = await db.execute(
            select(ExerciseBank).filter(ExerciseBank.id.in_(ids))
        )
        exercises = result.scalars().all()
        exercise_info = [{"id": ex.id, "content": ex.content[:30] if ex.content else ""} for ex in exercises]

        result = await db.execute(
            delete(ExerciseBank).where(ExerciseBank.id.in_(ids))
        )
        await db.commit()

        deleted_count = result.rowcount

        # 记录操作日志
        await log_operation(
            db, user, "batch_delete", "exercise",
            target_name=f"批量删除 {deleted_count} 道题",
            old_value={"deleted_ids": ids, "exercises": exercise_info},
            ip_address=request.client.host if request.client else None
        )

        logger.info(f"[题库] 批量删除成功: {deleted_count} 道")
        return {"success": True, "deleted_count": deleted_count, "message": f"成功删除 {deleted_count} 道题"}

    except Exception as e:
        await db.rollback()
        logger.error(f"[题库] 批量删除失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


# ============ Source CRUD Endpoints ============

@router.post("/sources/create")
async def create_source(
    request: Request,
    data: SourceCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """创建题目来源（需要登录）"""
    logger.info(f"[题库] {user['username']} 创建来源: {data.name}")

    try:
        source = ExerciseSource(
            name=data.name,
            source_type=data.source_type,
            year=data.year,
            region=data.region,
            description=data.description
        )

        db.add(source)
        await db.commit()
        await db.refresh(source)

        # 记录操作日志
        await log_operation(
            db, user, "create", "source",
            target_id=source.id,
            target_name=data.name,
            new_value={"name": data.name, "source_type": data.source_type, "year": data.year},
            ip_address=request.client.host if request.client else None
        )

        logger.info(f"[题库] 来源创建成功: id={source.id}")
        return {"success": True, "id": source.id, "message": "来源创建成功"}

    except Exception as e:
        await db.rollback()
        logger.error(f"[题库] 来源创建失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.put("/sources/update/{source_id}")
async def update_source(
    source_id: int,
    request: Request,
    data: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """更新题目来源（需要登录）"""
    logger.info(f"[题库] {user['username']} 更新来源: id={source_id}")

    try:
        result = await db.execute(
            select(ExerciseSource).filter(ExerciseSource.id == source_id)
        )
        source = result.scalar_one_or_none()

        if not source:
            raise HTTPException(404, detail="来源不存在")

        # 保存旧值
        old_value = {"name": source.name, "source_type": source.source_type, "year": source.year}

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if hasattr(source, key):
                setattr(source, key, value)

        await db.commit()

        # 记录操作日志
        await log_operation(
            db, user, "update", "source",
            target_id=source_id,
            target_name=source.name,
            old_value=old_value,
            new_value=update_data,
            ip_address=request.client.host if request.client else None
        )

        logger.info(f"[题库] 来源更新成功: id={source_id}")
        return {"success": True, "message": "来源更新成功"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[题库] 来源更新失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")


@router.delete("/sources/delete/{source_id}")
async def delete_source(
    source_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """删除题目来源（需要登录）"""
    logger.info(f"[题库] {user['username']} 删除来源: id={source_id}")

    try:
        # 检查是否有关联的题目
        result = await db.execute(
            select(func.count(ExerciseBank.id)).filter(ExerciseBank.source_id == source_id)
        )
        exercise_count = result.scalar()

        if exercise_count > 0:
            raise HTTPException(400, detail=f"该来源下有 {exercise_count} 道题目，无法删除")

        result = await db.execute(
            select(ExerciseSource).filter(ExerciseSource.id == source_id)
        )
        source = result.scalar_one_or_none()

        if not source:
            raise HTTPException(404, detail="来源不存在")

        source_name = source.name
        old_value = {"name": source.name, "source_type": source.source_type, "year": source.year}

        await db.delete(source)
        await db.commit()

        # 记录操作日志
        await log_operation(
            db, user, "delete", "source",
            target_id=source_id,
            target_name=source_name,
            old_value=old_value,
            ip_address=request.client.host if request.client else None
        )

        logger.info(f"[题库] 来源删除成功: id={source_id}")
        return {"success": True, "message": "来源删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[题库] 来源删除失败: {str(e)}")
        raise HTTPException(500, detail="服务器内部错误")
