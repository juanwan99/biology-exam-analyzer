# -*- coding: utf-8 -*-
"""
管理后台路由模块

从 main.py 提取的管理、报告和静态资源端点：
- GET  /api/admin/prompts           — 获取 Prompt 配置
- PUT  /api/admin/prompts           — 更新 Prompt（热生效）
- GET  /api/admin/logs              — 获取日志内容
- GET  /api/admin/logs/download/{d} — 下载日志文件
- GET  /api/admin/logs/list         — 列出所有日志文件
- GET  /api/reports/{filename}      — 下载 PDF / 查看 HTML 报告
- GET  /uploads/{path:path}         — 静态上传文件访问
"""
import hmac
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum

import aiofiles
from fastapi import APIRouter, HTTPException, Header, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from logger import get_logger
from config import LOG_DIR, PROMPT_DIR, REPORTS_DIR, UPLOAD_DIR

logger = get_logger()

router = APIRouter()

# ============ 安全配置 ============

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    logger.warning("警告: 未设置 ADMIN_PASSWORD 环境变量，管理功能将不可用")


# ============ Pydantic Models ============

class PromptType(str, Enum):
    """Prompt类型"""
    SPLIT = "split"
    ANALYSIS = "analysis"
    COMPETENCY = "competency"
    DIFFICULTY_REFINE = "difficulty_refine"


class PromptUpdate(BaseModel):
    """Prompt更新请求"""
    type: PromptType  # 使用枚举验证
    content: str


# ============ 认证依赖 ============

def verify_admin(password: Optional[str] = Header(None, alias="X-Admin-Password")):
    """验证管理员密码（timing-safe 比较，防时序攻击）"""
    if not password or not ADMIN_PASSWORD:
        logger.warning("管理员认证失败（密码为空）")
        raise HTTPException(status_code=401, detail="Invalid admin password")
    if not hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode()):
        logger.warning("管理员认证失败（密码错误）")
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return True


# ============ 管理后台API ============

@router.get("/api/admin/prompts")
async def get_prompts(admin_ok=Depends(verify_admin)):
    """获取当前Prompt配置"""
    logger.info("管理员获取Prompt配置")
    prompts = {}

    for prompt_type in ["split", "analysis"]:
        prompt_file = PROMPT_DIR / f"{prompt_type}_prompt.txt"
        if prompt_file.exists():
            async with aiofiles.open(prompt_file, 'r', encoding='utf-8') as f:
                prompts[prompt_type] = await f.read()
        else:
            prompts[prompt_type] = ""

    return prompts


@router.put("/api/admin/prompts")
async def update_prompt(
    data: PromptUpdate,
    admin_ok=Depends(verify_admin)
):
    """更新Prompt（热生效）"""
    logger.info(f"管理员更新Prompt类型: {data.type}")

    if data.type not in ["split", "analysis"]:
        raise HTTPException(400, "type必须为split或analysis")

    prompt_file = PROMPT_DIR / f"{data.type}_prompt.txt"
    async with aiofiles.open(prompt_file, 'w', encoding='utf-8') as f:
        await f.write(data.content)

    logger.info(f"Prompt已更新: {prompt_file}")
    return {"message": "更新成功", "file": str(prompt_file)}


