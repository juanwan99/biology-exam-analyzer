"""PDF 报告数据聚合层 — 从已有分析结果提取 ReportData 结构。

不含 LLM 调用，不含 IO。纯数据转换。
"""
from typing import List, Dict, Any
from logger import get_logger

logger = get_logger()

# 排除 question_type_factor（题型修正因子，非难度特征维度）
_FEATURE_DIMS = ["bloom", "reasoning_steps", "knowledge_breadth",
                 "info_density", "novelty", "representation_complexity"]

_FEATURE_WEIGHTS = {"bloom": 0.25, "reasoning_steps": 0.20, "knowledge_breadth": 0.15,
                    "info_density": 0.12, "novelty": 0.13, "representation_complexity": 0.15}


def _first_number(*values: Any, default: float = 0.0) -> float:
    for value in values:
        if isinstance(value, (int, float)):
            return value
    return default


def _analysis_dict(q: Dict) -> Dict:
    analysis = q.get("analysis")
    return analysis if isinstance(analysis, dict) else {}


def _score_record(q: Dict, analysis: Dict | None = None) -> tuple[float, Dict[str, Any] | None]:
    analysis = analysis if isinstance(analysis, dict) else _analysis_dict(q)
    candidates = (
        ("total_score", q.get("total_score")),
        ("analysis.total_score", analysis.get("total_score")),
    )
    for source, value in candidates:
        if isinstance(value, (int, float)):
            if value > 0:
                return float(value), None
            return 0.0, {
                "id": q.get("id"),
                "reason": "non_positive_score",
                "source": source,
                "value": value,
            }
        if isinstance(value, str) and value.strip():
            try:
                parsed = float(value)
            except ValueError:
                return 0.0, {
                    "id": q.get("id"),
                    "reason": "invalid_score",
                    "source": source,
                    "value": value,
                }
            if parsed > 0:
                return parsed, None
            return 0.0, {
                "id": q.get("id"),
                "reason": "non_positive_score",
                "source": source,
                "value": parsed,
            }
    return 0.0, {
        "id": q.get("id"),
        "reason": "missing_score",
        "source": "total_score",
        "value": None,
    }


def _list_value(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _first_nonempty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, (list, dict)) and value:
            return value
    return None


def _source_question_text(q: Dict, analysis: Dict | None = None):
    analysis = analysis or {}
    return _first_nonempty(
        q.get("question_text"),
        q.get("content"),
        q.get("stem"),
        analysis.get("question_text"),
        analysis.get("content"),
        analysis.get("stem"),
    )


def _source_answer(q: Dict, analysis: Dict | None = None):
    analysis = analysis or {}
    return _first_nonempty(
        q.get("answer"),
        q.get("correct_answer"),
        q.get("standard_answer"),
        q.get("reference_answer"),
        analysis.get("answer"),
        analysis.get("correct_answer"),
        analysis.get("standard_answer"),
        analysis.get("reference_answer"),
    )


def _metadata_envelope_for_question(q: Dict) -> tuple[Dict, bool]:
    """Return only the explicit metadata envelope.

    Structured analysis outputs are not enough provenance for a formal report.
    """
    envelope = q.get("_metadata_envelope")
    if isinstance(envelope, dict):
        return envelope, False
    return {}, False


_BLOCKING_DIFFICULTY_FLAGS = {
    "big_question_structure_failed",
    "big_question_points_mismatch",
    "feature_extraction_failed",
    "no_evaluation",
    # Legacy reports generated before fail-closed handling used this flag while
    # still emitting a numeric score. Treat it as blocked when rebuilding.
    "big_question_fallback",
}


def _difficulty_failure_reason(q: Dict) -> str | None:
    diff = q.get("difficulty") if isinstance(q.get("difficulty"), dict) else {}
    features = diff.get("features") if isinstance(diff.get("features"), dict) else {}
    flags = [str(flag) for flag in _list_value(diff.get("flags"))]

    if diff.get("analysis_failed"):
        return diff.get("failure_reason") or "analysis_failed"
    for flag in flags:
        if flag in _BLOCKING_DIFFICULTY_FLAGS:
            if flag == "big_question_fallback":
                return "big_question_structure_failed"
            return flag
    if features.get("_feature_status") == "failed":
        return features.get("analysis_failed_reason") or "feature_extraction_failed"
    if diff and not isinstance(diff.get("final_difficulty"), (int, float)):
        return diff.get("failure_reason") or "difficulty_missing"
    return None


