# -*- coding: utf-8 -*-
"""
分析路由模块

从 main.py 提取的所有分析相关端点：
- /api/analyze          — 主分析接口（上传+拆分+逐题分析）
- /api/analyze_auto     — 热路径主入口（规则拆分+并发分析）
- /api/analyze/auto_split    — 第一阶段：自动拆分
- /api/analyze/session/{id}  — 获取 session 拆分结果
- /api/analyze/confirm_split — 第二阶段：确认拆分+分析

辅助函数：
- analyze_question_full      — 单题完整分析
- generate_exam_statistics   — 整卷统计（从 analysis_statistics 导入，SEU 精确聚合）
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Body
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from enum import Enum
import asyncio
import os
import json
import re
import aiofiles
import base64
import time

from logger import get_logger
from config import UPLOAD_DIR, REPORTS_DIR
import credits_service

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
from session_manager import save_session, get_session
from utils import infer_question_type
from analysis_statistics import generate_exam_statistics, _build_competency_list
from deps import (
    get_analysis_service,
    get_analyzer,
    get_difficulty_engine,
    get_competency_analyzer,
    get_knowledge_mapper,
    get_doc_processor,
    get_word_splitter,
    get_pdf_splitter,
    MAX_WORKERS,
)

logger = get_logger()

router = APIRouter(tags=["analysis"])

_APP_BUILDER_READY_CACHE: Dict[str, float] = {}
_APP_BUILDER_READY_TTL_SECONDS = 300


# ============ 枚举（路由参数用） ============

class AnalysisMode(str, Enum):
    """分析模式"""
    FAST = "fast"    # 快速模式：仅规则引擎
    DEEP = "deep"    # 深度模式：规则引擎 + LLM精调


# ============ 辅助函数 ============

async def analyze_question_full(
    question: Dict[str, Any],
    image_bytes: List[bytes],
    mode: str = "deep",
    exam_review_channel: Optional[str] = None,
) -> Dict[str, Any]:
    """单题完整分析 — 委托给 AnalysisService。"""
    svc = get_analysis_service()
    return await svc.analyze_question(
        question,
        image_bytes,
        mode,
        exam_review_channel=exam_review_channel,
    )


def _compute_route_metadata_quality(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Expose metadata quality on route-level responses that still aggregate locally."""
    from report_data import compute_metadata_quality

    return compute_metadata_quality(questions)


def _validate_report_metadata_for_route(questions: List[Dict[str, Any]]) -> None:
    """Apply the same report gate when legacy routes generate PDF directly."""
    get_analysis_service().validate_report_metadata(questions)


def _ensure_review_channel_ready(exam_review_channel: Optional[str]) -> str | None:
    """Fail fast before consuming user credits when App Builder is unavailable."""
    from services.review_channel import channel_uses_app_builder, normalize_review_channel

    channel = normalize_review_channel(exam_review_channel)
    if not channel_uses_app_builder(exam_review_channel):
        return channel

    try:
        from services.evidence_client_loader import EvidenceClient, EvidenceConfig

        config = EvidenceConfig.from_env()
        credentials_path = Path(config.credentials_file)
        if not credentials_path.is_file():
            raise RuntimeError(f"credentials file not found: {config.credentials_file}")

        cache_key = "|".join(
            [
                config.project_id,
                config.credentials_file,
                config.location,
                config.ranking_config,
                config.grounding_config,
            ]
        )
        now = time.time()
        if _APP_BUILDER_READY_CACHE.get(cache_key, 0) > now:
            return channel

        EvidenceClient(config)._access_token()
        _APP_BUILDER_READY_CACHE.clear()
        _APP_BUILDER_READY_CACHE[cache_key] = now + _APP_BUILDER_READY_TTL_SECONDS
        return channel
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[审题渠道] App Builder preflight failed: %s", exc, exc_info=True)
        raise HTTPException(
            503,
            detail=f"1000赠金审题渠道不可用，请切换普通模型渠道或检查 证据服务配置：{exc}",
        ) from exc


