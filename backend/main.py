# -*- coding: utf-8 -*-
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
import os
import json
import re
import aiofiles
import base64
import time

from logger import get_logger
from config import UPLOAD_DIR, LOG_DIR, PROMPT_DIR, RULES_DIR, REPORTS_DIR
from document_processor import DocumentProcessor
from gemini_analyzer import GeminiAnalyzer
from difficulty_pipeline import DifficultyPipeline
from competency_analyzer import CompetencyAnalyzer
from knowledge_mapper import KnowledgeMapper
from report_generator import ReportGenerator
from rule_splitter import RuleSplitter
from word_splitter import WordQuestionSplitter
from pdf_splitter import PDFQuestionSplitter  # PDF拆分器
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

# ============ 初始化 ============
logger = get_logger()
app = FastAPI(title="Biology Question Analyzer API")

# ============ 配置常量 ============
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "21"))  # 并发线程数
API_REQUEST_INTERVAL = float(os.getenv("API_REQUEST_INTERVAL", "0.2"))  # API请求间隔（秒）
SESSION_EXPIRE_MINUTES = int(os.getenv("SESSION_EXPIRE_MINUTES", "30"))  # Session过期时间

# 安全配置：管理员密码必须通过环境变量设置
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    logger.warning("警告: 未设置 ADMIN_PASSWORD 环境变量，管理功能将不可用")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_BASE = os.getenv("GEMINI_API_BASE")

# 路径配置从 config 模块导入（已在顶部导入）

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
    allow_headers=["*"],
)


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


# 目录已在 config 模块中创建

# 初始化组件
if not GEMINI_API_KEY:
    logger.error("未配置GEMINI_API_KEY环境变量！")
    raise RuntimeError("Missing GEMINI_API_KEY")

gemini_analyzer = GeminiAnalyzer(GEMINI_API_KEY, api_base=GEMINI_API_BASE)
doc_processor = DocumentProcessor()
difficulty_engine = DifficultyPipeline()
competency_analyzer = CompetencyAnalyzer(gemini_analyzer=gemini_analyzer)
knowledge_mapper = KnowledgeMapper()
report_generator = ReportGenerator()
rule_splitter = RuleSplitter()
word_splitter = WordQuestionSplitter()
pdf_splitter = PDFQuestionSplitter()  # PDF拆分器

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

# Session存储
SESSION_STORAGE = OrderedDict()
SESSION_EXPIRE_TIME = timedelta(minutes=SESSION_EXPIRE_MINUTES)


# ============ 枚举类型定义 ============

class AnalysisMode(str, Enum):
    """分析模式"""
    FAST = "fast"    # 快速模式：仅规则引擎
    DEEP = "deep"    # 深度模式：规则引擎 + LLM精调


class PromptType(str, Enum):
    """Prompt类型"""
    SPLIT = "split"
    ANALYSIS = "analysis"
    COMPETENCY = "competency"
    DIFFICULTY_REFINE = "difficulty_refine"


# ============ Pydantic Models ============

class AnalyzeResponse(BaseModel):
    """分析结果响应"""
    questions: List[Dict[str, Any]]
    total_count: int
    processing_time: float


class PromptUpdate(BaseModel):
    """Prompt更新请求"""
    type: PromptType  # 使用枚举验证
    content: str


class QuestionCorrection(BaseModel):
    """人工修正的题目数据"""
    questions: List[Dict[str, Any]]


# ============ 辅助函数 ============

def clean_expired_sessions():
    """清理过期的session"""
    current_time = datetime.now()
    expired_keys = [
        k for k, v in SESSION_STORAGE.items()
        if v["expire_time"] < current_time
    ]
    for key in expired_keys:
        del SESSION_STORAGE[key]
        logger.debug(f"清理过期session: {key}")


def save_session(session_id: str, data: Dict[str, Any]) -> None:
    """保存session数据"""
    clean_expired_sessions()
    SESSION_STORAGE[session_id] = {
        "data": data,
        "expire_time": datetime.now() + SESSION_EXPIRE_TIME
    }
    logger.info(f"保存session: {session_id}")


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """获取session数据"""
    clean_expired_sessions()
    session = SESSION_STORAGE.get(session_id)
    if session:
        return session["data"]
    return None


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


