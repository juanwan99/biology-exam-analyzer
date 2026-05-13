"""整卷质量诊断 — 从统计描述升级为命题质量评价。"""
from typing import Dict, List, Optional, Any
from logger import get_logger

logger = get_logger()


def diagnose_exam(questions: List[Dict], statistics: Dict,
                  exam_scope: Optional[Dict] = None) -> Dict:
    """诊断试卷命题质量。

    Args:
        questions: 分析完成的题目列表
        statistics: generate_exam_statistics 的输出
        exam_scope: 可选，{"grade": "高三", "volumes": ["必修1", "必修2"]}

    Returns:
        {gradient, coverage, competency_balance, discrimination, overall_rating}
    """
    if not questions:
        return {"gradient": {}, "coverage": {}, "competency_balance": {},
                "discrimination": {}, "overall_rating": "数据不足"}

    result = {}
    result["gradient"] = _analyze_gradient(questions, statistics)
    result["coverage"] = _analyze_coverage(questions, exam_scope)
    result["competency_balance"] = _analyze_competency_balance(questions)
    result["discrimination"] = _analyze_discrimination(questions, statistics)
    result["overall_rating"] = _compute_overall(result)
    return result


def _analyze_gradient(questions: List[Dict], statistics: Dict) -> Dict:
    """难度梯度合理性分析。理想分布：30%简单 + 50%中等 + 20%困难。"""
    if len(questions) < 2:
        return {"rating": "题目不足", "detail": "至少需要2题才能分析梯度"}

    dist = statistics.get("difficulty_distribution", {})
    total = sum(dist.values()) or 1
    easy_pct = dist.get("简单", 0) / total
    medium_pct = dist.get("中等", 0) / total
    hard_pct = dist.get("困难", 0) / total

    # 与理想分布的偏差
    deviation = abs(easy_pct - 0.3) + abs(medium_pct - 0.5) + abs(hard_pct - 0.2)

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
        "ideal": {"简单": 0.3, "中等": 0.5, "困难": 0.2},
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
        kps = q.get("analysis", {}).get("knowledge_points", [])
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


def _analyze_discrimination(questions: List[Dict], statistics: Dict) -> Dict:
    """区分度估算。"""
    difficulties = []
    for q in questions:
        d = q.get("difficulty", {})
        if isinstance(d, dict) and "final_difficulty" in d:
            difficulties.append(d["final_difficulty"])

    if len(difficulties) < 3:
        return {"discrimination": "数据不足", "detail": "至少需要3题"}

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
        "discrimination": level,
        "difficulty_stdev": round(stdev_d, 2),
        "difficulty_spread": round(spread, 2),
        "difficulty_mean": round(mean_d, 2),
    }


def _compute_overall(result: Dict) -> str:
    """综合评价。"""
    scores = []

    gradient = result.get("gradient", {})
    if gradient.get("rating") == "优秀":
        scores.append(3)
    elif gradient.get("rating") == "良好":
        scores.append(2)
    elif gradient.get("rating") in ("偏难", "偏易"):
        scores.append(0)
    else:
        scores.append(1)

    balance = result.get("competency_balance", {})
    if balance.get("balance") == "均衡":
        scores.append(3)
    elif balance.get("balance") == "基本均衡":
        scores.append(2)
    elif balance.get("missing"):
        scores.append(0)
    else:
        scores.append(1)

    disc = result.get("discrimination", {})
    if disc.get("discrimination") == "高":
        scores.append(3)
    elif disc.get("discrimination") == "中等":
        scores.append(2)
    else:
        scores.append(1)

    avg = sum(scores) / len(scores) if scores else 0
    if avg >= 2.5:
        return "优秀"
    elif avg >= 1.5:
        return "良好"
    elif avg >= 0.5:
        return "一般"
    else:
        return "待改进"