async def _generate_route_report_artifacts(
    questions: List[Dict[str, Any]],
    competency_summary: Dict[str, Any],
    exam_statistics: Dict[str, Any],
    exam_info: Dict[str, Any],
    report_mode: str,
    pdf_path: Path,
    exam_review_channel: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Generate PDF and HTML reports for legacy route-level flows."""
    from report_data import aggregate_report_data
    from report_insights import generate_insights
    from report_product_publish import write_report_artifacts
    from services.review_channel import channel_grounding_enabled

    rdata = aggregate_report_data(
        questions, competency_summary, exam_statistics, exam_info
    )
    insights = await generate_insights(
        rdata,
        mode=report_mode,
        grounding_enabled=channel_grounding_enabled(exam_review_channel),
    )
    return write_report_artifacts(rdata, insights, mode=report_mode, pdf_path=pdf_path)


# generate_exam_statistics 和 _build_competency_list 从 analysis_statistics 导入（SEU 精确聚合）


# ============ 核心 API ============

@router.post("/api/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.FAST),
    generate_report: bool = Form(False),
    report_mode: str = Form("full"),
    exam_review_channel: Optional[str] = Form(None),
):
    """主接口：上传文档并完成完整分析流程。"""
    svc = get_analysis_service()
    start_time = datetime.now()
    logger.info(f"收到文件上传: {file.filename}, 类型: {file.content_type}")

    file_path = None
    try:
        effective_review_channel = _ensure_review_channel_ready(exam_review_channel)
        file_path = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        async with aiofiles.open(file_path, 'wb') as f:
            file_content = await file.read()
            if len(file_content) > MAX_UPLOAD_SIZE:
                raise HTTPException(413, detail=f"文件过大，上限 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
            await f.write(file_content)

        exam_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        result = await svc.run_full_analysis(
            file_path=str(file_path),
            filename=file.filename,
            mode=mode,
            generate_report=generate_report,
            report_mode=report_mode,
            reports_dir=str(REPORTS_DIR),
            exam_id=exam_id,
            exam_review_channel=effective_review_channel,
        )

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"完整流程完成，总耗时: {elapsed:.2f}秒")

        return {
            "questions": result["questions"],
            "total_count": len(result["questions"]),
            "processing_time": elapsed,
            "competency_summary": result["competency_summary"],
            "exam_statistics": result["exam_statistics"],
            "metadata_quality": result.get("metadata_quality") or _compute_route_metadata_quality(result["questions"]),
            "report_url": result.get("report_url"),
            "html_report_url": result.get("html_report_url"),
            "report_error": result.get("report_error"),
            "mode": mode,
            "exam_review_channel": effective_review_channel,
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"分析参数错误: {e}")
        raise HTTPException(400, detail=str(e))
    except RuntimeError as e:
        if "未配置" in str(e):
            raise HTTPException(503, detail=str(e))
        logger.error(f"分析运行时错误: {e}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")
    except Exception as e:
        logger.error(f"分析流程失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")
    finally:
        if file_path and file_path.exists():
            file_path.unlink()
            logger.debug(f"已删除临时文件: {file_path}")


# ============ 积分查询 ============

@router.get("/api/credits/balance")
async def get_credits_balance(authorization: Optional[str] = Header(None)):
    """查询当前用户积分余额。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="请先登录")
    token = authorization[7:]
    try:
        user_info = await credits_service.verify_token(token)
        balance = await credits_service.get_balance(user_info["id"])
        return {"success": True, "data": {"balance": balance, "analysis_cost": credits_service.ANALYSIS_COST}}
    except credits_service.InvalidTokenError as e:
        raise HTTPException(401, detail=str(e))
    except Exception as e:
        logger.error(f"[积分] 余额查询失败: {e}")
        raise HTTPException(500, detail="查询失败")


# ============ 规则拆分 + 自动分析 API（v3.3支持PDF）============