def analyze_question_full(
    question: Dict[str, Any],
    image_bytes: List[bytes],
    mode: str = "deep"
) -> Dict[str, Any]:
    """
    完整分析单道题目（分析 + 难度 + 素养 一次完成）

    Args:
        question: 题目数据
        image_bytes: 文档图片列表
        mode: 评估模式（fast/deep）

    Returns:
        包含 analysis, difficulty, competency 的完整题目数据
    """
    q_id = question.get("id", 0)

    try:
        # 步骤0：题型推断
        question_type = infer_question_type(question)
        question["question_type"] = question_type
        section_header = question.get("_section_header")

        # 准备图片数据
        q_image_indices = question.get("image_indices", [])
        q_images = [image_bytes[i] for i in q_image_indices if i < len(image_bytes)]

        # 如果有 _media_for_ai 字段（Word拆分模式），使用它
        media_for_ai = question.get("_media_for_ai", [])
        if media_for_ai:
            q_images = []
            for media_item in media_for_ai:
                try:
                    if media_item.get("type") in ["image", "table"]:
                        base64_str = media_item.get("base64", "")
                        if base64_str:
                            q_images.append(base64.b64decode(base64_str))
                except Exception as e:
                    logger.warning(f"[分析] 题目{q_id} 媒体解码失败: {str(e)}")

        # 步骤1：Gemini题目分析
        logger.info(f"[分析] 题目{q_id} 开始Gemini分析")
        analysis = gemini_analyzer.analyze_question(
            question_text=question.get("content", ""),
            question_images=q_images,
            question_id=q_id,
            question_type=question_type,
            section_header=section_header
        )
        question["analysis"] = analysis

        # 步骤2：难度评估
        logger.info(f"[分析] 题目{q_id} 开始难度评估")
        # q_images 已在上方提取（含 _media_for_ai 和 image_indices）
        q_image_b64 = ""
        if q_images:
            import base64 as _b64
            q_image_b64 = _b64.b64encode(q_images[0]).decode("utf-8")
        difficulty_result = difficulty_engine.evaluate_with_refinement_sync(
            question={
                "id": q_id,
                "content": question.get("content", ""),
                "knowledge_points": analysis.get("knowledge_points", []),
                "total_score": analysis.get("total_score", question.get("total_score", 0)),
                "num_options": analysis.get("num_options", 4),
                "question_type": question_type,
                "correct_answer": analysis.get("answer", ""),
                "sub_questions_count": question.get("sub_questions_count"),
                "sub_scores": question.get("sub_scores", []),
                "image_base64": q_image_b64,
            },
            mode=mode,
            analysis_result=analysis
        )
        question["difficulty"] = difficulty_result

        # 步骤3：素养分析
        logger.info(f"[分析] 题目{q_id} 开始素养分析")
        competency_result = competency_analyzer.analyze_competency(
            question={
                "id": q_id,
                "content": question.get("content", ""),
                "knowledge_points": analysis.get("knowledge_points", [])
            }
        )
        question["competency"] = competency_result

        logger.info(f"[分析] 题目{q_id} 完整分析完成")
        return question

    except Exception as e:
        logger.error(f"[分析] 题目{q_id} 分析失败: {str(e)}")
        question["analysis"] = {"error": str(e), "knowledge_points": [], "answer": "分析失败"}
        question["difficulty"] = {"error": str(e)}
        question["competency"] = {"error": str(e)}
        return question


# ============ 认证中间件 ============

def verify_admin(password: Optional[str] = Header(None, alias="X-Admin-Password")):
    """验证管理员密码"""
    if password != ADMIN_PASSWORD:
        logger.warning("管理员认证失败（密码错误）")
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return True


# ============ 核心API ============

