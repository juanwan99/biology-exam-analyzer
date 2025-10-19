from fastapi import FastAPI, UploadFile, File, HTTPException, Header
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

# 确保目录存在
for directory in [UPLOAD_DIR, LOG_DIR, PROMPT_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# 初始化Gemini
if not GEMINI_API_KEY:
    logger.error("未配置GEMINI_API_KEY环境变量！")
    raise RuntimeError("Missing GEMINI_API_KEY")

gemini_analyzer = GeminiAnalyzer(GEMINI_API_KEY, api_base=GEMINI_API_BASE)
doc_processor = DocumentProcessor()


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


# ============ 认证中间件 ============

def verify_admin(password: Optional[str] = Header(None, alias="X-Admin-Password")):
    """验证管理员密码"""
    if password != ADMIN_PASSWORD:
        logger.warning(f"管理员认证失败，密码: {password}")
        raise HTTPException(status_code=401, detail="Invalid admin password")
    return True


# ============ 核心API ============

@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_document(file: UploadFile = File(...)):
    """
    主接口：上传文档并完成完整分析流程

    流程：
    1. 保存上传文件
    2. 转换为图片
    3. Gemini拆分题目
    4. 逐题深度分析
    5. 返回完整结果
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

        # 清理上传文件（节省空间）
        file_path.unlink()
        logger.debug(f"已删除临时文件: {file_path}")

        # 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"分析完成，总耗时: {elapsed:.2f}秒")

        # 【调试】检查structured_content是否存在
        for q in questions:
            has_sc = 'structured_content' in q
            sc_count = len(q.get('structured_content', [])) if has_sc else 0
            logger.info(f"[DEBUG] 题目{q.get('id')} structured_content存在: {has_sc}, 元素数: {sc_count}")
            if has_sc and sc_count > 0:
                logger.info(f"[DEBUG] 题目{q.get('id')} 元素类型: {[e['type'] for e in q['structured_content']]}")

        return AnalyzeResponse(
            questions=questions,
            total_count=len(questions),
            processing_time=elapsed
        )

    except Exception as e:
        logger.error(f"分析流程失败: {str(e)}", exc_info=True)
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