@router.get("/api/admin/logs")
async def get_logs(
    date: Optional[str] = None,
    admin_ok=Depends(verify_admin)
):
    """获取日志内容"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')

    log_file = LOG_DIR / f"{date}.log"
    if not log_file.exists():
        raise HTTPException(404, f"日志文件不存在: {date}.log")

    async with aiofiles.open(log_file, 'r', encoding='utf-8') as f:
        content = await f.read()

    return {"date": date, "content": content}


@router.get("/api/admin/logs/download/{date}")
async def download_log(
    date: str,
    admin_ok=Depends(verify_admin)
):
    """下载日志文件"""
    log_file = LOG_DIR / f"{date}.log"
    if not log_file.exists():
        raise HTTPException(404, "日志文件不存在")

    return FileResponse(
        log_file,
        media_type='text/plain',
        filename=f"biology_analyzer_{date}.log"
    )


@router.get("/api/admin/logs/list")
async def list_logs(admin_ok=Depends(verify_admin)):
    """列出所有日志文件"""
    log_files = sorted(LOG_DIR.glob("*.log"), reverse=True)
    return {
        "logs": [
            {
                "date": f.stem,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            }
            for f in log_files
        ]
    }


# ============ Token 统计 API ============

@router.get("/api/admin/token-stats")
async def get_token_stats_api(admin_ok=Depends(verify_admin)):
    from llm_client import get_token_stats
    return {"providers": [{"name": k, **v} for k, v in get_token_stats().items()]}


# ============ 校准 API ============

@router.get("/api/admin/calibration")
async def get_calibration_api(admin_ok=Depends(verify_admin)):
    """获取当前校准状态"""
    from calibration_service import get_calibration_status
    return get_calibration_status()


@router.post("/api/admin/calibration/run")
async def run_calibration_api(admin_ok=Depends(verify_admin)):
    """执行校准分析"""
    from calibration_service import collect_data_from_db, analyze
    from database import async_session
    async with async_session() as session:
        pairs = await collect_data_from_db(session)
    result = analyze(pairs)
    return result


# ============ 报告下载 API ============

@router.get("/api/reports/{filename}")
async def download_report(filename: str):
    """
    下载生成的 PDF 报告或查看 HTML 报告

    Args:
        filename: 报告文件名（如: 20251019_143022.pdf / .html）

    Returns:
        报告文件响应
    """
    logger.info(f"请求下载报告: {filename}")

    # 安全检查：Path.resolve() + 基目录校验
    report_base = REPORTS_DIR.resolve()
    report_path = (report_base / filename).resolve()
    if not str(report_path).startswith(str(report_base)):
        logger.warning(f"路径穿越尝试: {filename} -> {report_path}")
        raise HTTPException(400, "非法文件名")

    if not report_path.exists():
        logger.warning(f"报告文件不存在: {report_path}")
        raise HTTPException(404, "报告文件不存在")

    suffix = report_path.suffix.lower()
    if suffix not in {".pdf", ".html"}:
        raise HTTPException(400, "不支持的报告类型")

    logger.info(f"返回报告文件: {report_path}")
    if suffix == ".html":
        return FileResponse(
            report_path,
            media_type='text/html; charset=utf-8',
            filename=filename,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
            }
        )

    return FileResponse(
        report_path,
        media_type='application/pdf',
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        }
    )


# ============ 静态资源访问 ============

@router.get("/uploads/{path:path}")
async def serve_uploads(path: str):
    """
    提供上传文件的访问（图片、表格等）

    安全检查：Path.resolve() + 基目录白名单校验
    """
    UPLOADS_BASE = UPLOAD_DIR.resolve()
    file_path = (UPLOADS_BASE / path).resolve()

    # 安全检查：resolve 后必须仍在基目录下（防 URL 编码绕过）
    if not str(file_path).startswith(str(UPLOADS_BASE)):
        logger.warning(f"路径穿越尝试: {path} -> {file_path}")
        raise HTTPException(400, "非法路径")

    if not file_path.exists():
        raise HTTPException(404, "文件不存在")

    if not file_path.is_file():
        raise HTTPException(400, "非法请求")

    # 确定 MIME 类型
    suffix = file_path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".pdf": "application/pdf"
    }
    mime_type = mime_types.get(suffix, "application/octet-stream")

    return FileResponse(file_path, media_type=mime_type)


@router.post("/api/feedback/score-rate")
async def submit_score_rate(request: Request, admin_ok=Depends(verify_admin)):
    """P5a: 教师回填题目实际得分率。"""
    from database import get_async_session
    from models import QuestionPerformance, ExamHistory
    from sqlalchemy import select

    data = await request.json()
    exam_id = data.get("exam_id")
    feedbacks = data.get("feedbacks", [])

    if not exam_id or not feedbacks:
        raise HTTPException(400, detail="需要 exam_id 和 feedbacks 数组")

    async with get_async_session() as session:
        exam = await session.get(ExamHistory, exam_id)
        if not exam:
            raise HTTPException(404, detail=f"考试 {exam_id} 不存在")

        updated = 0
        for fb in feedbacks:
            qn = fb.get("question_number")
            sr = fb.get("score_rate")
            if qn is None or sr is None:
                continue

            stmt = select(QuestionPerformance).where(
                QuestionPerformance.exam_id == exam_id,
                QuestionPerformance.question_number == qn
            )
            result = await session.execute(stmt)
            qp = result.scalar_one_or_none()

            if qp:
                qp.score_rate = sr
                if fb.get("predicted_difficulty") is not None:
                    qp.absolute_difficulty = fb["predicted_difficulty"]
            else:
                qp = QuestionPerformance(
                    exam_id=exam_id,
                    question_number=qn,
                    question_score=fb.get("total_score", 0),
                    score_rate=sr,
                    absolute_difficulty=fb.get("predicted_difficulty"),
                )
                session.add(qp)
            updated += 1

        await session.commit()

    logger.info(f"[P5] 得分率回填: exam_id={exam_id}, {updated} 题")

    # F-03: 回填后自动触发校准更新
    try:
        from calibration_service import collect_data_from_db, analyze
        async with get_async_session() as cal_session:
            pairs = await collect_data_from_db(cal_session)
        if len(pairs) >= 10:
            analyze(pairs)
            logger.info(f"[P5] 校准自动更新: {len(pairs)} 样本")
    except Exception as e:
        logger.warning(f"[P5] 校准更新失败（不影响回填）: {e}")

    return {"success": True, "updated": updated}