@app.post("/api/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.FAST),
    generate_report: bool = Form(False)
):
    """
    主接口：上传文档并完成完整分析流程

    Args:
        file: 上传的PDF或DOCX文件
        mode: 评估模式 "fast"(快速) 或 "deep"(深度)
        generate_report: 是否生成PDF报告

    流程：
    1. 保存上传文件
    2. 转换为图片
    3. Gemini拆分题目
    4. 逐题深度分析
    5. 难度评估（新增）
    6. 素养分析（新增）
    7. 生成PDF报告（可选）
    8. 返回完整结果
    """
    start_time = datetime.now()
    logger.info(f"收到文件上传: {file.filename}, 类型: {file.content_type}")

    try:
        # 1. 保存文件
        file_path = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        logger.debug(f"文件已保存: {file_path}, 大小: {len(content) / 1024:.2f}KB")

        # 2. 文档转图片
        extracted_text = None  # 存储提取的文字
        extracted_elements = None  # 存储提取的元素信息
        if file.filename.lower().endswith('.pdf'):
            images = doc_processor.process_pdf(str(file_path))
        elif file.filename.lower().endswith('.docx'):
            images = doc_processor.process_docx(str(file_path))
        else:
            raise HTTPException(400, "不支持的文件格式，仅支持PDF和DOCX")

        if not images:
            raise HTTPException(400, "文档转换失败，未生成图片")

        # 检查图片是否包含提取的文字和元素信息（PDF和Word都支持）
        if images and hasattr(images[0], 'info'):
            if 'extracted_text' in images[0].info:
                extracted_text = images[0].info['extracted_text']
                logger.info(f"检测到提取文字，长度: {len(extracted_text)} 字符")
            if 'elements' in images[0].info:
                extracted_elements = images[0].info['elements']
                logger.info(f"检测到元素信息，共 {len(extracted_elements)} 个元素")

        image_bytes = doc_processor.images_to_bytes(images)
        logger.info(f"图片转换完成，共{len(image_bytes)}张")

        # 3. Gemini拆分题目（传递提取的文字）
        questions = gemini_analyzer.split_questions(image_bytes, extracted_text=extracted_text)
        logger.info(f"题目拆分完成，共{len(questions)}道题")

        # 【调试】打印第一道题的内容，检查是否包含选项
        if questions:
            first_q_content = questions[0].get('content', '')
            logger.info(f"[DEBUG] 第一道题内容长度: {len(first_q_content)} 字符")
            logger.info(f"[DEBUG] 第一道题内容预览:\n{first_q_content[:300]}...")
            has_options = any(opt in first_q_content for opt in ['A.', 'B.', 'C.', 'D.', 'A、', 'B、'])
            logger.info(f"[DEBUG] 第一道题是否包含选项: {has_options}")

        # 3.5 如果有元素信息，使用智能匹配算法分配给题目
        if extracted_elements:
            doc_processor.match_elements_to_questions(questions, extracted_elements)

        # 4. 逐题分析
        for idx, question in enumerate(questions):
            logger.info(f"开始分析第{idx+1}/{len(questions)}题")

            # 获取该题的图片
            q_image_indices = question.get("image_indices", [])
            q_images = [image_bytes[i] for i in q_image_indices if i < len(image_bytes)]

            # 获取题型（从拆分阶段识别的）
            question_type = question.get("question_type", "unknown")

            # 获取分节标题
            section_header = question.get("_section_header")

            # 题型fallback推断：如果拆分阶段未识别题型，根据section_header推断
            if question_type == "unknown" and section_header:
                section_lower = section_header.lower()
                if "单选" in section_header or "单项选择" in section_header or "只有一项" in section_header or "只有一个选项" in section_header:
                    question_type = "single_choice"
                    logger.info(f"[题型推断] 题目{question.get('id')} 根据分节标题推断为 single_choice")
                elif "多选" in section_header or "不定项" in section_header or "多项" in section_header or "一项或多项" in section_header or "一个或多个选项" in section_header:
                    question_type = "multiple_choice"
                    logger.info(f"[题型推断] 题目{question.get('id')} 根据分节标题推断为 multiple_choice")
                elif "填空" in section_header:
                    question_type = "fill_blank"
                    logger.info(f"[题型推断] 题目{question.get('id')} 根据分节标题推断为 fill_blank")
                elif "非选择题" in section_header or "简答" in section_header or "实验" in section_header:
                    # 非选择题暂时归为short_answer（后续可细化为experiment）
                    question_type = "short_answer"
                    logger.info(f"[题型推断] 题目{question.get('id')} 根据分节标题推断为 short_answer")

            # 更新question对象的question_type（用于后续流程）
            question["question_type"] = question_type

            # 调用Gemini分析（传递题型和分节标题）
            analysis = gemini_analyzer.analyze_question(
                question_text=question.get("content", ""),
                question_images=q_images,
                question_id=question.get("id", idx+1),
                question_type=question_type,
                section_header=section_header  # 新增：传递分节标题
            )

            # 合并结果
            question["analysis"] = analysis

        # 5. 难度评估（新增）
        logger.info(f"开始难度评估，模式: {mode}")
        for idx, question in enumerate(questions):
            logger.info(f"评估第{idx+1}/{len(questions)}题难度")
            try:
                difficulty_result = await difficulty_engine.evaluate_with_refinement(
                    question={
                        "id": question.get("id"),
                        "content": question.get("content", ""),
                        "knowledge_points": question.get("analysis", {}).get("knowledge_points", []),
                        "correct_answer": question.get("analysis", {}).get("answer", ""),
                        "question_type": question.get("question_type", ""),
                        "total_score": question.get("analysis", {}).get("total_score", question.get("total_score", 0)),
                        "image_base64": question.get("_media_for_ai", [{}])[0].get("base64", "") if question.get("_media_for_ai") else "",
                    },
                    mode=mode,
                    analysis_result=question.get("analysis", {})
                )
                question["difficulty"] = difficulty_result
                logger.debug(f"题目{question.get('id')}难度: {difficulty_result.get('final_difficulty', 'N/A')}/10")
            except Exception as e:
                logger.error(f"题目{question.get('id')}难度评估失败: {str(e)}")
                question["difficulty"] = {"error": str(e)}

        # 6. 素养分析（新增）
        logger.info("开始核心素养分析")
        for idx, question in enumerate(questions):
            logger.info(f"分析第{idx+1}/{len(questions)}题素养")
            try:
                competency_result = competency_analyzer.analyze_competency(
                    question={
                        "id": question.get("id"),
                        "content": question.get("content", ""),
                        "knowledge_points": question.get("analysis", {}).get("knowledge_points", [])
                    }
                )
                question["competency"] = competency_result
                primary = competency_result.get("primary_competency", "未知")
                logger.debug(f"题目{question.get('id')}主要素养: {primary}")
            except Exception as e:
                logger.error(f"题目{question.get('id')}素养分析失败: {str(e)}")
                question["competency"] = {"error": str(e)}

        # 7. 聚合素养统计
        try:
            competency_list = [q.get("competency", {}) for q in questions if "error" not in q.get("competency", {})]
            competency_summary = competency_analyzer.aggregate_exam_competencies(competency_list)
            logger.info(f"素养聚合完成，主要素养: {competency_summary.get('primary_competency', 'N/A')}")
        except Exception as e:
            logger.error(f"素养聚合失败: {str(e)}")
            competency_summary = {"error": str(e)}

        # 8. 生成PDF报告（可选）
        report_url = None
        if generate_report:
            try:
                logger.info("开始生成PDF报告")
                exam_id = datetime.now().strftime('%Y%m%d_%H%M%S')
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                report_generator.generate_pdf_report(
                    questions_analysis=questions,
                    competency_summary=competency_summary,
                    exam_info={
                        "name": file.filename,
                        "total": len(questions),
                        "mode": mode,
                        "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    },
                    output_path=str(pdf_path)
                )

                report_url = f"/api/reports/{exam_id}.pdf"
                logger.info(f"报告生成成功: {report_url}")
            except Exception as e:
                logger.error(f"报告生成失败: {str(e)}", exc_info=True)
                report_url = f"error: {str(e)}"

        # 清理上传文件（节省空间）
        file_path.unlink()
        logger.debug(f"已删除临时文件: {file_path}")

        # 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"完整流程完成，总耗时: {elapsed:.2f}秒")

        # 返回完整结果
        return {
            "questions": questions,
            "total_count": len(questions),
            "processing_time": elapsed,
            "competency_summary": competency_summary,
            "report_url": report_url,
            "mode": mode
        }

    except Exception as e:
        logger.error(f"分析流程失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))


# ============ 规则拆分 + 自动分析 API（v3.3支持PDF）============

@app.post("/api/analyze_auto")
async def analyze_auto(
    file: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.DEEP),
    generate_report: bool = Form(False)
):
    """
    新接口：使用规则拆分 + 自动完整分析（不显示校准页面）

    v3.3更新：
    - 支持 .docx 和 .pdf 两种格式
    - 使用统一的 analyze_question_full 函数
    - 真正的并发处理（分析+难度+素养一次完成）
    """
    start_time = datetime.now()
    logger.info(f"[自动分析] 收到文件: {file.filename}")

    file_path = None
    file_ext = file.filename.lower().split('.')[-1] if '.' in file.filename else ''

    try:
        # 1. 验证文件格式
        if file_ext not in ['docx', 'pdf']:
            raise HTTPException(400, detail="仅支持 .docx 和 .pdf 格式")

        # 2. 保存文件
        file_path = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        logger.info(f"文件已保存: {file_path}")

        # 3. 根据文件类型选择拆分器
        if file_ext == 'docx':
            logger.info("使用Word原生拆分题目...")
            split_result = word_splitter.split(str(file_path))
            questions = split_result.get("questions", [])
            logger.info(f"Word拆分完成，共 {len(questions)} 道题")

            # 为题目准备图片（用于API分析）
            images = doc_processor.process_docx(str(file_path))
            image_bytes = doc_processor.images_to_bytes(images) if images else []

        elif file_ext == 'pdf':
            logger.info("使用PDF规则拆分题目...")
            split_result = pdf_splitter.split(str(file_path))
            questions = split_result.get("questions", [])
            logger.info(f"PDF拆分完成，共 {len(questions)} 道题，置信度: {split_result.get('confidence', 0):.2f}")

            # PDF的图片已包含在 _media_for_ai 中
            image_bytes = []

        # 4. 并发分析所有题目（分析+难度+素养一次完成）
        logger.info(f"开始并发分析 {len(questions)} 道题（{MAX_WORKERS}线程）...")

        def analyze_wrapper(q):
            return analyze_question_full(q, image_bytes, mode)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            questions = list(executor.map(analyze_wrapper, questions))

        logger.info(f"所有题目分析完成")

        # 6. 聚合统计数据
        try:
            competency_list = [q.get("competency", {}) for q in questions if "error" not in q.get("competency", {})]
            competency_summary = competency_analyzer.aggregate_exam_competencies(competency_list)
        except Exception as e:
            logger.error(f"素养聚合失败: {str(e)}")
            competency_summary = {}

        # 7. 生成PDF报告（可选）
        report_url = None
        if generate_report:
            try:
                exam_id = datetime.now().strftime('%Y%m%d_%H%M%S')
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                report_generator.generate_pdf_report(
                    questions_analysis=questions,
                    competency_summary=competency_summary,
                    exam_info={
                        "name": file.filename,
                        "total": len(questions),
                        "mode": mode
                    },
                    output_path=str(pdf_path)
                )

                report_url = f"/api/reports/{exam_id}.pdf"
                logger.info(f"PDF报告生成成功: {report_url}")
            except Exception as e:
                logger.error(f"PDF生成失败: {str(e)}")

        # 8. 计算整卷统计
        try:
            exam_statistics = generate_exam_statistics(questions, competency_summary)
        except Exception as e:
            logger.error(f"整卷统计失败: {str(e)}")
            exam_statistics = {}

        # 8.5 分数预估（如果数据库可用）
        score_prediction = None
        if DB_AVAILABLE:
            try:
                from database import get_db_session
                from prediction_service import PredictionService

                # 获取数据库会话
                db = await get_db_session()
                try:
                    prediction_service = PredictionService(db)

                    # 计算试卷总分
                    total_score = sum(
                        q.get('analysis', {}).get('total_score', q.get('total_score', 0))
                        for q in questions
                    )

                    # 推断年级（默认高三，后续可以从文件名或内容推断）
                    grade = "高三"

                    # 进行预估
                    score_prediction = await prediction_service.predict_exam_score(
                        questions=questions,
                        total_score=total_score,
                        grade=grade,
                        exam_name=file.filename,
                        save_prediction=True
                    )
                    logger.info(f"[自动分析] 分数预估完成: 预测均分={score_prediction.get('predicted_average')}")
                finally:
                    await db.close()
            except Exception as e:
                logger.warning(f"[自动分析] 分数预估失败（不影响主流程）: {str(e)}")

        # 9. 返回结果
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"[自动分析] 完成！总耗时: {elapsed_time:.1f}秒")

        result = {
            "total_count": len(questions),
            "questions": questions,
            "processing_time": elapsed_time,
            "mode": mode,
            "competency_summary": competency_summary,
            "exam_statistics": exam_statistics,
            "report_url": report_url
        }

        # 添加分数预估（如果有）
        if score_prediction:
            result["score_prediction"] = score_prediction

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[自动分析] 失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))
    finally:
        # 清理临时文件
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                logger.debug(f"已删除临时文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {str(e)}")