def _fine_grained_units(q: Dict) -> Dict:
    analysis = q.get("analysis") if isinstance(q.get("analysis"), dict) else {}
    fine = analysis.get("_fine_grained") if isinstance(analysis, dict) else None
    if isinstance(fine, dict):
        return fine

    direct_keys = ("scoring_units", "diagnostic_units", "stimulus_units")
    if any(key in analysis for key in direct_keys):
        return {
            "scoring_units": _list_value(analysis.get("scoring_units")),
            "diagnostic_units": _list_value(analysis.get("diagnostic_units")),
            "stimulus_units": _list_value(analysis.get("stimulus_units")),
        }
    return {}


def _stimulus_units_blank(units: List[Any]) -> bool:
    if not units:
        return False
    for unit in units:
        if not isinstance(unit, dict):
            return True
        description = str(unit.get("description") or "").strip()
        is_core = bool(unit.get("is_core"))
        complexity = _first_number(unit.get("complexity"), default=0)
        if description and (is_core or complexity > 1):
            return False
    return True


def _call_has_retry_or_parse_failure(call: Dict) -> bool:
    prompt_id = str(call.get("prompt_id") or call.get("prompt") or "").lower()
    metadata = call.get("metadata") if isinstance(call.get("metadata"), dict) else {}
    fallback_count = int(_first_number(call.get("fallback_count"), metadata.get("fallback_count"), default=0))
    retry_count = int(_first_number(call.get("retry_count"), metadata.get("retry_count"), default=0))
    status = str(metadata.get("status") or "").lower()
    recovery_mode = str(metadata.get("recovery_mode") or "").lower()
    recovery_status = str(metadata.get("recovery_status") or "").lower()
    has_final_failure_signal = (
        fallback_count > 0
        or bool(metadata.get("provider_errors"))
        or bool(metadata.get("validation_errors"))
        or bool(call.get("validation_errors"))
        or status in {"failed", "parse_failed", "provider_failed"}
        or recovery_status in {"degraded", "failed"}
        or recovery_mode == "deterministic_length_fallback"
    )
    if call.get("purpose") == "missing_evidence_repair" and not has_final_failure_signal:
        return False
    successful_model_recovery = (
        retry_count > 0
        and recovery_status == "ok"
        and not has_final_failure_signal
    )
    if successful_model_recovery:
        return False
    return (
        "compact_retry" in prompt_id
        or "json_repair" in prompt_id
        or "ultra_compact_retry" in prompt_id
        or "length_recovery" in prompt_id
        or retry_count > 0
        or has_final_failure_signal
        or bool(metadata.get("initial_parse_error"))
    )


def _purpose_satisfied(expected: str, purposes: set[str], q: Dict) -> bool:
    if expected == "feature_extraction":
        return bool(purposes & {"feature_extraction", "big_question_feature_extraction"})
    if expected == "competency_analysis":
        if "competency_analysis" in purposes:
            return True
        fine_grained = _fine_grained_units(q)
        for unit in _list_value(fine_grained.get("scoring_units")):
            if not isinstance(unit, dict):
                continue
            if unit.get("competency") or unit.get("primary_competency"):
                return True
            tags = unit.get("competency_tags")
            if isinstance(tags, list) and any(str(tag).strip() for tag in tags):
                return True
        return False
    return expected in purposes


def _compute_feature_profile(questions: List[Dict]) -> Dict:
    """聚合全卷 6 维特征均值 + 贡献最大的 3 维。"""
    sums = {dim: 0.0 for dim in _FEATURE_DIMS}
    count = 0
    for q in questions:
        diff = q.get("difficulty") if isinstance(q.get("difficulty"), dict) else {}
        features = diff.get("features") if isinstance(diff.get("features"), dict) else {}
        if not features or features.get("_feature_failed"):
            continue
        count += 1
        for dim in _FEATURE_DIMS:
            sums[dim] += features.get(dim, 0)

    avg = {dim: round(sums[dim] / count, 2) if count > 0 else 0 for dim in _FEATURE_DIMS}

    # 贡献最大的 3 维 = 均值 × 权重
    weighted = {dim: avg[dim] * _FEATURE_WEIGHTS[dim] for dim in _FEATURE_DIMS}
    top3 = sorted(weighted, key=weighted.get, reverse=True)[:3]

    return {"avg_per_dimension": avg, "top_difficulty_factors": top3}


