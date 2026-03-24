# -*- coding: utf-8 -*-
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from enum import Enum
import os
import aiofiles

from logger import get_logger
from middleware import RequestIdMiddleware
from config import UPLOAD_DIR, LOG_DIR, PROMPT_DIR, RULES_DIR, REPORTS_DIR
from deps import get_gemini_analyzer, GEMINI_API_KEY
from exceptions import (
    BiologyAnalyzerError,
    ConfigurationError,
    FileProcessingError,
    AnalysisError,
    ValidationError,
    AuthenticationError
)

# 数据库和教材路由（可选加载，数据库不可用时不影响主功能）
try:
    from database import init_db
    from textbook_router import router as textbook_router
    from knowledge_router import router as knowledge_router
    from exercise_router import router as exercise_router
    from auth_router import router as auth_router
    from quiz_router import router as quiz_router
    from prediction_router import router as prediction_router
    DB_AVAILABLE = True
except ImportError as e:
    DB_AVAILABLE = False
    logger_import_error = str(e)

# 分析路由
from analysis_router import router as analysis_router
# 管理后台路由
from admin_router import router as admin_router

# ============ 初始化 ============
logger = get_logger()
app = FastAPI(title="Biology Question Analyzer API")

# ============ 配置常量 ============
# CORS配置 - 从环境变量读取，支持多个来源
_default_origins = "http://127.0.0.1:3000,http://localhost:3000"
_origins_env = os.getenv("ALLOWED_ORIGINS", _default_origins)
ALLOWED_ORIGINS = [origin.strip() for origin in _origins_env.split(",") if origin.strip()]

# 开发环境默认添加本地地址
if os.getenv("ENV", "development") == "development":
    dev_origins = [
        "http://127.0.0.1", "http://127.0.0.1:80", "http://127.0.0.1:3000",
        "http://localhost", "http://localhost:80", "http://localhost:3000",
    ]
    ALLOWED_ORIGINS = list(set(ALLOWED_ORIGINS + dev_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.add_middleware(RequestIdMiddleware)


# ============ 全局异常处理器 ============

@app.exception_handler(BiologyAnalyzerError)
async def biology_analyzer_error_handler(request: Request, exc: BiologyAnalyzerError):
    """处理所有自定义业务异常"""
    logger.error(f"业务异常: {exc.code} - {exc.message}", extra={"details": exc.details})
    return JSONResponse(
        status_code=400,
        content=exc.to_dict()
    )


@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    """处理认证异常"""
    logger.warning(f"认证失败: {exc.message}")
    return JSONResponse(
        status_code=401,
        content=exc.to_dict()
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """处理验证异常"""
    logger.warning(f"输入验证失败: {exc.message}")
    return JSONResponse(
        status_code=422,
        content=exc.to_dict()
    )


# ============ Pydantic Models ============

class QuestionCorrection(BaseModel):
    """人工修正的题目数据"""
    questions: List[Dict[str, Any]]


# ============ 注册路由 ============

# 分析路由（/api/analyze, /api/analyze_auto, /api/analyze/auto_split 等）
app.include_router(analysis_router)
logger.info("[主模块] 分析路由已注册")

# 管理后台路由（/api/admin/*, /api/reports/*, /uploads/*）
app.include_router(admin_router)
logger.info("[主模块] 管理后台路由已注册")

# 注册教材管理路由（如果数据库可用）
if DB_AVAILABLE:
    app.include_router(textbook_router)
    app.include_router(knowledge_router)
    app.include_router(exercise_router)
    app.include_router(auth_router)
    app.include_router(quiz_router)
    app.include_router(prediction_router)
    logger.info("[主模块] 教材管理路由已注册")
    logger.info("[主模块] 知识库路由已注册")
    logger.info("[主模块] 题库路由已注册")
    logger.info("[主模块] 认证路由已注册")
    logger.info("[主模块] 测验生成路由已注册")
    logger.info("[主模块] 分数预估路由已注册")
else:
    logger.warning(f"[主模块] 数据库模块未加载: {logger_import_error}")


# ============ 健康检查 ============

@app.get("/health")
async def health_check():
    """健康检查接口（含数据库连通性）"""
    db_ok = False
    try:
        from sqlalchemy import text
        from database import get_db_session
        session = await get_db_session()
        try:
            await session.execute(text("SELECT 1"))
            db_ok = True
        finally:
            await session.close()
    except Exception:
        pass

    status = "healthy" if db_ok else "degraded"
    return {
        "status": status,
        "timestamp": datetime.now().isoformat(),
        "gemini_configured": bool(GEMINI_API_KEY),
        "database": "ok" if db_ok else "unreachable"
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("启动开发服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