# ============ Word文档题目拆分 API（v3.0优化）============

@app.post("/api/analyze/auto_split")
async def auto_split_questions(
    file: UploadFile = File(...),
    use_rule: bool = Form(True)  # 保留参数兼容性，v3.0固定使用Word提取
):
    """
    第一阶段：自动拆分题目（v3.0：仅支持Word文档）

    Args:
        file: 上传的DOCX文件

    Returns:
        {
            "session_id": "xxx",
            "questions": [...],  # 不含media字段
            "confidence": 1.0,
            "warnings": [...],
            "method": "word_native"
        }
    """
    start_time = datetime.now()
    logger.info(f"[自动拆分] 收到文件: {file.filename}")

    file_path = None

    try:
        # 1. 验证文件格式（仅支持.docx）
        if not file.filename.lower().endswith('.docx'):
            raise HTTPException(400, detail="仅支持.docx格式，请使用Word文档")

        # 2. 保存文件
        file_path = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)

        # 3. 使用Word提取器拆分
        logger.info("[自动拆分] 使用Word原生提取器")
        result = word_splitter.split(str(file_path))

        # 4. 分离前端数据和AI数据
        # 前端数据：移除_media_for_ai字段
        questions_for_frontend = []
        questions_with_media = []  # 保留完整数据（含_media_for_ai）

        for q in result["questions"]:
            # 保存完整数据（供AI使用）
            questions_with_media.append(q.copy())

            # 前端数据（移除下划线开头的内部字段）
            q_frontend = {k: v for k, v in q.items() if not k.startswith('_')}
            questions_for_frontend.append(q_frontend)

        # 5. 生成session_id
        session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

        # 6. 保存session数据（包含完整数据）
        save_session(session_id, {
            "file_path": str(file_path),
            "filename": file.filename,
            "auto_split_result": {
                "questions": questions_with_media,  # 完整数据（含_media_for_ai）
                "confidence": result["confidence"],
                "warnings": result["warnings"],
                "method": result["method"]
            },
            "upload_time": datetime.now().isoformat()
        })

        # 7. 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"[自动拆分] 完成，耗时{elapsed:.2f}秒，session_id={session_id}")

        # 8. 返回给前端（不含media）
        return {
            "session_id": session_id,
            "questions": questions_for_frontend,
            "confidence": result["confidence"],
            "warnings": result["warnings"],
            "method": result["method"],
            "processing_time": elapsed
        }

    except Exception as e:
        logger.error(f"[自动拆分] 失败: {str(e)}", exc_info=True)
        # 清理临时文件
        if file_path and file_path.exists():
            file_path.unlink()
        raise HTTPException(500, detail=str(e))


