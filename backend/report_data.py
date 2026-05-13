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


def _compute_feature_profile(questions: List[Dict]) -> Dict:
    """聚合全卷 6 维特征均值 + 贡献最大的 3 维。"""
    sums = {dim: 0.0 for dim in _FEATURE_DIMS}
    count = 0
    for q in questions:
        features = q.get("difficulty", {}).get("features", {})
        if not features:
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
    diff = q.get("difficulty", {})
    features = diff.get("features", {})
    analysis = q.get("analysis", {})
    comp = q.get("competency", {})

    return {
        "id": q.get("id"),
        "total_score": q.get("total_score", analysis.get("total_score", 0)) or 1,
        "question_type": q.get("question_type", "unknown"),
        # 难度
        "difficulty": diff.get("final_difficulty", 5.0),
        "difficulty_label": diff.get("difficulty_label", "中等"),
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
        # Gemini 分析
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
        # 素养
        "primary_competency": comp.get("primary_competency", ""),
        "competency_level": comp.get("competency_level", ""),
        "competency_details": {
            k: {"涉及": v.get("涉及", False), "权重": v.get("权重", 0), "分析说明": v.get("分析说明", "")}
            for k, v in comp.items()
            if isinstance(v, dict) and "涉及" in v
        },
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
        return q.get("total_score", q.get("analysis", {}).get("total_score", 0)) or 1

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
        },
        "competency": {
            "distribution": competency_summary,
            "primary_distribution": competency_summary.get("primary_distribution", {}),
        },
        "feature_profile": _compute_feature_profile(questions),
        "questions": [_extract_question_detail(q) for q in questions],
    }

    # Batch 3: 整卷质量诊断
    from exam_diagnostics import diagnose_exam
    try:
        diagnostics = diagnose_exam(questions, exam_statistics, exam_scope=None)
    except Exception as e:
        logger.warning(f"诊断失败: {e}")
        diagnostics = {}
    data["diagnostics"] = diagnostics

    logger.info(f"[报告数据] 聚合完成，总分={total_score}")
    return data
