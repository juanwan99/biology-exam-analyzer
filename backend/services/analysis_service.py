"""AnalysisService — analysis_router 的业务逻辑提取到 service 层。

职责：文档处理→题目拆分→逐题分析→统计聚合→报告生成。
Router 只负责 HTTP 边界（鉴权、参数校验、文件读写、HTTPException）。
"""
import asyncio
import base64
import copy
import inspect
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger
from analysis_calibration import canonicalize_knowledge_point, is_non_textbook_skill_point
from metadata_contracts import AnalyzedQuestionEnvelope, LLMCallRecord

logger = get_logger()


def _standardize_report_knowledge_points(raw_points: List[Any], knowledge_mapper: Any) -> List[str]:
    standardized: List[str] = []
    seen = set()
    for point in raw_points or []:
        if not isinstance(point, str) or not point.strip():
            continue
        raw = point.strip()
        if is_non_textbook_skill_point(raw):
            continue
        canonical, _ = canonicalize_knowledge_point(raw, knowledge_mapper=knowledge_mapper)
        canonical = canonical.strip() if isinstance(canonical, str) else ""
        if not canonical or is_non_textbook_skill_point(canonical) or canonical in seen:
            continue
        standardized.append(canonical)
        seen.add(canonical)
    return standardized


def _score_record(question: Dict, analysis: Dict | None = None) -> tuple[float, Dict[str, Any] | None]:
    analysis = analysis if isinstance(analysis, dict) else {}
    candidates = (
        ("total_score", question.get("total_score")),
        ("analysis.total_score", analysis.get("total_score")),
    )
    for source, value in candidates:
        if isinstance(value, (int, float)):
            if value > 0:
                return float(value), None
            return 0.0, {"id": question.get("id"), "reason": "non_positive_score", "source": source, "value": value}
        if isinstance(value, str) and value.strip():
            try:
                parsed = float(value)
            except ValueError:
                return 0.0, {"id": question.get("id"), "reason": "invalid_score", "source": source, "value": value}
            if parsed > 0:
                return parsed, None
            return 0.0, {"id": question.get("id"), "reason": "non_positive_score", "source": source, "value": parsed}
    return 0.0, {"id": question.get("id"), "reason": "missing_score", "source": "total_score", "value": None}