@app.get("/api/analyze/session/{session_id}")
async def get_session_data(session_id: str):
    """获取session中的拆分结果"""
    session_data = get_session(session_id)
    if not session_data:
        raise HTTPException(404, detail="Session not found or expired")

    auto_split_result = session_data.get("auto_split_result", {})

    return {
        "questions": auto_split_result.get("questions", []),
        "confidence": auto_split_result.get("confidence", 0),
        "warnings": auto_split_result.get("warnings", []),
        "method": auto_split_result.get("method", "unknown"),
        "filename": session_data.get("filename", "")
    }


@app.post("/api/analyze/confirm_split")
async def confirm_split(
    session_id: str = Form(...),
    corrected_questions: str = Form(...),  # JSON字符串
    mode: AnalysisMode = Form(AnalysisMode.FAST),
    generate_report: bool = Form(False)
):
    """
    第二阶段：确认拆分结果（人工修正后）并继续分析（v3.0：使用Word媒体数据）

    Args:
        session_id: 第一阶段返回的session_id
        corrected_questions: 人工修正后的题目列表（JSON字符串）
        mode: 评估模式
        generate_report: 是否生成报告

    Returns:
        完整分析结果（同/api/analyze）
    """
    start_time = datetime.now()
    logger.info(f"[确认拆分] session_id={session_id}, mode={mode}")

    try:
        # 1. 获取session数据
        session_data = get_session(session_id)
        if not session_data:
            raise HTTPException(404, "Session已过期或不存在")

        # 2. 解析修正后的题目（前端发来的，不含media）
        corrected_questions_list = json.loads(corrected_questions)
        logger.info(f"[确认拆分] 收到{len(corrected_questions_list)}道修正后的题目")

        # 3. 获取原始题目数据（含_media_for_ai）
        original_questions = session_data.get("auto_split_result", {}).get("questions", [])

        # 4. 合并用户修正和原始媒体数据
        # 用户可能在前端修改了题目文本、删除了题目、合并了题目等
        questions_with_media = []
        for corrected_q in corrected_questions_list:
            # 尝试找到原始题目的媒体数据
            original_q = next((q for q in original_questions if q.get("id") == corrected_q.get("id")), None)

            # 合并数据
            merged_q = corrected_q.copy()
            if original_q and "_media_for_ai" in original_q:
                merged_q["_media_for_ai"] = original_q["_media_for_ai"]
                logger.debug(f"[确认拆分] 题目{corrected_q.get('id')}找到{len(original_q['_media_for_ai'])}个媒体对象")
            else:
                merged_q["_media_for_ai"] = []
                logger.debug(f"[确认拆分] 题目{corrected_q.get('id')}没有媒体数据")

            questions_with_media.append(merged_q)

        # 4.5 分值校正：修正Gemini错误分配的分节总分
        logger.info(f"[分值校正] 开始检查并修正题目分值...")
        section_groups = {}

        # 按分节标题分组
        for q in questions_with_media:
            section_header = q.get("_section_header", "")
            if section_header:
                if section_header not in section_groups:
                    section_groups[section_header] = []
                section_groups[section_header].append(q)

        # 对每个分节进行分值校正
        for section_header, questions in section_groups.items():
            # 从分节标题中提取总分（如"共60分"、"共55分"）
            match = re.search(r'共\s*(\d+)\s*分', section_header)
            if match:
                section_total = int(match.group(1))
                num_questions = len(questions)

                # 检查是否所有题目的total_score都等于或接近section_total（错误情况）
                scores = [q.get("total_score", 0) for q in questions]
                avg_current_score = sum(scores) / len(scores) if scores else 0

                # 如果平均分接近分节总分，说明Gemini错误地给每道题都分配了总分
                if avg_current_score > section_total * 0.8 and num_questions > 1:
                    # 计算正确的每题平均分
                    avg_score = section_total / num_questions

                    logger.warning(f"[分值校正] 检测到错误：分节'{section_header[:40]}...'")
                    logger.warning(f"[分值校正]   共{num_questions}题，分节总分{section_total}，但题目平均分{avg_current_score:.1f}")
                    logger.info(f"[分值校正]   修正为每题{avg_score:.1f}分")

                    # 修正每道题的total_score
                    for q in questions:
                        old_score = q.get("total_score", 0)
                        q["total_score"] = round(avg_score, 1)
                        logger.info(f"[分值校正]   题目{q.get('id')}: {old_score}分 → {q['total_score']}分")

        # 5. 并发完整分析（使用统一的 analyze_question_full 函数）
        logger.info(f"[确认拆分] 开始并发分析{len(questions_with_media)}道题目（{MAX_WORKERS}线程）")

        def analyze_wrapper(q):
            # 删除_media_for_ai字段后返回（不返回给前端）
            result = analyze_question_full(q, [], mode)  # image_bytes为空，使用_media_for_ai
            if "_media_for_ai" in result:
                del result["_media_for_ai"]
            return result

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            questions_with_media = list(executor.map(analyze_wrapper, questions_with_media))

        logger.info("[确认拆分] 所有题目分析完成")

        # 6. 聚合素养统计
        try:
            competency_list = [q.get("competency", {}) for q in questions_with_media if "error" not in q.get("competency", {})]
            competency_summary = competency_analyzer.aggregate_exam_competencies(competency_list)
        except Exception as e:
            logger.error(f"素养聚合失败: {str(e)}")
            competency_summary = {"error": str(e)}

        # 7. 生成PDF报告（可选）
        report_url = None
        if generate_report:
            try:
                logger.info("[确认拆分] 开始生成PDF报告")
                exam_id = session_id
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                report_generator.generate_pdf_report(
                    questions_analysis=questions_with_media,
                    competency_summary=competency_summary,
                    exam_info={
                        "name": session_data["filename"],
                        "total": len(questions_with_media),
                        "mode": mode,
                        "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    },
                    output_path=str(pdf_path)
                )

                report_url = f"/api/reports/{exam_id}.pdf"
                logger.info(f"报告生成成功: {report_url}")
            except Exception as e:
                logger.error(f"报告生成失败: {str(e)}", exc_info=True)
                report_url = f"error: {str(e)}"

        # 8. 清理临时文件
        file_path = Path(session_data["file_path"])
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"已删除临时文件: {file_path}")

        # 9. 生成整卷统计分析
        logger.info("[确认拆分] 开始生成整卷统计分析")
        exam_statistics = generate_exam_statistics(questions_with_media, competency_summary)

        # 10. 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"[确认拆分] 完整流程完成，总耗时: {elapsed:.2f}秒")

        # 返回完整结果
        return {
            "questions": questions_with_media,
            "total_count": len(questions_with_media),
            "processing_time": elapsed,
            "competency_summary": competency_summary,
            "exam_statistics": exam_statistics,  # v3.0新增：整卷统计
            "report_url": report_url,
            "mode": mode
        }

    except Exception as e:
        logger.error(f"[确认拆分] 失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))


def generate_exam_statistics(questions: List[Dict], competency_summary: Dict) -> Dict:
    """
    生成整卷统计分析（v3.1优化）

    统计内容：
    1. 难度分布（简单/中等/困难的题目数量 + 分值分布）
    2. 难度曲线（按题号的难度趋势）
    3. 认知层级分布
    4. 知识点频率统计
    5. 知识点教材分布（v3.1新增）
    """
    try:
        # 难度分布统计（题目数量）
        difficulty_distribution = {"简单": 0, "中等": 0, "困难": 0}
        # 新增：基于分值的难度分布
        difficulty_distribution_by_score = {
            "简单": {"total_score": 0.0, "count": 0},
            "中等": {"total_score": 0.0, "count": 0},
            "困难": {"total_score": 0.0, "count": 0}
        }
        difficulty_curve = []  # 难度曲线数据
        cognitive_levels = []  # 认知层级数据
        knowledge_points_count = {}  # 知识点频率
        all_knowledge_points = []  # 收集所有知识点用于映射

        for q in questions:
            # 1. 难度分布
            if "difficulty" in q and "final_difficulty" in q["difficulty"]:
                diff_score = q["difficulty"]["final_difficulty"]
                difficulty_curve.append({
                    "question_id": q.get("id"),
                    "difficulty": diff_score
                })

                # 分类统计（题目数量）
                if diff_score <= 3.5:
                    difficulty_distribution["简单"] += 1
                elif diff_score <= 6.5:
                    difficulty_distribution["中等"] += 1
                else:
                    difficulty_distribution["困难"] += 1

                # 新增：聚合分值分布
                if "score_distribution_by_difficulty" in q["difficulty"]:
                    score_dist = q["difficulty"]["score_distribution_by_difficulty"]
                    difficulty_distribution_by_score["简单"]["total_score"] += score_dist.get("简单", 0.0)
                    difficulty_distribution_by_score["中等"]["total_score"] += score_dist.get("中等", 0.0)
                    difficulty_distribution_by_score["困难"]["total_score"] += score_dist.get("困难", 0.0)

                # 2. 认知层级
                if "cognitive_level" in q["difficulty"]:
                    cognitive_levels.append(q["difficulty"]["cognitive_level"])

            # 3. 知识点统计
            if "analysis" in q and "knowledge_points" in q["analysis"]:
                for kp in q["analysis"]["knowledge_points"]:
                    knowledge_points_count[kp] = knowledge_points_count.get(kp, 0) + 1
                    all_knowledge_points.append(kp)

        # 计算平均难度
        avg_difficulty = sum(item["difficulty"] for item in difficulty_curve) / len(difficulty_curve) if difficulty_curve else 0

        # 计算平均认知层级
        avg_cognitive = sum(cognitive_levels) / len(cognitive_levels) if cognitive_levels else 0

        # 计算分值分布的百分比
        total_score = sum(item["total_score"] for item in difficulty_distribution_by_score.values())
        for key in difficulty_distribution_by_score:
            difficulty_distribution_by_score[key]["percentage"] = (
                round((difficulty_distribution_by_score[key]["total_score"] / total_score * 100), 1)
                if total_score > 0 else 0
            )

        # v3.1新增：知识点教材映射
        logger.info(f"[知识点映射] 开始映射 {len(all_knowledge_points)} 个知识点到教材")
        mapped_points = knowledge_mapper.map_knowledge_points(all_knowledge_points)

        # 按教材聚合
        textbook_distribution = {
            "必修1": {"count": 0, "chapters": {}},
            "必修2": {"count": 0, "chapters": {}},
            "选择性必修1": {"count": 0, "chapters": {}},
            "选择性必修2": {"count": 0, "chapters": {}},
            "选择性必修3": {"count": 0, "chapters": {}}
        }

        for mapped in mapped_points:
            if mapped["mapped"]:
                textbook = mapped["textbook"]
                chapter = mapped["chapter"]
                textbook_distribution[textbook]["count"] += 1

                if chapter not in textbook_distribution[textbook]["chapters"]:
                    textbook_distribution[textbook]["chapters"][chapter] = {
                        "name": mapped["chapter_name"],
                        "count": 0
                    }
                textbook_distribution[textbook]["chapters"][chapter]["count"] += 1

        # 计算教材占比
        total_mapped = sum(item["count"] for item in textbook_distribution.values())
        for textbook in textbook_distribution:
            textbook_distribution[textbook]["percentage"] = (
                round((textbook_distribution[textbook]["count"] / total_mapped * 100), 1)
                if total_mapped > 0 else 0
            )

        logger.info(f"[知识点映射] 完成映射，成功映射 {total_mapped}/{len(all_knowledge_points)} 个知识点")

        # 知识点排序（前10）
        top_knowledge_points = sorted(
            knowledge_points_count.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            "difficulty_distribution": difficulty_distribution,  # 保留向后兼容
            "difficulty_distribution_by_score": difficulty_distribution_by_score,  # 新增字段
            "difficulty_curve": difficulty_curve,
            "avg_difficulty": round(avg_difficulty, 2),
            "avg_cognitive_level": round(avg_cognitive, 2),
            "top_knowledge_points": [
                {"name": kp, "count": count} for kp, count in top_knowledge_points
            ],
            "knowledge_textbook_distribution": textbook_distribution,  # v3.1新增
            "competency_distribution": competency_summary  # 直接引用素养分布
        }

    except Exception as e:
        logger.error(f"[整卷统计] 失败: {str(e)}", exc_info=True)
        return {"error": str(e)}


# ============ 管理后台API ============

@app.get("/api/admin/prompts")
async def get_prompts(_: bool = Header(verify_admin)):
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


@app.put("/api/admin/prompts")
async def update_prompt(
    data: PromptUpdate,
    _: bool = Header(verify_admin)
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


@app.get("/api/admin/logs")
async def get_logs(
    date: Optional[str] = None,
    _: bool = Header(verify_admin)
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


@app.get("/api/admin/logs/download/{date}")
async def download_log(
    date: str,
    _: bool = Header(verify_admin)
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


@app.get("/api/admin/logs/list")
async def list_logs(_: bool = Header(verify_admin)):
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


# ============ 难度评估 + 核心素养分析 + 报告生成 API ============

@app.get("/api/reports/{filename}")
async def download_report(filename: str):
    """
    下载生成的PDF报告

    Args:
        filename: PDF文件名（如: 20251019_143022.pdf）

    Returns:
        PDF文件下载响应
    """
    logger.info(f"请求下载报告: {filename}")

    # 安全检查：防止路径穿越攻击
    if ".." in filename or "/" in filename or "\\" in filename:
        logger.warning(f"非法文件名请求: {filename}")
        raise HTTPException(400, "非法文件名")

    report_path = REPORTS_DIR / filename
    if not report_path.exists():
        logger.warning(f"报告文件不存在: {report_path}")
        raise HTTPException(404, "报告文件不存在")

    logger.info(f"返回报告文件: {report_path}")
    return FileResponse(
        report_path,
        media_type='application/pdf',
        filename=filename
    )


# ============ 静态资源访问 ============

@app.get("/uploads/{path:path}")
async def serve_uploads(path: str):
    """
    提供上传文件的访问（图片、表格等）

    安全检查：防止路径穿越攻击
    """
    # 安全检查
    if ".." in path:
        raise HTTPException(400, "非法路径")

    file_path = Path("/home/ubuntu/biology-exam-analyzer/uploads") / path

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


# ============ 健康检查 ============

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "gemini_configured": bool(GEMINI_API_KEY)
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("启动开发服务器...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
