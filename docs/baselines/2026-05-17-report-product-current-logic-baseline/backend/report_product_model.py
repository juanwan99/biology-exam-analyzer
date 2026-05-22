"""Commercial-grade report model for exam quality diagnosis.

This module converts the existing ``report_data`` aggregate into a
Bain-style report contract: judgment first, evidence second, figures and
actions after that. It does not call LLMs and does not render HTML/PDF.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List

from report_commercial_narrative import (
    action_for_question,
    difficulty_thesis,
    metadata_status,
    primary_issue,
    question_risk_level,
    risk_stance,
)


PARSED_FIELDS = [
    "quality_score",
    "difficulty",
    "knowledge_points",
    "primary_competency",
    "fine_grained_units",
    "seu_knowledge_breakdown",
    "diagnostic_highlights",
    "competency_weights",
    "difficulty_estimate",
    "metadata_confidence",
    "metadata_warnings",
]

PROMPT_CONTRACTS = {
    "question_analysis": {
        "prompt_id": "biology.question_analysis.v2",
        "prompt": "backend/prompts/analysis_prompt_v2.txt：分析题目结构、SEU/DU 证据、知识关联、核心素养、难度与元数据追踪。",
        "analysis_dimensions": [
            "quality",
            "difficulty",
            "knowledge",
            "competency",
            "seu_du",
            "metadata",
        ],
        "parsed_fields": [
            "knowledge_points",
            "primary_competency",
            "fine_grained_units",
            "scoring_units",
            "diagnostic_units",
            "stimulus_units",
            "seu_knowledge_breakdown",
            "diagnostic_highlights",
            "competency_weights",
            "difficulty_estimate",
            "metadata_confidence",
            "metadata_warnings",
        ],
    },
    "feature_extraction": {
        "prompt_id": "biology.feature_extraction",
        "prompt": "prompts/biology/feature_extractor.txt 或 feature_extractor.build_feature_prompt：分析难度驱动因素、命题质量与教学价值。",
        "analysis_dimensions": [
            "working_memory",
            "reasoning_steps",
            "chain_coupling",
            "trap_density",
            "novelty",
            "knowledge_breadth",
            "bloom",
            "representation_complexity",
            "quality",
        ],
        "parsed_fields": [
            "working_memory",
            "reasoning_steps",
            "chain_coupling",
            "trap_density",
            "novelty",
            "knowledge_breadth",
            "bloom",
            "quality_score",
            "quality_scientific",
            "quality_normative",
            "quality_language",
            "quality_context",
            "teacher_comment",
            "metadata_confidence",
        ],
    },
    "big_question_feature_extraction": {
        "prompt_id": "biology.big_question_feature_extraction",
        "prompt": "prompts/biology/big_question_extractor.txt：分析小问依赖、全局情境负荷、方法新颖度、难度与质量。",
        "analysis_dimensions": [
            "sub_questions",
            "dependencies",
            "global_features",
            "difficulty",
            "quality",
            "metadata",
        ],
        "parsed_fields": [
            "sub_questions",
            "dependencies",
            "global_features",
            "bloom_distribution",
            "quality_score",
            "teacher_comment",
            "metadata_confidence",
        ],
    },
    "competency_analysis": {
        "prompt_id": "biology.competency_analysis",
        "prompt": "backend/prompts/competency_analysis_prompt.txt：映射四类生物核心素养，输出权重、层级与证据。",
        "analysis_dimensions": [
            "life_concept",
            "scientific_thinking",
            "scientific_inquiry",
            "social_responsibility",
            "evidence",
        ],
        "parsed_fields": [
            "生命观念",
            "科学思维",
            "科学探究",
            "社会责任",
            "metadata_confidence",
        ],
    },
    "split_questions": {
        "prompt_id": "biology.split_questions",
        "prompt": "prompts/biology/split_prompt.txt：在详细分析前，将原始试卷内容拆分为结构化题目记录。",
        "analysis_dimensions": ["question_boundary", "question_type", "section_header"],
        "parsed_fields": ["id", "content", "question_type", "section_header"],
    },
}

QUALITY_GATES = [
    "metadata envelope required",
    "question_analysis required",
    "feature_extraction or big_question_feature_extraction required",
    "competency_analysis or SEU-derived competency required",
]

LIMITATIONS = [
    "LLM 生成的诊断结论在正式使用前应由学科教师复核。",
    "低置信度元数据是复核信号，不等同于最终质量判定。",
    "题目风险等级综合模型输出与元数据质量，用于排序人工复核优先级。",
]


def _as_dict(value: Any) -> Dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List:
    return value if isinstance(value, list) else []


def _num(value: Any, default: float = 0.0) -> float:
    return value if isinstance(value, (int, float)) else default


def _format_num(value: Any, digits: int = 1) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value) if value is not None else "-"


def _quality_level(score: Any, feature_status: str = "ok") -> str:
    if feature_status == "failed":
        return "待优化"
    if not isinstance(score, (int, float)):
        return "未评估"
    if score <= 2:
        return "硬伤"
    if score == 3:
        return "待优化"
    return "稳定"


def _sorted_questions(questions: Iterable[Dict]) -> List[Dict]:
    return sorted(_as_list(list(questions)), key=lambda item: (item.get("id") is None, item.get("id") or 0))


def _llm_total(llm_counts: Dict[str, Any]) -> int:
    return int(sum(value for value in llm_counts.values() if isinstance(value, (int, float))))


def _competency_pct(value: Any) -> float:
    if isinstance(value, dict):
        value = value.get("占比", value.get("percentage", value.get("value", 0)))
    return float(value) if isinstance(value, (int, float)) else 0.0


def _missing_competency_dims(competency: Dict) -> List[str]:
    distribution = _as_dict(competency.get("distribution"))
    missing = []
    for name in ("生命观念", "科学思维", "科学探究", "社会责任"):
        if _competency_pct(distribution.get(name)) <= 0:
            missing.append(name)
    return missing


def _build_cover(exam: Dict) -> Dict:
    return {
        "title": "AI 试卷质量诊断报告",
        "exam_name": exam.get("name", "未命名试卷"),
        "subject": exam.get("subject", "biology"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_version": "commercial_report.v1",
    }


def _build_credibility(exam: Dict, questions: List[Dict], metadata: Dict) -> Dict:
    llm_counts = _as_dict(metadata.get("llm_call_counts"))
    total_score = exam.get("total_score")
    if not isinstance(total_score, (int, float)):
        total_score = sum(_num(q.get("total_score")) for q in questions)
    return {
        "analysis_scope": {
            "questions": exam.get("total_questions", len(questions)),
            "total_score": total_score,
        },
        "metadata_status": metadata_status(metadata),
        "llm_calls_total": _llm_total(llm_counts),
        "method_note": "报告基于题目分析、难度特征、核心素养与元数据门禁生成；高风险结论用于排序人工复核优先级。",
    }


def _build_question_rows(questions: List[Dict]) -> List[Dict]:
    rows = []
    for question in _sorted_questions(questions):
        qid = question.get("id")
        risk = question_risk_level(question)
        feature_status = question.get("feature_status", "ok")
        confidence = question.get("metadata_confidence", 0)
        scoring_units = _question_scoring_units(question)
        diagnostic_units = _question_diagnostic_units(question)
        pressure = _question_pressure(question, scoring_units, diagnostic_units)
        rows.append({
            "question_id": qid,
            "risk_level": risk,
            "stance": risk_stance(risk),
            "quality_level": _quality_level(question.get("quality_score"), feature_status),
            "difficulty": question.get("difficulty"),
            "difficulty_label": question.get("difficulty_label", ""),
            "score": question.get("total_score"),
            "metadata_confidence": confidence,
            "metadata_gap": pressure["metadata_gap"],
            "evidence_density": pressure["evidence_density"],
            "pressure_index": pressure["pressure_index"],
            "dominant_pressure": pressure["dominant_pressure"],
            "primary_issue": primary_issue(question),
            "action": action_for_question(question),
            "evidence_refs": [f"question:{qid}.quality", f"question:{qid}.metadata"],
        })
    return rows


def _question_fine_grained(question: Dict) -> Dict:
    fine_units = _as_dict(question.get("fine_grained_units"))
    if fine_units:
        return fine_units
    analysis = _as_dict(question.get("analysis"))
    fine = _as_dict(analysis.get("_fine_grained"))
    if fine:
        return fine
    envelope = _as_dict(question.get("_metadata_envelope"))
    return _as_dict(envelope.get("analysis_units"))


def _question_scoring_units(question: Dict) -> List[Dict]:
    fine = _question_fine_grained(question)
    units = _as_list(fine.get("scoring_units"))
    if units:
        return [_as_dict(unit) for unit in units]
    return [_as_dict(unit) for unit in _as_list(question.get("seu_knowledge_breakdown"))]


def _question_diagnostic_units(question: Dict) -> List[Dict]:
    fine = _question_fine_grained(question)
    units = _as_list(fine.get("diagnostic_units"))
    if units:
        return [_as_dict(unit) for unit in units]
    return [_as_dict(unit) for unit in _as_list(question.get("diagnostic_highlights"))]


def _question_stimulus_units(question: Dict) -> List[Dict]:
    fine = _question_fine_grained(question)
    return [_as_dict(unit) for unit in _as_list(fine.get("stimulus_units"))]


def _unit_knowledge(unit: Dict, question: Dict) -> str:
    links = _as_list(unit.get("knowledge_links"))
    for link in links:
        link = _as_dict(link)
        if link.get("knowledge_point"):
            return str(link.get("knowledge_point"))
    points = _as_list(question.get("knowledge_points"))
    return str(points[0]) if points else "未标注知识点"


def _unit_competency(unit: Dict, question: Dict) -> str:
    weights = _as_dict(unit.get("competency_weights"))
    weighted = {key: value for key, value in weights.items() if isinstance(value, (int, float))}
    if weighted:
        return str(max(weighted, key=weighted.get))
    competency = unit.get("competency")
    if isinstance(competency, dict):
        return str(competency.get("primary") or question.get("primary_competency") or "未标注素养")
    if competency:
        return str(competency)
    return str(question.get("primary_competency") or "未标注素养")


def _unit_competency_weights(unit: Dict, question: Dict) -> Dict[str, float]:
    weights = _as_dict(unit.get("competency_weights"))
    weighted = {str(key): float(value) for key, value in weights.items() if isinstance(value, (int, float))}
    if weighted:
        total = sum(value for value in weighted.values() if value > 0)
        return {key: round(value / total, 4) for key, value in weighted.items()} if total > 0 else weighted
    primary = _unit_competency(unit, question)
    return {primary: 1.0} if primary and primary != "未标注素养" else {}


def _unit_bloom(unit: Dict, question: Dict) -> int:
    value = unit.get("bloom_level", question.get("bloom_level", question.get("bloom", 3)))
    return int(value) if isinstance(value, (int, float)) else 3


def _unit_difficulty(unit: Dict, question: Dict) -> float:
    value = unit.get("difficulty_estimate", question.get("difficulty", 5))
    return float(value) if isinstance(value, (int, float)) else 5.0


def _question_pressure(question: Dict, scoring_units: List[Dict], diagnostic_units: List[Dict]) -> Dict[str, Any]:
    difficulty = max(0.0, min(1.0, _num(question.get("difficulty"), 0) / 10))
    quality_score = _num(question.get("quality_score"), 5)
    quality_gap = max(0.0, min(1.0, (5 - quality_score) / 5))
    metadata_gap = max(0.0, min(1.0, 1 - _num(question.get("metadata_confidence"), 1)))
    max_trap = max((_num(unit.get("trap_strength"), 0) for unit in diagnostic_units), default=0)
    trap_pressure = max(0.0, min(1.0, max_trap / 3))
    evidence_density = len(scoring_units) + len(diagnostic_units)
    density_pressure = max(0.0, min(1.0, evidence_density / 5))

    components = {
        "难度": difficulty,
        "质量": quality_gap,
        "元数据": metadata_gap,
        "陷阱": trap_pressure,
        "证据密度": density_pressure,
    }
    weighted = (
        difficulty * 0.30
        + quality_gap * 0.25
        + metadata_gap * 0.20
        + trap_pressure * 0.15
        + density_pressure * 0.10
    )
    return {
        "pressure_index": round(weighted * 100, 1),
        "dominant_pressure": max(components, key=components.get),
        "metadata_gap": round(metadata_gap, 2),
        "evidence_density": evidence_density,
        "quality_gap": round(quality_gap, 2),
        "trap_pressure": round(trap_pressure, 2),
    }


def _build_knowledge_exhibit_rows(knowledge: Dict, seu_rows: List[Dict]) -> List[Dict]:
    aggregate: Dict[str, Dict[str, Any]] = {}

    def bucket(name: str) -> Dict[str, Any]:
        return aggregate.setdefault(name, {
            "name": name,
            "weighted_score": 0.0,
            "seu_count": 0,
            "question_ids": set(),
            "risk_question_ids": set(),
            "bloom_total": 0.0,
            "bloom_count": 0,
        })

    for row in seu_rows:
        name = str(row.get("knowledge_point") or "未标注知识点")
        item = bucket(name)
        item["weighted_score"] += _num(row.get("score_contribution"), _num(row.get("weighted_score")))
        item["seu_count"] += 1
        qid = row.get("question_id")
        if qid is not None:
            item["question_ids"].add(qid)
            if row.get("risk_level") == "high":
                item["risk_question_ids"].add(qid)
        bloom = row.get("bloom_level")
        if isinstance(bloom, (int, float)):
            item["bloom_total"] += bloom
            item["bloom_count"] += 1

    for point in _as_list(knowledge.get("top_points")):
        point = _as_dict(point)
        name = str(point.get("name") or point.get("label") or "未标注知识点")
        item = bucket(name)
        item["weighted_score"] = max(item["weighted_score"], _num(point.get("weighted_score", point.get("value", point.get("count")))))

    rows = []
    for item in aggregate.values():
        bloom_count = item["bloom_count"] or 1
        rows.append({
            "name": item["name"],
            "weighted_score": round(item["weighted_score"], 2),
            "seu_count": item["seu_count"],
            "question_count": len(item["question_ids"]),
            "risk_count": len(item["risk_question_ids"]),
            "avg_bloom": round(item["bloom_total"] / bloom_count, 2) if item["bloom_count"] else 0,
        })
    return sorted(rows, key=lambda row: (-row["weighted_score"], -row["risk_count"], row["name"]))[:10]


def _build_fine_grained_exhibits(questions: List[Dict], rows: List[Dict]) -> Dict:
    by_id = {row["question_id"]: row for row in rows}
    seu_rows: List[Dict] = []
    du_rows: List[Dict] = []
    su_rows: List[Dict] = []
    knowledge_contribution_rows: List[Dict] = []
    competency_contribution_rows: List[Dict] = []
    metadata_audit_rows: List[Dict] = []
    factor_rows: List[Dict] = []

    for question in _sorted_questions(questions):
        qid = question.get("id")
        row = by_id.get(qid, {})
        score = _num(question.get("total_score"), 1.0) or 1.0
        scoring_units = _question_scoring_units(question)
        diagnostic_units = _question_diagnostic_units(question)
        stimulus_units = _question_stimulus_units(question)
        share_sum = 0.0
        knowledge_share_valid = True
        competency_weight_valid = True

        for index, unit in enumerate(scoring_units, 1):
            share = _num(unit.get("score_share"), 1 / max(len(scoring_units), 1))
            share_sum += share
            confidence = _num(unit.get("allocation_confidence"), question.get("metadata_confidence", 0))
            weighted_score = round(score * share, 2)
            knowledge_links = [_as_dict(link) for link in _as_list(unit.get("knowledge_links"))]
            competency_weights = _unit_competency_weights(unit, question)
            seu_id = unit.get("seu_id") or f"Q{qid}-SEU{index}"
            if knowledge_links:
                link_sum = sum(_num(link.get("share"), 0) for link in knowledge_links)
                if abs(link_sum - 1.0) > 0.03:
                    knowledge_share_valid = False
            weight_sum = sum(value for value in competency_weights.values() if isinstance(value, (int, float)))
            if competency_weights and abs(weight_sum - 1.0) > 0.03:
                competency_weight_valid = False
            seu_rows.append({
                "question_id": qid,
                "seu_id": seu_id,
                "label": unit.get("label") or f"采分单元 {index}",
                "score_share": round(share, 4),
                "weighted_score": weighted_score,
                "allocation_source": unit.get("allocation_source", "inferred"),
                "knowledge_point": _unit_knowledge(unit, question),
                "knowledge_links": knowledge_links,
                "competency": _unit_competency(unit, question),
                "competency_weights": competency_weights,
                "bloom_level": _unit_bloom(unit, question),
                "difficulty_estimate": round(_unit_difficulty(unit, question), 2),
                "allocation_confidence": round(confidence, 2),
                "reasoning_brief": unit.get("reasoning_brief", ""),
                "risk_level": row.get("risk_level", "medium"),
            })
            for link in knowledge_links:
                link_share = _num(link.get("share"), 1 / max(len(knowledge_links), 1))
                knowledge_contribution_rows.append({
                    "question_id": qid,
                    "seu_id": seu_id,
                    "knowledge_point": link.get("knowledge_point", "未标注知识点"),
                    "share": round(link_share, 4),
                    "score_contribution": round(score * share * link_share, 2),
                    "allocation_confidence": round(confidence, 2),
                    "risk_level": row.get("risk_level", "medium"),
                })
            for dim, weight in competency_weights.items():
                competency_contribution_rows.append({
                    "question_id": qid,
                    "seu_id": seu_id,
                    "competency": dim,
                    "weight": round(weight, 4),
                    "score_contribution": round(score * share * weight, 2),
                    "allocation_confidence": round(confidence, 2),
                    "risk_level": row.get("risk_level", "medium"),
                })

        for index, unit in enumerate(diagnostic_units, 1):
            du_rows.append({
                "question_id": qid,
                "du_id": unit.get("du_id") or f"Q{qid}-DU{index}",
                "option_or_trap": unit.get("option_or_trap") or unit.get("option") or f"trap_{index}",
                "distractor_type": unit.get("distractor_type", "misconception"),
                "misconception": unit.get("misconception", ""),
                "trap_strength": int(_num(unit.get("trap_strength"), 2)),
                "knowledge_boundary": unit.get("knowledge_boundary", ""),
                "risk_level": row.get("risk_level", "medium"),
            })

        for index, unit in enumerate(stimulus_units, 1):
            su_rows.append({
                "question_id": qid,
                "su_id": unit.get("su_id") or f"Q{qid}-SU{index}",
                "stimulus_type": unit.get("stimulus_type", unit.get("type", "unknown")),
                "description": unit.get("description", ""),
                "complexity": unit.get("complexity", unit.get("complexity_level")),
                "is_core": unit.get("is_core", True),
            })

        bloom_values = [_unit_bloom(unit, question) for unit in scoring_units]
        difficulty_values = [_unit_difficulty(unit, question) for unit in scoring_units]
        trap_values = [_num(unit.get("trap_strength"), 0) for unit in diagnostic_units]
        pressure = _question_pressure(question, scoring_units, diagnostic_units)
        avg_conf = (
            round(sum(_num(unit.get("allocation_confidence"), question.get("metadata_confidence", 0)) for unit in scoring_units) / len(scoring_units), 2)
            if scoring_units else _num(question.get("metadata_confidence"), 0)
        )
        metadata_audit_rows.append({
            "question_id": qid,
            "seu_count": len(scoring_units),
            "du_count": len(diagnostic_units),
            "su_count": len(stimulus_units),
            "score_share_sum": round(share_sum, 4) if scoring_units else 0,
            "score_share_valid": abs(share_sum - 1.0) <= 0.03 if scoring_units else False,
            "knowledge_share_valid": knowledge_share_valid,
            "competency_weight_valid": competency_weight_valid,
            "avg_allocation_confidence": avg_conf,
            "metadata_confidence": _num(question.get("metadata_confidence")),
            "warnings": _as_list(question.get("metadata_warnings")),
        })
        factor_rows.append({
            "question_id": qid,
            "score": score,
            "difficulty": _num(question.get("difficulty"), sum(difficulty_values) / len(difficulty_values) if difficulty_values else 0),
            "quality_score": _num(question.get("quality_score")),
            "metadata_confidence": _num(question.get("metadata_confidence")),
            "metadata_gap": pressure["metadata_gap"],
            "evidence_density": pressure["evidence_density"],
            "pressure_index": pressure["pressure_index"],
            "dominant_pressure": pressure["dominant_pressure"],
            "quality_gap": pressure["quality_gap"],
            "trap_pressure": pressure["trap_pressure"],
            "seu_count": len(scoring_units),
            "du_count": len(diagnostic_units),
            "avg_bloom": round(sum(bloom_values) / len(bloom_values), 2) if bloom_values else _num(question.get("bloom_level"), 0),
            "avg_seu_difficulty": round(sum(difficulty_values) / len(difficulty_values), 2) if difficulty_values else _num(question.get("difficulty")),
            "max_trap_strength": max(trap_values) if trap_values else 0,
            "risk_level": row.get("risk_level", "medium"),
        })

    avg_conf = (
        round(sum(row["allocation_confidence"] for row in seu_rows) / len(seu_rows), 2)
        if seu_rows else 0
    )
    return {
        "summary": {
            "total_seus": len(seu_rows),
            "total_dus": len(du_rows),
            "total_sus": len(su_rows),
            "knowledge_links": len(knowledge_contribution_rows),
            "competency_links": len(competency_contribution_rows),
            "avg_allocation_confidence": avg_conf,
            "questions_with_units": len([row for row in factor_rows if row["seu_count"] > 0]),
        },
        "seu_rows": seu_rows,
        "du_rows": du_rows,
        "su_rows": su_rows,
        "knowledge_contribution_rows": knowledge_contribution_rows,
        "competency_contribution_rows": competency_contribution_rows,
        "metadata_audit_rows": metadata_audit_rows,
        "difficulty_factor_rows": factor_rows,
    }


def _metric(name: str, value: Any, unit: str = "") -> Dict[str, Any]:
    return {"name": name, "value": value, "unit": unit}


def _build_findings(
    report_data: Dict,
    rows: List[Dict],
    fine_exhibits: Dict,
    knowledge_exhibit_rows: List[Dict],
) -> List[Dict]:
    summary = _as_dict(fine_exhibits.get("summary"))
    factor_rows = _as_list(fine_exhibits.get("difficulty_factor_rows"))
    seu_rows = _as_list(fine_exhibits.get("seu_rows"))
    du_rows = _as_list(fine_exhibits.get("du_rows"))
    audit_rows = _as_list(fine_exhibits.get("metadata_audit_rows"))
    findings: List[Dict] = []

    if summary.get("total_seus"):
        evidence = [
            f"seu:Q{row.get('question_id')}:{row.get('seu_id')}"
            for row in seu_rows[:6]
        ]
        findings.append({
            "id": "fine_grained_fidelity",
            "type": "metadata_finding",
            "title": "综合诊断已建立在 SEU/DU 证据层上",
            "claim": (
                f"本次报告可追溯到 {summary.get('total_seus', 0)} 个 SEU、"
                f"{summary.get('total_dus', 0)} 个 DU 和 {summary.get('total_sus', 0)} 个 SU。"
            ),
            "why_it_matters": (
                "执行摘要不再依赖题目级均值，而是绑定到可展开的评分单元、诊断单元和材料单元。"
            ),
            "severity": "medium",
            "confidence": summary.get("avg_allocation_confidence", 0),
            "metrics": [
                _metric("SEU", summary.get("total_seus", 0), "个"),
                _metric("DU", summary.get("total_dus", 0), "个"),
                _metric("SU", summary.get("total_sus", 0), "个"),
                _metric("知识点链接", summary.get("knowledge_links", 0), "条"),
            ],
            "contributors": [row.get("question_id") for row in factor_rows if row.get("seu_count")][:8],
            "evidence_refs": evidence,
            "recommended_action": "所有执行摘要结论优先引用 SEU/DU 贡献表，题目级均值只作为导航层。",
        })

    if len(factor_rows) >= 5:
        sorted_factors = sorted(factor_rows, key=lambda row: row.get("question_id") or 0)
        tail = sorted_factors[-5:]
        total_score = sum(_num(row.get("score")) for row in sorted_factors) or 1
        tail_score = sum(_num(row.get("score")) for row in tail)
        tail_seus = sum(int(_num(row.get("seu_count"))) for row in tail)
        tail_dus = sum(int(_num(row.get("du_count"))) for row in tail)
        tail_pressure = round(sum(_num(row.get("pressure_index")) for row in tail) / len(tail), 1)
        top_tail = sorted(tail, key=lambda row: _num(row.get("pressure_index")), reverse=True)[:3]
        findings.append({
            "id": "tail_pressure_source",
            "type": "difficulty_finding",
            "title": "后段题组是整卷压力和区分度的主要来源",
            "claim": (
                f"后 5 题占 {round(tail_score / total_score * 100, 1)}% 分值，"
                f"包含 {tail_seus} 个 SEU 和 {tail_dus} 个 DU。"
            ),
            "why_it_matters": (
                "后段题组同时承载更高分值、更多评分单元和更多诊断陷阱，是复核命题梯度的优先区域。"
            ),
            "severity": "high" if tail_pressure >= 65 else "medium",
            "confidence": summary.get("avg_allocation_confidence", 0),
            "metrics": [
                _metric("后段分值占比", round(tail_score / total_score * 100, 1), "%"),
                _metric("后段 SEU", tail_seus, "个"),
                _metric("后段 DU", tail_dus, "个"),
                _metric("后段平均压力指数", tail_pressure),
            ],
            "contributors": [row.get("question_id") for row in top_tail],
            "evidence_refs": [f"question:Q{row.get('question_id')}.pressure" for row in top_tail],
            "recommended_action": "优先展开后段题组，检查高阶能力要求、评分标准和陷阱设计是否匹配。",
        })

    invalid_rows = [
        row for row in audit_rows
        if not row.get("score_share_valid")
        or not row.get("knowledge_share_valid")
        or not row.get("competency_weight_valid")
        or _num(row.get("avg_allocation_confidence"), 1) < 0.7
    ]
    if invalid_rows:
        findings.append({
            "id": "metadata_audit_gap",
            "type": "metadata_finding",
            "title": "部分题目的细粒度权重需要复核",
            "claim": f"{len(invalid_rows)} 道题存在权重守恒、知识点占比或置信度风险。",
            "why_it_matters": "元数据权重不守恒会直接扭曲知识点贡献、素养覆盖和后续图表诊断。",
            "severity": "high",
            "confidence": 0.7,
            "metrics": [
                _metric("需复核题数", len(invalid_rows), "道"),
                _metric("审计覆盖题数", len(audit_rows), "道"),
            ],
            "contributors": [row.get("question_id") for row in invalid_rows[:8]],
            "evidence_refs": [f"metadata:Q{row.get('question_id')}" for row in invalid_rows[:8]],
            "recommended_action": "正式导出前先复核这些题的分值占比、知识点权重和素养权重。",
        })
    elif audit_rows:
        findings.append({
            "id": "metadata_audit_pass",
            "type": "metadata_finding",
            "title": "细粒度权重审计未发现阻断项",
            "claim": "SEU 分值守恒、知识点占比和素养权重可支撑当前聚合诊断。",
            "why_it_matters": "权重审计通过意味着当前综合诊断具备可追溯的细粒度证据底座。",
            "severity": "low",
            "confidence": summary.get("avg_allocation_confidence", 0),
            "metrics": [
                _metric("审计覆盖题数", len(audit_rows), "道"),
                _metric("平均 SEU 置信度", summary.get("avg_allocation_confidence", 0)),
            ],
            "contributors": [row.get("question_id") for row in audit_rows[:8]],
            "evidence_refs": [f"metadata:Q{row.get('question_id')}" for row in audit_rows[:8]],
            "recommended_action": "继续使用审计矩阵作为正式报告的可信度底座。",
        })

    top_knowledge = knowledge_exhibit_rows[:3]
    if top_knowledge:
        findings.append({
            "id": "knowledge_concentration",
            "type": "knowledge_finding",
            "title": "知识点诊断可追溯到 SEU 分值贡献",
            "claim": "高权重知识点不再只来自题目标签，而是来自 SEU × knowledge share 的分值贡献。",
            "why_it_matters": "知识点优先级来自分值贡献后，复习建议和图表排序才不会被粗粒度题目标签误导。",
            "severity": "medium",
            "confidence": summary.get("avg_allocation_confidence", 0),
            "metrics": [
                _metric(row.get("name"), row.get("weighted_score"), "分")
                for row in top_knowledge
            ],
            "contributors": [row.get("name") for row in top_knowledge],
            "evidence_refs": ["fine_grained_exhibits.knowledge_contribution_rows"],
            "recommended_action": "知识点复习建议按分值贡献和高风险题关联排序，而不是按出现次数排序。",
        })

    return findings[:6]


def _build_big_calls(report_data: Dict, rows: List[Dict]) -> List[Dict]:
    metadata = _as_dict(report_data.get("metadata_quality"))
    metrics = _as_dict(report_data.get("metrics"))
    gradient = _as_dict(report_data.get("difficulty_gradient"))
    competency = _as_dict(report_data.get("competency"))
    knowledge = _as_dict(report_data.get("knowledge"))
    calls = []

    high_risk = [row for row in rows if row["risk_level"] == "high"]
    if high_risk:
        ids = [row["question_id"] for row in high_risk[:6]]
        calls.append({
            "id": "question_quality_risk",
            "title": f"{len(high_risk)} 道题进入高风险复核",
            "stance": "risk",
            "why_it_matters": "高风险题会直接影响整卷诊断可信度和教师采信程度。",
            "evidence_refs": [f"question:{qid}" for qid in ids],
            "recommended_action": "先复核高风险题的科学性、设问边界与元数据链路。",
        })

    status = metadata_status(metadata)
    if status != "pass":
        warning_count = len(_as_list(metadata.get("warning_questions")))
        missing_count = len(_as_list(metadata.get("missing_envelope_questions")))
        calls.append({
            "id": "metadata_governance",
            "title": "元数据治理存在交付前关注项",
            "stance": "risk" if status == "blocked" else "watch",
            "why_it_matters": f"warning={warning_count}，missing={missing_count}；元数据是报告结论可追溯性的根。",
            "evidence_refs": ["metadata:warning_questions", "metadata:missing_envelope_questions"],
            "recommended_action": "正式交付前先处理低置信度和 warning 题目，再出最终判断。",
        })

    avg_difficulty = metrics.get("avg_difficulty")
    if isinstance(avg_difficulty, (int, float)):
        stance = "risk" if avg_difficulty >= 7 else "watch" if avg_difficulty >= 6 else "positive"
        calls.append({
            "id": "difficulty_structure",
            "title": f"平均难度 {_format_num(avg_difficulty, 2)}",
            "stance": stance,
            "why_it_matters": gradient.get("gradient_type", "难度梯度待确认"),
            "evidence_refs": ["metric:avg_difficulty", "figure:difficulty_gradient"],
            "recommended_action": "结合高分值题与后段题组检查区分度是否来自合理能力要求。",
        })

    missing_dims = _missing_competency_dims(competency)
    if missing_dims:
        calls.append({
            "id": "competency_gap",
            "title": "核心素养覆盖存在空档",
            "stance": "watch",
            "why_it_matters": "缺失素养会削弱整卷对课程目标的覆盖解释力。",
            "evidence_refs": ["figure:competency_distribution"],
            "recommended_action": "补充或重写采分点，使缺失素养进入可评估范围：" + "、".join(missing_dims),
        })

    unmapped = knowledge.get("unmapped_count")
    if isinstance(unmapped, int) and unmapped > 0:
        calls.append({
            "id": "knowledge_mapping_gap",
            "title": f"{unmapped} 个知识点未完成标准映射",
            "stance": "watch",
            "why_it_matters": "知识点无法标准映射会影响教材覆盖和复习建议。",
            "evidence_refs": ["knowledge:unmapped_count"],
            "recommended_action": "补齐知识点标准化映射后再生成正式知识覆盖结论。",
        })

    if not calls:
        calls.append({
            "id": "stable_structure",
            "title": "整卷结构具备进入人工抽样复核的条件",
            "stance": "positive",
            "why_it_matters": "未发现元数据阻断项或高风险题集中暴露。",
            "evidence_refs": ["metadata:llm_call_counts", "question_portfolio:risk_levels"],
            "recommended_action": "进入教研组抽样复核并确认最终口径。",
        })

    return calls[:5]


def _build_executive_summary(report_data: Dict, rows: List[Dict], findings: List[Dict] | None = None) -> Dict:
    metrics = _as_dict(report_data.get("metrics"))
    gradient = _as_dict(report_data.get("difficulty_gradient"))
    calls = list(findings or []) + _build_big_calls(report_data, rows)
    high_count = len([row for row in rows if row["risk_level"] == "high"])
    lead = difficulty_thesis(metrics.get("avg_difficulty"), gradient.get("gradient_type", ""))
    if high_count:
        lead += f" 同时，{high_count} 道题需要优先复核，报告应先服务于命题修订决策。"
    return {
        "lead_judgment": lead,
        "big_calls": calls[:5],
    }


def _build_at_a_glance(
    exam: Dict,
    report_data: Dict,
    metadata: Dict,
    questions: List[Dict],
    fine_exhibits: Dict | None = None,
) -> List[Dict]:
    metrics = _as_dict(report_data.get("metrics"))
    fine = _as_dict(_as_dict(fine_exhibits).get("summary")) or _as_dict(report_data.get("fine_grained_summary"))
    llm_counts = _as_dict(metadata.get("llm_call_counts"))
    return [
        {
            "metric": "题目数量",
            "value": str(exam.get("total_questions", len(questions))),
            "interpretation": "本次诊断覆盖全卷题目。",
            "evidence_ref": "exam_info.total_questions",
        },
        {
            "metric": "平均难度",
            "value": _format_num(metrics.get("avg_difficulty"), 2),
            "interpretation": "用于判断整卷压力水平和区分度来源。",
            "evidence_ref": "metric:avg_difficulty",
        },
        {
            "metric": "SEU / DU",
            "value": f"{fine.get('total_seus', 0)} / {fine.get('total_dus', 0)}",
            "interpretation": "细粒度采分和诊断单元决定报告可操作性。",
            "evidence_ref": "fine_grained_summary",
        },
        {
            "metric": "LLM 调用",
            "value": str(_llm_total(llm_counts)),
            "interpretation": "统计题目分析、特征抽取和素养分析的调用覆盖。",
            "evidence_ref": "metadata:llm_call_counts",
        },
    ]


def _build_chapters(
    report_data: Dict,
    rows: List[Dict],
    fine_exhibits: Dict | None = None,
    knowledge_exhibit_rows: List[Dict] | None = None,
) -> List[Dict]:
    metrics = _as_dict(report_data.get("metrics"))
    gradient = _as_dict(report_data.get("difficulty_gradient"))
    knowledge = _as_dict(report_data.get("knowledge"))
    competency = _as_dict(report_data.get("competency"))
    fine = _as_dict(report_data.get("fine_grained_summary"))
    metadata = _as_dict(report_data.get("metadata_quality"))

    high_count = len([row for row in rows if row["risk_level"] == "high"])
    medium_count = len([row for row in rows if row["risk_level"] == "medium"])

    fine_exhibits = _as_dict(fine_exhibits)
    knowledge_exhibit_rows = knowledge_exhibit_rows or _as_list(knowledge.get("top_points"))
    chapters = [
        {
            "id": "exam_structure",
            "title": "整卷结构诊断",
            "thesis": difficulty_thesis(metrics.get("avg_difficulty"), gradient.get("gradient_type", "")),
            "figures": [
                {
                    "id": "difficulty_gradient",
                    "title": "难度梯度显示后段压力集中" if gradient else "难度梯度数据不足",
                    "takeaway": gradient.get("gradient_type", "缺少三段难度梯度，需补齐统计输入。"),
                    "data": {
                        "front": gradient.get("front"),
                        "middle": gradient.get("middle"),
                        "back": gradient.get("back"),
                        "avg_difficulty": metrics.get("avg_difficulty"),
                    },
                    "source": "report_data.difficulty_gradient",
                    "notes": "按题序切分前中后三段，结合平均难度解释结构压力。",
                },
                {
                    "id": "bloom_distribution",
                    "title": "Bloom 层级分布决定能力考查深度",
                    "takeaway": "高阶层级占比越高，越需要检查设问边界和评分标准。",
                    "data": metrics.get("bloom_distribution", {}),
                    "source": "report_data.metrics.bloom_distribution",
                    "notes": "层级来自题目分析结果与统计聚合。",
                },
            ],
            "implications": ["复核高分值题组是否承担了合理区分功能。"],
        },
        {
            "id": "knowledge_competency",
            "title": "知识与核心素养覆盖",
            "thesis": "专业报告不只呈现覆盖率，还要判断覆盖结构是否服务于课程目标。",
            "figures": [
                {
                    "id": "knowledge_top_points",
                    "title": "高权重知识点决定复习建议优先级",
                    "takeaway": "权重最高且关联高风险题的知识点应在教学建议中优先解释。",
                    "data": knowledge_exhibit_rows,
                    "source": "fine_grained_exhibits.seu_rows + report_data.knowledge.top_points",
                    "notes": "按题目分值、SEU 数、涉及题数、风险题数和平均 Bloom 层级综合排序。",
                },
                {
                    "id": "competency_distribution",
                    "title": "核心素养分布暴露课程目标覆盖空档",
                    "takeaway": "缺失或低占比素养需要通过题目或采分点补足。",
                    "data": competency.get("distribution", {}),
                    "source": "report_data.competency.distribution",
                    "notes": "来自独立素养分析或 SEU 派生素养权重。",
                },
            ],
            "implications": ["把知识覆盖和素养覆盖合并解释，避免只给统计表。"],
        },
        {
            "id": "quality_metadata",
            "title": "命题质量与元数据可信度",
            "thesis": f"当前有 {high_count} 道高风险题、{medium_count} 道关注题；正式交付应先处理高风险项。",
            "figures": [
                {
                    "id": "question_risk_distribution",
                    "title": "题目风险分层决定复核顺序",
                    "takeaway": "先处理高风险题，再处理元数据 warning 题。",
                    "data": {
                        "high": high_count,
                        "medium": medium_count,
                        "low": len([row for row in rows if row["risk_level"] == "low"]),
                    },
                    "source": "question_portfolio.risk_level",
                    "notes": "由质量评分、元数据置信度和 warning 共同决定。",
                },
                {
                    "id": "metadata_quality",
                    "title": "元数据门禁是报告可信度根基",
                    "takeaway": metadata_status(metadata),
                    "data": metadata,
                    "source": "report_data.metadata_quality",
                    "notes": "报告生成前必须通过 metadata envelope 和 LLM purpose 覆盖校验。",
                },
            ],
            "implications": ["所有高层判断必须能追溯到题目、字段和 LLM 调用目的。"],
        },
    ]
    fine_summary = _as_dict(fine_exhibits.get("summary"))
    if fine_summary.get("total_seus") or fine_summary.get("total_dus"):
        chapters.append({
            "id": "fine_grained_evidence",
            "title": "细粒度证据矩阵",
            "thesis": (
                f"本报告的核心优势不是平均值，而是把 {fine_summary.get('total_seus', 0)} 个 SEU "
                f"和 {fine_summary.get('total_dus', 0)} 个 DU 转化为题目级证据网络。"
            ),
            "figures": [
                {
                    "id": "fine_grained_heatmap",
                    "title": "题目 × 难度因子热力图",
                    "takeaway": "逐题比较难度、质量、置信度、SEU/DU 数量和陷阱强度，定位粗粒度均值掩盖的异常题。",
                    "data": fine_exhibits.get("difficulty_factor_rows", []),
                    "source": "fine_grained_exhibits.difficulty_factor_rows",
                    "notes": "由题目元数据、SEU 和 DU 派生，不新增 LLM 调用。",
                },
                {
                    "id": "seu_competency_matrix",
                    "title": "SEU × 知识点 × 素养矩阵",
                    "takeaway": "按采分权重追踪知识点和核心素养，展示每个分值点到底考什么。",
                    "data": fine_exhibits.get("seu_rows", []),
                    "source": "fine_grained_exhibits.seu_rows",
                    "notes": "SEU 是采分证据单元；加权分 = 题目分值 × 分值占比。",
                },
                {
                    "id": "du_trap_map",
                    "title": "DU 误区与陷阱强度图",
                    "takeaway": "把干扰项、误区和陷阱强度拉出来，服务于讲评和命题修订。",
                    "data": fine_exhibits.get("du_rows", []),
                    "source": "fine_grained_exhibits.du_rows",
                    "notes": "DU 是诊断干扰单元，不参与分值守恒，但决定教学解释价值。",
                },
            ],
            "implications": [
                "报告应从题目组合进入 SEU/DU 证据网络，而不是停留在题目级平均值。",
                "低置信度 SEU 或高陷阱强度 DU 应成为人工复核优先级。",
            ],
        })
    return chapters


def _build_question_portfolio(rows: List[Dict]) -> Dict:
    high = [row for row in rows if row["risk_level"] == "high"]
    thesis = (
        f"高风险题集中在 {'、'.join('Q' + str(row['question_id']) for row in high[:8])}，应作为第一批复核对象。"
        if high else
        "当前未发现高风险题，建议进入人工抽样复核。"
    )
    return {
        "thesis": thesis,
        "rows": rows,
    }


def _build_deep_dives(questions: List[Dict], rows: List[Dict]) -> List[Dict]:
    by_id = {row["question_id"]: row for row in rows}
    ranked_questions = sorted(
        _sorted_questions(questions),
        key=lambda q: {"high": 0, "medium": 1, "low": 2}.get(by_id.get(q.get("id"), {}).get("risk_level", "low"), 2),
    )
    dives = []
    for question in ranked_questions[:8]:
        qid = question.get("id")
        row = by_id.get(qid, {})
        dives.append({
            "question_id": qid,
            "headline": f"Q{qid} {row.get('quality_level', '未评估')}：{row.get('primary_issue', '需复核')}",
            "diagnosis": row.get("primary_issue", primary_issue(question)),
            "seu_breakdown": _question_scoring_units(question),
            "du_diagnostics": _question_diagnostic_units(question),
            "su_context": _question_stimulus_units(question),
            "revision_plan": [row.get("action", action_for_question(question))],
            "metadata_trace": {
                "purposes": _as_list(question.get("metadata_call_purposes")),
                "confidence": question.get("metadata_confidence", 0),
                "warnings": _as_list(question.get("metadata_warnings")),
            },
        })
    return dives


def _build_methodology(metadata: Dict, questions: List[Dict]) -> Dict:
    llm_counts = _as_dict(metadata.get("llm_call_counts"))
    traced_counts: Dict[str, int] = {}
    for question in questions:
        for purpose in _as_list(question.get("metadata_call_purposes")):
            traced_counts[purpose] = traced_counts.get(purpose, 0) + 1

    purpose_counts: Dict[str, int] = {}
    for purpose, count in traced_counts.items():
        purpose_counts[purpose] = int(count)
    for purpose, count in llm_counts.items():
        if isinstance(count, (int, float)):
            purpose_counts[purpose] = int(count)

    prompt_inventory = []
    for purpose, count in sorted(purpose_counts.items()):
        contract = _as_dict(PROMPT_CONTRACTS.get(purpose))
        prompt_inventory.append({
            "purpose": purpose,
            "prompt_id": contract.get("prompt_id", f"biology.{purpose}"),
            "prompt": contract.get("prompt", f"Prompt contract for {purpose} is not registered."),
            "analysis_dimensions": _as_list(contract.get("analysis_dimensions")),
            "parsed_fields": _as_list(contract.get("parsed_fields")),
            "records": count,
            "question_traces": traced_counts.get(purpose, 0),
        })

    return {
        "llm_call_summary": {
            "total": sum(purpose_counts.values()),
            "purpose_counts": purpose_counts,
            "question_traced_counts": traced_counts,
        },
        "prompt_inventory": prompt_inventory,
        "parsed_fields": list(PARSED_FIELDS),
        "quality_gates": list(QUALITY_GATES),
        "limitations": list(LIMITATIONS),
    }


def build_report_product_model(report_data: Dict, insights: Dict | None = None) -> Dict:
    """Build the commercial report model from report aggregate data."""
    report_data = _as_dict(report_data)
    exam = _as_dict(report_data.get("exam_info"))
    questions = _sorted_questions(_as_list(report_data.get("questions")))
    metadata = _as_dict(report_data.get("metadata_quality"))
    rows = _build_question_rows(questions)
    fine_exhibits = _build_fine_grained_exhibits(questions, rows)
    knowledge_exhibit_rows = _build_knowledge_exhibit_rows(
        _as_dict(report_data.get("knowledge")),
        _as_list(fine_exhibits.get("knowledge_contribution_rows")) or _as_list(fine_exhibits.get("seu_rows")),
    )
    findings = _build_findings(report_data, rows, fine_exhibits, knowledge_exhibit_rows)

    return {
        "cover": _build_cover(exam),
        "credibility": _build_credibility(exam, questions, metadata),
        "executive_summary": _build_executive_summary(report_data, rows, findings),
        "at_a_glance": _build_at_a_glance(exam, report_data, metadata, questions, fine_exhibits),
        "chapters": _build_chapters(report_data, rows, fine_exhibits, knowledge_exhibit_rows),
        "fine_grained_exhibits": fine_exhibits,
        "findings": findings,
        "question_portfolio": _build_question_portfolio(rows),
        "deep_dives": _build_deep_dives(questions, rows),
        "methodology": _build_methodology(metadata, questions),
    }
