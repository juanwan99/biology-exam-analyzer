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


SAFE_DISTRACTOR_TERMS = (
    "干扰项",
    "错误选项",
    "错误设置",
    "错误性逻辑",
    "作为错误选项",
    "错误说法",
)

SAFE_OPTION_TERMS = (
    "选项",
    "A选项",
    "B选项",
    "C选项",
    "D选项",
    "A项",
    "B项",
    "C项",
    "D项",
    "A、B、C、D",
    "A、B、D",
    "B、C、D",
)

SAFE_DESIGN_QUALITY_TERMS = (
    "符合",
    "合理",
    "严谨",
    "唯一",
    "恰当",
    "科学事实",
    "科学准确",
    "考查意图",
    "不影响核心逻辑",
    "有效考查",
)

SAFE_DISTRACTOR_QUALITY_PATTERNS = (
    "错误典型",
    "错误明确",
    "绝对化错误典型",
    "干扰项有效",
    "选项平行",
    "干扰项设置合理",
    "错误说法典型",
)

HARD_RISK_PATTERNS = (
    "科学性错误",
    "答案与事实不符",
    "答案不唯一",
    "题目失效",
    "正确答案",
    "误导性",
    "存在矛盾",
    "舆论隐患",
    "严重",
    "人工复核",
    "需复核",
    "需要复核",
)


BENIGN_NEGATED_RISK_PHRASES = (
    "无明显科学性错误",
    "整体无明显科学性错误",
    "无明显质量问题",
    "无明显问题",
    "未发现显性质量问题",
    "没有明显的歧义",
    "没有明显歧义",
)


TEACHING_DIAGNOSTIC_TERMS = (
    "学生典型错误",
    "典型错误路径",
    "教学建议",
    "教学中",
    "误选",
    "错选",
)


def _review_text(value: str) -> str:
    text = value
    for phrase in BENIGN_NEGATED_RISK_PHRASES:
        text = text.replace(phrase, "")
    return text


def _risk_clauses(text: str) -> list[str]:
    return [
        clause.strip()
        for clause in (
            text.replace("。", "；")
            .replace("，", "；")
            .replace(",", "；")
            .replace("；", "\n")
            .replace(":", "\n")
            .replace("：", "\n")
            .splitlines()
        )
        if clause.strip() and any(term in clause for term in RISK_TERMS)
    ]


def _is_safe_distractor_clause(clause: str) -> bool:
    if any(pattern in clause for pattern in HARD_RISK_PATTERNS):
        return False
    if any(term in clause for term in TEACHING_DIAGNOSTIC_TERMS):
        return True
    has_error_word = "错误" in clause or "不准确" in clause or "不当" in clause
    if not has_error_word:
        return False
    has_option_context = any(term in clause for term in SAFE_OPTION_TERMS)
    has_distractor_context = any(term in clause for term in SAFE_DISTRACTOR_TERMS)
    has_design_quality = any(term in clause for term in SAFE_DESIGN_QUALITY_TERMS)
    has_distractor_quality = any(p in clause for p in SAFE_DISTRACTOR_QUALITY_PATTERNS)
    if has_distractor_quality and (has_option_context or has_distractor_context):
        return True
    return (has_option_context or has_distractor_context) and has_design_quality


def _is_safe_option_design_text(text: str) -> bool:
    if any(pattern in text for pattern in HARD_RISK_PATTERNS):
        return False
    has_error_word = "错误" in text or "不准确" in text or "不当" in text
    has_option_context = any(term in text for term in SAFE_OPTION_TERMS)
    has_distractor_context = any(term in text for term in SAFE_DISTRACTOR_TERMS)
    has_design_quality = any(term in text for term in SAFE_DESIGN_QUALITY_TERMS)
    return has_error_word and (has_option_context or has_distractor_context) and has_design_quality


