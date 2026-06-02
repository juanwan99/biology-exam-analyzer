"""整卷质量诊断 — 从统计描述升级为命题质量评价。"""
from typing import Dict, List, Optional, Any
from logger import get_logger

logger = get_logger()

DIFFICULTY_PROFILES = {
    "高考": {"简单": 0.3, "中等": 0.5, "困难": 0.2},
    "月考": {"简单": 0.2, "中等": 0.5, "困难": 0.3},
    "模拟考": {"简单": 0.25, "中等": 0.5, "困难": 0.25},
    "期中期末": {"简单": 0.3, "中等": 0.45, "困难": 0.25},
}


def _safe_dict(value: Any) -> Dict:
    return value if isinstance(value, dict) else {}


def diagnose_exam(questions: List[Dict], statistics: Dict,
                  exam_scope: Optional[Dict] = None,
                  exam_type: str = "高考") -> Dict:
    """诊断试卷命题质量。

    Args:
        questions: 分析完成的题目列表
        statistics: generate_exam_statistics 的输出
        exam_scope: 可选，{"grade": "高三", "volumes": ["必修1", "必修2"]}
        exam_type: 考试类型（高考/月考/模拟考/期中期末），决定理想难度分布

    Returns:
        {gradient, coverage, competency_balance, difficulty_spread,
         allocation_reliability, overall_rating}
    """
    if not questions:
        return {"gradient": {}, "coverage": {}, "competency_balance": {},
                "difficulty_spread": {}, "overall_rating": "数据不足"}

    profile = DIFFICULTY_PROFILES.get(exam_type, DIFFICULTY_PROFILES["高考"])

    result = {}
    result["gradient"] = _analyze_gradient(questions, statistics, profile)
    result["coverage"] = _analyze_coverage(questions, exam_scope)
    result["competency_balance"] = _analyze_competency_balance(questions)
    result["difficulty_spread"] = _analyze_difficulty_spread(questions, statistics)
    result["allocation_reliability"] = _analyze_allocation_reliability(questions)
    result["overall_rating"] = _compute_overall(result)
    return result


def _analyze_gradient(questions: List[Dict], statistics: Dict,
                      profile: Dict) -> Dict:
    """难度梯度合理性分析。理想分布由 exam_type 决定。"""
    if len(questions) < 2:
        return {"rating": "题目不足", "detail": "至少需要2题才能分析梯度"}

    dist = statistics.get("difficulty_distribution", {})
    total = sum(dist.values()) or 1
    easy_pct = dist.get("简单", 0) / total
    medium_pct = dist.get("中等", 0) / total
    hard_pct = dist.get("困难", 0) / total

    ideal_easy = profile["简单"]
    ideal_medium = profile["中等"]
    ideal_hard = profile["困难"]
    deviation = abs(easy_pct - ideal_easy) + abs(medium_pct - ideal_medium) + abs(hard_pct - ideal_hard)

    if deviation < 0.2:
        rating = "优秀"
    elif deviation < 0.4:
        rating = "良好"
    elif hard_pct > 0.5:
        rating = "偏难"
    elif easy_pct > 0.6:
        rating = "偏易"
    else:
        rating = "一般"

    return {
        "rating": rating,
        "actual": {"简单": round(easy_pct, 2), "中等": round(medium_pct, 2), "困难": round(hard_pct, 2)},
        "ideal": {"简单": ideal_easy, "中等": ideal_medium, "困难": ideal_hard},
        "deviation": round(deviation, 2),
    }