@router.post("/api/analyze_auto")
async def analyze_auto(
    file: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.DEEP),
    generate_report: bool = Form(False),
    report_mode: str = Form("full"),
    exam_review_channel: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    """
    新接口：使用规则拆分 + 自动完整分析（不显示校准页面）

    v3.3更新：
    - 支持 .docx 和 .pdf 两种格式
    - 使用统一的 analyze_question_full 函数
    - 真正的并发处理（分析+难度+素养一次完成）
    """
    # === 认证（支持评审旁路）===
    _review_mode = False
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="请先登录")
    token = authorization[7:]

    from auth_router import active_tokens as _admin_tokens
    _rev = _admin_tokens.get(token)
    if _rev and _rev.get("username") == "reviewer":
        _review_mode = True
        user_id = _rev["id"]
        logger.info(f"[评审] reviewer 评审模式，跳过积分")
    else:
        try:
            user_info = await credits_service.verify_token(token)
            user_id = user_info["id"]
            logger.info(f"[积分] 用户 {user_id} ({user_info.get('email')}) 请求分析")
        except credits_service.InvalidTokenError as e:
            raise HTTPException(401, detail=str(e))
        except Exception as e:
            logger.error(f"[积分] 认证失败: {e}")
            raise HTTPException(401, detail="认证失败，请重新登录")

        try:
            balance = await credits_service.get_balance(user_id)
            if balance < credits_service.ANALYSIS_COST:
                raise HTTPException(402, detail=f"积分不足：余额 {balance}，需要 {credits_service.ANALYSIS_COST}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[积分] 余额查询失败: {e}")
            raise HTTPException(500, detail="积分查询失败，请稍后重试")

    effective_review_channel = _ensure_review_channel_ready(exam_review_channel)

    doc_processor = get_doc_processor()
    word_splitter = get_word_splitter()
    pdf_splitter = get_pdf_splitter()
    competency_analyzer = get_competency_analyzer()

    start_time = datetime.now()
    logger.info(f"[自动分析] 收到文件: {file.filename} (用户 {user_id})")

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
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(413, detail=f"文件过大，上限 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
            await f.write(content)
        logger.info(f"文件已保存: {file_path}")

        # 3. 根据文件类型选择拆分器
        loop = asyncio.get_event_loop()
        if file_ext == 'docx':
            logger.info("使用Word原生拆分题目...")
            try:
                split_result = await loop.run_in_executor(None, word_splitter.split, str(file_path))
            except Exception as e:
                err_msg = str(e)
                logger.error(f"[Word拆分] 格式错误: {err_msg}")
                if "relationship" in err_msg or "opc" in err_msg.lower() or "package" in err_msg.lower():
                    raise HTTPException(400, detail="文件格式不兼容。请用 Microsoft Word 打开此文件，另存为 .docx 格式后重新上传（WPS 另存的文件可能不兼容）")
                raise HTTPException(400, detail=f"文件解析失败: {err_msg[:200]}")
            questions = split_result.get("questions", [])
            logger.info(f"Word拆分完成，共 {len(questions)} 道题")

            # 为题目准备图片（用于API分析）
            images = await loop.run_in_executor(None, doc_processor.process_docx, str(file_path))
            image_bytes = await loop.run_in_executor(None, doc_processor.images_to_bytes, images) if images else []

        elif file_ext == 'pdf':
            logger.info("使用PDF规则拆分题目...")
            split_result = await loop.run_in_executor(None, pdf_splitter.split, str(file_path))
            questions = split_result.get("questions", [])
            logger.info(f"PDF拆分完成，共 {len(questions)} 道题，置信度: {split_result.get('confidence', 0):.2f}")

            # PDF的图片已包含在 _media_for_ai 中
            image_bytes = []

        # 3.5 文件拆分成功，扣除积分（评审模式跳过）
        if not _review_mode:
            try:
                await credits_service.consume(user_id, credits_service.ANALYSIS_COST, f"智能审题-{file.filename}")
                logger.info(f"[积分] 文件拆分成功，已扣费 {credits_service.ANALYSIS_COST} 积分")
            except credits_service.InsufficientCreditsError as e:
                raise HTTPException(402, detail=f"积分不足：余额 {e.balance}，需要 {e.required}")
            except Exception as e:
                logger.error(f"[积分] 扣费失败: {e}")
                raise HTTPException(500, detail="积分扣费失败，请稍后重试")
        else:
            logger.info("[评审] 跳过扣费")

        # 4. 并发分析所有题目（分析+难度+素养一次完成）
        logger.info(f"开始并发分析 {len(questions)} 道题（{MAX_WORKERS}线程）...")
        sem = asyncio.Semaphore(MAX_WORKERS)

        async def analyze_one(q):
            async with sem:
                try:
                    return await analyze_question_full(
                        q,
                        image_bytes,
                        mode,
                        exam_review_channel=effective_review_channel,
                    )
                except Exception as e:
                    logger.error(f"题目 {q.get('id')} 分析失败: {e}")
                    q["error"] = str(e)
                    return q

        questions = list(await asyncio.gather(*[analyze_one(q) for q in questions]))

        logger.info(f"所有题目分析完成")

        # 6. 聚合统计数据（分值加权）
        try:
            competency_list = _build_competency_list(questions)
            competency_summary = competency_analyzer.aggregate_exam_competencies(competency_list)
        except Exception as e:
            logger.error(f"素养聚合失败: {str(e)}")
            competency_summary = {}

        # 7. 计算整卷统计（移到 PDF 生成之前）
        try:
            exam_statistics = generate_exam_statistics(questions, competency_summary)
        except Exception as e:
            logger.error(f"整卷统计失败: {str(e)}")
            exam_statistics = {}

        metadata_quality = _compute_route_metadata_quality(questions)

        # 8. 生成PDF报告（可选）
        report_url = None
        html_report_url = None
        report_error = None
        if generate_report:
            try:
                _validate_report_metadata_for_route(questions)

                exam_id = datetime.now().strftime('%Y%m%d_%H%M%S')
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                artifacts = await _generate_route_report_artifacts(
                    questions, competency_summary, exam_statistics,
                    {"name": file.filename, "total": len(questions), "mode": mode},
                    report_mode, pdf_path, effective_review_channel,
                )

                report_url = f"/api/reports/{exam_id}.pdf"
                if artifacts.get("html_path"):
                    html_report_url = f"/api/reports/{exam_id}.html"
                logger.info(f"报告生成成功: {report_url}, html={html_report_url}")
            except Exception as e:
                logger.error(f"PDF生成失败: {str(e)}", exc_info=True)
                report_error = f"报告生成失败: {str(e)}"

        # 8.5 分数预估（如果数据库可用）
        score_prediction = None
        try:
            from database import get_db_session
            from prediction_service import PredictionService

            # 获取数据库会话
            db = await get_db_session()
            try:
                prediction_service = PredictionService(db)

                # 计算试卷总分
                # AI 可能只提取部分题目分值，导致总分不完整
                # 策略：如果提取的总分 < 题目数*2（不合理），使用默认 100 分
                raw_total = sum(
                    q.get('analysis', {}).get('total_score', q.get('total_score', 0))
                    for q in questions
                )
                min_reasonable = len(questions) * 2  # 每题至少 2 分
                if raw_total < min_reasonable:
                    total_score = 100
                    logger.info(f"[自动分析] 提取总分 {raw_total} 不合理（< {min_reasonable}），使用默认 100 分")
                else:
                    total_score = raw_total

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
        except ImportError:
            pass  # 数据库模块不可用，跳过
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
            "metadata_quality": metadata_quality,
            "report_url": report_url,
            "html_report_url": html_report_url,
            "report_error": report_error,
            "exam_review_channel": effective_review_channel,
        }

        # 添加分数预估（如果有）
        if score_prediction:
            result["score_prediction"] = score_prediction

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[自动分析] 失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")
    finally:
        # 清理临时文件
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                logger.debug(f"已删除临时文件: {file_path}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {str(e)}")


