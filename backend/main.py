from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import aiofiles
from pathlib import Path
from datetime import datetime
import glob

from logger import get_logger
from document_processor import DocumentProcessor
from gemini_analyzer import GeminiAnalyzer
from difficulty_engine import DifficultyEngine
from competency_analyzer import CompetencyAnalyzer
from report_generator import ReportGenerator
from rule_splitter import RuleSplitter

# 初始化
logger = get_logger()
app = FastAPI(title="Biology Question Analyzer API")

# CORS配置（允许前端访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_BASE = os.getenv("GEMINI_API_BASE")  # 自定义API端点（可选）
UPLOAD_DIR = Path("/app/uploads")
LOG_DIR = Path("/app/logs")
PROMPT_DIR = Path("/app/prompts")
RULES_DIR = Path("/app/rules")
REPORTS_DIR = Path("/app/reports")

# 确保目录存在
for directory in [UPLOAD_DIR, LOG_DIR, PROMPT_DIR, RULES_DIR, REPORTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# 初始化Gemini
if not GEMINI_API_KEY:
    logger.error("未配置GEMINI_API_KEY环境变量！")
    raise RuntimeError("Missing GEMINI_API_KEY")

gemini_analyzer = GeminiAnalyzer(GEMINI_API_KEY, api_base=GEMINI_API_BASE)
doc_processor = DocumentProcessor()
difficulty_engine = DifficultyEngine(gemini_analyzer=gemini_analyzer)
competency_analyzer = CompetencyAnalyzer(gemini_analyzer=gemini_analyzer)
report_generator = ReportGenerator()
rule_splitter = RuleSplitter()

# Session存储（临时存储auto_split结果，30分钟过期）
from collections import OrderedDict
from datetime import timedelta

SESSION_STORAGE = OrderedDict()  # {session_id: {"data": ..., "expire_time": ...}}
SESSION_EXPIRE_TIME = timedelta(minutes=30)


# ============ Pydantic Models ============

class AnalyzeResponse(BaseModel):
    """分析结果响应"""
    questions: List[Dict[str, Any]]
    total_count: int
    processing_time: float


class PromptUpdate(BaseModel):
    """Prompt更新请求"""
    type: str  # "split" or "analysis"
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


# ============ 认证中间件 ============

def verify_admin(password: Optional[str] = Header(None, alias="X-Admin-Password")):
    """验证管理员密码"""
    if password != ADMIN_PASSWORD:
        logger.warning(f"管理员认证失败，密码: {password}")
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return True


# ============ 核心API ============

@app.post("/api/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    mode: str = Form("fast"),
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

            # 调用Gemini分析
            analysis = gemini_analyzer.analyze_question(
                question_text=question.get("content", ""),
                question_images=q_images,
                question_id=question.get("id", idx+1)
            )

            # 合并结果
            question["analysis"] = analysis

        # 5. 难度评估（新增）
        logger.info(f"开始难度评估，模式: {mode}")
        for idx, question in enumerate(questions):
            logger.info(f"评估第{idx+1}/{len(questions)}题难度")
            try:
                difficulty_result = difficulty_engine.evaluate_with_refinement(
                    question={
                        "id": question.get("id"),
                        "content": question.get("content", ""),
                        "knowledge_points": question.get("analysis", {}).get("knowledge_points", [])
                    },
                    mode=mode  # "fast" 或 "deep"
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


# ============ 规则拆分 + 人工校准 API（v2.0新增）============

@app.post("/api/analyze/auto_split")
async def auto_split_questions(
    file: UploadFile = File(...),
    use_rule: bool = Form(True)  # 是否使用规则拆分（False则使用LLM）
):
    """
    第一阶段：自动拆分题目（规则引擎或LLM）

    Args:
        file: 上传的PDF文件
        use_rule: 是否使用规则拆分

    Returns:
        {
            "session_id": "xxx",
            "questions": [...],
            "confidence": 0.95,
            "warnings": [...],
            "method": "rule" | "llm"
        }
    """
    start_time = datetime.now()
    logger.info(f"[自动拆分] 收到文件: {file.filename}, 拆分方式: {'规则' if use_rule else 'LLM'}")

    try:
        # 1. 保存文件
        file_path = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)

        # 2. 选择拆分方式
        if use_rule and file.filename.lower().endswith('.pdf'):
            # 规则拆分
            logger.info("[自动拆分] 使用规则引擎拆分")
            result = rule_splitter.split_questions(str(file_path), use_llm_fallback=True)

            if not result["success"]:
                if result.get("method") == "llm_fallback_required":
                    logger.warning("[自动拆分] 规则拆分失败，降级到LLM拆分")
                    # 降级到LLM拆分
                    images = doc_processor.process_pdf(str(file_path))
                    image_bytes = doc_processor.images_to_bytes(images)
                    questions = gemini_analyzer.split_questions(image_bytes)
                    result = {
                        "success": True,
                        "questions": [{"id": q.get("id"), "content": q.get("content"), "confidence": 0.8} for q in questions],
                        "confidence": 0.8,
                        "warnings": ["规则拆分失败，已降级到LLM拆分"],
                        "method": "llm_fallback"
                    }
                else:
                    raise HTTPException(500, result.get("error", "拆分失败"))
        else:
            # LLM拆分
            logger.info("[自动拆分] 使用LLM拆分")
            if file.filename.lower().endswith('.pdf'):
                images = doc_processor.process_pdf(str(file_path))
            elif file.filename.lower().endswith('.docx'):
                images = doc_processor.process_docx(str(file_path))
            else:
                raise HTTPException(400, "不支持的文件格式")

            image_bytes = doc_processor.images_to_bytes(images)
            questions = gemini_analyzer.split_questions(image_bytes)

            result = {
                "success": True,
                "questions": [{"id": q.get("id"), "content": q.get("content"), "confidence": 0.9} for q in questions],
                "confidence": 0.9,
                "warnings": [],
                "method": "llm"
            }

        # 3. 生成session_id
        session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

        # 4. 保存session数据
        save_session(session_id, {
            "file_path": str(file_path),
            "filename": file.filename,
            "auto_split_result": result,
            "upload_time": datetime.now().isoformat()
        })

        # 5. 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"[自动拆分] 完成，耗时{elapsed:.2f}秒，session_id={session_id}")

        return {
            "session_id": session_id,
            "questions": result["questions"],
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


@app.post("/api/analyze/confirm_split")
async def confirm_split(
    session_id: str = Form(...),
    corrected_questions: str = Form(...),  # JSON字符串
    mode: str = Form("fast"),
    generate_report: bool = Form(False)
):
    """
    第二阶段：确认拆分结果（人工修正后）并继续分析

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

        # 2. 解析修正后的题目
        import json
        questions = json.loads(corrected_questions)
        logger.info(f"[确认拆分] 收到{len(questions)}道修正后的题目")

        # 3. 逐题分析（复用原有逻辑）
        file_path = Path(session_data["file_path"])

        # 加载文档图片（用于分析）
        if session_data["filename"].lower().endswith('.pdf'):
            images = doc_processor.process_pdf(str(file_path))
        else:
            images = doc_processor.process_docx(str(file_path))

        image_bytes = doc_processor.images_to_bytes(images)

        # 4. 逐题深度分析
        for idx, question in enumerate(questions):
            logger.info(f"[确认拆分] 分析第{idx+1}/{len(questions)}题")

            # 获取该题的图片（如果有）
            q_image_indices = question.get("image_indices", [])
            q_images = [image_bytes[i] for i in q_image_indices if i < len(image_bytes)]

            # 调用Gemini分析
            analysis = gemini_analyzer.analyze_question(
                question_text=question.get("content", ""),
                question_images=q_images,
                question_id=question.get("id", idx+1)
            )

            question["analysis"] = analysis

        # 5. 难度评估
        logger.info(f"[确认拆分] 开始难度评估，模式: {mode}")
        for idx, question in enumerate(questions):
            try:
                difficulty_result = difficulty_engine.evaluate_with_refinement(
                    question={
                        "id": question.get("id"),
                        "content": question.get("content", ""),
                        "knowledge_points": question.get("analysis", {}).get("knowledge_points", [])
                    },
                    mode=mode
                )
                question["difficulty"] = difficulty_result
            except Exception as e:
                logger.error(f"题目{question.get('id')}难度评估失败: {str(e)}")
                question["difficulty"] = {"error": str(e)}

        # 6. 素养分析
        logger.info("[确认拆分] 开始核心素养分析")
        for idx, question in enumerate(questions):
            try:
                competency_result = competency_analyzer.analyze_competency(
                    question={
                        "id": question.get("id"),
                        "content": question.get("content", ""),
                        "knowledge_points": question.get("analysis", {}).get("knowledge_points", [])
                    }
                )
                question["competency"] = competency_result
            except Exception as e:
                logger.error(f"题目{question.get('id')}素养分析失败: {str(e)}")
                question["competency"] = {"error": str(e)}

        # 7. 聚合素养统计
        try:
            competency_list = [q.get("competency", {}) for q in questions if "error" not in q.get("competency", {})]
            competency_summary = competency_analyzer.aggregate_exam_competencies(competency_list)
        except Exception as e:
            logger.error(f"素养聚合失败: {str(e)}")
            competency_summary = {"error": str(e)}

        # 8. 生成PDF报告（可选）
        report_url = None
        if generate_report:
            try:
                logger.info("[确认拆分] 开始生成PDF报告")
                exam_id = session_id
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                report_generator.generate_pdf_report(
                    questions_analysis=questions,
                    competency_summary=competency_summary,
                    exam_info={
                        "name": session_data["filename"],
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

        # 9. 清理临时文件
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"已删除临时文件: {file_path}")

        # 10. 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"[确认拆分] 完整流程完成，总耗时: {elapsed:.2f}秒")

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
        logger.error(f"[确认拆分] 失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))


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