def _compute_gradient(curve: List[Dict]) -> Dict:
    """前中后三段分值加权平均难度。"""
    curve = [q for q in curve if isinstance(q.get("difficulty"), (int, float))]
    if len(curve) < 3:
        avg = curve[0]["difficulty"] if curve else 0
        return {"front": avg, "middle": avg, "back": avg, "gradient_type": "题目过少"}

    n = len(curve)
    size = n // 3
    parts = [curve[:size], curve[size:size*2], curve[size*2:]]

    def _wavg(part):
        w = sum(q.get("total_score", 1) for q in part)
        if w > 0:
            return round(sum(q["difficulty"] * q.get("total_score", 1) for q in part) / w, 2)
        return round(sum(q["difficulty"] for q in part) / len(part), 2) if part else 0

    front, middle, back = _wavg(parts[0]), _wavg(parts[1]), _wavg(parts[2])

    if back > middle > front:
        gtype = "前易后难（递增）"
    elif front > middle > back:
        gtype = "前难后易（递减）"
    elif abs(front - middle) < 0.5 and abs(middle - back) < 0.5:
        gtype = "难度均衡"
    else:
        gtype = "难度波动较大"

    return {"front": front, "middle": middle, "back": back, "gradient_type": gtype}


def _extract_question_detail(q: Dict) -> Dict:
    """提取单题详情（精简档+完整档通用）。"""
    diff = q.get("difficulty") if isinstance(q.get("difficulty"), dict) else {}
    features = diff.get("features") if isinstance(diff.get("features"), dict) else {}
    analysis = _analysis_dict(q)
    comp = q.get("competency") if isinstance(q.get("competency"), dict) else {}
    total_score_value, score_issue = _score_record(q, analysis)
    envelope, envelope_inferred = _metadata_envelope_for_question(q)
    envelope_confidence = envelope.get("confidence", {}) if isinstance(envelope, dict) else {}
    envelope_calls = envelope.get("llm_calls", []) if isinstance(envelope, dict) else []
    difficulty_value = diff.get("final_difficulty") if isinstance(diff.get("final_difficulty"), (int, float)) else None
    feature_status = features.get("_feature_status", "ok") if features else "missing"
    difficulty_flags = _list_value(diff.get("flags"))

    detail = {
        "id": q.get("id"),
        "question_text": _source_question_text(q, analysis),
        "answer": _source_answer(q, analysis),
        "total_score": total_score_value,
        "score_status": score_issue["reason"] if score_issue else "valid",
        "score_issue": score_issue,
        "question_type": q.get("question_type", "unknown"),
        # 难度
        "difficulty": difficulty_value,
        "_difficulty_authoritative": difficulty_value is not None,
        "difficulty_flags": difficulty_flags,
        "difficulty_source": diff.get("difficulty_source") or diff.get("source") or "",
        "analysis_failed": bool(diff.get("analysis_failed")),
        "failure_reason": diff.get("failure_reason", ""),
        "difficulty_label": diff.get("difficulty_label") if difficulty_value is not None else "未评估",
        "bloom": features.get("bloom", 3),
        "bloom_reason": features.get("bloom_reason", ""),
        "cognitive_level": diff.get("cognitive_level", 5.0),
        "confidence": diff.get("confidence", 0),
        # 7维 reason
        "steps_detail": features.get("steps_detail", ""),
        "breadth_reason": features.get("breadth_reason", ""),
        "density_reason": features.get("density_reason", ""),
        "novelty_reason": features.get("novelty_reason", ""),
        "representation_reason": features.get("representation_reason", ""),
        # 模型分析结果
        "knowledge_points": analysis.get("knowledge_points", []),
        "detailed_analysis": analysis.get("detailed_analysis", ""),
        "common_mistakes": analysis.get("common_mistakes", []),
        # 分值分布（PR-02: 传递给图表函数避免退化为按题数统计）
        "score_distribution_by_difficulty": diff.get("score_distribution_by_difficulty", {}),
        # 质量审查（v3: 从 feature_extractor 合并）
        "quality_score": features.get("quality_score"),
        "quality_scientific": features.get("quality_scientific", ""),
        "quality_normative": features.get("quality_normative", ""),
        "quality_language": features.get("quality_language", ""),
        "quality_context": features.get("quality_context", ""),
        "teacher_comment": features.get("teacher_comment", ""),
        "bloom_distribution": features.get("bloom_distribution"),
        # 特征状态（四态：ok/partial/failed）
        "feature_status": feature_status,
        # 6 维难度因子原始值（供 SVG 雷达图使用）
        "features": {
            "working_memory": features.get("working_memory", 0),
            "reasoning_steps": features.get("reasoning_steps", 0),
            "chain_coupling": features.get("chain_coupling", 0),
            "trap_density": features.get("trap_density", 0),
            "novelty": features.get("novelty", 0),
            "knowledge_breadth": features.get("knowledge_breadth", 0),
        } if (any(features.get(k) for k in ("working_memory", "reasoning_steps", "chain_coupling",
                                             "trap_density", "novelty", "knowledge_breadth"))
              and features.get("_feature_status", "ok") in ("ok", "partial")) else None,
        # 素养
        "primary_competency": comp.get("primary_competency", ""),
        "competency_level": comp.get("competency_level", ""),
        "competency_details": {
            k: {"涉及": v.get("涉及", False), "权重": v.get("权重", 0), "分析说明": v.get("分析说明", "")}
            for k, v in comp.items()
            if isinstance(v, dict) and "涉及" in v
        },
        "metadata_confidence": envelope_confidence.get("overall", 0),
        "metadata_warnings": envelope.get("warnings", []) if isinstance(envelope, dict) else [],
        "metadata_call_purposes": [
            call.get("purpose") for call in envelope_calls if isinstance(call, dict) and call.get("purpose")
        ],
        "metadata_envelope_source": "structured_inferred" if envelope_inferred else "explicit",
    }

    # === 细粒度数据（Batch 4: SEU/DU 单题提取） ===
    fine_grained = _fine_grained_units(q)
    if fine_grained and fine_grained.get("scoring_units"):
        seus = fine_grained["scoring_units"]
        dus = fine_grained.get("diagnostic_units", [])
        sus = fine_grained.get("stimulus_units", [])

        detail["scoring_units_count"] = len(seus)
        detail["diagnostic_units_count"] = len(dus)
        detail["stimulus_units_count"] = len(sus)
        detail["fine_grained_units"] = {
            "scoring_units": list(seus),
            "diagnostic_units": list(dus),
            "stimulus_units": list(sus),
        }
        detail["allocation_confidence"] = round(
            sum(s.get("allocation_confidence", 0.5) for s in seus) / len(seus), 2
        )

        # 前 2 个最强干扰项（按 trap_strength 降序）
        sorted_dus = sorted(dus, key=lambda d: d.get("trap_strength", 0), reverse=True)
        detail["diagnostic_highlights"] = [
            {"option": d.get("option_or_trap", "?"),
             "misconception": d.get("misconception", ""),
             "trap_strength": d.get("trap_strength", 1)}
            for d in sorted_dus[:2]
        ]

        # SEU 知识点明细（供逐题卡片展示）
        def _get_primary_comp(s):
            cw = s.get("competency_weights")
            if cw and isinstance(cw, dict):
                return max(cw, key=cw.get) if any(cw.values()) else ""
            c = s.get("competency")
            if c and isinstance(c, dict):
                return c.get("primary", "")
            return ""

        detail["seu_knowledge_breakdown"] = [
            {"label": s.get("label", ""),
             "score_share": s.get("score_share", 0),
             "knowledge_links": s.get("knowledge_links", []),
             "bloom_level": s.get("bloom_level", 3),
             "competency": _get_primary_comp(s),
             "competency_weights": s.get("competency_weights", {}),
             "difficulty_estimate": s.get("difficulty_estimate"),
             "allocation_confidence": s.get("allocation_confidence"),
             "allocation_source": s.get("allocation_source"),
             "reasoning_brief": s.get("reasoning_brief", "")}
            for s in seus
        ]

    return detail


