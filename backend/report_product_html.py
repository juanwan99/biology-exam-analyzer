"""HTML renderer for the commercial exam report contract."""
from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List

from report_product_charts import (
    render_figure_chart,
    render_methodology_chart,
    render_portfolio_bubble,
)

FAIL_CLOSED_DIFFICULTY_FLAGS = {
    "big_question_structure_failed",
    "big_question_points_mismatch",
    "points_sum_mismatch",
    "score_share_sum_mismatch",
    "points_unknown",
    "cannot_identify_subquestions",
    "invalid_subquestion_schema",
    "invalid_dependency_ids",
    "insufficient_stem",
    "json_parse_failed",
    "json_truncated",
    "llm_parse_error",
    "llm_parse_failure",
    "provider_failed",
    "quality_score_too_low",
    "question_analysis_failed",
    "feature_extraction_failed",
    "no_evaluation",
    "seu_fallback",
    "big_question_fallback",
}


def _has_fail_closed_difficulty_flag(flags: Iterable[Any]) -> bool:
    return any(str(flag) in FAIL_CLOSED_DIFFICULTY_FLAGS for flag in flags)


def _e(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, default=str)
    return payload.replace("</", "<\\/").replace("<!--", "<\\!--")


def _slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() else "-" for ch in text).strip("-") or "section"


def _icon(name: str) -> str:
    return f'<span class="report-icon icon-{_e(_slug(name))}" aria-hidden="true"></span>'


def _section_heading(number: str, title: str, icon_name: str) -> str:
    return (
        '<div class="section-heading">'
        f'{_icon(icon_name)}'
        '<div>'
        f'<div class="section-label">{_e(number)}</div>'
        f'<h2>{_e(title)}</h2>'
        '</div></div>'
    )


def _call_icon(call_id: Any, stance: Any) -> str:
    if stance == "risk":
        return "risk-high"
    if "metadata" in str(call_id):
        return "metadata"
    if "difficulty" in str(call_id):
        return "gradient"
    if "competency" in str(call_id):
        return "competency"
    if "knowledge" in str(call_id):
        return "knowledge"
    return "executive"


def _figure_icon(figure_id: Any) -> str:
    text = str(figure_id or "")
    if "difficulty" in text:
        return "gradient"
    if "bloom" in text:
        return "bloom"
    if "knowledge" in text:
        return "knowledge"
    if "competency" in text:
        return "competency"
    if "metadata" in text:
        return "metadata"
    if "risk" in text:
        return "risk-high"
    return "figure"


def _purpose_label(value: Any) -> str:
    return {
        "question_analysis": "题目结构分析",
        "feature_extraction": "难度与质量特征抽取",
        "big_question_feature_extraction": "大题结构特征抽取",
        "competency_analysis": "核心素养分析",
        "split_questions": "题目拆分",
        "image_inputs": "图像识别",
        "report_insights": "报告综合分析",
        "report_teaching_suggestions": "教学建议生成",
        "report_grounding_check": "证据核查",
    }.get(str(value), str(value))


def _call_label(value: Any) -> str:
    return {
        "quality_risk": "质量风险",
        "question_quality_risk": "题目质量风险",
        "metadata_governance": "元数据治理",
        "difficulty_structure": "难度结构",
        "competency_gap": "素养覆盖缺口",
        "knowledge_mapping_gap": "知识映射缺口",
        "stable_structure": "结构稳定",
        "fine_grained_fidelity": "审题证据",
        "tail_pressure_source": "后段压力来源",
        "metadata_audit_gap": "元数据审计",
        "metadata_audit_pass": "元数据审计",
        "knowledge_concentration": "知识贡献",
    }.get(str(value), str(value))


def _risk_label(value: Any) -> str:
    return {"high": "高风险", "medium": "关注", "data_gap": "数据缺口", "low": "稳定"}.get(str(value), str(value))


def _status_label(value: Any) -> str:
    return {
        "baseline_visual_big_question_floor": "基础图文大题保底校准",
        "evidence_rich_big_question_floor": "证据丰富大题保底校准",
        "general_visual_big_question_ceiling": "图文大题上限校准",
        "high_value_biotech_synthesis_floor": "高价值生物技术综合保底校准",
        "high_value_breeding_engineering_floor": "高价值育种工程保底校准",
        "seu_extreme_rule_moderation": "采分点极端值校准",
        "seu_low_construct_moderation": "采分点低区分度校准",
        "seu_many_medium_unit_moderation": "多中等采分点校准",
        "compact_seu_bottleneck_lift": "采分点瓶颈难度上调校准",
        "ok": "正常",
        "pass": "通过",
        "warning": "需治理",
        "missing": "缺失",
        "failed": "未通过",
        "high": "高风险",
        "medium": "关注",
        "data_gap": "数据缺口",
        "low": "稳定",
        "biology": "生物",
        "commercial_report.v1": "审题质量报告",
        "inferred": "推断分配",
        "rubric": "评分标准",
        "structured_inferred": "结构化推断",
        "rule_scorer": "规则评分器",
        "analysis_failed": "分析失败",
        "llm": "模型分析",
        "model": "模型分析",
        "pipeline.final": "流水线最终结果",
        "text": "文字材料",
        "multi": "复合材料",
        "image": "图像材料",
        "table": "表格材料",
        "chart": "图表材料",
        "flowchart": "流程图",
        "pedigree": "系谱图",
        "calculation_trap": "计算陷阱",
        "reading_trap": "阅读陷阱",
        "misconception": "概念误区",
        "typical_misconception": "典型误区",
        "partial_truth": "部分正确干扰",
        "trap_1": "陷阱 1",
        "trap 1": "陷阱 1",
        "trap_2": "陷阱 2",
        "trap 2": "陷阱 2",
        "trap_3": "陷阱 3",
        "trap 3": "陷阱 3",
        "trap_4": "陷阱 4",
        "trap 4": "陷阱 4",
        "bounded_item_seu_ceiling": "有限题型难度上限校准",
        "seu_no_top_bottleneck_moderation": "采分点无最高瓶颈时的难度校准",
        "media_representation_adjustment": "图表/材料表征负荷校准",
        "seu_bottleneck_adjustment": "采分点瓶颈校准",
        "visual_seu_evidence_floor": "图像证据下限校准",
        "fragmented_medium_big_item_moderation": "中等大题分散采分校准",
        "seu_bottleneck_crosscheck": "采分点瓶颈交叉校验",
        "visual_diagnostic_burden_adjustment": "图像诊断负荷校准",
        "diagnostic_burden_adjustment": "诊断负荷校准",
        "rule_llm_mismatch": "规则特征与模型判断不一致",
        "choice_decision_trap_adjustment": "选择题决策陷阱校准",
        "choice_strong_misconception_lift": "强误区干扰项校准",
        "big_question_structure_failed": "大题结构解析失败",
        "big_question_points_mismatch": "大题采分点与分值不一致",
        "points_sum_mismatch": "采分点分值合计不一致",
        "score_share_sum_mismatch": "采分点占比合计不一致",
        "points_unknown": "采分点分值未知",
        "cannot_identify_subquestions": "无法识别小问边界",
        "invalid_subquestion_schema": "小问结构不合法",
        "invalid_dependency_ids": "小问依赖关系不合法",
        "insufficient_stem": "题干证据不足",
        "json_parse_failed": "结构化结果解析失败",
        "json_truncated": "结构化结果截断",
        "llm_parse_error": "模型结果解析错误",
        "llm_parse_failure": "模型结果解析失败",
        "provider_failed": "模型服务调用失败",
        "quality_score_too_low": "质量评分过低",
        "question_analysis_failed": "题目分析失败",
        "feature_extraction_failed": "特征抽取失败",
        "no_evaluation": "未形成有效评估",
        "seu_fallback": "采分点拆解失败",
        "big_question_fallback": "大题结构分析失败",
    }.get(str(value), str(value))


def _field_label(value: Any) -> str:
    return {
        "metadata": "元数据",
        "metadata_confidence": "元数据置信度",
        "metadata_warnings": "元数据告警",
        "diagnostic_highlights": "诊断要点",
        "knowledge_points": "知识点",
        "primary_competency": "核心素养",
        "seu_knowledge_breakdown": "采分点-知识素养拆解",
        "life_concept": "生命观念",
        "scientific_thinking": "科学思维",
        "scientific_inquiry": "科学探究",
        "social_responsibility": "社会责任",
        "working_memory": "工作记忆负荷",
        "reasoning_steps": "推理步数",
        "chain_coupling": "链路耦合度",
        "trap_density": "陷阱密度",
        "novelty": "情境新颖度",
        "knowledge_breadth": "知识跨度",
        "bloom": "布卢姆层级",
        "quality_score": "质量评分",
        "quality_scientific": "科学性",
        "quality_normative": "规范性",
        "quality_language": "语言清晰度",
        "quality_context": "情境质量",
        "teacher_comment": "教师评语",
        "warning_questions": "告警题目",
        "missing_envelope_questions": "缺失元数据包题目",
        "llm_call_counts": "AI 调用次数",
        "difficulty_gradient": "逐题难度",
        "bloom_distribution": "认知层级分布",
        "knowledge_top_points": "高频知识点",
        "competency_distribution": "核心素养分布",
        "risk_distribution": "风险分布",
        "metadata_quality": "元数据质量",
        "metrics": "指标",
        "knowledge": "知识点",
        "top": "高频",
        "points": "项",
        "top_points": "高频项",
        "difficulty_factor_rows": "题目压力矩阵",
        "seu_rows": "采分点矩阵",
        "du_rows": "误区诊断图",
        "competency_detail_rows": "二级素养明细",
        "competency_evidence_rows": "二级素养证据",
        "competency": "核心素养",
        "distribution": "分布",
        "question": "题目",
        "risk": "风险",
        "bloom": "认知层级",
        "risk_level": "风险等级",
        "question_id": "题号",
        "seu_id": "采分点",
        "du_id": "误区诊断点",
        "label": "证据描述",
        "score_share": "分值占比",
        "weighted_score": "贡献分",
        "allocation_source": "分配来源",
        "allocation_confidence": "分配置信度",
        "knowledge_point": "知识点",
        "knowledge_links": "知识点权重",
        "competency_weights": "素养权重",
        "bloom_level": "认知层级",
        "difficulty_estimate": "难度估计",
        "option_or_trap": "选项/陷阱",
        "distractor_type": "干扰类型",
        "misconception": "典型误区",
        "trap_strength": "陷阱强度",
        "knowledge_boundary": "知识边界",
        "difficulty": "难度",
        "score": "分值",
        "quality_level": "质量等级",
        "primary_issue": "核心问题",
        "evidence_refs": "证据引用",
        "action": "动作建议",
        "exam_info": "考试信息",
        "total_questions": "题目总数",
        "fine_grained_summary": "审题证据概览",
        "fine_grained_units": "审题证据单元",
        "scoring_units": "评分单元",
        "diagnostic_units": "诊断单元",
        "stimulus_units": "情境单元",
    }.get(str(value), str(value).replace("_", " "))


