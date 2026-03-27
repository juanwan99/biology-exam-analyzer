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
- generate_exam_statistics   — 整卷统计
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header
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

from logger import get_logger
from config import UPLOAD_DIR, REPORTS_DIR
import credits_service

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
from session_manager import save_session, get_session
from utils import infer_question_type
from deps import (
    get_gemini_analyzer,
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


# ============ 枚举（路由参数用） ============

class AnalysisMode(str, Enum):
    """分析模式"""
    FAST = "fast"    # 快速模式：仅规则引擎
    DEEP = "deep"    # 深度模式：规则引擎 + LLM精调


# ============ 辅助函数 ============

async def analyze_question_full(
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
    gemini_analyzer = get_gemini_analyzer()
    difficulty_engine = get_difficulty_engine()
    competency_analyzer = get_competency_analyzer()

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
        if not gemini_analyzer:
            raise HTTPException(503, detail="AI 分析服务未配置（缺少 GEMINI_API_KEY）")
        logger.info(f"[分析] 题目{q_id} 开始Gemini分析")
        analysis = await gemini_analyzer.analyze_question(
            question_text=question.get("content", ""),
            question_images=q_images,
            question_id=q_id,
            question_type=question_type,
            section_header=section_header
        )
        question["analysis"] = analysis

        # 步骤2：难度评估
        logger.info(f"[分析] 题目{q_id} 开始难度评估")
        q_image_b64 = ""
        if q_images:
            import base64 as _b64
            q_image_b64 = _b64.b64encode(q_images[0]).decode("utf-8")
        difficulty_result = await difficulty_engine.evaluate_with_refinement(
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
        competency_result = await competency_analyzer.analyze_competency(
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


def generate_exam_statistics(questions: List[Dict], competency_summary: Dict) -> Dict:
    """
    生成整卷统计分析（v4.0 分值加权）

    统计内容：
    1. 难度分布（简单/中等/困难的题目数量 + 分值分布）
    2. 难度曲线（按题号的难度趋势）
    3. 认知层级分布（分值加权）
    4. 知识点分值加权统计
    5. 知识点教材分布（分值加权）
    6. Bloom 认知层级分布（分值加权）
    """
    knowledge_mapper = get_knowledge_mapper()

    BLOOM_LABELS = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}

    try:
        # 难度分布统计（题目数量）
        difficulty_distribution = {"简单": 0, "中等": 0, "困难": 0}
        # 基于分值的难度分布
        difficulty_distribution_by_score = {
            "简单": {"total_score": 0.0, "count": 0},
            "中等": {"total_score": 0.0, "count": 0},
            "困难": {"total_score": 0.0, "count": 0}
        }
        difficulty_curve = []          # 难度曲线数据（含 total_score）
        cognitive_levels = []          # 认知层级数据 [{level, total_score}]
        knowledge_points_weighted = {} # 知识点分值加权
        kp_with_weights = []           # (kp, weight) 对，用于教材映射
        bloom_score_accum = {label: 0.0 for label in BLOOM_LABELS.values()}

        for q in questions:
            total_score_val = q.get("total_score", q.get("analysis", {}).get("total_score", 0)) or 1  # fallback 等权

            # 1. 难度分布
            if "difficulty" in q and "final_difficulty" in q["difficulty"]:
                diff_score = q["difficulty"]["final_difficulty"]
                difficulty_curve.append({
                    "question_id": q.get("id"),
                    "difficulty": diff_score,
                    "total_score": total_score_val,
                })

                # 分类统计（题目数量）
                if diff_score <= 3.5:
                    difficulty_distribution["简单"] += 1
                elif diff_score <= 6.5:
                    difficulty_distribution["中等"] += 1
                else:
                    difficulty_distribution["困难"] += 1

                # 聚合分值分布
                if "score_distribution_by_difficulty" in q["difficulty"]:
                    score_dist = q["difficulty"]["score_distribution_by_difficulty"]
                    difficulty_distribution_by_score["简单"]["total_score"] += score_dist.get("简单", 0.0)
                    difficulty_distribution_by_score["中等"]["total_score"] += score_dist.get("中等", 0.0)
                    difficulty_distribution_by_score["困难"]["total_score"] += score_dist.get("困难", 0.0)

                # 2. 认知层级（带分值）
                if "cognitive_level" in q["difficulty"]:
                    cognitive_levels.append({
                        "level": q["difficulty"]["cognitive_level"],
                        "total_score": total_score_val,
                    })

                # 3. Bloom 分值累计（优先使用 bloom_distribution 细粒度分布）
                features = q.get("difficulty", {}).get("features", {})
                bloom_dist = features.get("bloom_distribution")
                if bloom_dist and total_score_val > 0:
                    dist_total = sum(bloom_dist.values())
                    if dist_total > 0:
                        dist_detail = []
                        for label, count in bloom_dist.items():
                            if label in bloom_score_accum and count > 0:
                                bloom_score_accum[label] += total_score_val * (count / dist_total)
                                dist_detail.append(f"{label}:{count}")
                        logger.info(f"[Bloom诊断] 题目{q.get('id')}: 分布={{{','.join(dist_detail)}}}, 分值={total_score_val}")
                    else:
                        # bloom_distribution 全零，fallback 到单值
                        bloom_val = features.get("bloom")
                        if bloom_val is not None:
                            bloom_label = BLOOM_LABELS.get(int(round(bloom_val)))
                            if bloom_label:
                                bloom_score_accum[bloom_label] += total_score_val
                                logger.info(f"[Bloom诊断] 题目{q.get('id')}: bloom={bloom_val} ({bloom_label}), 分值={total_score_val}")
                else:
                    # 无 bloom_distribution，使用单值 bloom
                    bloom_val = features.get("bloom")
                    if bloom_val is not None and total_score_val > 0:
                        bloom_label = BLOOM_LABELS.get(int(round(bloom_val)))
                        if bloom_label:
                            bloom_score_accum[bloom_label] += total_score_val
                            logger.info(f"[Bloom诊断] 题目{q.get('id')}: bloom={bloom_val} ({bloom_label}), 分值={total_score_val}")
                    else:
                        logger.warning(f"[Bloom诊断] 题目{q.get('id')}: bloom缺失或分值为0")

            # 4. 知识点分值加权
            if "analysis" in q and "knowledge_points" in q["analysis"]:
                kp_list = q["analysis"]["knowledge_points"]
                kp_weight = total_score_val / len(kp_list) if kp_list else 0
                for kp in kp_list:
                    knowledge_points_weighted[kp] = knowledge_points_weighted.get(kp, 0) + kp_weight
                    kp_with_weights.append((kp, kp_weight))

        # 分值加权平均难度
        total_weight = sum(item["total_score"] for item in difficulty_curve)
        if total_weight > 0:
            avg_difficulty = sum(item["difficulty"] * item["total_score"] for item in difficulty_curve) / total_weight
        else:
            avg_difficulty = 0

        # 分值加权平均认知层级
        cog_weight = sum(item["total_score"] for item in cognitive_levels)
        if cog_weight > 0:
            avg_cognitive = sum(item["level"] * item["total_score"] for item in cognitive_levels) / cog_weight
        else:
            avg_cognitive = 0

        # 计算分值分布的百分比
        total_score = sum(item["total_score"] for item in difficulty_distribution_by_score.values())
        for key in difficulty_distribution_by_score:
            difficulty_distribution_by_score[key]["percentage"] = (
                round((difficulty_distribution_by_score[key]["total_score"] / total_score * 100), 1)
                if total_score > 0 else 0
            )

        # Bloom 分布归一化
        bloom_total = sum(bloom_score_accum.values())
        bloom_distribution = {
            k: round(v / bloom_total, 3) if bloom_total > 0 else 0
            for k, v in bloom_score_accum.items()
        }

        # 知识点教材映射（分值加权）
        all_knowledge_points = [kp for kp, _ in kp_with_weights]
        kp_weight_list = [w for _, w in kp_with_weights]
        logger.info(f"[知识点映射] 开始映射 {len(all_knowledge_points)} 个知识点到教材")
        mapped_points = knowledge_mapper.map_knowledge_points(all_knowledge_points)

        textbook_distribution = {
            tb: {"weighted_score": 0.0, "chapters": {}}
            for tb in ["必修1", "必修2", "选择性必修1", "选择性必修2", "选择性必修3"]
        }

        for i, mapped in enumerate(mapped_points):
            if mapped["mapped"]:
                textbook = mapped["textbook"]
                chapter = mapped["chapter"]
                weight = kp_weight_list[i]
                textbook_distribution[textbook]["weighted_score"] += weight

                if chapter not in textbook_distribution[textbook]["chapters"]:
                    textbook_distribution[textbook]["chapters"][chapter] = {
                        "name": mapped["chapter_name"],
                        "weighted_score": 0.0,
                    }
                textbook_distribution[textbook]["chapters"][chapter]["weighted_score"] += weight

        # 计算教材占比
        total_mapped_weight = sum(item["weighted_score"] for item in textbook_distribution.values())
        for textbook in textbook_distribution:
            textbook_distribution[textbook]["percentage"] = (
                round((textbook_distribution[textbook]["weighted_score"] / total_mapped_weight * 100), 1)
                if total_mapped_weight > 0 else 0
            )

        logger.info(f"[知识点映射] 完成映射，加权总分 {total_mapped_weight:.1f}")

        # 知识点排序（前10，按分值加权）
        top_knowledge_points = sorted(
            knowledge_points_weighted.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            "difficulty_distribution": difficulty_distribution,
            "difficulty_distribution_by_score": difficulty_distribution_by_score,
            "difficulty_curve": difficulty_curve,
            "avg_difficulty": round(avg_difficulty, 2),
            "avg_cognitive_level": round(avg_cognitive, 2),
            "top_knowledge_points": [
                {"name": kp, "weighted_score": round(score, 1)} for kp, score in top_knowledge_points
            ],
            "knowledge_textbook_distribution": textbook_distribution,
            "competency_distribution": competency_summary,
            "bloom_distribution": bloom_distribution,
        }

    except Exception as e:
        logger.error(f"[整卷统计] 失败: {str(e)}", exc_info=True)
        return {"error": str(e)}


def _build_competency_list(questions):
    """构建带 _total_score 的素养列表，供分值加权聚合"""
    result = []
    for q in questions:
        if "error" not in q.get("competency", {}):
            comp = dict(q.get("competency", {}))
            comp["_total_score"] = q.get("total_score", q.get("analysis", {}).get("total_score", 0)) or 1  # fallback 等权
            result.append(comp)
    return result


# ============ 核心 API ============

@router.post("/api/analyze")
async def analyze_document(
    file: UploadFile = File(...),
    mode: AnalysisMode = Form(AnalysisMode.FAST),
    generate_report: bool = Form(False),
    report_mode: str = Form("full"),
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
    gemini_analyzer = get_gemini_analyzer()
    doc_processor = get_doc_processor()
    difficulty_engine = get_difficulty_engine()
    competency_analyzer = get_competency_analyzer()

    start_time = datetime.now()
    logger.info(f"收到文件上传: {file.filename}, 类型: {file.content_type}")

    try:
        # 1. 保存文件
        file_path = UPLOAD_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(413, detail=f"文件过大，上限 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")
            await f.write(content)
        logger.debug(f"文件已保存: {file_path}, 大小: {len(content) / 1024:.2f}KB")

        # 2. 文档转图片
        extracted_text = None  # 存储提取的文字
        extracted_elements = None  # 存储提取的元素信息
        loop = asyncio.get_event_loop()
        if file.filename.lower().endswith('.pdf'):
            images = await loop.run_in_executor(None, doc_processor.process_pdf, str(file_path))
        elif file.filename.lower().endswith('.docx'):
            images = await loop.run_in_executor(None, doc_processor.process_docx, str(file_path))
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

        image_bytes = await loop.run_in_executor(None, doc_processor.images_to_bytes, images)
        logger.info(f"图片转换完成，共{len(image_bytes)}张")

        # 3. Gemini拆分题目（传递提取的文字）
        if not gemini_analyzer:
            raise HTTPException(503, detail="AI 分析服务未配置（缺少 GEMINI_API_KEY）")
        questions = await gemini_analyzer.split_questions(image_bytes, extracted_text=extracted_text)
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
                    question_type = "short_answer"
                    logger.info(f"[题型推断] 题目{question.get('id')} 根据分节标题推断为 short_answer")

            # 更新question对象的question_type（用于后续流程）
            question["question_type"] = question_type

            # 调用Gemini分析（传递题型和分节标题）
            if not gemini_analyzer:
                raise HTTPException(503, detail="AI 分析服务未配置（缺少 GEMINI_API_KEY）")
            analysis = await gemini_analyzer.analyze_question(
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
                        "image_base64": (
                            question.get("_media_for_ai", [{}])[0].get("base64", "")
                            if question.get("_media_for_ai")
                            else (
                                __import__("base64").b64encode(
                                    image_bytes[question["image_indices"][0]]
                                ).decode("utf-8")
                                if image_bytes and question.get("image_indices")
                                and question["image_indices"][0] < len(image_bytes)
                                else ""
                            )
                        ),
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
                competency_result = await competency_analyzer.analyze_competency(
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

        # 7. 聚合素养统计（分值加权）
        try:
            competency_list = _build_competency_list(questions)
            competency_summary = competency_analyzer.aggregate_exam_competencies(competency_list)
            logger.info(f"素养聚合完成，主要素养: {competency_summary.get('primary_competency', 'N/A')}")
        except Exception as e:
            logger.error(f"素养聚合失败: {str(e)}")
            competency_summary = {"error": str(e)}

        # 8. 计算整卷统计（新增，原来此 endpoint 没有）
        try:
            exam_statistics = generate_exam_statistics(questions, competency_summary)
        except Exception as e:
            logger.error(f"整卷统计失败: {str(e)}")
            exam_statistics = {}

        # 9. 生成PDF报告（可选）
        report_url = None
        report_error = None
        if generate_report:
            try:
                from report_data import aggregate_report_data
                from report_insights import generate_insights
                from report_generator import generate_pdf_report as gen_pdf

                logger.info("开始生成PDF报告")
                exam_id = datetime.now().strftime('%Y%m%d_%H%M%S')
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                rdata = aggregate_report_data(
                    questions, competency_summary, exam_statistics,
                    {"name": file.filename, "total": len(questions), "mode": mode},
                )
                insights = await generate_insights(rdata, mode=report_mode)
                gen_pdf(rdata, insights, mode=report_mode, output_path=str(pdf_path))

                report_url = f"/api/reports/{exam_id}.pdf"
                logger.info(f"PDF报告生成成功: {report_url}")
            except Exception as e:
                logger.error(f"PDF生成失败: {str(e)}", exc_info=True)
                report_error = f"报告生成失败: {str(e)}"

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
            "exam_statistics": exam_statistics,
            "report_url": report_url,
            "report_error": report_error,
            "mode": mode
        }

    except Exception as e:
        logger.error(f"分析流程失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")


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
    authorization: Optional[str] = Header(None),
):
    """
    新接口：使用规则拆分 + 自动完整分析（不显示校准页面）

    v3.3更新：
    - 支持 .docx 和 .pdf 两种格式
    - 使用统一的 analyze_question_full 函数
    - 真正的并发处理（分析+难度+素养一次完成）
    """
    # === 积分校验 ===
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, detail="请先登录")
    token = authorization[7:]
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
        await credits_service.consume(user_id, credits_service.ANALYSIS_COST, f"智能审题-{file.filename}")
    except credits_service.InsufficientCreditsError as e:
        raise HTTPException(402, detail=f"积分不足：余额 {e.balance}，需要 {e.required}")
    except Exception as e:
        logger.error(f"[积分] 扣费失败: {e}")
        raise HTTPException(500, detail="积分扣费失败，请稍后重试")

    doc_processor = get_doc_processor()
    word_splitter = get_word_splitter()
    pdf_splitter = get_pdf_splitter()
    competency_analyzer = get_competency_analyzer()

    start_time = datetime.now()
    logger.info(f"[自动分析] 收到文件: {file.filename} (用户 {user_id}, 已扣 {credits_service.ANALYSIS_COST} 积分)")

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
            split_result = await loop.run_in_executor(None, word_splitter.split, str(file_path))
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

        # 4. 并发分析所有题目（分析+难度+素养一次完成）
        logger.info(f"开始并发分析 {len(questions)} 道题（{MAX_WORKERS}线程）...")

        async def analyze_one(q):
            try:
                return await analyze_question_full(q, image_bytes, mode)
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

        # 8. 生成PDF报告（可选）
        report_url = None
        report_error = None
        if generate_report:
            try:
                from report_data import aggregate_report_data
                from report_insights import generate_insights
                from report_generator import generate_pdf_report as gen_pdf

                exam_id = datetime.now().strftime('%Y%m%d_%H%M%S')
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                rdata = aggregate_report_data(
                    questions, competency_summary, exam_statistics,
                    {"name": file.filename, "total": len(questions), "mode": mode},
                )
                insights = await generate_insights(rdata, mode=report_mode)
                gen_pdf(rdata, insights, mode=report_mode, output_path=str(pdf_path))

                report_url = f"/api/reports/{exam_id}.pdf"
                logger.info(f"PDF报告生成成功: {report_url}")
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
                # Gemini 可能只提取部分题目分值，导致总分不完整
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
            "report_url": report_url,
            "report_error": report_error,
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
        for section_header, section_questions in section_groups.items():
            # 从分节标题中提取总分（如"共60分"、"共55分"）
            match = re.search(r'共\s*(\d+)\s*分', section_header)
            if match:
                section_total = int(match.group(1))
                num_questions = len(section_questions)

                # 检查是否所有题目的total_score都等于或接近section_total（错误情况）
                scores = [q.get("total_score", 0) for q in section_questions]
                avg_current_score = sum(scores) / len(scores) if scores else 0

                # 如果平均分接近分节总分，说明Gemini错误地给每道题都分配了总分
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

        async def analyze_one(q):
            try:
                result = await analyze_question_full(q, [], mode)
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

        # 8. 生成PDF报告（可选）
        report_url = None
        report_error = None
        if generate_report:
            try:
                from report_data import aggregate_report_data
                from report_insights import generate_insights
                from report_generator import generate_pdf_report as gen_pdf

                logger.info("[确认拆分] 开始生成PDF报告")
                exam_id = session_id
                pdf_path = REPORTS_DIR / f"{exam_id}.pdf"

                rdata = aggregate_report_data(
                    questions_with_media, competency_summary, exam_statistics,
                    {"name": session_data["filename"], "total": len(questions_with_media), "mode": mode},
                )
                insights = await generate_insights(rdata, mode=report_mode)
                gen_pdf(rdata, insights, mode=report_mode, output_path=str(pdf_path))

                report_url = f"/api/reports/{exam_id}.pdf"
                logger.info(f"报告生成成功: {report_url}")
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
            "report_url": report_url,
            "report_error": report_error,
            "mode": mode
        }

    except Exception as e:
        logger.error(f"[确认拆分] 失败: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="服务器内部错误")
