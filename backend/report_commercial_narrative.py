"""Narrative helpers for the report product model.

The model keeps quantitative scoring and teacher-facing wording separate.
These helpers convert structured question and metadata signals into concise
labels used by executive summaries, portfolio rows, and chapter takeaways.
"""
from __future__ import annotations

from typing import Any, Dict


RISK_TERMS = (
    "错误",
    "不准确",
    "不清",
    "不当",
    "矛盾",
    "争议",
    "风险",
    "隐患",
    "误导",
    "缺失",
    "无法",
    "需要复核",
    "需复核",
)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


RISK_NEGATION_PREFIXES = ("无明显", "未发现", "暂无")
RISK_CONTRAST_TERMS = (
    "但",
    "但是",
    "然而",
    "仍",
    "存在",
    "风险",
    "错误",
    "不准确",
    "不清",
    "歧义",
    "缺失",
    "阻断",
    "需要复核",
    "需复核",
)


def contains_risk_text(value: Any) -> bool:
    """Return True only when the text carries an actionable review risk."""
    text = str(value or "").strip()
    if not text or not any(term in text for term in RISK_TERMS):
        return False
    if text.startswith(RISK_NEGATION_PREFIXES) and not any(term in text for term in RISK_CONTRAST_TERMS):
        return False
    return True


_contains_risk_text = contains_risk_text


def _is_data_gap_warning(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith((
        "feature_status:",
        "analysis_failed",
        "difficulty_blocked:",
        "llm_retry:",
        "llm_parse_failure:",
        "diagnostic_units_missing",
        "stimulus_units_missing",
        "stimulus_units_blank",
        "missing_llm_calls",
    ))


def metadata_status(metadata: Dict[str, Any]) -> str:
    """Return pass/warning/blocked from metadata gate fields."""
    blocked = (
        _as_list(metadata.get("missing_envelope_questions"))
        + _as_list(metadata.get("blocked_questions"))
        + _as_list(metadata.get("missing_purpose_questions"))
        + _as_list(metadata.get("evidence_gap_questions"))
    )
    if blocked:
        return "blocked"

    low_confidence = _as_list(metadata.get("low_confidence_questions"))
    warnings = _as_list(metadata.get("warning_questions"))
    retries = _as_list(metadata.get("retry_questions"))
    if low_confidence or warnings or retries:
        return "warning"

    return "pass"


def question_risk_level(question: Dict[str, Any]) -> str:
    """Classify a question for review ordering, not as final quality verdict."""
    raw_quality = question.get("quality_score")
    has_quality_score = isinstance(raw_quality, (int, float))
    quality = _num(raw_quality, 5.0)
    confidence = _num(question.get("metadata_confidence"), 1.0)
    warnings = _as_list(question.get("metadata_warnings"))
    feature_status = str(question.get("feature_status") or "ok").lower()
    issue = primary_issue(question)

    if (
        question.get("analysis_failed")
        or feature_status in {"failed", "missing"}
        or (not has_quality_score and (confidence < 0.7 or warnings))
    ):
        return "data_gap"
    if quality <= 2:
        return "high"
    if _contains_risk_text(issue) and quality <= 3:
        return "high"
    if confidence < 0.7:
        return "data_gap"
    if quality <= 3 or confidence < 0.82 or warnings or feature_status in {"partial", "warning"}:
        return "medium"
    return "low"


def risk_stance(risk_level: str) -> str:
    return {
        "high": "risk",
        "medium": "watch",
        "data_gap": "watch",
        "low": "positive",
    }.get(str(risk_level or "").lower(), "watch")


def primary_issue(question: Dict[str, Any]) -> str:
    """Pick the most useful teacher-facing issue sentence for a question."""
    explicit = question.get("primary_issue")
    if explicit:
        return str(explicit)

    structure_warnings = [str(item) for item in _as_list(question.get("structure_warnings")) if item]
    if structure_warnings:
        return "题面结构需复核：" + "；".join(structure_warnings)

    difficulty_warnings = [str(item) for item in _as_list(question.get("difficulty_review_warnings")) if item]
    if difficulty_warnings:
        return "难度评估需复核：" + "；".join(difficulty_warnings)

    for key in (
        "quality_scientific",
        "quality_feasibility",
        "quality_language",
        "quality_normative",
        "quality_public_opinion",
        "quality_context",
        "teacher_comment",
    ):
        value = question.get(key)
        if value and _contains_risk_text(value):
            return str(value)

    quality = _num(question.get("quality_score"), 5.0)
    confidence = _num(question.get("metadata_confidence"), 1.0)
    warnings = _as_list(question.get("metadata_warnings"))
    feature_status = str(question.get("feature_status") or "ok").lower()
    if question.get("analysis_failed") or feature_status in {"failed", "missing"} or (
        bool(warnings) and all(_is_data_gap_warning(item) for item in warnings)
    ):
        return "分析数据不完整，需要先补齐题目分析、难度特征或元数据记录。"
    if quality <= 2:
        return "质量评分偏低，需要优先复核设问边界、科学性和评分标准。"
    if confidence < 0.7:
        return "元数据置信度偏低，需要先核对题干、答案、解析和分析记录。"
    if warnings:
        return "元数据存在告警，需要人工确认分析链路是否完整。"
    return "未发现显性质量问题"


def action_for_question(question: Dict[str, Any]) -> str:
    risk = question_risk_level(question)
    issue = primary_issue(question)
    if risk == "data_gap":
        return "先补齐分析数据，再判断题目质量和讲评优先级。"
    if risk == "high":
        return "进入人工优先复核清单，确认科学性、设问边界、评分标准和讲评口径。"
    if risk == "medium":
        return "讲评或交付前抽样复核，重点核对元数据告警、语言表述和评分依据。"
    if _contains_risk_text(issue):
        return "保留题目主体，复核问题表述后再进入正式使用。"
    return "保留当前设计，作为同类题目参照。"


def difficulty_thesis(avg_difficulty: Any, gradient_type: str = "") -> str:
    avg = _num(avg_difficulty)
    gradient = str(gradient_type or "难度梯度待确认")
    if avg >= 7:
        return f"整卷难度偏高，{gradient} 是解释学生表现分化的关键线索。"
    if avg >= 6:
        return f"整卷难度处于中高区间，{gradient} 是解释学生表现分化的重要线索。"
    if avg >= 4.5:
        return f"整卷难度整体可控，{gradient} 仍需结合分值权重复核。"
    return f"整卷难度偏低，{gradient} 下需要检查区分度是否足够。"