def _localize_text(value: Any) -> str:
    text = str(value)
    replacements = {
        "metadata envelope": "元数据包",
        "LLM purpose": "AI 调用目的",
        "warning_questions": "告警题目",
        "missing_envelope_questions": "缺失元数据包题目",
        "metadata_quality": "元数据质量",
        "metadata_confidence": "元数据置信度",
        "warning": "告警题",
        "missing": "缺失项",
        "score share": "分值占比",
        "knowledge links": "知识点权重",
        "competency weights": "素养权重",
        "bloom level": "认知层级",
        "allocation source": "分配来源",
        "allocation confidence": "分配置信度",
        "difficulty estimate": "难度估计",
        "knowledge point": "知识点",
        "trap strength": "陷阱强度",
        "knowledge boundary": "知识边界",
        "metadata": "元数据",
        "Bloom": "认知层级",
        "partial truth": "部分正确干扰",
        "reading trap": "阅读陷阱",
        "calculation trap": "计算陷阱",
        "typical misconception": "典型误区",
        "partial truth": "部分正确干扰",
        "rule scorer": "规则评分器",
        "bounded item seu ceiling": "有限题型难度上限校准",
        "seu no top bottleneck moderation": "采分点无最高瓶颈时的难度校准",
        "fine grained summary": "审题证据概览",
        "fine grained units": "审题证据单元",
        "scoring units": "评分单元",
        "diagnostic units": "诊断单元",
        "stimulus units": "情境单元",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _ref_label(value: Any) -> str:
    text = str(value or "")
    mapping = {
        "metadata:warning_questions": "元数据：告警题目",
        "metadata:missing_envelope_questions": "元数据：缺失元数据包题目",
        "metadata:llm_call_counts": "元数据：AI 调用次数",
        "report_data.difficulty_gradient": "报告数据：难度梯度",
        "report_data.metadata_quality": "报告数据：元数据质量",
        "fine_grained_exhibits.seu_rows + report_data.knowledge.top_points": "审题证据：知识点聚合",
        "fine_grained_exhibits.knowledge_contribution_rows": "审题证据：知识点贡献表",
        "fine_grained_exhibits.difficulty_factor_rows": "审题证据：题目压力矩阵",
        "fine_grained_exhibits.seu_rows": "审题证据：采分点矩阵",
        "fine_grained_exhibits.du_rows": "审题证据：误区诊断图",
        "fine_grained_exhibits.competency_detail_rows": "审题证据：二级素养明细",
        "question_portfolio.risk_level": "题目组合：风险等级",
        "metric:avg_difficulty": "指标：平均难度",
        "knowledge:unmapped_count": "知识点：未映射数量",
        "risk:high_count": "风险：高风险题数量",
    }
    if text in mapping:
        return mapping[text]
    if text.startswith("report_data."):
        parts = text.split(".")[1:]
        return "报告数据：" + " / ".join(_field_label(part) for part in parts)
    if text.startswith("exam_info."):
        parts = text.split(".")[1:]
        return "考试信息：" + " / ".join(_field_label(part) for part in parts)
    if text.startswith("fine_grained_exhibits."):
        parts = text.split(".")[1:]
        return "审题证据：" + " / ".join(_field_label(part) for part in parts)
    match = re.fullmatch(r"figure:([A-Za-z0-9_. -]+)", text)
    if match:
        figure_key = match.group(1).strip().replace(" ", "_").replace("-", "_")
        return "图表：" + _field_label(figure_key)
    match = re.fullmatch(r"seu:Q?(\d+):(.+)", text)
    if match:
        unit = re.sub(r"(?i)^q?\d+[-_: ]*seu[-_: ]*", "", match.group(2)).strip()
        unit = re.sub(r"(?i)^seu[-_: ]*", "", unit).strip()
        return f"第 {match.group(1)} 题：采分点 {unit or '1'}"
    match = re.fullmatch(r"metadata:Q?(\d+)", text)
    if match:
        return f"第 {match.group(1)} 题：元数据审计"
    match = re.fullmatch(r"question:Q?(\d+)\.(pressure|metadata|quality)", text)
    if match:
        suffix = {"pressure": "压力来源", "metadata": "元数据", "quality": "质量"}.get(match.group(2), "证据")
        return f"第 {match.group(1)} 题：{suffix}"
    match = re.fullmatch(r"question:(\d+)(?:\.(metadata|quality))?", text)
    if match:
        suffix = {"metadata": "：元数据", "quality": "：质量"}.get(match.group(2), "")
        return f"第 {match.group(1)} 题{suffix}"
    return _field_label(_status_label(text))


def _source_label(value: Any) -> str:
    label = _ref_label(value)
    if str(value or "") == "report_data.difficulty_gradient":
        return f"{label}；来源：报告数据：逐题难度"
    return label


def _display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "、".join(_display_value(item) for item in value)
    if isinstance(value, dict):
        return "；".join(f"{_field_label(key)}：{_display_value(val)}" for key, val in value.items())
    text = _status_label(value)
    return _localize_text(_field_label(text))


def _txt(value: Any) -> str:
    return _e(_display_value(value))


def _prompt_summary(item: Dict[str, Any]) -> str:
    purpose = str(item.get("purpose") or "")
    return {
        "question_analysis": "识别题干、设问、答案与解析结构，抽取可追溯的题目级元数据。",
        "feature_extraction": "分析难度驱动因素、命题质量、知识跨度与教学价值。",
        "big_question_feature_extraction": "抽取大题内部结构、跨小题依赖和整体命题压力。",
        "competency_analysis": "将知识点映射到核心素养维度，形成素养覆盖判断。",
        "split_questions": "将试卷拆分为稳定题目单元，为后续诊断提供边界。",
    }.get(purpose, _display_value(item.get("prompt")))


def _gate_label(value: Any) -> str:
    return {
        "metadata envelope required": "必须具备完整元数据包",
        "question_analysis required": "必须完成题目结构分析",
        "feature_extraction or big_question_feature_extraction required": "必须完成特征抽取或大题特征抽取",
        "competency_analysis or scoring-unit-derived competency required": "必须完成核心素养分析或采分点派生素养",
    }.get(str(value), str(value))


def _stance_class(value: Any) -> str:
    return {
        "positive": "stance-positive",
        "watch": "stance-watch",
        "risk": "stance-risk",
    }.get(str(value or "").lower(), "stance-watch")


def _risk_class(value: Any) -> str:
    return {
        "high": "risk-high",
        "medium": "risk-medium",
        "data_gap": "risk-medium",
        "low": "risk-low",
    }.get(str(value or "").lower(), "risk-medium")


def _render_list(items: Iterable[Any], empty: str = "暂无") -> str:
    rows = [f"<li>{_e(_display_value(item))}</li>" for item in items if str(item).strip()]
    if not rows:
        rows.append(f'<li class="muted">{_e(empty)}</li>')
    return f"<ul>{''.join(rows)}</ul>"


def _render_evidence(refs: Any, compact_question_label: bool = False) -> str:
    labels = []
    for ref in _items(refs):
        label = _ref_label(ref)
        if compact_question_label:
            label = re.sub(r"^第\s*\d+\s*题[：:]\s*", "", label).strip()
        labels.append(label)
    text = "、".join(labels) if labels else "证据引用缺失"
    return (
        '<div class="evidence-row evidence-text-row">'
        '<span class="evidence-label">证据：</span>'
        f'<span class="evidence-text">{_e(text)}</span>'
        '</div>'
    )


def _render_data(value: Any) -> str:
    if isinstance(value, dict):
        rows = "".join(
            f"<tr><th>{_e(_field_label(key))}</th><td>{_e(_display_value(val))}</td></tr>"
            for key, val in value.items()
        )
        return f'<table class="data-table"><tbody>{rows}</tbody></table>'
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            keys = []
            for item in value:
                for key in item:
                    if key not in keys:
                        keys.append(key)
            head = "".join(f"<th>{_e(_field_label(key))}</th>" for key in keys)
            body = "".join(
                "<tr>" + "".join(f"<td>{_e(_display_value(item.get(key)))}</td>" for key in keys) + "</tr>"
                for item in value
            )
            return f'<table class="data-table compact-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
        rows = "".join(f"<li>{_e(_display_value(item))}</li>" for item in value)
        return f"<ul>{rows}</ul>" if rows else '<p class="muted">暂无数据</p>'
    if value is None:
        return '<p class="muted">暂无数据</p>'
    return f"<p>{_e(_display_value(value))}</p>"


def _detail_cell(label: str, value: Any) -> str:
    return f'<td data-label="{_e(label)}">{_e(_display_value(value))}</td>'


def _question_id_list(values: Any) -> str:
    labels = []
    for item in _items(values):
        if isinstance(item, (int, float)):
            labels.append(f"Q{int(item)}")
        elif item:
            text = str(item)
            labels.append(text if text.startswith("Q") else f"Q{text}")
    return "、".join(labels) if labels else "暂无题号"


def _render_detail_table(title: str, columns: List[tuple[str, Any]], rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    head = "".join(f"<th>{_e(label)}</th>" for label, _ in columns)
    body_rows = []
    for row in rows:
        cells = []
        for label, getter in columns:
            value = getter(row) if callable(getter) else row.get(str(getter))
            cells.append(_detail_cell(label, value))
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        '<details class="figure-details">'
        "<summary>展开完整明细</summary>"
        '<div class="figure-detail-body">'
        f'<div class="figure-detail-title">{_e(title)}</div>'
        '<table class="data-table figure-detail-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        "</div>"
        "</details>"
    )


def _render_figure_details(figure: Dict[str, Any]) -> str:
    figure_id = str(figure.get("id") or "")
    rows = [_dict(row) for row in _items(figure.get("data"))]
    data = _dict(figure.get("data"))
    if figure_id == "competency_distribution":
        return '<p class="figure-evidence-note">采分点级证据见后文单题审查。</p>'
    if figure_id == "du_trap_map":
        return _render_detail_table(
            "完整误区诊断点",
            [
                ("题号", lambda row: f"Q{row.get('question_id')}"),
                ("陷阱/选项", lambda row: row.get("option_or_trap") or row.get("du_id")),
                ("误区诊断", "misconception"),
                ("知识边界", "knowledge_boundary"),
                ("强度", "trap_strength"),
                ("题目难度", "question_difficulty"),
            ],
            rows,
        )
    if figure_id == "seu_competency_matrix":
        return _render_detail_table(
            "完整采分点明细",
            [
                ("题号", lambda row: f"Q{row.get('question_id')}"),
                ("采分点", "label"),
                ("知识点", "knowledge_point"),
                ("核心素养", "competency"),
                ("认知层级", "bloom_level"),
                ("估计难度", "difficulty_estimate"),
                ("分值贡献", "weighted_score"),
                ("推理说明", "reasoning_brief"),
            ],
            rows,
        )
    if figure_id == "knowledge_top_points":
        return _render_detail_table(
            "完整知识点明细",
            [
                ("知识点", "name"),
                ("分值权重", "weighted_score"),
                ("题数", "question_count"),
                ("风险题", "risk_count"),
                ("采分点", "seu_count"),
                ("平均层级", "avg_bloom"),
            ],
            rows,
        )
    return ""


def _pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if 0 <= number <= 1:
        return f"{number * 100:.0f}%"
    return f"{number:.1f}%"


def _short_unit_id(value: Any, prefix: str) -> str:
    text = str(value or "").strip()
    text = re.sub(rf"(?i)^q?\d+[-_: ]*{prefix}[-_: ]*", "", text)
    text = re.sub(rf"(?i)^{prefix}[-_: ]*", "", text)
    return text or "1"


def _render_score_bar(value: Any) -> str:
    try:
        number = max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        number = 0
    return (
        '<div class="score-bar" aria-hidden="true">'
        f'<span style="width:{number * 100:.1f}%"></span>'
        '</div>'
    )


def _render_weight_tags(items: Any, key_name: str, label_name: str) -> str:
    tags = []
    if isinstance(items, dict):
        iterable = [{"name": key, "share": val} for key, val in items.items()]
    else:
        iterable = [
            {"name": _dict(item).get(key_name), "share": _dict(item).get(label_name)}
            for item in _items(items)
        ]
    for item in iterable:
        name = item.get("name")
        if not name:
            continue
        tags.append(
            '<span class="weight-tag">'
            f'<b>{_txt(name)}</b><em>{_e(_pct(item.get("share")))}</em>'
            '</span>'
        )
    return "".join(tags) if tags else '<span class="muted">未标注</span>'


def _render_seu_cards(units: Any) -> str:
    cards = []
    for index, unit in enumerate(_items(units), 1):
        unit = _dict(unit)
        share = unit.get("score_share", 0)
        cards.append(
            '<article class="evidence-unit-card">'
            '<div class="unit-card-head">'
            f'<span>采分点 {_e(_short_unit_id(unit.get("seu_id"), "seu"))}</span>'
            f'<strong>{_e(_pct(share))}</strong>'
            '</div>'
            f'{_render_score_bar(share)}'
            f'<p class="unit-title">{_txt(unit.get("label") or f"采分单元 {index}")}</p>'
            '<div class="unit-metrics">'
            f'<span>来源：{_txt(unit.get("allocation_source"))}</span>'
            f'<span>置信度：{_e(_pct(unit.get("allocation_confidence")))}</span>'
            f'<span>认知层级：{_e(_display_value(unit.get("bloom_level")))}</span>'
            '</div>'
            '<div class="unit-evidence-block"><b>知识点权重</b>'
            f'<div class="weight-tags">{_render_weight_tags(unit.get("knowledge_links"), "knowledge_point", "share")}</div>'
            '</div>'
            '<div class="unit-evidence-block"><b>素养权重</b>'
            f'<div class="weight-tags">{_render_weight_tags(unit.get("competency_weights"), "name", "share")}</div>'
            '</div>'
            '</article>'
        )
    if not cards:
        cards.append('<p class="muted">暂无采分点拆解</p>')
    return f'<div class="evidence-unit-grid">{"".join(cards)}</div>'


def _render_du_cards(units: Any) -> str:
    cards = []
    for index, unit in enumerate(_items(units), 1):
        unit = _dict(unit)
        strength = unit.get("trap_strength", 0)
        cards.append(
            '<article class="du-unit-card">'
            '<div class="unit-card-head">'
            f'<span>误区卡点 {_e(_short_unit_id(unit.get("du_id"), "du"))}</span>'
            f'<strong>强度 {_e(_display_value(strength))}</strong>'
            '</div>'
            f'<p class="unit-title">{_txt(unit.get("misconception") or f"误区诊断点 {index}")}</p>'
            '<div class="unit-metrics">'
            f'<span>选项/陷阱：{_txt(unit.get("option_or_trap"))}</span>'
            f'<span>类型：{_txt(unit.get("distractor_type"))}</span>'
            '</div>'
            f'<p class="unit-boundary"><b>知识边界</b>{_txt(unit.get("knowledge_boundary"))}</p>'
            '</article>'
        )
    if not cards:
        cards.append('<p class="data-failure">误区诊断未抽取成功；不能据此判断学生没有误区。</p>')
    return f'<div class="du-unit-grid">{"".join(cards)}</div>'


def _render_su_cards(units: Any) -> str:
    cards = []
    for index, unit in enumerate(_items(units), 1):
        unit = _dict(unit)
        cards.append(
            '<article class="su-unit-card">'
            f'<span>材料与情境信息 {_e(_short_unit_id(unit.get("su_id"), "su"))}</span>'
            f'<b>{_txt(unit.get("stimulus_type") or unit.get("type") or f"材料单元 {index}")}</b>'
            f'<p>{_txt(unit.get("description") or "材料描述缺失；不能据此判断材料负担。")}</p>'
            '</article>'
        )
    return f'<div class="su-unit-grid">{"".join(cards)}</div>' if cards else ""


def _render_nav() -> str:
    links = [
        ("hero", "封面"),
        ("summary", "执行摘要"),
        ("glance", "一页速览"),
        ("chapters", "章节"),
        ("portfolio", "题目组合"),
        ("deep-dives", "单题审查"),
        ("methodology", "方法论"),
    ]
    return (
        '<a class="skip-link" href="#main-content">跳到主要内容</a>'
        '<nav class="top-nav" aria-label="报告导航">'
        f'<div class="brand">{_icon("brand")}<span>审题与审卷质量诊断报告</span></div>'
        '<div class="nav-links">'
        + "".join(f'<a href="#{href}">{label}</a>' for href, label in links)
        + "</div></nav>"
    )


def _render_hero(model: Dict[str, Any]) -> str:
    cover = _dict(model.get("cover"))
    credibility = _dict(model.get("credibility"))
    scope = _dict(credibility.get("analysis_scope"))
    metrics = [
        ("scope", "题目数", scope.get("questions", "-")),
        ("score", "总分", scope.get("total_score", "-")),
        ("metadata", "元数据状态", _status_label(credibility.get("metadata_status", "-"))),
        ("llm", "AI 调用", credibility.get("llm_calls_total", "-")),
    ]
    metric_html = "".join(
        f'<div class="hero-metric">{_icon(icon)}<span>{_e(label)}</span><strong>{_e(value)}</strong></div>'
        for icon, label, value in metrics
    )
    return (
        '<section class="hero" id="hero">'
        '<div class="hero-kicker">审题与审卷质量诊断</div>'
        f'<h1>{_e(cover.get("title", "AI 审题与审卷质量诊断报告"))}</h1>'
        f'<p class="exam-name">{_e(cover.get("exam_name", "未命名试卷"))}</p>'
        f'<p class="hero-note">{_e(credibility.get("method_note", ""))}</p>'
        f'<div class="hero-metrics">{metric_html}</div>'
        '<div class="hero-footer">'
        f'<span>{_e(_status_label(cover.get("subject", "")))}</span>'
        f'<span>{_e(cover.get("generated_at", ""))}</span>'
        "</div>"
        "</section>"
    )


def _render_evidence_integrity(model: Dict[str, Any]) -> str:
    methodology = _dict(model.get("methodology"))
    integrity = _dict(model.get("evidence_integrity")) or _dict(methodology.get("evidence_integrity"))
    items = [_dict(item) for item in _items(integrity.get("items"))]
    explanations = [_dict(item) for item in _items(integrity.get("failure_explanations"))]
    if not items and not explanations:
        return ""
    cards = []
    for item in items:
        severity = item.get("severity", "info")
        cards.append(
            f'<article class="integrity-card integrity-{_e(severity)}">'
            f'<span>{_e(item.get("title", "证据提示"))}</span>'
            f'<strong>{_e(_display_value(item.get("value")))}</strong>'
            f'<p>{_txt(item.get("detail"))}</p>'
            "</article>"
        )
    explanation_html = _render_failure_explanations(explanations[:8], compact=False)
    missing_purpose_questions = [
        _dict(item) for item in _items(integrity.get("missing_purpose_questions"))
        if isinstance(item, dict)
    ]
    missing_ids = []
    for item in missing_purpose_questions:
        qid = item.get("id")
        if qid not in missing_ids and qid not in (None, ""):
            missing_ids.append(qid)
    missing_text = ""
    if missing_ids:
        missing_text = (
            '<p class="integrity-note">'
            f'调用链缺口涉及：{_e(", ".join(f"Q{qid}" for qid in missing_ids[:10]))}'
            "</p>"
        )
    return (
        '<aside class="evidence-integrity-panel">'
        '<div class="panel-heading"><span>证据完整性提示</span></div>'
        '<p>以下项目不是新的质量结论，而是说明当前报告哪些地方来自规则推断、结构化回退或缺失摘录，便于老师复核时把握证据边界。</p>'
        f'<div class="integrity-grid">{"".join(cards)}</div>'
        f'{explanation_html}'
        f'{missing_text}'
        "</aside>"
    )


def _render_failure_explanations(explanations: List[Dict[str, Any]], compact: bool = False) -> str:
    rows = []
    for item in explanations:
        qid = item.get("question_id")
        q_label = f"Q{qid} · " if qid not in (None, "") else ""
        severity = item.get("severity", "warning")
        rows.append(
            f'<article class="failure-explain failure-{_e(severity)}">'
            f'<div class="failure-title"><strong>{_e(q_label)}{_e(item.get("title", "数据异常"))}</strong>'
            f'<span>{_e(item.get("stage", "数据质量检查"))}</span></div>'
            f'<p>{_txt(item.get("reason", "未记录具体原因"))}</p>'
            f'<ul>'
            f'<li><b>影响</b>{_txt(item.get("impact", "相关结论需要人工复核。"))}</li>'
            f'<li><b>处理</b>{_txt(item.get("action", "请查看元数据追踪后重新分析。"))}</li>'
            f'</ul>'
            f'</article>'
        )
    if not rows:
        return ""
    title = "失败原因说明" if not compact else "失败原因"
    return f'<div class="failure-explain-list"><h4>{title}</h4>{"".join(rows)}</div>'


def _render_summary(model: Dict[str, Any]) -> str:
    summary = _dict(model.get("executive_summary"))
    verdict = _dict(summary.get("overall_verdict"))
    priorities = [_dict(item) for item in _items(summary.get("teacher_priorities"))]
    student_fit = _dict(summary.get("student_fit"))
    scale = _dict(summary.get("evidence_scale"))
    cards = []

    if verdict:
        cards.append(
            f'<article class="big-call {_stance_class(verdict.get("stance"))}">'
            '<div class="call-heading">'
            f'{_icon("executive")}'
            '<div>'
            f'<div class="call-id">{_e(verdict.get("label", "总体判断"))}</div>'
            '<h3>总体结论</h3>'
            '<div class="call-subtitle">总体使用建议</div>'
            '</div></div>'
            f'<p>{_txt(verdict.get("teacher_takeaway") or summary.get("lead_judgment", ""))}</p>'
            f'<div class="action-line"><b>学情适配</b><span>{_txt(student_fit.get("teacher_note", "需结合班级实际水平复核使用。"))}</span></div>'
            "</article>"
        )

    for item in priorities:
        cards.append(
            f'<article class="big-call {_stance_class(item.get("stance", "watch"))}">'
            '<div class="call-heading">'
            f'{_icon(_call_icon(item.get("id"), item.get("stance", "watch")))}'
            '<div>'
            '<div class="call-id">教师行动</div>'
            f'<h3>{_e(item.get("title"))}</h3>'
            '</div></div>'
            f'<p>{_txt(item.get("summary"))}</p>'
            "</article>"
        )

    if scale:
        scale_items = [
            ("覆盖题目", scale.get("questions")),
            ("采分点", scale.get("scoring_units")),
            ("误区诊断点", scale.get("diagnostic_units")),
            ("阻断题", scale.get("blocked_items")),
            ("优先复核题", scale.get("reviewed_risk_items")),
        ]
        scale_html = "".join(
            '<div class="summary-scale-item">'
            f'<span>{_e(label)}</span>'
            f'<strong>{_e(_display_value(value))}</strong>'
            '</div>'
            for label, value in scale_items
        )
        cards.append(
            '<article class="big-call stance-positive summary-scale-card">'
            '<div class="call-heading">'
            f'{_icon("metadata")}'
            '<div><div class="call-id">证据规模</div><h3>本报告依据哪些材料</h3></div>'
            '</div>'
            '<p>摘要只保留证据覆盖范围；具体采分点、误区诊断和元数据追踪放在后文展开。</p>'
            f'<div class="summary-scale">{scale_html}</div>'
            "</article>"
        )

    if not cards:
        cards.append('<p class="muted">暂无执行摘要结论</p>')
    return (
        '<section class="report-section" id="summary">'
        f'{_section_heading("01", "执行摘要", "executive")}'
        f'<p class="lead-judgment">{_txt(summary.get("lead_judgment", ""))}</p>'
        f'<div class="big-call-grid summary-card-grid">{"".join(cards)}</div>'
        f'{_render_evidence_integrity(model)}'
        "</section>"
    )


def _render_glance(model: Dict[str, Any]) -> str:
    cards = []
    for item in _items(model.get("at_a_glance")):
        cards.append(
            '<article class="glance-card">'
            f'{_icon("glance")}'
            f'<span>{_e(item.get("metric"))}</span>'
            f'<strong>{_e(_display_value(item.get("value")))}</strong>'
            f'<p>{_txt(item.get("interpretation"))}</p>'
            f'<em>{_e(_ref_label(item.get("evidence_ref")))}</em>'
            "</article>"
        )
    if not cards:
        cards.append('<p class="muted">暂无关键指标</p>')
    return (
        '<section class="report-section compact" id="glance">'
        f'{_section_heading("02", "一页速览", "glance")}'
        f'<div class="glance-grid">{"".join(cards)}</div>'
        "</section>"
    )


def _render_figure(figure: Dict[str, Any]) -> str:
    figure_id = str(figure.get("id") or "")
    wide_class = " wide-figure" if figure_id in {
        "fine_grained_heatmap",
        "seu_competency_matrix",
        "du_trap_map",
        "question_portfolio",
        "methodology_llm",
    } else ""
    chart = render_figure_chart(figure)
    chart_html = (
        f'<div class="chart-frame"><div class="chart-kicker">图表展板</div>{chart}</div>'
        if chart else
        f'<div class="chart-frame chart-fallback"><div class="chart-kicker">证据展板</div>{_render_data(figure.get("data"))}</div>'
    )
    details_html = _render_figure_details(figure)
    return (
        f'<figure class="report-figure{wide_class}" id="figure-{_e(_slug(figure.get("id")))}">'
        f'<div class="exhibit-label">{_e(_ref_label(figure.get("source")))}</div>'
        f'{_icon(_figure_icon(figure.get("id")))}'
        f'<figcaption>{_txt(figure.get("title"))}</figcaption>'
        f'<p class="takeaway">{_txt(figure.get("takeaway"))}</p>'
        f'{chart_html}'
        f'{details_html}'
        f'<p class="source-note">来源：{_e(_source_label(figure.get("source")))}</p>'
        f'<p class="figure-note">{_e(_display_value(figure.get("notes")))}</p>'
        "</figure>"
    )


def _render_chapters(model: Dict[str, Any]) -> str:
    chapters = []
    for index, chapter in enumerate(_items(model.get("chapters")), 1):
        figures = "".join(_render_figure(_dict(fig)) for fig in _items(chapter.get("figures")))
        chapters.append(
            f'<article class="chapter" id="{_e(chapter.get("id", f"chapter-{index}"))}">'
            f'<div class="chapter-number">{_icon("chapter")}<span>{index:02d}</span></div>'
            f'<h3>{_e(chapter.get("title"))}</h3>'
            f'<p class="chapter-thesis">{_txt(chapter.get("thesis"))}</p>'
            f'<div class="figure-grid">{figures}</div>'
            '<div class="implications"><b>关键影响</b>'
            f'{_render_list(_items(chapter.get("implications")))}'
            "</div>"
            "</article>"
        )
    if not chapters:
        chapters.append('<p class="muted">暂无章节分析</p>')
    return (
        '<section class="report-section" id="chapters">'
        f'{_section_heading("03", "章节分析", "figure")}'
        f'{"".join(chapters)}'
        "</section>"
    )


def _render_portfolio(model: Dict[str, Any]) -> str:
    portfolio = _dict(model.get("question_portfolio"))
    rows = []
    for row in _items(portfolio.get("rows")):
        risk = row.get("risk_level")
        icon_risk = risk if risk in {"high", "medium", "low"} else "medium"
        rows.append(
            f'<tr class="{_risk_class(risk)}">'
            f'<td data-label="题号">Q{_e(row.get("question_id"))}</td>'
            f'<td data-label="风险"><span class="risk-cell">{_icon("risk-" + str(icon_risk or "medium"))}{_e(_risk_label(risk))}</span></td>'
            f'<td data-label="质量">{_e(_status_label(row.get("quality_level")))}</td>'
            f'<td data-label="难度">{_e(row.get("difficulty_display", row.get("difficulty")))}</td>'
            f'<td data-label="分值">{_e(row.get("score"))}</td>'
            f'<td data-label="元数据置信度">{_e(_status_label(row.get("metadata_confidence")))}</td>'
            f'<td data-label="核心问题与证据">{_txt(row.get("primary_issue"))}{_render_evidence(row.get("evidence_refs"), compact_question_label=True)}</td>'
            f'<td data-label="动作">{_txt(row.get("action"))}</td>'
            "</tr>"
        )
    if not rows:
        rows.append('<tr><td colspan="8" class="muted" data-label="状态">暂无题目组合数据</td></tr>')
    portfolio_chart = render_portfolio_bubble(_items(portfolio.get("rows")))
    return (
        '<section class="report-section" id="portfolio">'
        f'{_section_heading("04", "题目组合诊断", "portfolio")}'
        f'<p class="section-thesis">{_txt(portfolio.get("thesis"))}</p>'
        f'<div class="wide-chart-frame"><div class="chart-kicker">组合图表</div>{portfolio_chart}</div>'
        '<div class="table-wrap"><table class="portfolio-table">'
        '<caption class="sr-only">题目组合诊断明细</caption>'
        '<thead><tr><th>题号</th><th>风险</th><th>质量</th><th>难度</th><th>分值</th>'
        '<th>元数据置信度</th><th>核心问题与证据</th><th>动作</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        "</section>"
    )


def _render_dive_integrity(dive: Dict[str, Any]) -> str:
    integrity = _dict(dive.get("evidence_integrity"))
    if not integrity:
        return ""
    explanations = [_dict(item) for item in _items(integrity.get("failure_explanations"))]
    flags = _items(integrity.get("difficulty_flags"))
    rows = []
    if integrity.get("analysis_failed") or any(str(flag) in FAIL_CLOSED_DIFFICULTY_FLAGS for flag in flags):
        reason = integrity.get("failure_reason") or "结构化证据不足"
        rows.append(f'<li>证据链异常：{_e(reason)}</li>')
    if flags:
        flag_labels = "、".join(_display_value(flag) for flag in flags)
        rows.append(f'<li>难度算法调整：{_e(flag_labels)}</li>')
    if integrity.get("source_excerpt_status") == "missing":
        rows.append("<li>原题/答案摘录未进入报告数据，复核时需回看原卷。</li>")
    if integrity.get("difficulty_source"):
        rows.append(f'<li>难度来源：{_txt(integrity.get("difficulty_source"))}</li>')
    if integrity.get("score_adjusted_from") is not None:
        rows.append(
            f'<li>分值规范化：原始 {_e(_display_value(integrity.get("score_adjusted_from")))} '
            f'→ 报告 {_e(_display_value(integrity.get("score_adjusted_to")))}；需回看原卷确认。</li>'
        )
    if not rows:
        return _render_failure_explanations(explanations, compact=True)
    return (
        f'<div class="integrity-trace"><b>证据边界</b><ul>{"".join(rows)}</ul></div>'
        f'{_render_failure_explanations(explanations, compact=True)}'
    )


def _markdown_cells(line: str) -> List[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _is_markdown_separator(line: str) -> bool:
    cells = _markdown_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _render_source_text(text: str) -> str:
    lines = str(text or "").splitlines()
    blocks = []
    paragraph = []
    index = 0

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            blocks.append(f'<p class="source-paragraph">{_e(" ".join(paragraph).strip())}</p>')
            paragraph = []

    while index < len(lines):
        line = lines[index]
        if (
            "|" in line
            and index + 1 < len(lines)
            and _is_markdown_separator(lines[index + 1])
        ):
            flush_paragraph()
            headers = _markdown_cells(line)
            index += 2
            rows = []
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_markdown_cells(lines[index]))
                index += 1
            head = "".join(f"<th>{_e(cell)}</th>" for cell in headers)
            body = "".join(
                "<tr>" + "".join(f"<td>{_e(cell)}</td>" for cell in row) + "</tr>"
                for row in rows
            )
            blocks.append(
                '<table class="source-table">'
                f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
            )
            continue
        if line.strip():
            paragraph.append(line.strip())
        else:
            flush_paragraph()
        index += 1
    flush_paragraph()
    return "".join(blocks)


def _render_source_excerpt(dive: Dict[str, Any]) -> str:
    source = _dict(dive.get("source_excerpt"))
    if source.get("status") != "available":
        return '<div class="source-evidence missing">原题摘录缺失：需要回看原卷后复核本题。</div>'

    question_html = _render_source_text(source.get("question_text", ""))
    answer = str(source.get("answer") or "").strip()
    answer_html = f'<p class="source-answer"><b>参考答案/解析摘录：</b>{_e(answer)}</p>' if answer else ""
    truncated = '<p class="source-note">原题摘录已截断，完整内容以原卷为准。</p>' if source.get("truncated") else ""
    empty_source = '<p class="source-paragraph muted">未带入题干文本。</p>'
    return (
        '<details class="source-evidence" open>'
        '<summary>原题依据摘录</summary>'
        f'{question_html or empty_source}'
        f'{answer_html}{truncated}'
        '</details>'
    )


def _render_deep_dives(model: Dict[str, Any]) -> str:
    panels = []
    for dive in _items(model.get("deep_dives")):
        trace = _dict(dive.get("metadata_trace"))
        metadata_warnings = _items(trace.get("warnings"))
        integrity = _dict(dive.get("evidence_integrity"))
        if not metadata_warnings and (
            integrity.get("analysis_failed")
            or _has_fail_closed_difficulty_flag(_items(integrity.get("difficulty_flags")))
            or integrity.get("difficulty_source") == "analysis_failed"
        ):
            metadata_warnings = ["证据链异常：该题存在未闭合的数据缺口。"]
        su_html = _render_su_cards(dive.get("su_context")) or '<p class="data-failure">材料描述缺失；不能据此判断材料负担。</p>'
        panels.append(
            '<article class="deep-dive">'
            f'<div class="call-heading">{_icon("deep-dive")}<h3>第 {_e(dive.get("question_id"))} 题单题审查</h3></div>'
            f'<p class="headline">{_txt(dive.get("headline"))}</p>'
            f'<p>{_txt(dive.get("diagnosis"))}</p>'
            f'{_render_source_excerpt(_dict(dive))}'
            '<div class="deep-grid">'
            '<section><h4>采分点与评分依据</h4>'
            f'{_render_seu_cards(dive.get("seu_breakdown"))}</section>'
            '<section><h4>学生可能卡点</h4>'
            f'{_render_du_cards(dive.get("du_diagnostics"))}</section>'
            '<section><h4>材料与情境信息</h4>'
            f'{su_html}</section>'
            '<section><h4>修订建议</h4>'
            f'{_render_list(_items(dive.get("revision_plan")))}</section>'
            '<section><h4>元数据追踪</h4>'
            f'<p>元数据置信度：{_e(_status_label(trace.get("confidence")))}</p>'
            f'<p>调用目的：{_e("、".join(_purpose_label(item) for item in _items(trace.get("purposes"))))}</p>'
            f'{_render_list(metadata_warnings, "未记录元数据告警；仍需结合证据完整性判断")}'
            f'{_render_dive_integrity(_dict(dive))}</section>'
            "</div></article>"
        )
    if not panels:
        panels.append('<p class="muted">暂无单题审查明细</p>')
    return (
        '<section class="report-section" id="deep-dives">'
        f'{_section_heading("05", "单题审查明细", "deep-dive")}'
        f'{"".join(panels)}'
        "</section>"
    )


def _render_methodology(model: Dict[str, Any]) -> str:
    methodology = _dict(model.get("methodology"))
    summary = _dict(methodology.get("llm_call_summary"))
    purpose_counts = _dict(summary.get("purpose_counts"))
    summary_cards = (
        '<div class="method-summary">'
        f'<article><span>逐题记录调用</span><strong>{_e(summary.get("total", 0))}</strong></article>'
        f'<article><span>调用目的数</span><strong>{len(purpose_counts)}</strong></article>'
        f'<article><span>字段解析数</span><strong>{len(_items(methodology.get("parsed_fields")))}</strong></article>'
        f'<article><span>质量门禁数</span><strong>{len(_items(methodology.get("quality_gates")))}</strong></article>'
        '</div>'
    )
    prompt_rows = []
    for item in _items(methodology.get("prompt_inventory")):
        prompt_rows.append(
            "<tr>"
            f'<td data-label="调用目的">{_e(_purpose_label(item.get("purpose")))}</td>'
            f'<td data-label="记录数">{_e(item.get("records"))}</td>'
            f'<td data-label="解析字段">{_e("、".join(_field_label(field) for field in _items(item.get("parsed_fields"))))}</td>'
            f'<td data-label="提示词摘要">{_e(_prompt_summary(_dict(item)))}</td>'
            "</tr>"
        )
    if not prompt_rows:
        prompt_rows.append('<tr><td colspan="4" class="muted" data-label="状态">暂无提示词清单</td></tr>')
    return (
        '<section class="report-section methodology" id="methodology">'
        f'{_section_heading("06", "AI 调用与方法论", "methodology")}'
        f'{summary_cards}'
        f'<div class="wide-chart-frame"><div class="chart-kicker">方法论图表</div>{render_methodology_chart(methodology)}</div>'
        '<div class="method-grid">'
        f'<article>{_icon("fields")}<h3>解析字段</h3>'
        f'{_render_list([_field_label(item) for item in _items(methodology.get("parsed_fields"))])}</article>'
        f'<article>{_icon("gate")}<h3>质量门禁</h3>'
        f'{_render_list([_gate_label(item) for item in _items(methodology.get("quality_gates"))])}</article>'
        f'<article>{_icon("limits")}<h3>局限说明</h3>'
        f'{_render_list(_items(methodology.get("limitations")))}</article>'
        "</div>"
        '<div class="table-wrap"><table class="prompt-table">'
        '<caption class="sr-only">AI 调用提示词清单</caption>'
        '<thead><tr><th>调用目的</th><th>记录数</th><th>解析字段</th><th>提示词摘要</th></tr></thead>'
        f'<tbody>{"".join(prompt_rows)}</tbody></table></div>'
        "</section>"
    )


def _stylesheet() -> str:
    return """
:root {
  --bain-red: #cc0000;
  --bain-red-2: #cc2027;
  --bain-black: #030404;
  --bain-gray-900: #231f20;
  --bain-gray-700: #777877;
  --bain-gray-500: #a5a4a4;
  --bain-gray-300: #d2d3d1;
  --bain-gray-200: #d6d6d6;
  --bain-gray-100: #f3f0ea;
  --ink: #030404;
  --muted: #666666;
  --line: #d2d3d1;
  --hairline: #e6e6e6;
  --paper: #ffffff;
  --paper-2: #f8f8f8;
  --ivory: #ffffff;
  --panel: #ffffff;
  --panel-warm: #f8f8f8;
  --accent: #cc0000;
  --accent-2: #cc2027;
  --copper: #cc0000;
  --gold: #cc0000;
  --risk: #cc0000;
  --watch: #777877;
  --positive: #333333;
  --blue: #666666;
  --shadow: 0 18px 42px rgba(0, 0, 0, .08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--paper);
  font-family: "Segoe UI", "Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
  line-height: 1.55;
  overflow-x: hidden;
}
.skip-link {
  position: absolute;
  left: 18px;
  top: 12px;
  z-index: 20;
  padding: 9px 12px;
  color: #fff;
  background: var(--bain-red);
  text-decoration: none;
  transform: translateY(-160%);
}
.skip-link:focus-visible {
  transform: translateY(0);
  outline: 2px solid #030404;
  outline-offset: 3px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.report-main { min-width: 0; }
.report-section, .report-figure, .chapter, .portfolio-section, .deep-section {
  scroll-margin-top: 74px;
}
.top-nav {
  position: static;
  top: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 13px 4vw;
  background: rgba(255, 255, 255, 0.97);
  border-bottom: 1px solid var(--line);
  backdrop-filter: blur(14px);
}
.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-weight: 750;
  letter-spacing: 0;
}
.nav-links { display: flex; gap: 16px; flex-wrap: wrap; justify-content: flex-end; }
.nav-links a {
  color: var(--ink);
  font-size: 14px;
  text-decoration: none;
  border-bottom: 1px solid transparent;
}
.nav-links a:hover { border-color: var(--accent); color: var(--accent); }
.nav-links a:focus-visible {
  outline: 2px solid var(--bain-red);
  outline-offset: 3px;
}
.hero {
  min-height: 56vh;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  padding: clamp(76px, 9vh, 112px) 7vw 54px;
  border-bottom: 1px solid #b00000;
  background: #cc0000;
  color: #fff;
  box-shadow: inset 0 12px 0 #fff;
}
.hero-kicker {
  color: #fff;
  font-size: 13px;
  font-weight: 850;
  text-transform: uppercase;
  letter-spacing: .08em;
}
h1 {
  max-width: 980px;
  margin: 18px 0 8px;
  font-size: clamp(42px, 6.3vw, 80px);
  line-height: 0.96;
  letter-spacing: 0;
  text-wrap: balance;
  overflow-wrap: anywhere;
}
.exam-name {
  max-width: 100%;
  margin: 0;
  color: #fff;
  font-size: clamp(21px, 3vw, 34px);
  overflow-wrap: anywhere;
  word-break: break-word;
}
.hero-note {
  width: min(100%, 820px);
  max-width: 820px;
  margin: 24px 0 0;
  color: #fff;
  font-size: 17px;
  border-left: 3px solid #fff;
  padding-left: 16px;
  overflow-wrap: anywhere;
}
.hero-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 1px;
  width: min(940px, 100%);
  margin-top: 34px;
  background: rgba(255,255,255,.18);
  border: 1px solid rgba(255,255,255,.45);
  box-shadow: 0 26px 64px rgba(0,0,0,.18);
}
.hero-metric { min-height: 96px; padding: 17px; background: rgba(255,255,255,.10); }
.hero-metric span { display: block; color: #fff; font-size: 14px; }
.hero-metric strong { display: block; margin-top: 8px; color: #fff; font-size: 28px; }
.hero-footer { display: flex; gap: 18px; flex-wrap: wrap; margin-top: 24px; color: #fff; font-size: 14px; }
.report-icon {
  position: relative;
  display: inline-flex;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  margin-right: 10px;
  color: var(--accent);
  border: 1.4px solid currentColor;
  border-radius: 50%;
  vertical-align: middle;
  background: color-mix(in srgb, currentColor 7%, transparent);
}
.report-icon::before, .report-icon::after {
  content: "";
  position: absolute;
  display: block;
}
.hero .report-icon, .top-nav .report-icon {
  color: #cc0000;
}
.hero-metric .report-icon {
  margin: 0 0 10px;
  color: #fff;
}
.icon-brand::before, .icon-executive::before {
  left: 8px;
  top: 8px;
  width: 16px;
  height: 16px;
  border: 2px solid currentColor;
  border-radius: 50%;
}
.icon-brand::after, .icon-executive::after {
  left: 15px;
  top: 3px;
  width: 2px;
  height: 26px;
  background: currentColor;
}
.icon-scope::before, .icon-portfolio::before {
  left: 8px;
  top: 9px;
  width: 17px;
  height: 13px;
  border: 2px solid currentColor;
  border-radius: 2px;
}
.icon-scope::after, .icon-portfolio::after {
  left: 12px;
  top: 15px;
  width: 10px;
  height: 2px;
  background: currentColor;
  box-shadow: 0 5px 0 currentColor;
}
.icon-score::before, .icon-glance::before {
  left: 8px;
  bottom: 8px;
  width: 4px;
  height: 8px;
  background: currentColor;
  box-shadow: 7px -5px 0 currentColor, 14px -10px 0 currentColor;
}
.icon-score::after, .icon-glance::after {
  left: 7px;
  top: 8px;
  width: 20px;
  height: 2px;
  background: currentColor;
  transform: rotate(-30deg);
}
.icon-metadata::before, .icon-methodology::before, .icon-fields::before {
  left: 9px;
  top: 7px;
  width: 14px;
  height: 18px;
  border: 2px solid currentColor;
  border-radius: 2px;
}
.icon-metadata::after, .icon-methodology::after, .icon-fields::after {
  left: 13px;
  top: 13px;
  width: 8px;
  height: 2px;
  background: currentColor;
  box-shadow: 0 5px 0 currentColor;
}
.icon-llm::before {
  left: 8px;
  top: 10px;
  width: 16px;
  height: 12px;
  border: 2px solid currentColor;
  border-radius: 3px;
}
.icon-llm::after {
  left: 12px;
  top: 6px;
  width: 8px;
  height: 4px;
  border-top: 2px solid currentColor;
  border-left: 2px solid currentColor;
  border-right: 2px solid currentColor;
}
.icon-gradient::before, .icon-figure::before, .icon-chapter::before {
  left: 8px;
  top: 19px;
  width: 18px;
  height: 2px;
  background: currentColor;
  transform: rotate(-28deg);
}
.icon-gradient::after, .icon-figure::after, .icon-chapter::after {
  left: 8px;
  top: 8px;
  width: 4px;
  height: 4px;
  background: currentColor;
  border-radius: 50%;
  box-shadow: 8px 6px 0 currentColor, 17px 1px 0 currentColor;
}
.icon-bloom::before, .icon-competency::before {
  left: 8px;
  top: 8px;
  width: 8px;
  height: 8px;
  border: 2px solid currentColor;
  border-radius: 50%;
  box-shadow: 10px 0 0 -1px var(--paper), 10px 0 0 1px currentColor, 5px 11px 0 -1px var(--paper), 5px 11px 0 1px currentColor;
}
.icon-knowledge::before {
  left: 8px;
  top: 9px;
  width: 18px;
  height: 14px;
  border: 2px solid currentColor;
  border-radius: 2px;
}
.icon-knowledge::after {
  left: 16px;
  top: 9px;
  width: 2px;
  height: 14px;
  background: currentColor;
}
.icon-risk-high, .risk-high .report-icon { color: var(--risk); }
.icon-risk-medium, .risk-medium .report-icon { color: var(--watch); }
.icon-risk-low, .risk-low .report-icon { color: var(--positive); }
.icon-risk-high::before, .icon-risk-medium::before, .icon-risk-low::before {
  left: 15px;
  top: 7px;
  width: 3px;
  height: 15px;
  background: currentColor;
}
.icon-risk-high::after, .icon-risk-medium::after, .icon-risk-low::after {
  left: 14px;
  bottom: 7px;
  width: 5px;
  height: 5px;
  background: currentColor;
  border-radius: 50%;
}
.icon-gate::before, .icon-limits::before {
  left: 8px;
  top: 8px;
  width: 17px;
  height: 17px;
  border: 2px solid currentColor;
  border-radius: 3px;
}
.icon-gate::after {
  left: 13px;
  top: 15px;
  width: 9px;
  height: 5px;
  border-left: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(-45deg);
}
.icon-limits::after {
  left: 15px;
  top: 9px;
  width: 2px;
  height: 16px;
  background: currentColor;
  transform: rotate(45deg);
}
.icon-deep-dive::before {
  left: 9px;
  top: 9px;
  width: 11px;
  height: 11px;
  border: 2px solid currentColor;
  border-radius: 50%;
}
.icon-deep-dive::after {
  left: 20px;
  top: 20px;
  width: 9px;
  height: 2px;
  background: currentColor;
  transform: rotate(45deg);
}
.report-section {
  width: min(1180px, 92vw);
  margin: 0 auto;
  padding: 76px 0;
  border-bottom: 1px solid var(--line);
}
.report-section.compact { padding-bottom: 48px; }
.section-heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 24px;
}
.section-heading h2 { margin-bottom: 0; }
.section-label {
  color: var(--accent);
  font-size: 13px;
  font-weight: 800;
  text-transform: uppercase;
  margin-bottom: 10px;
  letter-spacing: .08em;
}
h2 { margin: 0 0 24px; font-size: clamp(30px, 4vw, 52px); line-height: 1.05; letter-spacing: 0; }
h3 { margin: 0 0 12px; font-size: 24px; line-height: 1.2; letter-spacing: 0; }
h4 { margin: 0 0 8px; font-size: 15px; letter-spacing: 0; }
.lead-judgment, .section-thesis, .chapter-thesis {
  max-width: 860px;
  font-size: 21px;
  color: #231f20;
  overflow-wrap: anywhere;
}
.big-call-grid, .glance-grid, .figure-grid, .method-grid, .deep-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 18px;
}
.summary-card-grid {
  grid-template-columns: repeat(6, minmax(0, 1fr));
  align-items: stretch;
}
.summary-card-grid .big-call {
  grid-column: span 2;
}
.summary-card-grid .summary-scale-card {
  grid-column: span 4;
}
.evidence-integrity-panel {
  margin-top: 22px;
  border: 1px solid #f0b8b8;
  background: #fffafa;
  padding: 18px;
}
.panel-heading {
  color: var(--accent);
  font-weight: 850;
  margin-bottom: 8px;
}
.integrity-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
  margin-top: 14px;
}
.integrity-card {
  border: 1px solid var(--line);
  background: #fff;
  padding: 13px;
  min-width: 0;
}
.integrity-card span {
  display: block;
  font-size: 13px;
  font-weight: 800;
  color: var(--muted);
}
.integrity-card strong {
  display: block;
  margin: 6px 0;
  font-size: 25px;
  color: var(--accent);
}
.integrity-card p, .integrity-note { margin: 0; font-size: 14px; }
.integrity-warning { border-color: #f0b8b8; }
.integrity-trace {
  margin-top: 12px;
  border-left: 3px solid var(--accent);
  background: #fff7f7;
  padding: 10px 12px;
  font-size: 14px;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.integrity-trace ul { margin: 6px 0 0; padding-left: 18px; min-width: 0; }
.integrity-trace li { min-width: 0; overflow-wrap: anywhere; word-break: break-word; }
.failure-explain-list {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}
.failure-explain-list h4 {
  margin: 0;
  font-size: 16px;
}
.failure-explain {
  border: 1px solid #f0b8b8;
  border-left: 4px solid var(--accent);
  background: #fff;
  padding: 12px 14px;
}
.failure-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}
.failure-title strong {
  font-size: 16px;
}
.failure-title span {
  font-size: 13px;
  color: var(--accent);
  font-weight: 800;
  white-space: nowrap;
}
.failure-explain p {
  margin: 8px 0;
}
.failure-explain ul {
  margin: 0;
  padding-left: 0;
  display: grid;
  gap: 6px;
  list-style: none;
}
.failure-explain li {
  font-size: 14px;
}
.failure-explain li b {
  display: inline-block;
  min-width: 44px;
  color: var(--muted);
}
.figure-grid {
  grid-template-columns: minmax(0, 1fr);
  gap: 28px;
}
.call-heading {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.call-heading .report-icon { margin-right: 0; }
.big-call, .glance-card, .report-figure, .method-grid article, .deep-dive {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 0;
  padding: 22px;
  box-shadow: var(--shadow);
}
.wide-figure { grid-column: 1 / -1; }
.wide-figure .chart-frame { padding: 20px; }
.big-call { border-top: 4px solid var(--watch); }
.stance-risk { border-top-color: var(--risk); }
.stance-positive { border-top-color: var(--positive); }
.call-id, .glance-card span {
  color: var(--muted);
  font-size: 13px;
  font-weight: 800;
  text-transform: uppercase;
}
.call-subtitle {
  color: var(--muted);
  font-size: 14px;
  font-weight: 700;
  margin-top: 4px;
}
.action-line {
  display: grid;
  grid-template-columns: 72px 1fr;
  gap: 12px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}
.evidence-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
.evidence-text-row {
  align-items: baseline;
  gap: 4px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}
.evidence-label {
  font-weight: 800;
}
.evidence-text {
  overflow-wrap: anywhere;
}
.evidence-chip {
  display: inline-flex;
  max-width: 100%;
  padding: 3px 8px;
  border: 1px solid #d2d3d1;
  border-radius: 0;
  color: #231f20;
  background: #f8f8f8;
  font-size: 13px;
}
.summary-scale {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.summary-scale-item {
  border-top: 1px solid var(--line);
  padding-top: 10px;
}
.summary-scale-item span {
  display: block;
  color: var(--muted);
  font-size: 13px;
  font-weight: 760;
}
.summary-scale-item strong {
  display: block;
  margin-top: 6px;
  font-size: 28px;
  line-height: 1;
}
.glance-card strong { display: block; margin: 8px 0; font-size: 34px; color: var(--accent); line-height: 1; }
.glance-card em { color: var(--muted); font-size: 13px; font-style: normal; }
.chapter {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 24px;
  padding: 34px 0;
  border-top: 1px solid var(--line);
}
.chapter-number {
  display: flex;
  align-items: center;
  color: var(--gold);
  font-size: 38px;
  font-weight: 800;
  line-height: 1;
  grid-row: 1 / 5;
}
.chapter-number .report-icon { color: var(--gold); }
.chapter > h3,
.chapter > .chapter-thesis,
.chapter > .figure-grid,
.chapter > .implications {
  grid-column: 2;
}
.chapter > .chapter-thesis {
  max-width: 980px;
  margin-bottom: 12px;
}
.report-figure { min-width: 0; position: relative; overflow: visible; }
.report-figure::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 4px;
  background: var(--bain-red);
}
.exhibit-label {
  display: inline-flex;
  margin: 0 0 12px;
  padding: 4px 8px;
  color: var(--bain-red);
  background: #fff;
  border: 1px solid var(--bain-red);
  border-radius: 0;
  font-size: 13px;
  font-weight: 800;
}
figcaption { font-size: 22px; font-weight: 800; line-height: 1.25; }
.takeaway { color: #231f20; font-size: 17px; font-weight: 650; }
.source-note, .figure-note, .muted {
  color: var(--muted);
  font-size: 13px;
}
.data-failure {
  margin: 0;
  padding: 10px 12px;
  border-left: 3px solid var(--accent);
  background: #fff7f7;
  color: #8c0000;
  font-size: 14px;
  font-weight: 700;
}
.chart-frame, .wide-chart-frame {
  margin: 18px 0 12px;
  padding: 18px;
  background: #fbfbfb;
  border: 1px solid #e6e6e6;
  border-radius: 0;
  overflow-x: auto;
  overflow-y: visible;
  box-shadow: none;
}
.wide-chart-frame { padding: 20px; }
.chart-kicker {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  color: var(--bain-red);
  font-size: 13px;
  font-weight: 850;
  text-transform: uppercase;
  letter-spacing: .11em;
}
.chart-kicker::before {
  content: "";
  width: 18px;
  height: 1px;
  background: var(--bain-red);
}
.report-chart {
  display: block;
  width: 100%;
  height: auto;
}
.chart-mobile-list {
  display: none;
}
.chart-mobile-card {
  padding: 11px 12px;
  background: #fff;
  border: 1px solid var(--line);
}
.chart-mobile-card div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--ink);
  font-size: 15px;
  font-weight: 850;
}
.chart-mobile-card div span {
  color: var(--bain-red);
  white-space: nowrap;
}
.chart-mobile-card p {
  margin: 6px 0 4px;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.45;
}
.chart-mobile-card small {
  display: block;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.35;
}
.chart-competency-mobile-card ul {
  margin: 9px 0 6px;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 7px;
}
.chart-competency-mobile-card li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding-top: 7px;
  border-top: 1px solid var(--line);
  color: var(--ink);
  font-size: 14px;
  line-height: 1.35;
}
.chart-competency-mobile-card li:first-child {
  border-top: 0;
  padding-top: 0;
}
.chart-competency-mobile-card li span {
  overflow-wrap: anywhere;
}
.chart-competency-mobile-card li b {
  color: var(--bain-red);
  font-size: 13px;
  white-space: nowrap;
}
.figure-details {
  margin: 10px 0 12px;
  background: #fff;
  border: 1px solid var(--line);
}
.figure-details summary {
  padding: 10px 12px;
  color: var(--bain-red);
  font-size: 14px;
  font-weight: 850;
  cursor: pointer;
}
.figure-details[open] summary {
  border-bottom: 1px solid var(--line);
}
.figure-detail-body {
  padding: 12px;
}
.figure-detail-title {
  margin-bottom: 10px;
  color: var(--ink);
  font-size: 15px;
  font-weight: 850;
}
.figure-evidence-note {
  margin: 10px 0 12px;
  padding: 10px 12px;
  color: var(--muted);
  background: #fff;
  border: 1px solid var(--line);
  font-size: 13px;
}
.figure-detail-table {
  width: 100%;
  table-layout: fixed;
}
.figure-detail-table th,
.figure-detail-table td {
  overflow-wrap: anywhere;
  word-break: break-word;
  vertical-align: top;
  line-height: 1.45;
}
.method-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin: 0 0 18px;
}
.method-summary article {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 0;
  padding: 14px 16px;
  box-shadow: 0 12px 28px rgba(57,45,30,.08);
}
.method-summary span {
  display: block;
  color: var(--muted);
  font-size: 13px;
}
.method-summary strong {
  display: block;
  margin-top: 4px;
  color: var(--accent);
  font-size: 28px;
}
.source-evidence {
  margin: 14px 0 16px;
  padding: 12px 14px;
  background: #fff;
  border: 1px solid var(--line);
  box-shadow: 0 10px 22px rgba(57,45,30,.06);
}
.source-evidence summary {
  color: var(--bain-red);
  font-weight: 850;
  cursor: pointer;
}
.source-evidence.missing {
  color: var(--muted);
  font-size: 14px;
}
.source-paragraph,
.source-answer,
.source-note {
  margin: 10px 0 0;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.source-note {
  color: var(--muted);
}
.source-table {
  width: 100%;
  margin-top: 10px;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 14px;
}
.source-table th,
.source-table td {
  padding: 9px 10px;
  border: 1px solid var(--hairline);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
.source-table th {
  background: #f3f0ea;
  font-weight: 800;
}
.data-table, .portfolio-table, .prompt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
  table-layout: fixed;
}
.data-table th, .data-table td, .portfolio-table th, .portfolio-table td, .prompt-table th, .prompt-table td {
  padding: 11px 12px;
  border-top: 1px solid var(--hairline);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
.data-table th { width: 42%; color: var(--muted); font-weight: 650; }
.compact-table th { width: auto; }
.table-wrap {
  overflow: visible;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 0;
  box-shadow: var(--shadow);
}
.portfolio-table th, .prompt-table th {
  background: #f3f0ea;
  color: #231f20;
  font-size: 13px;
  text-transform: uppercase;
}
.portfolio-table tbody tr:nth-child(even), .prompt-table tbody tr:nth-child(even), .data-table tbody tr:nth-child(even) {
  background: #f8f8f8;
}
.portfolio-table td:first-child { font-weight: 800; }
.portfolio-table th:nth-child(1), .portfolio-table td:nth-child(1) { width: 5%; }
.portfolio-table th:nth-child(2), .portfolio-table td:nth-child(2) { width: 9%; }
.portfolio-table th:nth-child(3), .portfolio-table td:nth-child(3) { width: 8%; }
.portfolio-table th:nth-child(4), .portfolio-table td:nth-child(4) { width: 7%; }
.portfolio-table th:nth-child(5), .portfolio-table td:nth-child(5) { width: 6%; }
.portfolio-table th:nth-child(6), .portfolio-table td:nth-child(6) { width: 11%; }
.portfolio-table th:nth-child(7), .portfolio-table td:nth-child(7) { width: 36%; }
.portfolio-table th:nth-child(8), .portfolio-table td:nth-child(8) { width: 18%; }
.portfolio-table th:nth-child(-n + 6),
.portfolio-table td:nth-child(-n + 6) {
  white-space: nowrap;
}
.portfolio-table th:nth-child(4),
.portfolio-table td:nth-child(4),
.portfolio-table th:nth-child(5),
.portfolio-table td:nth-child(5),
.portfolio-table th:nth-child(6),
.portfolio-table td:nth-child(6) {
  text-align: center;
}
.portfolio-table td:nth-child(7),
.portfolio-table td:nth-child(8) {
  line-height: 1.72;
  overflow-wrap: break-word;
}
.portfolio-table td:nth-child(7) .evidence-links {
  margin-top: 12px;
}
.risk-cell { display: inline-flex; align-items: center; gap: 8px; white-space: nowrap; }
.risk-cell .report-icon { width: 24px; height: 24px; margin-right: 0; }
.risk-cell .report-icon::before { left: 10px; top: 5px; height: 11px; }
.risk-cell .report-icon::after { left: 9px; bottom: 5px; }
.risk-high td:first-child { color: var(--risk); }
.risk-medium td:first-child { color: var(--watch); }
.risk-low td:first-child { color: var(--positive); }
.deep-dive { margin-bottom: 18px; }
.headline { font-size: 18px; font-weight: 750; color: var(--accent); }
.evidence-unit-grid, .du-unit-grid, .su-unit-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.evidence-unit-card, .du-unit-card, .su-unit-card {
  border: 1px solid var(--line);
  background: #fff;
  padding: 14px;
  min-width: 0;
}
.unit-card-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--accent);
  font-size: 13px;
  font-weight: 850;
}
.unit-card-head strong { color: #231f20; white-space: nowrap; }
.unit-title { margin: 10px 0; font-weight: 760; color: #231f20; }
.score-bar { height: 5px; background: #ecebea; margin-top: 9px; }
.score-bar span { display: block; height: 100%; background: var(--accent); }
.unit-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0;
}
.unit-metrics span {
  border: 1px solid var(--hairline);
  padding: 3px 7px;
  font-size: 13px;
  color: var(--muted);
}
.unit-evidence-block { margin-top: 10px; }
.unit-evidence-block > b, .unit-boundary > b {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--accent);
}
.weight-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.weight-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--hairline);
  padding: 4px 7px;
  font-size: 13px;
  background: #f8f8f8;
}
.weight-tag b { font-weight: 650; }
.weight-tag em { color: var(--accent); font-style: normal; font-weight: 800; }
.unit-boundary { color: var(--muted); }
.su-unit-card span {
  color: var(--accent);
  font-size: 13px;
  font-weight: 850;
}
.su-unit-card b { display: block; margin-top: 6px; }
.methodology { padding-bottom: 90px; }
ul { margin: 8px 0 0; padding-left: 20px; }
li + li { margin-top: 4px; }
@media (max-width: 1024px) {
  .portfolio-table,
  .prompt-table,
  .figure-detail-table,
  .portfolio-table tbody,
  .prompt-table tbody,
  .figure-detail-table tbody,
  .portfolio-table tr,
  .prompt-table tr,
  .figure-detail-table tr,
  .portfolio-table td,
  .prompt-table td,
  .figure-detail-table td {
    display: block;
    width: 100%;
  }
  .portfolio-table thead,
  .prompt-table thead,
  .figure-detail-table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
  .portfolio-table tr,
  .prompt-table tr,
  .figure-detail-table tr {
    padding: 14px 14px 12px;
    border-top: 1px solid var(--line);
  }
  .portfolio-table tr:first-child,
  .prompt-table tr:first-child,
  .figure-detail-table tr:first-child {
    border-top: 0;
  }
  .portfolio-table td,
  .prompt-table td,
  .figure-detail-table td {
    display: grid;
    grid-template-columns: minmax(88px, 112px) minmax(0, 1fr);
    gap: 12px;
    padding: 7px 0;
    border-top: 0;
  }
  .portfolio-table th:nth-child(n),
  .portfolio-table td:nth-child(n) {
    width: 100%;
    text-align: left;
  }
  .portfolio-table td::before,
  .prompt-table td::before,
  .figure-detail-table td::before {
    content: attr(data-label);
    color: var(--muted);
    font-size: 13px;
    font-weight: 800;
  }
  .portfolio-table td[colspan],
  .prompt-table td[colspan],
  .figure-detail-table td[colspan] {
    display: block;
  }
}
@media (max-width: 760px) {
  .top-nav { position: static; align-items: flex-start; flex-direction: column; }
  .nav-links {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
    gap: 8px;
    padding-bottom: 3px;
  }
  .nav-links a { min-width: 0; font-size: 13px; overflow-wrap: anywhere; }
  .hero { min-height: auto; padding: 64px 24px 42px; }
  h1 { font-size: clamp(38px, 13vw, 50px); line-height: 1.04; }
  .exam-name { font-size: 23px; max-width: 100%; overflow-wrap: anywhere; word-break: break-word; }
  .hero-note { width: min(100%, 300px); max-width: 300px; padding-right: 0; font-size: 15px; overflow-wrap: break-word; }
  .hero-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .report-section { width: calc(100% - 40px); padding: 64px 0; }
  .lead-judgment, .section-thesis, .chapter-thesis { max-width: 330px; font-size: 19px; overflow-wrap: break-word; }
  .big-call-grid, .glance-grid, .figure-grid, .method-grid, .deep-grid { grid-template-columns: 1fr; }
  .summary-card-grid .big-call,
  .summary-card-grid .summary-scale-card { grid-column: auto; }
  .report-section { width: calc(100% - 24px); }
  .report-figure { padding: 18px 14px; }
  .chart-frame, .wide-chart-frame {
    margin: 14px 0 12px;
    padding: 10px;
    overflow-x: visible;
  }
  .report-chart {
    min-width: 0;
    max-width: 100%;
  }
  .chart-du-trap-map {
    display: none;
  }
  .chart-du-trap-mobile-list {
    display: grid;
    gap: 8px;
  }
  .chart-competency-distribution {
    display: none;
  }
  .chart-competency-mobile-list {
    display: grid;
    gap: 8px;
  }
  .wide-chart-frame .report-chart,
  .wide-figure .chart-frame .report-chart {
    min-width: 0;
  }
  .chapter { grid-template-columns: 1fr; }
  .chapter-number,
  .chapter > h3,
  .chapter > .chapter-thesis,
  .chapter > .figure-grid,
  .chapter > .implications {
    grid-column: 1;
    grid-row: auto;
  }
  .action-line { grid-template-columns: 1fr; }
  .portfolio-table,
  .prompt-table,
  .figure-detail-table,
  .portfolio-table tbody,
  .prompt-table tbody,
  .figure-detail-table tbody,
  .portfolio-table tr,
  .prompt-table tr,
  .figure-detail-table tr,
  .portfolio-table td,
  .prompt-table td,
  .figure-detail-table td {
    display: block;
    width: 100%;
  }
  .portfolio-table thead,
  .prompt-table thead,
  .figure-detail-table thead {
    display: none;
  }
  .portfolio-table tr,
  .prompt-table tr,
  .figure-detail-table tr {
    padding: 14px 14px 12px;
    border-top: 1px solid var(--line);
  }
  .portfolio-table tr:first-child,
  .prompt-table tr:first-child,
  .figure-detail-table tr:first-child {
    border-top: 0;
  }
  .portfolio-table td,
  .prompt-table td,
  .figure-detail-table td {
    display: grid;
    grid-template-columns: minmax(88px, 112px) minmax(0, 1fr);
    gap: 12px;
    padding: 7px 0;
    border-top: 0;
  }
  .portfolio-table th:nth-child(n),
  .portfolio-table td:nth-child(n) {
    width: 100%;
    text-align: left;
  }
  .portfolio-table td::before,
  .prompt-table td::before,
  .figure-detail-table td::before {
    content: attr(data-label);
    color: var(--muted);
    font-size: 13px;
    font-weight: 800;
  }
  .portfolio-table td[colspan],
  .prompt-table td[colspan],
  .figure-detail-table td[colspan] {
    display: block;
  }
}
@media (max-width: 520px) {
  .chart-difficulty-gradient {
    display: none;
  }
  .chart-difficulty-mobile-list {
    display: grid;
    gap: 8px;
  }
}
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
  .top-nav {
    backdrop-filter: none;
  }
}
"""


def _pdf_stylesheet() -> str:
    return """
@page {
  size: A4 landscape;
  margin: 12mm 13mm 11mm;
  @bottom-left { content: "AI 审题与审卷质量诊断报告"; color: #7a7369; font-size: 8pt; }
  @bottom-right { content: counter(page); color: #7a7369; font-size: 8pt; }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: #030404;
  background: #ffffff;
  font-family: "Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
  line-height: 1.35;
}
.pdf-report {
  counter-reset: section;
}
.pdf-page {
  page-break-after: always;
  min-height: 170mm;
  padding: 8mm 9mm;
  background: #ffffff;
  border: 1px solid #d2d3d1;
}
.pdf-page:last-child { page-break-after: auto; }
.pdf-page.pdf-cover {
  display: grid;
  grid-template-columns: 1.15fr .85fr;
  gap: 12mm;
  align-items: center;
  height: 187mm;
  min-height: 187mm;
  background: #cc0000;
  border-color: #cc0000;
  color: #fff;
}
.pdf-kicker {
  color: #fff;
  font-size: 9pt;
  font-weight: 800;
}
.pdf-cover h1 {
  margin: 6mm 0 3mm;
  font-size: 32pt;
  line-height: .98;
}
.pdf-cover .exam-name {
  font-size: 17pt;
  color: #ffffff;
}
.pdf-cover-note {
  margin-top: 8mm;
  max-width: 145mm;
  color: #ddd3c1;
  font-size: 10pt;
}
.pdf-cover-metrics {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1px;
  border: 1px solid rgba(255,255,255,.28);
  background: rgba(255,255,255,.20);
}
.pdf-cover-metrics article {
  min-height: 28mm;
  padding: 5mm;
  background: rgba(255,255,255,.10);
}
.pdf-cover-metrics span {
  display: block;
  color: #ffffff;
  font-size: 8pt;
}
.pdf-cover-metrics strong {
  display: block;
  margin-top: 3mm;
  color: #fff;
  font-size: 21pt;
}
.pdf-page-header {
  display: grid;
  grid-template-columns: 16mm 1fr;
  gap: 5mm;
  align-items: start;
  margin-bottom: 3mm;
}
.pdf-page-number {
  color: #cc0000;
  font-size: 20pt;
  font-weight: 900;
  line-height: 1;
}
.pdf-page h2 {
  margin: 0;
  font-size: 19pt;
  line-height: 1.08;
}
.pdf-thesis {
  margin: 2mm 0 0;
  color: #231f20;
  font-size: 10pt;
  font-weight: 650;
}
.pdf-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3.2mm;
}
.pdf-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 3mm;
}
.pdf-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 3mm;
}
.pdf-grid-1 {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2.4mm;
}
.pdf-figure-matrix {
  gap: 2.2mm;
}
.pdf-figure-matrix .pdf-figure {
  padding: 2mm;
}
.pdf-figure-spread {
  display: flex;
  gap: 3.2mm;
  align-items: stretch;
}
.pdf-figure-spread .pdf-figure {
  flex: 1 1 0;
  min-width: 0;
  min-height: 138mm;
}
.pdf-figure-spread .chart-frame {
  margin: 1.5mm 0;
  padding: 1.2mm;
}
.pdf-figure-spread .report-chart {
  height: 94mm;
}
.pdf-page-footnote {
  margin-top: 3mm;
}
.pdf-figure-matrix .pdf-figure h3 {
  font-size: 8.4pt;
  margin: 0 0 1mm;
}
.pdf-figure-matrix .pdf-figure p,
.pdf-figure-matrix .pdf-source {
  font-size: 6.4pt;
  line-height: 1.28;
}
.pdf-figure-matrix .pdf-figure .chart-frame {
  margin: 1mm 0;
  padding: .8mm;
}
.pdf-figure-matrix .pdf-figure .report-chart {
  height: 34mm;
}
.pdf-call, .pdf-metric, .pdf-panel, .pdf-figure {
  background: #ffffff;
  border: 1px solid #d2d3d1;
  border-radius: 0;
  padding: 3mm;
}
.pdf-call {
  border-top: 1mm solid #777877;
}
.pdf-call.stance-risk { border-top-color: #cc0000; }
.pdf-call.stance-positive { border-top-color: #333333; }
.pdf-call-id, .pdf-metric span {
  color: #666666;
  font-size: 7.5pt;
  font-weight: 800;
}
.pdf-call h3, .pdf-figure h3, .pdf-panel h3 {
  margin: 1mm 0;
  font-size: 10pt;
  line-height: 1.18;
}
.pdf-call p, .pdf-panel p, .pdf-figure p {
  margin: 1mm 0;
  font-size: 7.8pt;
}
.pdf-metric strong {
  display: block;
  color: #cc0000;
  font-size: 16pt;
}
.pdf-evidence {
  margin-top: 1.2mm;
  color: #666666;
  font-size: 7pt;
}
.pdf-figure {
  break-inside: avoid;
  border-top: 1mm solid #cc0000;
}
.pdf-exhibit-label {
  display: inline-block;
  margin: 0 0 1.5mm;
  padding: .7mm 1.6mm;
  color: #cc0000;
  background: #ffffff;
  border: 1px solid #cc0000;
  border-radius: 0;
  font-size: 6.4pt;
  font-weight: 800;
}
.pdf-figure .chart-kicker,
.pdf-wide-chart .chart-kicker {
  display: block;
  margin: 0 0 1mm;
  color: #cc0000;
  font-size: 6.5pt;
  font-weight: 850;
  text-transform: uppercase;
  letter-spacing: .08em;
}
.pdf-figure .chart-frame {
  margin: 2mm 0;
  padding: 1.5mm;
  border: 1px solid #d2d3d1;
  background: #ffffff;
}
.pdf-figure .report-chart,
.pdf-wide-chart .report-chart {
  display: block;
  width: 100%;
  min-width: 0;
}
.pdf-figure .chart-mobile-list,
.pdf-wide-chart .chart-mobile-list {
  display: none !important;
}
.pdf-figure .report-chart { height: 94mm; }
.pdf-wide-chart .report-chart { height: 82mm; }
.pdf-figure-matrix .pdf-figure .report-chart { height: 34mm; }
.pdf-fine-page .pdf-figure {
  padding: 2.2mm;
}
.pdf-fine-page .pdf-figure h3 {
  font-size: 8.8pt;
  margin: 0 0 .8mm;
}
.pdf-fine-page .pdf-figure p,
.pdf-fine-page .pdf-source {
  font-size: 6.5pt;
  line-height: 1.25;
  margin: .6mm 0;
}
.pdf-fine-page .pdf-figure .chart-frame {
  margin: .8mm 0;
  padding: .8mm;
}
.pdf-fine-page .pdf-figure .report-chart {
  height: 94mm;
}
.pdf-wide-chart {
  margin: 3mm 0;
  padding: 2mm;
  border: 1px solid #d2d3d1;
  background: #ffffff;
  border-radius: 0;
}
.pdf-source {
  color: #666666;
  font-size: 7pt;
}
.pdf-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 7.6pt;
}
.pdf-table th, .pdf-table td {
  padding: 1.8mm 1.5mm;
  border-top: 1px solid #e6e6e6;
  text-align: left;
  vertical-align: top;
}
.pdf-table th {
  background: #f3f0ea;
  color: #231f20;
  font-weight: 800;
}
.pdf-risk-high td:first-child { color: #cc0000; font-weight: 800; }
.pdf-risk-medium td:first-child { color: #777877; font-weight: 800; }
.pdf-risk-low td:first-child { color: #333333; font-weight: 800; }
.pdf-note-list {
  margin: 1.5mm 0 0;
  padding-left: 4mm;
  font-size: 8.5pt;
}
.pdf-note-list li + li { margin-top: 1mm; }
.report-icon { display: none; }
"""


def _render_pdf_page_header(number: str, title: str, thesis: str = "") -> str:
    html = (
        '<div class="pdf-page-header">'
        f'<div class="pdf-page-number">{_e(number)}</div>'
        '<div>'
        f'<h2>{_e(title)}</h2>'
    )
    if thesis:
        html += f'<p class="pdf-thesis">{_txt(thesis)}</p>'
    return html + '</div></div>'


def _render_pdf_cover(model: Dict[str, Any]) -> str:
    cover = _dict(model.get("cover"))
    credibility = _dict(model.get("credibility"))
    scope = _dict(credibility.get("analysis_scope"))
    metrics = [
        ("题目数", scope.get("questions", "-")),
        ("总分", scope.get("total_score", "-")),
        ("元数据状态", _status_label(credibility.get("metadata_status", "-"))),
        ("AI 调用", credibility.get("llm_calls_total", "-")),
    ]
    metric_html = "".join(
        f'<article><span>{_e(label)}</span><strong>{_e(value)}</strong></article>'
        for label, value in metrics
    )
    return (
        '<section class="pdf-page pdf-cover">'
        '<div>'
        '<div class="pdf-kicker">PDF 专用版式 / 审题与审卷质量诊断</div>'
        f'<h1>{_e(cover.get("title", "AI 审题与审卷质量诊断报告"))}</h1>'
        f'<div class="exam-name">{_e(cover.get("exam_name", "未命名试卷"))}</div>'
        f'<p class="pdf-cover-note">{_txt(credibility.get("method_note", ""))}</p>'
        '</div>'
        f'<div class="pdf-cover-metrics">{metric_html}</div>'
        '</section>'
    )


def _render_pdf_summary(model: Dict[str, Any]) -> str:
    summary = _dict(model.get("executive_summary"))
    calls = []
    for item in _items(summary.get("big_calls"))[:4]:
        calls.append(
            f'<article class="pdf-call {_stance_class(item.get("stance"))}">'
            f'<div class="pdf-call-id">{_e(_call_label(item.get("id")))}</div>'
            f'<h3>{_e(item.get("title"))}</h3>'
            f'<p>{_txt(item.get("why_it_matters"))}</p>'
            f'<p><b>行动建议：</b>{_txt(item.get("recommended_action"))}</p>'
            f'<div class="pdf-evidence">证据：{_e(" / ".join(_ref_label(ref) for ref in _items(item.get("evidence_refs"))))}</div>'
            '</article>'
        )
    glance = "".join(
        f'<article class="pdf-metric"><span>{_e(item.get("metric"))}</span><strong>{_e(_display_value(item.get("value")))}</strong><p>{_txt(item.get("interpretation"))}</p></article>'
        for item in _items(model.get("at_a_glance"))
    )
    return (
        '<section class="pdf-page pdf-content">'
        f'{_render_pdf_page_header("01", "执行摘要", summary.get("lead_judgment", ""))}'
        f'<div class="pdf-grid-2">{"".join(calls)}</div>'
        f'<div class="pdf-grid-4" style="margin-top:3mm">{glance}</div>'
        '</section>'
    )


def _render_pdf_figure_card(figure: Dict[str, Any]) -> str:
    chart = render_figure_chart(figure)
    return (
        '<article class="pdf-figure">'
        f'<div class="pdf-exhibit-label">{_e(_ref_label(figure.get("source")))}</div>'
        f'<h3>{_txt(figure.get("title"))}</h3>'
        f'<p><b>结论：</b>{_txt(figure.get("takeaway"))}</p>'
        f'<div class="chart-frame"><div class="chart-kicker">图表展板</div>{chart or _render_data(figure.get("data"))}</div>'
        f'<div class="pdf-source">来源：{_e(_ref_label(figure.get("source")))}</div>'
        '</article>'
    )


def _render_pdf_figure_pages(
    *,
    number: str,
    title: Any,
    thesis: Any,
    figures: List[Dict[str, Any]],
    implications: List[Any] | None = None,
    panel_title: str = "综合判读",
    page_class: str = "",
    per_page: int = 1,
) -> str:
    if not figures:
        return ""
    page_chunks = [figures[index : index + per_page] for index in range(0, len(figures), per_page)]
    pages = []
    extra_class = f" {page_class}" if page_class else ""
    total_pages = len(page_chunks)
    for index, chunk in enumerate(page_chunks):
        page_number = number if total_pages == 1 else f"{number}.{index + 1}"
        page_title = title if total_pages == 1 else f"{title}（{index + 1}/{total_pages}）"
        pages.append(
            f'<section class="pdf-page pdf-content{extra_class}">'
            f'{_render_pdf_page_header(page_number, page_title, thesis)}'
            f'<div class="pdf-grid-2 pdf-figure-spread">{"".join(_render_pdf_figure_card(figure) for figure in chunk)}</div>'
            '</section>'
        )
    return "".join(pages)


def _render_pdf_chapter_pages(model: Dict[str, Any]) -> str:
    figures = []
    implications: List[Any] = []
    for chapter in _items(model.get("chapters")):
        chapter = _dict(chapter)
        implications.extend(_items(chapter.get("implications"))[:1])
        for figure in _items(chapter.get("figures")):
            figures.append(_dict(figure))
    return _render_pdf_figure_pages(
        number="02",
        title="核心图表矩阵",
        thesis="难度、认知层级、知识点、素养、风险与元数据分组展示，避免压缩后失真。",
        figures=figures[:6],
        implications=implications[:4],
        panel_title="综合判读",
        page_class="pdf-core-chart-page",
    )


def _render_pdf_fine_grained(model: Dict[str, Any]) -> str:
    target = None
    for chapter in _items(model.get("chapters")):
        chapter = _dict(chapter)
        if chapter.get("id") == "fine_grained_evidence":
            target = chapter
            break
    if not target:
        return ""

    figures = []
    for figure in _items(target.get("figures"))[:3]:
        figures.append(_dict(figure))
    return _render_pdf_figure_pages(
        number="03",
        title=target.get("title", "审题证据矩阵"),
        thesis=target.get("thesis", ""),
        figures=figures,
        implications=_items(target.get("implications"))[:3],
        panel_title="业务含义",
        page_class="pdf-fine-page",
    )


def _render_pdf_portfolio(model: Dict[str, Any]) -> str:
    portfolio = _dict(model.get("question_portfolio"))
    rows = []
    for row in _items(portfolio.get("rows"))[:14]:
        risk = row.get("risk_level")
        rows.append(
            f'<tr class="pdf-{_risk_class(risk)}">'
            f'<td>Q{_e(row.get("question_id"))}</td>'
            f'<td>{_e(_risk_label(risk))}</td>'
            f'<td>{_e(_status_label(row.get("quality_level")))}</td>'
            f'<td>{_e(row.get("difficulty_display", row.get("difficulty")))}</td>'
            f'<td>{_e(row.get("score"))}</td>'
            f'<td>{_e(_status_label(row.get("metadata_confidence")))}</td>'
            f'<td>{_txt(row.get("primary_issue"))}</td>'
            '</tr>'
        )
    return (
        '<section class="pdf-page pdf-content">'
        f'{_render_pdf_page_header("04", "题目组合诊断", portfolio.get("thesis", ""))}'
        f'<div class="pdf-wide-chart"><div class="chart-kicker">组合图表</div>{render_portfolio_bubble(_items(portfolio.get("rows")))}</div>'
        '<table class="pdf-table"><thead><tr><th>题号</th><th>风险</th><th>质量</th><th>难度</th><th>分值</th><th>置信度</th><th>核心问题</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        '</section>'
    )


def _render_pdf_deep_dives(model: Dict[str, Any]) -> str:
    panels = []
    for dive in _items(model.get("deep_dives"))[:4]:
        trace = _dict(dive.get("metadata_trace"))
        panels.append(
            '<article class="pdf-panel">'
            f'<h3>Q{_e(dive.get("question_id"))}｜{_e(dive.get("headline"))}</h3>'
            f'<p>{_txt(dive.get("diagnosis"))}</p>'
            '<ul class="pdf-note-list">'
            + "".join(f'<li>{_e(_display_value(item))}</li>' for item in _items(dive.get("revision_plan")))
            + f'<li>元数据置信度：{_e(_status_label(trace.get("confidence")))}</li>'
            + '</ul></article>'
        )
    return (
        '<section class="pdf-page pdf-content">'
        f'{_render_pdf_page_header("05", "高风险题单题审查", "只保留首批高优先级题目，避免 PDF 变成流水账。")}'
        f'<div class="pdf-grid-2">{"".join(panels)}</div>'
        '</section>'
    )


def _render_pdf_methodology(model: Dict[str, Any]) -> str:
    methodology = _dict(model.get("methodology"))
    rows = []
    for item in _items(methodology.get("prompt_inventory")):
        rows.append(
            '<tr>'
            f'<td>{_e(_purpose_label(item.get("purpose")))}</td>'
            f'<td>{_e(item.get("records"))}</td>'
            f'<td>{_e("、".join(_field_label(field) for field in _items(item.get("parsed_fields"))[:5]))}</td>'
            f'<td>{_e(_prompt_summary(_dict(item)))}</td>'
            '</tr>'
        )
    return (
        '<section class="pdf-page pdf-content">'
        f'{_render_pdf_page_header("06", "AI 调用与方法论", "元数据、提示词和字段解析是报告可信度的根。")}'
        f'<div class="pdf-wide-chart"><div class="chart-kicker">方法论图表</div>{render_methodology_chart(methodology)}</div>'
        '<table class="pdf-table"><thead><tr><th>调用目的</th><th>记录数</th><th>关键字段</th><th>提示词摘要</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        '</section>'
    )


def render_report_product_pdf_html(model: Dict[str, Any]) -> str:
    """Render the dense PDF-specific commercial report layout."""
    title = _dict(model.get("cover")).get("title", "AI 审题与审卷质量诊断报告")
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head>'
        '<meta charset="UTF-8">'
        f'<title>{_e(title)} PDF</title>'
        f'<style>{_pdf_stylesheet()}</style>'
        '</head><body>'
        '<main class="pdf-report">'
        f'{_render_pdf_cover(model)}'
        f'{_render_pdf_summary(model)}'
        f'{_render_pdf_chapter_pages(model)}'
        f'{_render_pdf_fine_grained(model)}'
        f'{_render_pdf_portfolio(model)}'
        f'{_render_pdf_deep_dives(model)}'
        f'{_render_pdf_methodology(model)}'
        '</main>'
        '</body></html>'
    )


def render_report_product_html(model: Dict[str, Any]) -> str:
    """Render a complete commercial report page from the product model."""
    title = _dict(model.get("cover")).get("title", "AI 审题与审卷质量诊断报告")
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head>"
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{_e(title)}</title>"
        '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Ccircle cx=%2716%27 cy=%2716%27 r=%2714%27 fill=%27none%27 stroke=%27%23cc0000%27 stroke-width=%273%27/%3E%3Cpath d=%27M16 4v24M7 16h18%27 stroke=%27%23cc0000%27 stroke-width=%272%27/%3E%3C/svg%3E">'
        f"<style>{_stylesheet()}</style>"
        "</head><body>"
        f"{_render_nav()}"
        '<main id="main-content" class="report-main">'
        f"{_render_hero(model)}"
        f"{_render_summary(model)}"
        f"{_render_glance(model)}"
        f"{_render_chapters(model)}"
        f"{_render_portfolio(model)}"
        f"{_render_deep_dives(model)}"
        f"{_render_methodology(model)}"
        "</main>"
        f'<script id="productData" type="application/json">{_json(model)}</script>'
        "</body></html>"
    )


def write_report_product_html(model: Dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report_product_html(model), encoding="utf-8")
    return path