# ============ Word文档题目拆分 API（v3.0优化）============

@router.post("/api/analyze/auto_split")
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
    word_splitter = get_word_splitter()

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
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(413, detail=f"文件过大，上限 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
            await f.write(content)

        # 3. 使用Word提取器拆分
        logger.info("[自动拆分] 使用Word原生提取器")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, word_splitter.split, str(file_path))

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
        raise HTTPException(500, detail="服务器内部错误")


@router.get("/api/analyze/session/{session_id}")
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


@router.post("/api/analyze/confirm_split")
async def confirm_split(
    session_id: str = Form(...),
    corrected_questions: str = Form(...),  # JSON字符串
    mode: AnalysisMode = Form(AnalysisMode.FAST),
    generate_report: bool = Form(False),
    report_mode: str = Form("full"),
    exam_review_channel: Optional[str] = Form(None),
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
    competency_analyzer = get_competency_analyzer()

    start_time = datetime.now()
    logger.info(f"[确认拆分] session_id={session_id}, mode={mode}")

    try:
        # 1. 获取session数据
        effective_review_channel = _ensure_review_channel_ready(exam_review_channel)
        session_data = get_session(session_id)
        if not session_data:
            raise HTTPException(404, "Session已过期或不存在")

        # 2. 解析修正后的题目（前端发来的，不含media）
        corrected_questions_list = json.loads(corrected_questions)
        # 输入校验：必须是列表，每项必须是 dict 且含 id 字段
        if not isinstance(corrected_questions_list, list):
            raise HTTPException(400, "corrected_questions 必须是 JSON 数组")
        if len(corrected_questions_list) > 200:
            raise HTTPException(400, "题目数量超出上限（最多200题）")
        for i, q in enumerate(corrected_questions_list):
            if not isinstance(q, dict):
                raise HTTPException(400, f"第{i+1}项不是有效的题目对象")
            if "id" not in q:
                raise HTTPException(400, f"第{i+1}项缺少 id 字段")
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

            # 回填分节标题和分值（auto_split 前端返回时被过滤）
            if original_q:
                if "_section_header" in original_q and "_section_header" not in merged_q:
                    merged_q["_section_header"] = original_q["_section_header"]
                if "total_score" in original_q and not merged_q.get("total_score"):
                    merged_q["total_score"] = original_q["total_score"]

            questions_with_media.append(merged_q)

        # 4.5 分值校正：修正AI错误分配的分节总分
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
        for section_header, section_questions in section_groups.items():
            # 从分节标题中提取总分（如"共60分"、"共55分"）
            match = re.search(r'共\s*(\d+)\s*分', section_header)
            if match:
                section_total = int(match.group(1))
                num_questions = len(section_questions)

                # 检查是否所有题目的total_score都等于或接近section_total（错误情况）
                scores = [q.get("total_score", 0) for q in section_questions]
                avg_current_score = sum(scores) / len(scores) if scores else 0

                # 如果平均分接近分节总分，说明AI错误地给每道题都分配了总分
                if avg_current_score > section_total * 0.8 and num_questions > 1:
                    # 计算正确的每题平均分
                    avg_score = section_total / num_questions

                    logger.warning(f"[分值校正] 检测到错误：分节'{section_header[:40]}...'")
                    logger.warning(f"[分值校正]   共{num_questions}题，分节总分{section_total}，但题目平均分{avg_current_score:.1f}")
                    logger.info(f"[分值校正]   修正为每题{avg_score:.1f}分")

                    # 修正每道题的total_score
                    for q in section_questions:
                        old_score = q.get("total_score", 0)
                        q["total_score"] = round(avg_score, 1)
                        logger.info(f"[分值校正]   题目{q.get('id')}: {old_score}分 → {q['total_score']}分")

        # 5. 并发完整分析（使用统一的 analyze_question_full 函数）
        logger.info(f"[确认拆分] 开始并发分析{len(questions_with_media)}道题目（{MAX_WORKERS}线程）")
        sem = asyncio.Semaphore(MAX_WORKERS)

        async def analyze_one(q):
            async with sem:
                try:
                    result = await analyze_question_full(
                        q,
                        [],
                        mode,
                        exam_review_channel=effective_review_channel,
                    )
                    if "_media_for_ai" in result:
                        del result["_media_for_ai"]
                    return result
                except Exception as e:
                    logger.error(f"题目 {q.get('id')} 分析失败: {e}")
                    q["error"] = str(e)
                    return q

        questions_with_media = list(await asyncio.gather(*[analyze_one(q) for q in questions_with_media]))

        logger.info("[确认拆分] 所有题目分析完成")

        # 6. 聚合素养统计（分值加权）
        try:
            competency_list = _build_competency_list(questions_with_media)
            competency_summary = competency_analyzer.aggregate_exam_competencies(competency_list)
        except Exception as e:
            logger.error(f"素养聚合失败: {str(e)}")
            competency_summary = {"error": str(e)}

        # 7. 计算整卷统计（移到 PDF 生成之前）
        logger.info("[确认拆分] 开始生成整卷统计分析")
        try:
            exam_statistics = generate_exam_statistics(questions_with_media, competency_summary)
        except Exception as e:
            logger.error(f"整卷统计失败: {str(e)}")
            exam_statistics = {}

        metadata_quality = _compute_route_metadata_quality(questions_with_media)

        # 8. 生成PDF报告（可选）
        report_url = None
        html_report_url = None
        report_error = None
        if generate_report:
            try:
                _validate_report_metadata_for_route(questions_with_media)

                logger.info("[确认拆分] 开始生成PDF报告")
                exam_id = session_id
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                artifacts = await _generate_route_report_artifacts(
                    questions_with_media, competency_summary, exam_statistics,
                    {"name": session_data["filename"], "total": len(questions_with_media), "mode": mode},
                    report_mode, pdf_path, effective_review_channel,
                )

                report_url = f"/api/reports/{exam_id}.pdf"
                if artifacts.get("html_path"):
                    html_report_url = f"/api/reports/{exam_id}.html"
                logger.info(f"报告生成成功: {report_url}, html={html_report_url}")
            except Exception as e:
                logger.error(f"报告生成失败: {str(e)}", exc_info=True)
                report_error = f"报告生成失败: {str(e)}"

        # 9. 清理临时文件
        file_path = Path(session_data["file_path"])
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"已删除临时文件: {file_path}")

        # 10. 计算耗时
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"[确认拆分] 完整流程完成，总耗时: {elapsed:.2f}秒")

        # 返回完整结果
        return {
            "questions": questions_with_media,
            "total_count": len(questions_with_media),
            "processing_time": elapsed,
            "competency_summary": competency_summary,
            "exam_statistics": exam_statistics,
            "metadata_quality": metadata_quality,
            "report_url": report_url,
            "html_report_url": html_report_url,
            "report_error": report_error,
            "mode": mode,
            "exam_review_channel": exam_review_channel,
        }

    except Exception as e:
        logger.error(f"[确认拆分] 失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


# ============ 教师修正 API ============

@router.patch("/api/questions/{question_id}/analysis")
async def update_question_analysis(question_id: int, body: dict = Body(...)):
    """教师修正分析结果 — manual_override 不覆盖原始分析（ORC-007）"""
    if not body:
        raise HTTPException(400, detail="修正内容不能为空")
    # 存储到 session 内存（当前无持久化需求，月均63次）
    if not hasattr(router, '_overrides'):
        router._overrides = {}
    router._overrides[question_id] = {
        "override": body,
        "override_at": datetime.now().isoformat(),
    }
    logger.info(f"[修正] 题目{question_id} 分析已修正: {list(body.keys())}")
    return {"status": "ok", "question_id": question_id, "overridden_fields": list(body.keys())}