def compute_metadata_quality(
    questions: List[Dict],
    min_confidence: float = 0.7,
    exam_statistics: Dict | None = None,
) -> Dict:
    low_confidence = []
    warning_questions = []
    missing_envelope = []
    inferred_envelope = []
    call_counts = {}
    expected_purposes = ("question_analysis", "feature_extraction", "competency_analysis")
    missing_purpose_questions = []
    blocked_questions = []
    evidence_gap_questions = []
    retry_questions = []
    question_text_missing_count = 0
    answer_missing_count = 0
    score_issue_questions = []
    failure_events = []

    if isinstance(exam_statistics, dict) and exam_statistics.get("error"):
        failure_events.append({
            "stage": "exam_statistics",
            "severity": "blocked",
            "reason": exam_statistics.get("error"),
        })
    if isinstance(exam_statistics, dict):
        for event in _list_value(exam_statistics.get("document_failure_events")):
            if isinstance(event, dict):
                failure_events.append(event)

    for q in questions:
        q_id = q.get("id")
        analysis = _analysis_dict(q)
        if not _source_question_text(q, analysis):
            question_text_missing_count += 1
        if not _source_answer(q, analysis):
            answer_missing_count += 1

        total_score, score_issue = _score_record(q, analysis)
        if score_issue:
            score_issue_questions.append(score_issue)
            failure_events.append({
                "stage": "score_extraction",
                "severity": "warning",
                "question_id": q_id,
                "reason": score_issue["reason"],
                "source": score_issue["source"],
                "value": score_issue["value"],
            })

        failure_reason = _difficulty_failure_reason(q)
        if failure_reason:
            blocked_questions.append({"id": q_id, "reason": failure_reason})
            failure_events.append({
                "stage": "difficulty",
                "severity": "blocked",
                "question_id": q_id,
                "reason": failure_reason,
            })

        fine_grained = _fine_grained_units(q)
        if total_score >= 8:
            diagnostic_units = _list_value(fine_grained.get("diagnostic_units"))
            stimulus_units = _list_value(fine_grained.get("stimulus_units"))
            if not diagnostic_units:
                evidence_gap_questions.append({"id": q_id, "reason": "diagnostic_units_missing"})
            if not stimulus_units:
                evidence_gap_questions.append({"id": q_id, "reason": "stimulus_units_missing"})
            elif _stimulus_units_blank(stimulus_units):
                evidence_gap_questions.append({"id": q_id, "reason": "stimulus_units_blank"})

        envelope, envelope_inferred = _metadata_envelope_for_question(q)
        if not isinstance(envelope, dict) or (not envelope and not envelope_inferred):
            missing_envelope.append(q_id)
            continue
        if envelope_inferred:
            inferred_envelope.append(q_id)

        confidence = envelope.get("confidence", {})
        overall = confidence.get("overall", 0) if isinstance(confidence, dict) else 0
        if isinstance(overall, (int, float)) and overall < min_confidence:
            low_confidence.append(q_id)

        warnings = envelope.get("warnings", [])
        if warnings:
            warning_questions.append({"id": q_id, "warnings": list(warnings)})

        purposes_for_question = set()
        for call in envelope.get("llm_calls", []):
            if isinstance(call, dict) and call.get("purpose"):
                purpose = call["purpose"]
                purposes_for_question.add(purpose)
                call_counts[purpose] = call_counts.get(purpose, 0) + 1
                if _call_has_retry_or_parse_failure(call):
                    retry_questions.append({"id": q_id, "purpose": purpose})
        for purpose in expected_purposes:
            if not _purpose_satisfied(purpose, purposes_for_question, q):
                missing_purpose_questions.append({"id": q_id, "purpose": purpose})

    return {
        "total_questions": len(questions),
        "missing_envelope_questions": missing_envelope,
        "inferred_envelope_questions": inferred_envelope,
        "low_confidence_questions": low_confidence,
        "warning_questions": warning_questions,
        "missing_purpose_questions": missing_purpose_questions,
        "blocked_questions": blocked_questions,
        "evidence_gap_questions": evidence_gap_questions,
        "retry_questions": retry_questions,
        "score_issue_questions": score_issue_questions,
        "failure_events": failure_events,
        "question_text_missing_count": question_text_missing_count,
        "answer_missing_count": answer_missing_count,
        "llm_call_counts": call_counts,
        "min_confidence": min_confidence,
    }