def _only_safe_distractor_risks(text: str) -> bool:
    clauses = _risk_clauses(text)
    if not clauses:
        return False
    return all(_is_safe_distractor_clause(clause) for clause in clauses) or _is_safe_option_design_text(text)


NEGATION_MARKERS = ("无", "没有", "未", "暂无", "缺乏", "不存在")
ACTION_NEGATION_VERBS = ("说明", "解释", "给出", "指出", "明确", "标注", "标明", "提供", "涉及")
ALWAYS_RISK_TERMS = ("无法", "需复核", "需要复核")
DOUBLE_NEGATION_RISK = (
    "不是没有", "并非没有", "不能说没有", "并非无", "不无",
    "无法排除", "不能排除", "难以排除",
    "无法确认", "不能确认", "难以确认",
    "无法保证", "不能保证",
)


def _has_double_negation_or_uncertainty(clause: str) -> bool:
    return any(p in clause for p in DOUBLE_NEGATION_RISK)


def _split_by_contrast_connectors(clause: str) -> list:
    import re
    parts = re.split(r"但是|但|然而|不过|尽管如此|仍然|仍|却", clause)
    return [p for p in parts if p.strip()] or [clause]


def _risk_term_positions(segment: str) -> list:
    out = []
    for term in RISK_TERMS:
        start = 0
        while True:
            pos = segment.find(term, start)
            if pos < 0:
                break
            out.append((pos, term))
            start = pos + len(term)
    return out


def _risk_term_is_negated(segment: str, idx: int, term: str) -> bool:
    if term in ALWAYS_RISK_TERMS:
        return False
    window = segment[max(0, idx - 12):idx]
    for neg in NEGATION_MARKERS:
        npos = window.rfind(neg)
        if npos < 0:
            continue
        after = window[npos + len(neg):]
        if any(after.startswith(verb) for verb in ACTION_NEGATION_VERBS):
            continue
        return True
    return False


def contains_risk_text(value: Any) -> bool:
    """Return True only when the text carries an actionable review risk.

    通用否定识别：正面评价(无X错误/无歧义)不算风险；双重否定/不确定(不能排除/
    无法确认)与转折后的真风险仍算风险。只判断文本语义，不改难度/质量计算。
    """
    text = str(value or "").strip()
    review_text = _review_text(text)
    if not review_text or not any(term in review_text for term in RISK_TERMS):
        return False
    if _only_safe_distractor_risks(review_text):
        return False
    clauses = _risk_clauses(review_text)
    if not clauses:
        return False
    for clause in clauses:
        if _has_double_negation_or_uncertainty(clause):
            return True
        for segment in _split_by_contrast_connectors(clause):
            for idx, term in _risk_term_positions(segment):
                if not _risk_term_is_negated(segment, idx, term):
                    return True
    return False


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


def _question_failure_reason(question: Dict[str, Any]) -> str:
    difficulty = question.get("difficulty")
    if isinstance(difficulty, dict) and difficulty.get("failure_reason"):
        return str(difficulty.get("failure_reason"))
    return str(question.get("failure_reason") or "")


def _is_quality_blocked(question: Dict[str, Any]) -> bool:
    if _question_failure_reason(question) == "quality_score_too_low":
        return True
    difficulty = question.get("difficulty")
    flags = _as_list(difficulty.get("flags")) if isinstance(difficulty, dict) else []
    return "quality_score_too_low" in {str(flag) for flag in flags}


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

    if _is_quality_blocked(question):
        return "high"
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

    if _is_quality_blocked(question):
        for key in (
            "quality_scientific",
            "quality_normative",
            "quality_language",
            "quality_context",
            "teacher_comment",
        ):
            value = question.get(key)
            if value:
                return f"题目质量阻断：{value}"
        return "题目质量评分低于阈值，需先核对答案、科学性和评分口径。"

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
    if _is_quality_blocked(question):
        return "先核对答案、科学性、设问边界和评分口径；修正前不要纳入难度均值。"
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