def _analyze_coverage(questions: List[Dict], exam_scope: Optional[Dict]) -> Dict:
    """知识点覆盖度分析。"""
    if exam_scope is None:
        return {"coverage": "unknown", "reason": "未指定考试范围",
                "covered_chapters": [], "total_points_count": 0}

    # 收集所有知识点涉及的章节
    covered = set()
    for q in questions:
        mapping = q.get("knowledge_mapping", [])
        if isinstance(mapping, list):
            for m in mapping:
                ch = m.get("chapter") or m.get("textbook")
                if ch:
                    covered.add(ch)

        # SEU 路径优先：从 scoring_units knowledge_links 获取更精确的知识点
        analysis = _safe_dict(q.get("analysis"))
        fg = analysis.get("_fine_grained")
        if fg and fg.get("scoring_units"):
            for seu in fg["scoring_units"]:
                for kl in seu.get("knowledge_links", []):
                    kp = kl.get("knowledge_point", "")
                    if kp:
                        covered.add(kp)
        else:
            # fallback: 旧逻辑从 analysis.knowledge_points 收集
            kps = analysis.get("knowledge_points", [])
            for kp in kps:
                covered.add(kp)

    # 从 exam_scope 获取应覆盖的范围
    volumes = exam_scope.get("volumes", [])
    if not volumes:
        return {"coverage": "unknown", "reason": "考试范围未指定册别",
                "covered_chapters": list(covered), "total_points_count": len(covered)}

    # 简化计算：统计覆盖了多少个指定册别
    covered_volumes = set()
    for ch in covered:
        for v in volumes:
            if v in str(ch):
                covered_volumes.add(v)

    coverage_rate = len(covered_volumes) / len(volumes) if volumes else 0

    return {
        "coverage": round(coverage_rate, 2),
        "covered_volumes": list(covered_volumes),
        "required_volumes": volumes,
        "covered_points_count": len(covered),
        "grade": exam_scope.get("grade", "未知"),
    }


def _analyze_competency_balance(questions: List[Dict]) -> Dict:
    """素养均衡度分析。"""
    competencies = {"生命观念": 0, "科学思维": 0, "科学探究": 0, "社会责任": 0}
    valid_count = 0

    for q in questions:
        # SEU 路径优先：从 scoring_units competency 按 score_share 加权
        analysis = _safe_dict(q.get("analysis"))
        fg = analysis.get("_fine_grained")
        if fg and fg.get("scoring_units"):
            valid_count += 1
            q_score = q.get("total_score") or 1
            for seu in fg["scoring_units"]:
                score_share = seu.get("score_share", 0)
                weights = seu.get("competency_weights")
                if isinstance(weights, dict):
                    for name in competencies:
                        weight = weights.get(name, 0)
                        if isinstance(weight, (int, float)):
                            competencies[name] += q_score * score_share * weight
                    continue

                comp_link = _safe_dict(seu.get("competency"))
                c = comp_link.get("primary", "")
                if c in competencies:
                    comp_weight = comp_link.get("weight", 1.0)
                    competencies[c] += q_score * score_share * comp_weight
        else:
            # fallback: 旧逻辑从题目级 competency 统计
            comp = q.get("competency", {})
            if isinstance(comp, dict) and "error" not in comp:
                valid_count += 1
                for key in competencies:
                    if isinstance(comp.get(key), dict) and comp[key].get("涉及"):
                        weight = comp[key].get("权重", 0)
                        if isinstance(weight, (int, float)):
                            competencies[key] += weight

    if valid_count == 0:
        return {"balance": "数据不足", "distribution": competencies}

    # 归一化
    total = sum(competencies.values()) or 1
    normalized = {k: round(v / total, 2) for k, v in competencies.items()}

    # 均衡度（方差越小越均衡）
    mean = 0.25
    variance = sum((v - mean) ** 2 for v in normalized.values()) / 4

    missing = [k for k, v in normalized.items() if v < 0.05]

    if variance < 0.01 and not missing:
        balance = "均衡"
    elif missing:
        balance = "缺失: " + ", ".join(missing)
    elif variance < 0.03:
        balance = "基本均衡"
    else:
        dominant = max(normalized, key=normalized.get)
        balance = "偏重" + dominant

    return {"balance": balance, "distribution": normalized, "missing": missing, "variance": round(variance, 4)}