def _compute_fine_grained_summary(questions: List[Dict]) -> Dict:
    """全卷 SEU/DU 细粒度汇总（供报告顶部概览使用）。"""
    total_seus = 0
    total_dus = 0
    confidence_sum = 0.0
    inferred_score = 0.0
    total_score_allocated = 0.0
    has_fine_grained = 0

    for q in questions:
        analysis = _analysis_dict(q)
        fg = _fine_grained_units(q)
        if not fg or not fg.get("scoring_units"):
            continue
        has_fine_grained += 1
        q_score, _ = _score_record(q, analysis)
        for seu in fg["scoring_units"]:
            total_seus += 1
            confidence_sum += seu.get("allocation_confidence", 0.5)
            allocated = q_score * seu.get("score_share", 0)
            total_score_allocated += allocated
            if seu.get("allocation_source") == "inferred":
                inferred_score += allocated
        total_dus += len(fg.get("diagnostic_units", []))

    return {
        "total_seus": total_seus,
        "total_dus": total_dus,
        "questions_with_fine_grained": has_fine_grained,
        "questions_total": len(questions),
        "avg_allocation_confidence": round(confidence_sum / total_seus, 2) if total_seus > 0 else 0,
        "inferred_score_pct": round(inferred_score / total_score_allocated * 100, 1) if total_score_allocated > 0 else 0,
    }


