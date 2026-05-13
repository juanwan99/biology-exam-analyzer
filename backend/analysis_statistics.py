"""整卷统计分析 — 从 analysis_router 独立出来。"""
from typing import List, Dict, Any
from deps import get_knowledge_mapper
from logger import get_logger

logger = get_logger()

BLOOM_LABELS = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}


def generate_exam_statistics(questions: List[Dict], competency_summary: Dict) -> Dict:
    """
    生成整卷统计分析（v4.0 分值加权）

    统计内容：
    1. 难度分布（简单/中等/困难的题目数量 + 分值分布）
    2. 难度曲线（按题号的难度趋势）
    3. 认知层级分布（分值加权）
    4. 知识点分值加权统计
    5. 知识点教材分布（分值加权）
    6. Bloom 认知层级分布（分值加权）
    """
    knowledge_mapper = get_knowledge_mapper()

    BLOOM_LABELS = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}

    try:
        # 难度分布统计（题目数量）
        difficulty_distribution = {"简单": 0, "中等": 0, "困难": 0}
        # 基于分值的难度分布
        difficulty_distribution_by_score = {
            "简单": {"total_score": 0.0, "count": 0},
            "中等": {"total_score": 0.0, "count": 0},
            "困难": {"total_score": 0.0, "count": 0}
        }
        difficulty_curve = []          # 难度曲线数据（含 total_score）
        cognitive_levels = []          # 认知层级数据 [{level, total_score}]
        knowledge_points_weighted = {} # 知识点分值加权
        kp_with_weights = []           # (kp, weight) 对，用于教材映射
        bloom_score_accum = {label: 0.0 for label in BLOOM_LABELS.values()}

        for q in questions:
            total_score_val = q.get("total_score", q.get("analysis", {}).get("total_score", 0)) or 1  # fallback 等权

            # 1. 难度分布
            if "difficulty" in q and "final_difficulty" in q["difficulty"]:
                diff_score = q["difficulty"]["final_difficulty"]
                difficulty_curve.append({
                    "question_id": q.get("id"),
                    "difficulty": diff_score,
                    "total_score": total_score_val,
                })

                # 分类统计（题目数量）
                if diff_score <= 3.5:
                    difficulty_distribution["简单"] += 1
                elif diff_score <= 6.5:
                    difficulty_distribution["中等"] += 1
                else:
                    difficulty_distribution["困难"] += 1

                # 聚合分值分布
                if "score_distribution_by_difficulty" in q["difficulty"]:
                    score_dist = q["difficulty"]["score_distribution_by_difficulty"]
                    difficulty_distribution_by_score["简单"]["total_score"] += score_dist.get("简单", 0.0)
                    difficulty_distribution_by_score["中等"]["total_score"] += score_dist.get("中等", 0.0)
                    difficulty_distribution_by_score["困难"]["total_score"] += score_dist.get("困难", 0.0)

                # 2. 认知层级（带分值）
                if "cognitive_level" in q["difficulty"]:
                    cognitive_levels.append({
                        "level": q["difficulty"]["cognitive_level"],
                        "total_score": total_score_val,
                    })

                # 3. Bloom 分值累计（优先使用 bloom_distribution 细粒度分布）
                features = q.get("difficulty", {}).get("features", {})
                bloom_dist = features.get("bloom_distribution")
                if bloom_dist and total_score_val > 0:
                    dist_total = sum(bloom_dist.values())
                    if dist_total > 0:
                        dist_detail = []
                        for label, count in bloom_dist.items():
                            if label in bloom_score_accum and count > 0:
                                bloom_score_accum[label] += total_score_val * (count / dist_total)
                                dist_detail.append(f"{label}:{count}")
                        logger.info(f"[Bloom诊断] 题目{q.get('id')}: 分布={{{','.join(dist_detail)}}}, 分值={total_score_val}")
                    else:
                        # bloom_distribution 全零，fallback 到单值
                        bloom_val = features.get("bloom")
                        if bloom_val is not None:
                            bloom_label = BLOOM_LABELS.get(int(round(bloom_val)))
                            if bloom_label:
                                bloom_score_accum[bloom_label] += total_score_val
                                logger.info(f"[Bloom诊断] 题目{q.get('id')}: bloom={bloom_val} ({bloom_label}), 分值={total_score_val}")
                else:
                    # 无 bloom_distribution，使用单值 bloom
                    bloom_val = features.get("bloom")
                    if bloom_val is not None and total_score_val > 0:
                        bloom_label = BLOOM_LABELS.get(int(round(bloom_val)))
                        if bloom_label:
                            bloom_score_accum[bloom_label] += total_score_val
                            logger.info(f"[Bloom诊断] 题目{q.get('id')}: bloom={bloom_val} ({bloom_label}), 分值={total_score_val}")
                    else:
                        logger.warning(f"[Bloom诊断] 题目{q.get('id')}: bloom缺失或分值为0")

            # 4. 知识点分值加权
            if "analysis" in q and "knowledge_points" in q["analysis"]:
                kp_list = q["analysis"]["knowledge_points"]
                kp_weight = total_score_val / len(kp_list) if kp_list else 0
                for kp in kp_list:
                    knowledge_points_weighted[kp] = knowledge_points_weighted.get(kp, 0) + kp_weight
                    kp_with_weights.append((kp, kp_weight))

        # 分值加权平均难度
        total_weight = sum(item["total_score"] for item in difficulty_curve)
        if total_weight > 0:
            avg_difficulty = sum(item["difficulty"] * item["total_score"] for item in difficulty_curve) / total_weight
        else:
            avg_difficulty = 0

        # 分值加权平均认知层级
        cog_weight = sum(item["total_score"] for item in cognitive_levels)
        if cog_weight > 0:
            avg_cognitive = sum(item["level"] * item["total_score"] for item in cognitive_levels) / cog_weight
        else:
            avg_cognitive = 0

        # 计算分值分布的百分比
        total_score = sum(item["total_score"] for item in difficulty_distribution_by_score.values())
        for key in difficulty_distribution_by_score:
            difficulty_distribution_by_score[key]["percentage"] = (
                round((difficulty_distribution_by_score[key]["total_score"] / total_score * 100), 1)
                if total_score > 0 else 0
            )

        # Bloom 分布归一化
        bloom_total = sum(bloom_score_accum.values())
        bloom_distribution = {
            k: round(v / bloom_total, 3) if bloom_total > 0 else 0
            for k, v in bloom_score_accum.items()
        }

        # 知识点教材映射（分值加权）
        all_knowledge_points = [kp for kp, _ in kp_with_weights]
        kp_weight_list = [w for _, w in kp_with_weights]
        logger.info(f"[知识点映射] 开始映射 {len(all_knowledge_points)} 个知识点到教材")
        mapped_points = knowledge_mapper.map_knowledge_points(all_knowledge_points)

        textbook_distribution = {
            tb: {"weighted_score": 0.0, "chapters": {}}
            for tb in ["必修1", "必修2", "选择性必修1", "选择性必修2", "选择性必修3"]
        }

        for i, mapped in enumerate(mapped_points):
            if mapped["mapped"]:
                textbook = mapped["textbook"]
                chapter = mapped["chapter"]
                weight = kp_weight_list[i]
                textbook_distribution[textbook]["weighted_score"] += weight

                if chapter not in textbook_distribution[textbook]["chapters"]:
                    textbook_distribution[textbook]["chapters"][chapter] = {
                        "name": mapped["chapter_name"],
                        "weighted_score": 0.0,
                    }
                textbook_distribution[textbook]["chapters"][chapter]["weighted_score"] += weight

        # 计算教材占比
        total_mapped_weight = sum(item["weighted_score"] for item in textbook_distribution.values())
        for textbook in textbook_distribution:
            textbook_distribution[textbook]["percentage"] = (
                round((textbook_distribution[textbook]["weighted_score"] / total_mapped_weight * 100), 1)
                if total_mapped_weight > 0 else 0
            )

        logger.info(f"[知识点映射] 完成映射，加权总分 {total_mapped_weight:.1f}")

        # 知识点排序（前10，按分值加权）
        top_knowledge_points = sorted(
            knowledge_points_weighted.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # 置信度统计
        confidences = [q.get("analysis_confidence", 0) for q in questions if "analysis_confidence" in q]
        low_confidence_count = sum(1 for c in confidences if c < 0.6)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        return {
            "difficulty_distribution": difficulty_distribution,
            "difficulty_distribution_by_score": difficulty_distribution_by_score,
            "difficulty_curve": difficulty_curve,
            "avg_difficulty": round(avg_difficulty, 2),
            "avg_cognitive_level": round(avg_cognitive, 2),
            "top_knowledge_points": [
                {"name": kp, "weighted_score": round(score, 1)} for kp, score in top_knowledge_points
            ],
            "knowledge_textbook_distribution": textbook_distribution,
            "competency_distribution": competency_summary,
            "bloom_distribution": bloom_distribution,
            "confidence_stats": {
                "average": round(avg_confidence, 2),
                "low_confidence_count": low_confidence_count,
                "total_analyzed": len(confidences),
            },
        }

    except Exception as e:
        logger.error(f"[整卷统计] 失败: {str(e)}", exc_info=True)
        return {"error": str(e)}



def _build_competency_list(questions):
    """构建带 _total_score 的素养列表，供分值加权聚合"""
    result = []
    for q in questions:
        if "error" not in q.get("competency", {}):
            comp = dict(q.get("competency", {}))
            comp["_total_score"] = q.get("total_score", q.get("analysis", {}).get("total_score", 0)) or 1  # fallback 等权
            result.append(comp)
    return result