class AnalysisService:
    """试卷分析服务 — 编排完整分析流程。"""

    def __init__(self, analyzer, difficulty_engine, competency_analyzer,
                 knowledge_mapper, doc_processor, word_splitter, pdf_splitter,
                 max_workers: int = None):
        self.analyzer = analyzer
        self.difficulty_engine = difficulty_engine
        self.competency_analyzer = competency_analyzer
        self.knowledge_mapper = knowledge_mapper
        self.doc_processor = doc_processor
        self.word_splitter = word_splitter
        self.pdf_splitter = pdf_splitter
        import os
        self.max_workers = max_workers or int(os.environ.get("ANALYSIS_CONCURRENCY", "5"))
        self._last_report_insights = None
        self._last_pipeline_audit = None
        self._last_channel_usage = None

    # ── 单题完整分析 ──────────────────────────────────────────

    async def analyze_question(self, question: Dict, image_bytes: List[bytes],
                                mode: str = "deep",
                                exam_review_channel: str | None = None) -> Dict:
        q_id = question.get("id", 0)
        from llm_client import set_llm_review_channel, reset_llm_review_channel
        review_channel_token = set_llm_review_channel(exam_review_channel)
        try:
            from utils import infer_question_type
            question_type = infer_question_type(question)
            question["question_type"] = question_type
            section_header = question.get("_section_header")

            q_images = self._resolve_images(question, image_bytes)
            q_media_items = self._media_items_for_llm(question, q_images)
            if q_media_items and not question.get("_media_for_ai"):
                question["_media_for_ai"] = q_media_items

            if not self.analyzer:
                raise RuntimeError("AI 分析服务未配置")

            from services.review_channel import (
                channel_evidence_ranking_enabled,
                channel_uses_agent_search,
            )
            analysis = await self.analyzer.analyze_question(
                question_text=question.get("content", ""),
                question_images=q_images,
                question_id=q_id,
                question_type=question_type,
                section_header=section_header,
                evidence_ranking_enabled=channel_evidence_ranking_enabled(exam_review_channel),
                agent_search_enabled=channel_uses_agent_search(exam_review_channel),
            )
            question["analysis"] = analysis

            if "total_score" not in question or question.get("total_score") is None:
                question["total_score"] = analysis.get("total_score")
            total_score, score_issue = _score_record(question, analysis)
            question["total_score"] = total_score
            question["score_status"] = score_issue["reason"] if score_issue else "valid"
            if score_issue:
                question["_score_issue"] = score_issue

            q_image_b64 = ""
            if q_images:
                q_image_b64 = base64.b64encode(q_images[0]).decode("utf-8")

            difficulty_q = {
                "id": q_id,
                "content": question.get("content", ""),
                "knowledge_points": analysis.get("knowledge_points", []),
                "total_score": total_score,
                "num_options": analysis.get("num_options", 4),
                "options": question.get("options", ""),
                "question_type": question_type,
                "correct_answer": analysis.get("answer", ""),
                "sub_questions_count": question.get("sub_questions_count"),
                "sub_scores": question.get("sub_scores", []),
                "image_base64": q_image_b64,
                "media_items": q_media_items,
                "_media_for_ai": q_media_items,
                "media_integrity": question.get("media_integrity"),
            }

            # v2 细粒度路径：从 SEU 派生权重 + 独立素养调用补充具体维度/分析说明
            fine_grained = analysis.get("_fine_grained")
            need_independent_competency = True
            v2_seu_competency = None  # SEU 派生的权重数据（F-003: 保留用于合并）
            analysis_warnings = []

            def add_analysis_warning(value: str) -> None:
                if value and value not in analysis_warnings:
                    analysis_warnings.append(value)
            if fine_grained and fine_grained.get("scoring_units"):
                try:
                    from llm_schemas import FineGrainedResult, compute_summary_from_units
                    fg = FineGrainedResult(
                        scoring_units=fine_grained["scoring_units"],
                        diagnostic_units=fine_grained.get("diagnostic_units", []),
                        stimulus_units=fine_grained.get("stimulus_units", []),
                    )
                    summary = compute_summary_from_units(fg)
                    # R2-002 + R2R-001 修复：归一化权重严格合计=1.0
                    raw_weights = summary["competency_details"]
                    weight_sum = sum(raw_weights.values())
                    if weight_sum > 0:
                        items = list(raw_weights.items())
                        norm_weights = {k: round(v / weight_sum, 2) for k, v in items}
                        remainder = round(1.0 - sum(norm_weights.values()), 2)
                        if remainder != 0:
                            max_key = max(norm_weights, key=norm_weights.get)
                            norm_weights[max_key] = round(norm_weights[max_key] + remainder, 2)
                    else:
                        norm_weights = {k: 0.25 for k in raw_weights}
                    v2_seu_competency = {
                        "primary_competency": summary["primary_competency"],
                        "competency_level": summary["competency_level"],
                        **{k: {"涉及": v > 0, "权重": v}
                           for k, v in norm_weights.items()},
                    }
                    logger.info(f"[分析] 题目{q_id} 从v2 SEU派生素养权重 (primary={summary['primary_competency']})")
                except Exception as e:
                    add_analysis_warning(f"seu_derivation_failed:{type(e).__name__}")
                    logger.warning(f"[分析] 题目{q_id} v2素养派生失败: {e}，改用独立素养分析并写入元数据告警")

            if v2_seu_competency:
                # v2 路径 — SEU 权重 + 独立素养分析补充具体维度/分析说明（F-003）
                competency_q = {
                    "id": q_id,
                    "content": question.get("content", ""),
                    "knowledge_points": analysis.get("knowledge_points", []),
                    "media_items": q_media_items,
                    "_media_for_ai": q_media_items,
                }
                difficulty_result, supplement = await asyncio.gather(
                    self.difficulty_engine.evaluate_with_refinement(
                        question=difficulty_q, mode=mode, analysis_result=analysis),
                    self.competency_analyzer.analyze_competency(question=competency_q),
                )
                question["difficulty"] = difficulty_result
                merged = dict(v2_seu_competency)
                if isinstance(supplement, dict) and "error" not in supplement:
                    for dim in ["生命观念", "科学思维", "科学探究", "社会责任"]:
                        sup_dim = supplement.get(dim, {})
                        if isinstance(sup_dim, dict) and isinstance(merged.get(dim), dict):
                            if sup_dim.get("具体维度"):
                                merged[dim]["具体维度"] = sup_dim["具体维度"]
                            if sup_dim.get("分析说明"):
                                merged[dim]["分析说明"] = sup_dim["分析说明"]
                    logger.info(f"[分析] 题目{q_id} v2素养合并完成 (SEU权重+独立分析文字)")
                else:
                    reason = supplement.get("error") if isinstance(supplement, dict) else "invalid_competency_supplement"
                    reason_text = str(reason or "unknown")[:80]
                    add_analysis_warning(f"competency_supplement_soft_failed:{reason_text}")
                    logger.info(f"[分析] 题目{q_id} v2素养独立补充失败，仅使用SEU权重；已写入元数据告警")
                question["competency"] = merged
                if isinstance(supplement, dict) and supplement.get("_llm_calls"):
                    question["competency"]["_llm_calls"] = supplement["_llm_calls"]
                need_independent_competency = False

            if need_independent_competency:
                # v1 路径：尝试合并素养或独立调用
                merged_competency = analysis.get("competency")
                if merged_competency and isinstance(merged_competency, dict) and merged_competency.get("primary_competency"):
                    weights = [merged_competency.get(k, {}).get("权重", 0) for k in ["生命观念", "科学思维", "科学探究", "社会责任"]]
                    weight_sum = sum(w for w in weights if isinstance(w, (int, float)))
                    if weight_sum >= 0.9:
                        question["competency"] = merged_competency
                        need_independent_competency = False
                        logger.info(f"[分析] 题目{q_id} 使用合并素养结果 (primary={merged_competency.get('primary_competency')})")
                    else:
                        add_analysis_warning(f"competency_merged_incomplete:weight_sum={weight_sum:.2f}")
                        logger.info(f"[分析] 题目{q_id} 合并素养权重和={weight_sum:.2f}<0.9，改用独立素养分析并写入元数据告警")

            if need_independent_competency:
                competency_q = {
                    "id": q_id,
                    "content": question.get("content", ""),
                    "knowledge_points": analysis.get("knowledge_points", []),
                    "media_items": q_media_items,
                    "_media_for_ai": q_media_items,
                }
                difficulty_result, competency_result = await asyncio.gather(
                    self.difficulty_engine.evaluate_with_refinement(question=difficulty_q, mode=mode, analysis_result=analysis),
                    self.competency_analyzer.analyze_competency(question=competency_q),
                )
                question["difficulty"] = difficulty_result
                question["competency"] = competency_result
            # 知识点标准化映射
            if self.knowledge_mapper and analysis.get("knowledge_points"):
                report_points = _standardize_report_knowledge_points(
                    analysis["knowledge_points"],
                    self.knowledge_mapper,
                )
                standardized = self.knowledge_mapper.map_knowledge_points(report_points)
                question["knowledge_mapping"] = standardized

            # 置信度计算（基础 + 质量信号）
            confidence = 0.0
            if "error" not in analysis:
                confidence += 0.2
            if analysis.get("knowledge_points"):
                confidence += 0.15
            if analysis.get("answer"):
                confidence += 0.15
            if question.get("competency") and "error" not in question.get("competency", {}):
                confidence += 0.1
            if analysis.get("bloom_level"):
                confidence += 0.1
            # 质量信号：特征提取状态
            diff_data = question.get("difficulty", {})
            if isinstance(diff_data, dict):
                feat = diff_data.get("features", {})
                if isinstance(feat, dict):
                    fs = feat.get("_feature_status", "ok")
                    if fs == "ok":
                        confidence += 0.15
                    elif fs == "partial":
                        confidence += 0.08
                    # failed/unknown: +0
                # 质量信号：难度置信度
                d_conf = diff_data.get("confidence", 0.5)
                if isinstance(d_conf, (int, float)):
                    confidence += 0.15 * d_conf
            question["analysis_confidence"] = round(max(0.1, min(1.0, confidence)), 2)
            if analysis_warnings:
                question["_analysis_warnings"] = analysis_warnings
            self._attach_metadata_envelope(question)

            reset_llm_review_channel(review_channel_token)
            return question

        except Exception as e:
            logger.error(f"[分析] 题目{q_id} 分析失败: {e}")
            question["analysis_failed"] = True
            question["analysis_failure_reason"] = str(e)
            question["analysis_confidence"] = 0.0
            question["analysis"] = {"error": str(e), "knowledge_points": [], "answer": "分析失败"}
            question["difficulty"] = {"error": str(e)}
            question["competency"] = {"error": str(e)}
            question["_llm_calls"] = []
            question["_metadata_envelope"] = {
                "status": "analysis_failed",
                "question": {
                    "id": question.get("id"),
                    "content": question.get("content", ""),
                    "question_type": question.get("question_type"),
                    "total_score": question.get("total_score"),
                },
                "llm_calls": [],
                "analysis_units": {},
                "derived": {
                    "knowledge_points": [],
                    "difficulty": None,
                    "competency": None,
                },
                "confidence": {
                    "overall": 0.0,
                    "analysis": 0.0,
                    "features": 0.0,
                    "competency": 0.0,
                },
                "lineage": {
                    "status": "analysis_failed",
                    "failure_reason": question.get("analysis_failure_reason"),
                },
                "warnings": ["analysis_failed"],
            }
            reset_llm_review_channel(review_channel_token)
            return question

    # ── 批量并发分析 ──────────────────────────────────────────

    async def analyze_questions_batch(self, questions: List[Dict],
                                      image_bytes: List[bytes],
                                      mode: str = "deep",
                                      subject: str = "biology",
                                      exam_review_channel: str | None = None) -> List[Dict]:
        for idx, q in enumerate(questions):
            if not q.get("id"):
                q["id"] = idx + 1

        sem = asyncio.Semaphore(self.max_workers)

        async def _analyze_one(q):
            async with sem:
                if self._accepts_kwarg(self.analyze_question, "exam_review_channel"):
                    return await self.analyze_question(
                        q, image_bytes, mode, exam_review_channel=exam_review_channel
                    )
                return await self.analyze_question(q, image_bytes, mode)

        originals = [copy.deepcopy(q) for q in questions]
        tasks = [_analyze_one(q) for q in questions]
        results = list(await asyncio.gather(*tasks))

        for idx, result in enumerate(results):
            retry_reason = self._metadata_retry_reason(result)
            if not retry_reason:
                continue
            q_id = result.get("id", idx + 1) if isinstance(result, dict) else idx + 1
            logger.warning(f"[元数据] 题目{q_id} 关键元数据不完整，顺序重试一次")
            if self._accepts_kwarg(self.analyze_question, "exam_review_channel"):
                retry = await self.analyze_question(
                    copy.deepcopy(originals[idx]),
                    image_bytes,
                    mode,
                    exam_review_channel=exam_review_channel,
                )
            else:
                retry = await self.analyze_question(copy.deepcopy(originals[idx]), image_bytes, mode)
            retry_still_needed = self._metadata_retry_reason(retry)
            if not retry_still_needed:
                self._mark_recovered_metadata_retry(retry, retry_reason, emit_warning=False)
                results[idx] = retry
            elif self._metadata_retry_needed(result) and isinstance(retry.get("_metadata_envelope"), dict):
                self._mark_recovered_metadata_retry(
                    retry,
                    retry_still_needed or retry_reason,
                    emit_warning=True,
                )
                results[idx] = retry

        return results

    # ── 统计聚合 ──────────────────────────────────────────────

    def aggregate_statistics(self, questions: List[Dict], competency_summary: Dict) -> Dict:
        from analysis_statistics import generate_exam_statistics
        return generate_exam_statistics(questions, competency_summary)

    def build_competency_summary(self, questions: List[Dict]) -> Dict:
        competency_list = []
        for q in questions:
            if "error" not in q.get("competency", {}):
                comp = dict(q.get("competency", {}))
                comp["_total_score"], score_issue = _score_record(q, q.get("analysis", {}))
                comp["_score_status"] = score_issue["reason"] if score_issue else "valid"
                fg = (q.get("analysis") or {}).get("_fine_grained")
                if fg:
                    comp["_fine_grained"] = fg
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
        failure_events = []
        if images and hasattr(images[0], "info"):
            extracted_text = images[0].info.get("extracted_text")
            extracted_elements = images[0].info.get("elements")
            failure_events = images[0].info.get("failure_events") or []

        image_bytes = await loop.run_in_executor(None, self.doc_processor.images_to_bytes, images)
        return {
            "image_bytes": image_bytes,
            "extracted_text": extracted_text,
            "extracted_elements": extracted_elements,
            "failure_events": failure_events,
        }

    # ── 题目拆分 ──────────────────────────────────────────────

    async def split_questions_llm(self, image_bytes: List[bytes],
                                   extracted_text: str = None,
                                   exam_review_channel: str | None = None) -> List[Dict]:
        if not self.analyzer:
            raise RuntimeError("AI 分析服务未配置")
        from llm_client import set_llm_review_channel, reset_llm_review_channel
        review_channel_token = set_llm_review_channel(exam_review_channel)
        try:
            return await self.analyzer.split_questions(image_bytes, extracted_text=extracted_text)
        finally:
            reset_llm_review_channel(review_channel_token)

    @staticmethod
    def _main_question_ids_from_text(text: str | None) -> List[int]:
        if not text:
            return []
        ids: List[int] = []
        for line in str(text).splitlines():
            match = re.match(r"^\s*(\d{1,2})[.、．]\s+", line)
            if match:
                ids.append(int(match.group(1)))
        return ids

    def validate_split_integrity(self, questions: List[Dict], source_text: str | None = None) -> None:
        ids = [q.get("id") for q in questions if isinstance(q.get("id"), int)]
        if not ids:
            raise ValueError("split integrity failed: no question ids")

        expected_from_result = list(range(min(ids), max(ids) + 1))
        if ids != expected_from_result:
            raise ValueError(
                "split integrity failed: non-contiguous result ids "
                f"{ids[:5]}...{ids[-5:]}"
            )

        source_ids = self._main_question_ids_from_text(source_text)
        if source_ids:
            expected_from_source = list(range(min(source_ids), max(source_ids) + 1))
            missing = sorted(set(expected_from_source) - set(ids))
            if missing or max(source_ids) > max(ids):
                raise ValueError(
                    "split integrity failed: source/result question ids mismatch "
                    f"missing={missing}, source_max={max(source_ids)}, result_max={max(ids)}"
                )

        id_set = set(ids)
        for question in questions:
            qid = question.get("id")
            content = str(question.get("content") or "")
            for match in re.finditer(r"(?m)^\s*(\d{1,2})[.、．]\s+", content):
                embedded = int(match.group(1))
                if embedded != qid and embedded in id_set:
                    raise ValueError(
                        "split integrity failed: question content contains another main id "
                        f"Q{qid}->Q{embedded}"
                    )

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
                               output_path: str = None,
                               exam_review_channel: str | None = None) -> Optional[str]:
        from report_data import aggregate_report_data
        from report_insights import generate_insights
        from report_product_publish import write_report_artifacts
        from exam_diagnostics import diagnose_exam

        self.validate_report_metadata(questions)
        rdata = aggregate_report_data(
            questions, competency_summary, exam_statistics, exam_info
        )
        rdata["diagnostics"] = diagnose_exam(questions, exam_statistics,
            exam_type=exam_info.get("exam_type", "高考"))
        from services.review_channel import channel_grounding_enabled
        from llm_client import set_llm_review_channel, reset_llm_review_channel
        review_channel_token = set_llm_review_channel(exam_review_channel)
        try:
            insights = await generate_insights(
                rdata,
                mode=mode,
                grounding_enabled=channel_grounding_enabled(exam_review_channel),
            )
        finally:
            reset_llm_review_channel(review_channel_token)
        self._last_pipeline_audit = self.build_pipeline_audit(
            rdata.get("metadata_quality", {}),
            report_insights=insights,
            exam_review_channel=exam_review_channel,
        )
        self._last_report_insights = insights
        self._last_channel_usage = self.build_channel_usage(questions, insights)
        self.assert_channel_usage(
            exam_review_channel,
            self._last_channel_usage,
            require_grounding=channel_grounding_enabled(exam_review_channel),
        )
        self.assert_pipeline_ready(self._last_pipeline_audit)
        write_report_artifacts(rdata, insights, mode=mode, pdf_path=output_path)
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
                        except Exception as exc:
                            logger.warning(f"[media] base64 decode failed for question media item: {exc}")
            return result

        indices = question.get("image_indices", [])
        return [image_bytes[i] for i in indices if 0 <= i < len(image_bytes)]

    @staticmethod
    def _media_items_for_llm(question: Dict, images: List[bytes]) -> List[Dict[str, str]]:
        media_for_ai = question.get("_media_for_ai", [])
        if isinstance(media_for_ai, list) and media_for_ai:
            return [
                {
                    "type": str(item.get("type") or "image"),
                    "base64": str(item.get("base64") or ""),
                    **({"mime_type": str(item.get("mime_type"))} if item.get("mime_type") else {}),
                }
                for item in media_for_ai
                if isinstance(item, dict) and item.get("base64")
            ]
        return [
            {
                "type": "image",
                "base64": base64.b64encode(image).decode("utf-8"),
            }
            for image in images or []
        ]

    @staticmethod
    def _accepts_kwarg(func, name: str) -> bool:
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            return False
        return name in params or any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in params.values()
        )

    def validate_report_metadata(self, questions: List[Dict],
                                 min_overall_confidence: float = 0.7) -> Dict:
        blocked = []
        low_confidence = []
        low_component_confidence = []
        warning_questions = []
        required = {"question_analysis"}
        feature_purposes = {"feature_extraction", "big_question_feature_extraction"}
        required_call_fields = {
            "call_id", "purpose", "prompt_id", "prompt_hash", "provider",
            "model", "input_refs", "parsed_schema", "confidence",
        }

        for q in questions:
            q_id = q.get("id")
            envelope = q.get("_metadata_envelope")
            if not isinstance(envelope, dict):
                blocked.append({"id": q_id, "reason": "metadata envelope missing"})
                continue
            if envelope.get("status") == "analysis_failed" or q.get("analysis_failed"):
                blocked.append({"id": q_id, "reason": "analysis failed"})
                continue

            calls = envelope.get("llm_calls", [])
            if not isinstance(calls, list) or not calls:
                blocked.append({"id": q_id, "reason": "llm_calls missing"})
                continue

            purposes = {call.get("purpose") for call in calls if isinstance(call, dict)}
            missing_purposes = sorted(required - purposes)
            if not (purposes & feature_purposes):
                missing_purposes.append("feature_extraction|big_question_feature_extraction")
            if missing_purposes:
                blocked.append({
                    "id": q_id,
                    "reason": "required llm purpose missing",
                    "missing": missing_purposes,
                })
            has_seu_derived_competency = self._has_seu_derived_competency(envelope)
            has_competency_source = (
                "competency_analysis" in purposes
                or has_seu_derived_competency
            )
            if not has_competency_source:
                blocked.append({
                    "id": q_id,
                    "reason": "required metadata source missing",
                    "missing": ["competency_analysis|v2_seu_derived_competency"],
                })

            for idx, call in enumerate(calls):
                if not isinstance(call, dict):
                    blocked.append({"id": q_id, "reason": f"llm_call[{idx}] invalid"})
                    continue
                missing_fields = sorted(required_call_fields - set(call))
                if missing_fields:
                    blocked.append({
                        "id": q_id,
                        "reason": f"llm_call[{idx}] required fields missing",
                        "missing": missing_fields,
                    })

            confidence = envelope.get("confidence", {})
            overall = confidence.get("overall", 0) if isinstance(confidence, dict) else 0
            if isinstance(overall, (int, float)) and overall < min_overall_confidence:
                low_confidence.append(q_id)
            if isinstance(confidence, dict):
                component_keys = ("analysis", "features", "competency")
                for component in component_keys:
                    value = confidence.get(component)
                    if value is None:
                        blocked.append({
                            "id": q_id,
                            "reason": "component confidence missing",
                            "component": component,
                        })
                    elif isinstance(value, (int, float)):
                        if (
                            value <= 0
                            and not (
                                component == "competency"
                                and has_seu_derived_competency
                            )
                        ):
                            blocked.append({
                                "id": q_id,
                                "reason": "component confidence failed",
                                "component": component,
                                "confidence": value,
                            })
                        elif value < min_overall_confidence:
                            low_component_confidence.append({
                                "id": q_id,
                                "component": component,
                                "confidence": value,
                            })

            warnings = envelope.get("warnings", [])
            if warnings:
                warning_questions.append({"id": q_id, "warnings": list(warnings)})

        if blocked:
            detail = "; ".join(f"Q{b.get('id')}: {b.get('reason')}" for b in blocked[:5])
            raise ValueError(f"metadata envelope missing or invalid: {detail}")

        return {
            "total_questions": len(questions),
            "blocked_questions": blocked,
            "low_confidence_questions": low_confidence,
            "low_component_confidence_questions": low_component_confidence,
            "warning_questions": warning_questions,
        }

    @staticmethod
    def build_pipeline_audit(metadata_quality: Dict | None,
                             report_insights: Dict | None = None,
                             exam_review_channel: str | None = None) -> Dict:
        metadata_quality = metadata_quality or {}
        blockers = []
        warnings = []

        def add_block(stage: str, code: str, message: str, detail: Any = None) -> None:
            blockers.append({
                "stage": stage,
                "code": code,
                "message": message,
                "detail": detail,
            })

        hard_list_keys = {
            "missing_envelope_questions": ("question_metadata", "missing_envelope"),
            "inferred_envelope_questions": ("question_metadata", "inferred_envelope"),
            "missing_component_confidence_questions": ("question_metadata", "missing_component_confidence"),
            "failed_component_confidence_questions": ("question_metadata", "failed_component_confidence"),
            "missing_purpose_questions": ("llm_calls", "missing_purpose"),
            "blocked_questions": ("question_analysis", "blocked_question"),
            "evidence_gap_questions": ("evidence_units", "evidence_gap"),
            "retry_questions": ("llm_calls", "retry_or_parse_failure"),
            "score_issue_questions": ("score_extraction", "score_issue"),
        }
        for key, (stage, code) in hard_list_keys.items():
            items = metadata_quality.get(key) or []
            if items:
                add_block(stage, code, f"{key} is not empty", items)

        for item in metadata_quality.get("low_component_confidence_questions") or []:
            warnings.append({
                "stage": "question_metadata",
                "code": "low_component_confidence",
                "detail": item,
            })

        for event in metadata_quality.get("failure_events") or []:
            if not isinstance(event, dict):
                continue
            severity = str(event.get("severity") or "").lower()
            if severity in {"blocked", "error", "fatal"}:
                add_block(
                    str(event.get("stage") or "pipeline"),
                    "failure_event",
                    str(event.get("reason") or "blocked failure event"),
                    event,
                )

        hard_warning_prefixes = (
            "analysis_failed:",
            "difficulty_blocked:",
            "llm_fallback:",
            "invalid_llm_call:",
            "llm_parse_failure:",
            "llm_provider_error:",
            "media_not_passed:",
            "seu_derivation_failed:",
            "competency_supplement_failed:",
            "competency_merged_incomplete:",
        )
        hard_warning_values = {
            "missing_llm_calls",
            "diagnostic_units_missing",
            "stimulus_units_missing",
            "stimulus_units_blank",
        }
        for item in metadata_quality.get("warning_questions") or []:
            qid = item.get("id") if isinstance(item, dict) else None
            for warning in (item.get("warnings") if isinstance(item, dict) else []) or []:
                warning_text = str(warning)
                if warning_text in hard_warning_values or warning_text.startswith(hard_warning_prefixes):
                    add_block(
                        "question_metadata",
                        "hard_warning",
                        f"Q{qid}: {warning_text}",
                        {"id": qid, "warning": warning_text},
                    )
                else:
                    warnings.append({"id": qid, "warning": warning_text})

        if report_insights is not None:
            report_calls = report_insights.get("_llm_calls") or []
            for call in report_calls:
                if not isinstance(call, dict):
                    continue
                purpose = call.get("purpose") or "report_llm"
                metadata = call.get("metadata") if isinstance(call.get("metadata"), dict) else {}
                if int(call.get("fallback_count") or metadata.get("fallback_count") or 0) > 0:
                    add_block("report_llm", "llm_fallback", f"{purpose} used fallback", call)
                if metadata.get("provider_errors"):
                    add_block("report_llm", "provider_error", f"{purpose} has provider errors", call)
                if call.get("validation_errors") and purpose != "report_grounding_check":
                    add_block("report_llm", "parse_or_validation_error", f"{purpose} validation failed", call)

            grounding_required = False
            try:
                from services.review_channel import channel_grounding_enabled
                grounding_required = channel_grounding_enabled(exam_review_channel)
            except Exception:
                grounding_required = False
            if grounding_required:
                checks = report_insights.get("_grounding_checks") or []
                status = report_insights.get("_grounding_status")
                if status != "ok" or not checks:
                    failed_checks = [
                        check for check in checks
                        if isinstance(check, dict) and check.get("status") != "ok"
                    ]
                    first_failed = failed_checks[0] if failed_checks else {}
                    detail_message = f"report grounding status is {status or 'missing'}"
                    if first_failed:
                        detail_message += (
                            f"; first failed section={first_failed.get('section') or 'unknown'}"
                            f", support_score={first_failed.get('support_score')}"
                            f", threshold={first_failed.get('threshold')}"
                        )
                    add_block(
                        "report_grounding",
                        "grounding_not_ok",
                        detail_message,
                        {"status": status, "checks": checks},
                    )

        return {
            "status": "blocked" if blockers else "ok",
            "blockers": blockers,
            "warnings": warnings,
            "metadata_quality": metadata_quality,
            "report_grounding_status": (
                report_insights.get("_grounding_status")
                if isinstance(report_insights, dict) else None
            ),
        }

    @staticmethod
    def build_channel_usage(questions: List[Dict] | None,
                            report_insights: Dict | None = None) -> Dict:
        """Summarize which parts of the review used 证据服务 vs model calls."""
        from services.evidence_audit import summarize_evidence_usage

        return summarize_evidence_usage(questions, report_insights)

    @staticmethod
    def assert_channel_usage(exam_review_channel: str | None,
                             channel_usage: Dict | None,
                             require_grounding: bool = False) -> None:
        from services.review_channel import channel_uses_agent_search, channel_uses_evidence

        if not channel_uses_evidence(exam_review_channel):
            return
        channel_usage = channel_usage or {}
        if (
            channel_uses_agent_search(exam_review_channel)
            and int(channel_usage.get("agent_search_answer_count") or 0) <= 0
        ):
            raise RuntimeError(
                "agent_search channel requested but no Search App answer_query evidence "
                "was recorded; verify the evidence service configuration and the question evidence context"
            )
        if int(channel_usage.get("unsupported_generation_count") or 0) > 0:
            raise RuntimeError(
                "证据增强审题失败：检测到不应使用的 证据服务 "
                "generateGroundedContent 调用；当前通道应使用模型生成 + Ranking/Grounding 门禁。"
            )
        rank_count = int(
            channel_usage.get("evidence_rank_count")
            or channel_usage.get("evidence_rank_count")
            or 0
        )
        grounding_count = int(
            channel_usage.get("evidence_grounding_check_count")
            or channel_usage.get("evidence_grounding_check_count")
            or 0
        )
        if rank_count <= 0:
            missing = channel_usage.get("missing_rank_question_ids") or []
            if missing:
                first = missing[0]
                raise RuntimeError(
                    f"证据增强审题失败：第 {first} 题缺少 Ranking 证据"
                    "（证据服务 Ranking 未记录），不能进入正式报告。"
                )
            raise RuntimeError(
                "证据增强审题失败：缺少 证据服务 Ranking 记录，"
                "不能进入正式报告。"
            )
        missing = channel_usage.get("missing_rank_question_ids") or []
        if missing:
            first = missing[0]
            raise RuntimeError(
                f"证据增强审题失败：第 {first} 题缺少 Ranking 证据"
                "（证据服务 Ranking 未记录），不能进入正式报告。"
            )
        if require_grounding and grounding_count <= 0:
            raise RuntimeError(
                "证据增强审题失败：报告结论缺少 Check Grounding 校验"
                "（证据服务 Check Grounding 未记录），不能进入正式报告。"
            )

    @staticmethod
    def assert_pipeline_ready(audit: Dict | None) -> None:
        audit = audit or {}
        blockers = audit.get("blockers") or []
        if blockers:
            first = blockers[0]
            raise RuntimeError(
                "pipeline gate failed: "
                f"{first.get('stage')}.{first.get('code')} - {first.get('message')}"
            )

    @staticmethod
    def _has_seu_derived_competency(envelope: Dict) -> bool:
        analysis_units = envelope.get("analysis_units", {})
        derived = envelope.get("derived", {})
        if not isinstance(analysis_units, dict) or not isinstance(derived, dict):
            return False

        scoring_units = analysis_units.get("scoring_units", [])
        competency = derived.get("competency") or derived.get("primary_competency")
        return bool(scoring_units) and bool(competency)

    @staticmethod
    def _metadata_retry_needed(question: Dict) -> bool:
        return AnalysisService._metadata_retry_reason(question) is not None

    @staticmethod
    def _metadata_retry_reason(question: Dict) -> str | None:
        if not isinstance(question, dict):
            return "invalid_question_result"
        envelope = question.get("_metadata_envelope")
        if not isinstance(envelope, dict):
            return "missing_metadata_envelope"

        calls = envelope.get("llm_calls", [])
        if not isinstance(calls, list) or not calls:
            return "missing_llm_calls"

        purposes = {call.get("purpose") for call in calls if isinstance(call, dict)}
        if "question_analysis" not in purposes:
            return "missing_question_analysis"
        if not (purposes & {"feature_extraction", "big_question_feature_extraction"}):
            return "missing_feature_extraction"
        if "competency_analysis" not in purposes:
            return "missing_competency_analysis"
        warnings = envelope.get("warnings", [])
        if isinstance(warnings, list) and any(
            warning in {
                "diagnostic_units_missing",
                "stimulus_units_missing",
                "stimulus_units_blank",
            }
            or str(warning).startswith("llm_parse_failure:")
            for warning in warnings
        ):
            visible = ",".join(str(w) for w in warnings[:3])
            return f"metadata_warning:{visible or 'unknown'}"
        return None

    @staticmethod
    def _mark_recovered_metadata_retry(
        question: Dict,
        reason: str | None,
        *,
        emit_warning: bool = False,
    ) -> None:
        if not isinstance(question, dict) or not reason:
            return
        warning = f"question_retried_after_metadata_failure:{reason}"
        question.setdefault("_recovered_failures", []).append({
            "stage": "question_analysis",
            "severity": "warning" if emit_warning else "info",
            "reason": reason,
            "recovered_by": "sequential_retry",
        })
        envelope = question.get("_metadata_envelope")
        if not isinstance(envelope, dict):
            return
        if emit_warning:
            warnings = envelope.setdefault("warnings", [])
            if isinstance(warnings, list) and warning not in warnings:
                warnings.append(warning)
        lineage = envelope.setdefault("lineage", {})
        if isinstance(lineage, dict):
            lineage["recovered_retry"] = {
                "reason": reason,
                "recovered_by": "sequential_retry",
                "warning_emitted": emit_warning,
            }

    @staticmethod
    def _valid_llm_call(call: Dict) -> tuple[Optional[Dict], Optional[str]]:
        try:
            return LLMCallRecord.model_validate(call).model_dump(), None
        except Exception as e:
            logger.warning(f"[元数据] 丢弃无效 LLM 调用记录: {e}")
            return None, str(e)

    def _collect_llm_calls(self, question: Dict) -> List[Dict]:
        buckets = [
            question,
            question.get("analysis"),
            question.get("difficulty"),
            (question.get("difficulty") or {}).get("features")
            if isinstance(question.get("difficulty"), dict) else None,
            question.get("competency"),
        ]
        calls = []
        invalid_calls = []
        seen = set()
        for bucket in buckets:
            if not isinstance(bucket, dict):
                continue
            for raw_call in bucket.get("_llm_calls", []):
                if not isinstance(raw_call, dict):
                    invalid_calls.append({"reason": "llm_call_record_not_dict"})
                    continue
                call, error = self._valid_llm_call(raw_call)
                if not call:
                    invalid_calls.append({
                        "reason": "llm_call_record_invalid",
                        "error": error or "unknown validation error",
                        "purpose": raw_call.get("purpose"),
                    })
                    continue
                key = (
                    call.get("call_id"),
                    call.get("purpose"),
                    call.get("prompt_hash"),
                )
                if key in seen:
                    continue
                seen.add(key)
                calls.append(call)
        question["_invalid_llm_call_errors"] = invalid_calls
        return calls

    def _attach_metadata_envelope(self, question: Dict) -> None:
        calls = self._collect_llm_calls(question)
        question["_llm_calls"] = calls

        analysis = question.get("analysis") if isinstance(question.get("analysis"), dict) else {}
        difficulty = question.get("difficulty") if isinstance(question.get("difficulty"), dict) else {}
        features = difficulty.get("features") if isinstance(difficulty.get("features"), dict) else {}
        competency = question.get("competency") if isinstance(question.get("competency"), dict) else {}
        fine_grained = analysis.get("_fine_grained") if isinstance(analysis, dict) else None

        def numeric_confidence(value) -> float:
            return float(value) if isinstance(value, (int, float)) else 0.0

        def call_confidence_for(*purposes: str) -> float:
            wanted = set(purposes)
            best = 0.0
            for call in calls:
                if call.get("purpose") not in wanted:
                    continue
                metadata = call.get("metadata") if isinstance(call.get("metadata"), dict) else {}
                if call.get("validation_errors") or metadata.get("validation_errors"):
                    continue
                if metadata.get("status") in {"failed", "parse_failed", "provider_failed"}:
                    continue
                best = max(best, numeric_confidence(call.get("confidence")))
            return best

        def result_or_call_confidence(value, *purposes: str) -> float:
            result_value = numeric_confidence(value)
            return result_value if result_value > 0 else call_confidence_for(*purposes)

        confidence = {
            "overall": question.get("analysis_confidence", 0.0),
            "analysis": result_or_call_confidence(
                analysis.get("_extraction_confidence", 0.0),
                "question_analysis",
            ),
            "features": result_or_call_confidence(
                features.get("_extraction_confidence", 0.0),
                "feature_extraction",
                "big_question_feature_extraction",
            ),
            "competency": result_or_call_confidence(
                competency.get("_extraction_confidence", 0.0),
                "competency_analysis",
            ),
        }
        warnings = []
        def add_warning(value: str) -> None:
            if value and value not in warnings:
                warnings.append(value)

        invalid_call_errors = question.get("_invalid_llm_call_errors") or []
        if invalid_call_errors:
            add_warning(f"invalid_llm_call:{len(invalid_call_errors)}")
        for warning in question.get("_analysis_warnings") or []:
            add_warning(str(warning))
        if not calls:
            add_warning("missing_llm_calls")
        if features.get("_feature_status") in ("partial", "failed"):
            add_warning(f"feature_status:{features.get('_feature_status')}")
        if difficulty.get("analysis_failed"):
            add_warning(f"analysis_failed:{difficulty.get('failure_reason') or 'unknown'}")
        for flag in difficulty.get("flags", []) if isinstance(difficulty.get("flags"), list) else []:
            if flag in {
                "big_question_structure_failed",
                "big_question_points_mismatch",
                "feature_extraction_failed",
                "big_question_fallback",
                "no_evaluation",
            }:
                add_warning(f"difficulty_blocked:{flag}")
        for call in calls:
            metadata = call.get("metadata") if isinstance(call.get("metadata"), dict) else {}
            input_refs = call.get("input_refs") if isinstance(call.get("input_refs"), dict) else {}
            prompt_id = str(call.get("prompt_id") or "").lower()
            purpose = call.get("purpose") or "unknown"
            retry_count = call.get("retry_count") or metadata.get("retry_count") or 0
            call_has_failure_signal = (
                int(call.get("fallback_count") or metadata.get("fallback_count") or 0) > 0
                or bool(metadata.get("provider_errors"))
                or bool(metadata.get("initial_parse_error"))
                or bool(metadata.get("validation_errors"))
                or bool(call.get("validation_errors"))
                or str(metadata.get("status") or "").lower() in {"failed", "parse_failed", "provider_failed"}
            )
            successful_evidence_repair = purpose == "missing_evidence_repair" and not call_has_failure_signal
            successful_model_recovery = (
                bool(retry_count)
                and metadata.get("recovery_status") == "ok"
                and not call_has_failure_signal
            )
            if (
                ("compact_retry" in prompt_id or retry_count)
                and not successful_evidence_repair
                and not successful_model_recovery
            ):
                add_warning(f"llm_retry:{purpose}")
            if int(call.get("fallback_count") or metadata.get("fallback_count") or 0) > 0:
                add_warning(f"llm_fallback:{purpose}")
            if metadata.get("provider_errors"):
                add_warning(f"llm_provider_error:{purpose}")
            if (
                metadata.get("initial_parse_error")
                or metadata.get("validation_errors")
                or call.get("validation_errors")
            ):
                add_warning(f"llm_parse_failure:{purpose}")
            if (
                (question.get("_media_for_ai") or question.get("media_items") or question.get("image_indices"))
                and call.get("purpose") in {
                    "question_analysis",
                    "feature_extraction",
                    "big_question_feature_extraction",
                    "competency_analysis",
                }
                and not (input_refs.get("media_count") or input_refs.get("image_count"))
            ):
                add_warning(f"media_not_passed:{call.get('purpose') or 'unknown'}")
        if float(question.get("total_score") or 0) >= 8 and isinstance(fine_grained, dict):
            if not fine_grained.get("diagnostic_units"):
                add_warning("diagnostic_units_missing")
            stimulus_units = fine_grained.get("stimulus_units") or []
            if not stimulus_units:
                add_warning("stimulus_units_missing")
            elif all(
                not str(unit.get("description") or "").strip()
                and not bool(unit.get("is_core"))
                and float(unit.get("complexity") or 0) <= 1
                for unit in stimulus_units
                if isinstance(unit, dict)
            ):
                add_warning("stimulus_units_blank")

        envelope = AnalyzedQuestionEnvelope(
            question={
                "id": question.get("id"),
                "content": question.get("content", ""),
                "question_type": question.get("question_type"),
                "total_score": question.get("total_score"),
            },
            llm_calls=[LLMCallRecord.model_validate(call) for call in calls],
            analysis_units=fine_grained or {},
            derived={
                "knowledge_points": analysis.get("knowledge_points", []),
                "difficulty": difficulty.get("final_difficulty"),
                "competency": competency.get("primary_competency"),
                "invalid_llm_call_errors": invalid_call_errors,
            },
            confidence=confidence,
            lineage={
                "knowledge_points": "analysis.knowledge_points",
                "difficulty_features": "difficulty.features",
                "competency": "competency",
            },
            warnings=warnings,
        )
        question["_metadata_envelope"] = envelope.model_dump()


    # ── 完整端点编排（从 router 提取）────────────────────────

    async def run_full_analysis(self, file_path: str, filename: str,
                                 mode: str = "deep", generate_report: bool = False,
                                 report_mode: str = "full", reports_dir: str = None,
                                 exam_id: str = None,
                                 exam_review_channel: str | None = None) -> Dict:
        """完整分析流程：文档→拆分→分析→统计→报告。对应 /api/analyze。"""
        doc = await self.process_document(file_path, filename)
        image_bytes = doc["image_bytes"]
        extracted_text = doc["extracted_text"]
        extracted_elements = doc["extracted_elements"]
        document_failure_events = doc.get("failure_events") or []

        if filename.lower().endswith(".docx") and self.word_splitter:
            loop = asyncio.get_event_loop()
            split_result = await loop.run_in_executor(None, self.word_splitter.split, file_path)
            questions = split_result.get("questions", [])
        else:
            questions = await self.split_questions_llm(
                image_bytes,
                extracted_text,
                exam_review_channel=exam_review_channel,
            )

        self.validate_split_integrity(questions, extracted_text)

        if extracted_elements and self.doc_processor:
            self.doc_processor.match_elements_to_questions(questions, extracted_elements)

        if self._accepts_kwarg(self.analyze_questions_batch, "exam_review_channel"):
            questions = await self.analyze_questions_batch(
                questions, image_bytes, mode, exam_review_channel=exam_review_channel
            )
        else:
            questions = await self.analyze_questions_batch(questions, image_bytes, mode)

        competency_summary = self.build_competency_summary(questions)
        exam_statistics = self.aggregate_statistics(questions, competency_summary)
        if document_failure_events:
            exam_statistics["document_failure_events"] = document_failure_events
        from report_data import compute_metadata_quality
        metadata_quality = compute_metadata_quality(questions, exam_statistics=exam_statistics)
        pipeline_audit = self.build_pipeline_audit(metadata_quality)
        self._last_pipeline_audit = pipeline_audit
        channel_usage = self.build_channel_usage(questions)
        self.assert_channel_usage(exam_review_channel, channel_usage)

        report_url = None
        html_report_url = None
        report_error = None
        report_insights = None
        if generate_report and reports_dir:
            self.assert_pipeline_ready(pipeline_audit)
            try:
                from pathlib import Path
                pdf_path = str(Path(reports_dir) / f"{exam_id}.pdf")
                await self.generate_report(
                    questions, competency_summary, exam_statistics,
                    {"name": filename, "total": len(questions), "mode": mode},
                    mode=report_mode,
                    output_path=pdf_path,
                    exam_review_channel=exam_review_channel,
                )
                report_url = f"/api/reports/{exam_id}.pdf"
                if Path(pdf_path).with_suffix(".html").exists():
                    html_report_url = f"/api/reports/{exam_id}.html"
                report_insights = self._last_report_insights
                pipeline_audit = self._last_pipeline_audit or pipeline_audit
                channel_usage = self._last_channel_usage or self.build_channel_usage(questions, report_insights)
                self.assert_channel_usage(
                    exam_review_channel,
                    channel_usage,
                    require_grounding=True,
                )
            except Exception as e:
                logger.exception("[报告生成] 自动分析报告生成失败")
                raise RuntimeError(f"report generation failed: {e}") from e

        return {
            "questions": questions,
            "competency_summary": competency_summary,
            "exam_statistics": exam_statistics,
            "metadata_quality": metadata_quality,
            "pipeline_audit": pipeline_audit,
            "document_failure_events": document_failure_events,
            "report_url": report_url,
            "html_report_url": html_report_url,
            "report_error": report_error,
            "report_insights": report_insights,
            "channel_usage": channel_usage,
        }

    async def run_auto_analysis(self, file_path: str, filename: str,
                                 file_bytes: bytes, mode: str = "deep",
                                 subject: str = "biology",
                                 generate_report: bool = False,
                                 report_mode: str = "full",
                                 reports_dir: str = None,
                                 exam_id: str = None,
                                 exam_review_channel: str | None = None) -> Dict:
        """规则拆分 + 自动分析。对应 /api/analyze_auto 的核心逻辑。"""
        file_ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        document_failure_events = []

        if file_ext == "docx":
            loop = asyncio.get_event_loop()
            split_result = await loop.run_in_executor(
                None, self.word_splitter.split, file_path
            )
            questions = split_result.get("questions", [])
            self.validate_split_integrity(questions)
            images = await loop.run_in_executor(
                None, self.doc_processor.process_docx, file_path
            )
            image_bytes = (
                await loop.run_in_executor(None, self.doc_processor.images_to_bytes, images)
                if images else []
            )
            if images and hasattr(images[0], "info"):
                document_failure_events = images[0].info.get("failure_events") or []
        elif file_ext == "pdf":
            loop = asyncio.get_event_loop()
            split_result = await loop.run_in_executor(
                None, self.pdf_splitter.split, file_path
            )
            questions = split_result.get("questions", [])
            self.validate_split_integrity(questions)
            images = (
                await loop.run_in_executor(None, self.doc_processor.process_pdf, file_path)
                if self.doc_processor else []
            )
            image_bytes = (
                await loop.run_in_executor(None, self.doc_processor.images_to_bytes, images)
                if self.doc_processor and images else []
            )
            if images and hasattr(images[0], "info"):
                document_failure_events = images[0].info.get("failure_events") or []
        else:
            raise ValueError(f"不支持的文件格式: {filename}")

        if self._accepts_kwarg(self.analyze_questions_batch, "exam_review_channel"):
            analyzed = await self.analyze_questions_batch(
                questions, image_bytes, mode, subject, exam_review_channel=exam_review_channel
            )
        else:
            analyzed = await self.analyze_questions_batch(questions, image_bytes, mode, subject)
        competency_summary = self.build_competency_summary(analyzed)
        exam_statistics = self.aggregate_statistics(analyzed, competency_summary)
        if document_failure_events:
            exam_statistics["document_failure_events"] = document_failure_events
        from report_data import compute_metadata_quality
        metadata_quality = compute_metadata_quality(analyzed, exam_statistics=exam_statistics)
        pipeline_audit = self.build_pipeline_audit(metadata_quality)
        self._last_pipeline_audit = pipeline_audit
        channel_usage = self.build_channel_usage(analyzed)
        self.assert_channel_usage(exam_review_channel, channel_usage)

        report_url = None
        html_report_url = None
        report_error = None
        report_insights = None
        if generate_report and reports_dir:
            self.assert_pipeline_ready(pipeline_audit)
            try:
                from pathlib import Path
                pdf_path = str(Path(reports_dir) / f"{exam_id}.pdf")
                report_kwargs = {"mode": report_mode, "output_path": pdf_path}
                if self._accepts_kwarg(self.generate_report, "exam_review_channel"):
                    report_kwargs["exam_review_channel"] = exam_review_channel
                await self.generate_report(
                    analyzed, competency_summary, exam_statistics,
                    {"name": filename, "total": len(analyzed), "mode": mode},
                    **report_kwargs,
                )
                report_url = f"/api/reports/{exam_id}.pdf"
                if Path(pdf_path).with_suffix(".html").exists():
                    html_report_url = f"/api/reports/{exam_id}.html"
                report_insights = self._last_report_insights
                pipeline_audit = self._last_pipeline_audit or pipeline_audit
                channel_usage = self._last_channel_usage or self.build_channel_usage(analyzed, report_insights)
                self.assert_channel_usage(
                    exam_review_channel,
                    channel_usage,
                    require_grounding=True,
                )
            except Exception as e:
                logger.exception("[报告生成] 确认拆分报告生成失败")
                raise RuntimeError(f"report generation failed: {e}") from e

        return {
            "questions": analyzed,
            "split_result": split_result,
            "competency_summary": competency_summary,
            "exam_statistics": exam_statistics,
            "metadata_quality": metadata_quality,
            "pipeline_audit": pipeline_audit,
            "document_failure_events": document_failure_events,
            "report_url": report_url,
            "html_report_url": html_report_url,
            "report_error": report_error,
            "report_insights": report_insights,
            "channel_usage": channel_usage,
        }
