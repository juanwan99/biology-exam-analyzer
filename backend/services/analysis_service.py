"""AnalysisService — analysis_router 的业务逻辑提取到 service 层。

职责：文档处理→题目拆分→逐题分析→统计聚合→报告生成。
Router 只负责 HTTP 边界（鉴权、参数校验、文件读写、HTTPException）。
"""
import asyncio
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

logger = get_logger()


class AnalysisService:
    """试卷分析服务 — 编排完整分析流程。"""

    def __init__(self, analyzer, difficulty_engine, competency_analyzer,
                 knowledge_mapper, doc_processor, word_splitter, pdf_splitter,
                 max_workers: int = 21):
        self.analyzer = analyzer
        self.difficulty_engine = difficulty_engine
        self.competency_analyzer = competency_analyzer
        self.knowledge_mapper = knowledge_mapper
        self.doc_processor = doc_processor
        self.word_splitter = word_splitter
        self.pdf_splitter = pdf_splitter
        self.max_workers = max_workers

    # ── 单题完整分析 ──────────────────────────────────────────

    async def analyze_question(self, question: Dict, image_bytes: List[bytes],
                                mode: str = "deep") -> Dict:
        q_id = question.get("id", 0)
        try:
            from utils import infer_question_type
            question_type = infer_question_type(question)
            question["question_type"] = question_type
            section_header = question.get("_section_header")

            q_images = self._resolve_images(question, image_bytes)

            if not self.analyzer:
                raise RuntimeError("AI 分析服务未配置")

            analysis = await self.analyzer.analyze_question(
                question_text=question.get("content", ""),
                question_images=q_images,
                question_id=q_id,
                question_type=question_type,
                section_header=section_header,
            )
            question["analysis"] = analysis

            q_image_b64 = ""
            if q_images:
                q_image_b64 = base64.b64encode(q_images[0]).decode("utf-8")

            difficulty_result = await self.difficulty_engine.evaluate_with_refinement(
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
                analysis_result=analysis,
            )
            question["difficulty"] = difficulty_result

            competency_result = await self.competency_analyzer.analyze_competency(
                question={
                    "id": q_id,
                    "content": question.get("content", ""),
                    "knowledge_points": analysis.get("knowledge_points", []),
                }
            )
            question["competency"] = competency_result
            return question

        except Exception as e:
            logger.error(f"[分析] 题目{q_id} 分析失败: {e}")
            question["analysis"] = {"error": str(e), "knowledge_points": [], "answer": "分析失败"}
            question["difficulty"] = {"error": str(e)}
            question["competency"] = {"error": str(e)}
            return question

    # ── 批量并发分析 ──────────────────────────────────────────

    async def analyze_questions_batch(self, questions: List[Dict],
                                      image_bytes: List[bytes],
                                      mode: str = "deep",
                                      subject: str = "biology") -> List[Dict]:
        for idx, q in enumerate(questions):
            if not q.get("id"):
                q["id"] = idx + 1

        sem = asyncio.Semaphore(self.max_workers)

        async def _analyze_one(q):
            async with sem:
                return await self.analyze_question(q, image_bytes, mode)

        tasks = [_analyze_one(q) for q in questions]
        return await asyncio.gather(*tasks)

    # ── 统计聚合 ──────────────────────────────────────────────

    def aggregate_statistics(self, questions: List[Dict], competency_summary: Dict) -> Dict:
        from analysis_statistics import generate_exam_statistics
        return generate_exam_statistics(questions, competency_summary)

    def build_competency_summary(self, questions: List[Dict]) -> Dict:
        competency_list = []
        for q in questions:
            if "error" not in q.get("competency", {}):
                comp = dict(q.get("competency", {}))
                comp["_total_score"] = q.get("total_score",
                    q.get("analysis", {}).get("total_score", 0)) or 1
                competency_list.append(comp)
        return self.competency_analyzer.aggregate_exam_competencies(competency_list)

    # ── 文档处理 ──────────────────────────────────────────────

    async def process_document(self, file_path: str, filename: str) -> Dict:
        loop = asyncio.get_event_loop()
        if filename.lower().endswith(".pdf"):
            images = await loop.run_in_executor(None, self.doc_processor.process_pdf, file_path)
        elif filename.lower().endswith(".docx"):
            images = await loop.run_in_executor(None, self.doc_processor.process_docx, file_path)
        else:
            raise ValueError(f"不支持的文件格式: {filename}")

        if not images:
            raise ValueError("文档转换失败，未生成图片")

        extracted_text = None
        extracted_elements = None
        if images and hasattr(images[0], "info"):
            extracted_text = images[0].info.get("extracted_text")
            extracted_elements = images[0].info.get("elements")

        image_bytes = await loop.run_in_executor(None, self.doc_processor.images_to_bytes, images)
        return {
            "image_bytes": image_bytes,
            "extracted_text": extracted_text,
            "extracted_elements": extracted_elements,
        }

    # ── 题目拆分 ──────────────────────────────────────────────

    async def split_questions_llm(self, image_bytes: List[bytes],
                                   extracted_text: str = None) -> List[Dict]:
        if not self.analyzer:
            raise RuntimeError("AI 分析服务未配置")
        return await self.analyzer.split_questions(image_bytes, extracted_text=extracted_text)

    async def split_questions_rule(self, file_bytes: bytes, filename: str,
                                    subject: str = "biology") -> List[Dict]:
        if filename.lower().endswith(".docx"):
            return self.word_splitter.split(file_bytes, subject=subject)
        elif filename.lower().endswith(".pdf"):
            return self.pdf_splitter.split(file_bytes, subject=subject)
        raise ValueError(f"规则拆分不支持: {filename}")

    # ── 报告生成 ──────────────────────────────────────────────

    async def generate_report(self, questions: List[Dict],
                               competency_summary: Dict,
                               exam_statistics: Dict,
                               exam_info: Dict,
                               mode: str = "full",
                               output_path: str = None) -> Optional[str]:
        from report_data import aggregate_report_data
        from report_insights import generate_insights
        from report_generator import generate_pdf_report

        rdata = aggregate_report_data(
            questions, competency_summary, exam_statistics, exam_info
        )
        insights = await generate_insights(rdata, mode=mode)
        generate_pdf_report(rdata, insights, mode=mode, output_path=output_path)
        return output_path

    # ── 内部工具 ──────────────────────────────────────────────

    @staticmethod
    def _resolve_images(question: Dict, image_bytes: List[bytes]) -> List[bytes]:
        media_for_ai = question.get("_media_for_ai", [])
        if media_for_ai:
            result = []
            for item in media_for_ai:
                if item.get("type") in ("image", "table"):
                    b64 = item.get("base64", "")
                    if b64:
                        try:
                            result.append(base64.b64decode(b64))
                        except Exception:
                            pass
            return result

        indices = question.get("image_indices", [])
        return [image_bytes[i] for i in indices if 0 <= i < len(image_bytes)]


    # ── 完整端点编排（从 router 提取）────────────────────────

    async def run_full_analysis(self, file_path: str, filename: str,
                                 mode: str = "deep", generate_report: bool = False,
                                 report_mode: str = "full", reports_dir: str = None,
                                 exam_id: str = None) -> Dict:
        """完整分析流程：文档→拆分→分析→统计→报告。对应 /api/analyze。"""
        doc = await self.process_document(file_path, filename)
        image_bytes = doc["image_bytes"]
        extracted_text = doc["extracted_text"]
        extracted_elements = doc["extracted_elements"]

        questions = await self.split_questions_llm(image_bytes, extracted_text)

        if extracted_elements and self.doc_processor:
            self.doc_processor.match_elements_to_questions(questions, extracted_elements)

        for q in questions:
            q = await self.analyze_question(q, image_bytes, mode)

        competency_summary = self.build_competency_summary(questions)
        exam_statistics = self.aggregate_statistics(questions, competency_summary)

        report_url = None
        report_error = None
        if generate_report and reports_dir:
            try:
                from pathlib import Path
                pdf_path = str(Path(reports_dir) / f"{exam_id}.pdf")
                await self.generate_report(
                    questions, competency_summary, exam_statistics,
                    {"name": filename, "total": len(questions), "mode": mode},
                    mode=report_mode, output_path=pdf_path,
                )
                report_url = f"/api/reports/{exam_id}.pdf"
            except Exception as e:
                report_error = f"报告生成失败: {e}"

        return {
            "questions": questions,
            "competency_summary": competency_summary,
            "exam_statistics": exam_statistics,
            "report_url": report_url,
            "report_error": report_error,
        }

    async def run_auto_analysis(self, file_path: str, filename: str,
                                 file_bytes: bytes, mode: str = "deep",
                                 subject: str = "biology",
                                 generate_report: bool = False,
                                 report_mode: str = "full",
                                 reports_dir: str = None,
                                 exam_id: str = None) -> Dict:
        """规则拆分 + 自动分析。对应 /api/analyze_auto 的核心逻辑。"""
        file_ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

        if file_ext == "docx":
            loop = asyncio.get_event_loop()
            split_result = await loop.run_in_executor(
                None, self.word_splitter.split, file_path
            )
            questions = split_result.get("questions", [])
            images = await loop.run_in_executor(
                None, self.doc_processor.process_docx, file_path
            )
            image_bytes = (
                await loop.run_in_executor(None, self.doc_processor.images_to_bytes, images)
                if images else []
            )
        elif file_ext == "pdf":
            loop = asyncio.get_event_loop()
            split_result = await loop.run_in_executor(
                None, self.pdf_splitter.split, file_path
            )
            questions = split_result.get("questions", [])
            image_bytes = []
        else:
            raise ValueError(f"不支持的文件格式: {filename}")

        analyzed = await self.analyze_questions_batch(questions, image_bytes, mode, subject)
        competency_summary = self.build_competency_summary(analyzed)
        exam_statistics = self.aggregate_statistics(analyzed, competency_summary)

        report_url = None
        report_error = None
        if generate_report and reports_dir:
            try:
                from pathlib import Path
                pdf_path = str(Path(reports_dir) / f"{exam_id}.pdf")
                await self.generate_report(
                    analyzed, competency_summary, exam_statistics,
                    {"name": filename, "total": len(analyzed), "mode": mode},
                    mode=report_mode, output_path=pdf_path,
                )
                report_url = f"/api/reports/{exam_id}.pdf"
            except Exception as e:
                report_error = f"报告生成失败: {e}"

        return {
            "questions": analyzed,
            "split_result": split_result,
            "competency_summary": competency_summary,
            "exam_statistics": exam_statistics,
            "report_url": report_url,
            "report_error": report_error,
        }