def _analyze_difficulty_spread(questions: List[Dict], statistics: Dict) -> Dict:
    """难度离散度分析（注：基于预估难度，非基于学生实际作答的区分度）。"""
    difficulties = []
    unavailable = []
    for q in questions:
        d = q.get("difficulty", {})
        value = None
        if isinstance(d, dict) and "final_difficulty" in d:
            value = d["final_difficulty"]
        elif isinstance(d, (int, float)):
            value = d
        if isinstance(value, (int, float)):
            difficulties.append(float(value))
        else:
            unavailable.append(q.get("id"))

    if len(difficulties) < 3:
        return {"spread_level": "数据不足", "detail": "至少需要3题"}

    import statistics as stats_mod
    mean_d = stats_mod.mean(difficulties)
    stdev_d = stats_mod.stdev(difficulties) if len(difficulties) > 1 else 0
    spread = max(difficulties) - min(difficulties)

    if stdev_d > 2.5 and spread > 5:
        level = "高"
    elif stdev_d > 1.5 and spread > 3:
        level = "中等"
    else:
        level = "低"

    return {
        "spread_level": level,
        "difficulty_stdev": round(stdev_d, 2),
        "difficulty_range": round(spread, 2),
        "difficulty_mean": round(mean_d, 2),
        "unavailable_questions": [qid for qid in unavailable if qid is not None],
        "note": "本指标基于预估难度计算，非基于学生实际作答的区分度",
    }


def _analyze_allocation_reliability(questions: List[Dict]) -> Dict:
    """分析 SEU 分配的可靠性。

    统计 inferred vs explicit 的比例和低置信度 SEU，给出可靠性评级。
    无 SEU 数据时返回 status=no_fine_grained_data。
    """
    total_seus = 0
    inferred_count = 0
    low_confidence_seus = []

    for q in questions:
        analysis = _safe_dict(q.get("analysis"))
        fg = analysis.get("_fine_grained")
        if not fg or not fg.get("scoring_units"):
            continue
        for seu in fg["scoring_units"]:
            total_seus += 1
            if seu.get("allocation_source") == "inferred":
                inferred_count += 1
            conf = seu.get("allocation_confidence", 0.5)
            if conf < 0.5:
                low_confidence_seus.append({
                    "question_id": q.get("id"),
                    "seu_id": seu.get("seu_id"),
                    "confidence": conf,
                })

    if total_seus == 0:
        return {"status": "no_fine_grained_data"}

    inferred_pct = round(inferred_count / total_seus * 100, 1)

    # 可靠性评级
    if inferred_pct <= 30:
        rating = "高"
    elif inferred_pct <= 60:
        rating = "中"
    else:
        rating = "低"

    return {
        "total_seus": total_seus,
        "inferred_count": inferred_count,
        "inferred_pct": inferred_pct,
        "rating": rating,
        "low_confidence_seus": low_confidence_seus[:5],
    }


def _compute_overall(result: Dict) -> str:
    """综合评价（加权：梯度 0.4 + 素养均衡 0.35 + 离散度 0.25）。"""
    weighted_sum = 0.0
    weight_sum = 0.0

    gradient = result.get("gradient", {})
    if gradient.get("rating") not in (None, "题目不足"):
        s = {"优秀": 3, "良好": 2, "一般": 1, "偏难": 0, "偏易": 0}.get(gradient["rating"], 1)
        weighted_sum += s * 0.4
        weight_sum += 0.4

    balance = result.get("competency_balance", {})
    if balance.get("balance") not in (None, "数据不足"):
        if balance["balance"] == "均衡":
            s = 3
        elif balance["balance"] == "基本均衡":
            s = 2
        elif balance.get("missing"):
            s = 0
        else:
            s = 1
        weighted_sum += s * 0.35
        weight_sum += 0.35

    spread = result.get("difficulty_spread", {})
    if spread.get("spread_level") not in (None, "数据不足"):
        s = {"高": 3, "中等": 2, "低": 1}.get(spread["spread_level"], 1)
        weighted_sum += s * 0.25
        weight_sum += 0.25

    if weight_sum == 0:
        return "数据不足"

    avg = weighted_sum / weight_sum
    if avg >= 2.5:
        return "优秀"
    elif avg >= 1.5:
        return "良好"
    elif avg >= 0.5:
        return "一般"
    else:
        return "待改进"