def aggregate_report_data(
    questions: List[Dict],
    competency_summary: Dict,
    exam_statistics: Dict,
    exam_info: Dict,
) -> Dict:
    """聚合 PDF 报告所需的全部数据。

    Args:
        questions: 分析完成的题目列表
        competency_summary: 素养聚合结果
        exam_statistics: generate_exam_statistics() 的输出
        exam_info: {"name", "total", "mode"}

    Returns:
        ReportData dict
    """
    logger.info(f"[报告数据] 开始聚合 {len(questions)} 题")

    def _get_score(q):
        """取题目分值，兼容 total_score 在顶层或 analysis 子字典的情况。"""
        score, _ = _score_record(q)
        return score

    competency_summary = competency_summary or {}
    if isinstance(exam_statistics, dict) and exam_statistics.get("error"):
        raise ValueError(f"exam statistics failed: {exam_statistics.get('error')}")
    exam_statistics = exam_statistics or {}
    exam_info = exam_info or {}
    total_score = sum(_get_score(q) for q in questions)
    curve = exam_statistics.get("difficulty_curve", [])

    data = {
        "exam_info": {
            "name": exam_info.get("name", "未命名"),
            "total_questions": exam_info.get("total", len(questions)),
            "total_score": total_score,
            "mode": exam_info.get("mode", "fast"),
        },
        "metrics": {
            "avg_difficulty": exam_statistics.get("avg_difficulty", 0),
            "avg_cognitive_level": exam_statistics.get("avg_cognitive_level", 0),
            "difficulty_distribution": exam_statistics.get("difficulty_distribution", {}),
            "difficulty_distribution_by_score": exam_statistics.get("difficulty_distribution_by_score", {}),
            "bloom_distribution": exam_statistics.get("bloom_distribution", {}),
        },
        "difficulty_curve": curve,
        "difficulty_gradient": _compute_gradient(curve),
        "knowledge": {
            "top_points": exam_statistics.get("top_knowledge_points", []),
            "textbook_distribution": exam_statistics.get("knowledge_textbook_distribution", {}),
            "unmapped_count": exam_statistics.get("knowledge_unmapped_count") or 0,
            "mapped_count": exam_statistics.get("knowledge_mapped_count") or 0,
            "unmapped_points": exam_statistics.get("knowledge_unmapped_points", []),
            "total_knowledge_points": exam_statistics.get("knowledge_total_count") or 0,
            "non_textbook_count": exam_statistics.get("knowledge_non_textbook_count") or 0,
            "non_textbook_points": exam_statistics.get("knowledge_non_textbook_points", []),
        },
        "competency": {
            "distribution": competency_summary,
            "primary_distribution": competency_summary.get("primary_distribution", {}),
            "seu_primary_distribution": competency_summary.get("seu_primary_distribution", {}),
        },
        "feature_profile": _compute_feature_profile(questions),
        "metadata_quality": compute_metadata_quality(questions, exam_statistics=exam_statistics),
        "questions": [_extract_question_detail(q) for q in questions],
        # 细粒度全卷汇总（Batch 4）
        "fine_grained_summary": _compute_fine_grained_summary(questions),
    }

    logger.info(f"[报告数据] 聚合完成，总分={total_score}")
    return data
