"""整卷统计分析 — 从 analysis_router 独立出来。

v4.1: SEU 精确加权聚合（知识点 + Bloom）。
当 question["analysis"]["_fine_grained"]["scoring_units"] 存在时，
从 SEU score_share × knowledge_links.share 精确加权；
否则 fallback 到旧的等分逻辑。
"""
from typing import List, Dict, Any
from analysis_calibration import canonicalize_knowledge_point, is_non_textbook_skill_point
from deps import get_knowledge_mapper
from logger import get_logger

logger = get_logger()
_DEFAULT_GET_KNOWLEDGE_MAPPER = get_knowledge_mapper

BLOOM_LABELS = {1: "识记", 2: "理解", 3: "应用", 4: "分析", 5: "评价", 6: "创造"}


def _get_knowledge_mapper_for_statistics():
    """Resolve mapper injection without leaking analysis_router global state."""
    import sys

    if get_knowledge_mapper is not _DEFAULT_GET_KNOWLEDGE_MAPPER:
        return get_knowledge_mapper()

    router = sys.modules.get("analysis_router")
    router_getter = getattr(router, "get_knowledge_mapper", None) if router is not None else None
    if router_getter is not None and router_getter is not _DEFAULT_GET_KNOWLEDGE_MAPPER:
        return router_getter()
    return get_knowledge_mapper()


def _analysis_dict(q: Dict) -> Dict:
    analysis = q.get("analysis")
    return analysis if isinstance(analysis, dict) else {}


def _score_record(q: Dict) -> tuple[float, Dict[str, Any] | None]:
    analysis = _analysis_dict(q)
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


def _usable_difficulty(q: Dict) -> float | None:
    difficulty = q.get("difficulty")
    if not isinstance(difficulty, dict):
        return None
    score = difficulty.get("final_difficulty")
    if not isinstance(score, (int, float)):
        return None
    features = difficulty.get("features")
    feature_status = features.get("_feature_status") if isinstance(features, dict) else None
    source = difficulty.get("source") or difficulty.get("difficulty_source")
    fine_grained = _analysis_dict(q).get("_fine_grained")
    if feature_status == "failed" and source != "structured_big_question":
        if not (fine_grained and fine_grained.get("scoring_units")):
            return None
    return float(score)


_KP_ABILITY_BLACKLIST_EXACT = {
    "数据处理",
    "数据分析",
    "实验设计",
    "信息获取",
    "信息处理",
    "逻辑推理",
    "模型建构",
    "批判性思维",
    "科学探究能力",
}
_KP_NON_TEXTBOOK_PATTERNS = (
    "实验设计",
    "变量控制",
    "实验数据分析",
    "实验分析",
    "探究实验",
    "科学探究",
    "分析与结论",
    "严谨性",
)


def _is_non_textbook_skill_point(kp: str) -> bool:
    if not isinstance(kp, str):
        return False
    normalized = kp.strip()
    return (
        is_non_textbook_skill_point(normalized)
        or
        normalized in _KP_ABILITY_BLACKLIST_EXACT
        or any(pattern in normalized for pattern in _KP_NON_TEXTBOOK_PATTERNS)
    )


def _add_weighted_point(
    bucket: Dict[str, Dict[str, Any]],
    name: str,
    weight: float,
    occurrences: int = 1,
) -> None:
    item = bucket.setdefault(name, {"weighted_score": 0.0, "occurrences": 0})
    item["weighted_score"] += weight
    item["occurrences"] += occurrences


def _safe_positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _normalised_knowledge_links(
    links: List[Dict[str, Any]],
    knowledge_mapper=None,
) -> List[tuple[str, float]]:
    valid = []
    for link in links or []:
        kp = link.get("knowledge_point", "")
        if not isinstance(kp, str) or not kp.strip():
            continue
        kp = kp.strip()
        if not _is_non_textbook_skill_point(kp):
            kp, _ = canonicalize_knowledge_point(kp, knowledge_mapper=knowledge_mapper)
        if not kp:
            continue
        raw_share = link.get("share", 1.0)
        valid.append((kp, _safe_positive_float(raw_share, 1.0)))
    if not valid:
        return []
    share_total = sum(share for _, share in valid)
    if share_total <= 0:
        equal_share = 1.0 / len(valid)
        return [(kp, equal_share) for kp, _ in valid]
    return [(kp, share / share_total) for kp, share in valid]


def _diminished_non_textbook_weight(raw_weight: float, question_score: float,
                                    occurrences: int) -> float:
    """Repeated method/ability tags describe one capability burden, not new content."""
    if occurrences <= 1 or question_score <= 0:
        return raw_weight
    per_occurrence = raw_weight / occurrences
    diminished = per_occurrence * (1.0 + 0.50 * (occurrences - 1))
    cap = question_score * 0.45
    return min(raw_weight, diminished, cap)


def _weighted_point_list(bucket: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        [
            {
                "name": name,
                "weighted_score": round(data["weighted_score"], 1),
                "occurrences": data["occurrences"],
            }
            for name, data in bucket.items()
        ],
        key=lambda item: (-item["weighted_score"], item["name"]),
    )


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
    knowledge_mapper = _get_knowledge_mapper_for_statistics()

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
        cognitive_levels = []
        kp_with_weights = []
        score_issue_questions = []
        valid_score_questions = 0
        missing_bloom_questions = []
        non_textbook_points_weighted = {}

        for q in questions:
            total_score_val, score_issue = _score_record(q)
            if score_issue:
                score_issue_questions.append(score_issue)
            else:
                valid_score_questions += 1
            analysis = _analysis_dict(q)
            difficulty = q.get("difficulty") if isinstance(q.get("difficulty"), dict) else {}

            # 1. 难度分布
            diff_score = _usable_difficulty(q)
            if diff_score is not None:
                difficulty_curve.append({
                    "question_id": q.get("id"),
                    "difficulty": diff_score,
                    "total_score": total_score_val,
                })

                # 分类统计（题目数量）
                if diff_score <= 3.5:
                    difficulty_distribution["简单"] += 1
                    primary_diff_level = "简单"
                elif diff_score <= 6.5:
                    difficulty_distribution["中等"] += 1
                    primary_diff_level = "中等"
                else:
                    difficulty_distribution["困难"] += 1
                    primary_diff_level = "困难"

                # 聚合分值分布 + count
                difficulty_distribution_by_score[primary_diff_level]["count"] += 1
                if "score_distribution_by_difficulty" in difficulty:
                    score_dist = difficulty["score_distribution_by_difficulty"]
                    difficulty_distribution_by_score["简单"]["total_score"] += score_dist.get("简单", 0.0)
                    difficulty_distribution_by_score["中等"]["total_score"] += score_dist.get("中等", 0.0)
                    difficulty_distribution_by_score["困难"]["total_score"] += score_dist.get("困难", 0.0)

                # 2. 认知层级（带分值）
                if "cognitive_level" in difficulty:
                    cognitive_levels.append({
                        "level": difficulty["cognitive_level"],
                        "total_score": total_score_val,
                    })

                # 3. Bloom 分值累计
                # 优先级：SEU bloom_level > bloom_distribution > 单值 bloom
                fine_grained = analysis.get("_fine_grained")
                if fine_grained and fine_grained.get("scoring_units") and total_score_val > 0:
                    # === SEU 精确路径 ===
                    seu_detail = []
                    for seu in fine_grained["scoring_units"]:
                        bl = seu.get("bloom_level", 3)
                        bloom_label = BLOOM_LABELS.get(bl)
                        if bloom_label:
                            bloom_score_accum[bloom_label] += total_score_val * seu.get("score_share", 0)
                            seu_detail.append(f"{bloom_label}:{seu.get('score_share', 0):.2f}")
                    logger.info(f"[Bloom诊断] 题目{q.get('id')}: SEU路径 [{','.join(seu_detail)}], 分值={total_score_val}")
                else:
                    # === fallback: bloom_distribution 或单值 bloom ===
                    features = difficulty.get("features") if isinstance(difficulty.get("features"), dict) else {}
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
                            bloom_val = features.get("bloom")
                            if bloom_val is not None:
                                bloom_label = BLOOM_LABELS.get(int(round(bloom_val)))
                                if bloom_label:
                                    bloom_score_accum[bloom_label] += total_score_val
                                    logger.info(f"[Bloom诊断] 题目{q.get('id')}: bloom={bloom_val} ({bloom_label}), 分值={total_score_val}")
                    else:
                        bloom_val = features.get("bloom")
                        if bloom_val is not None and total_score_val > 0:
                            bloom_label = BLOOM_LABELS.get(int(round(bloom_val)))
                            if bloom_label:
                                bloom_score_accum[bloom_label] += total_score_val
                                logger.info(f"[Bloom诊断] 题目{q.get('id')}: bloom={bloom_val} ({bloom_label}), 分值={total_score_val}")
                        else:
                            logger.warning(f"[Bloom诊断] 题目{q.get('id')}: bloom缺失或分值为0")

            # 4. 知识点分值加权
            # 优先级：SEU knowledge_links > 旧等分逻辑
            fg = analysis.get("_fine_grained")
            if fg and fg.get("scoring_units"):
                # === SEU 精确路径 ===
                question_non_textbook_points = {}
                for seu in fg["scoring_units"]:
                    seu_score = total_score_val * seu.get("score_share", 0)
                    for kp, link_share in _normalised_knowledge_links(
                        seu.get("knowledge_links", []),
                        knowledge_mapper,
                    ):
                        w = seu_score * link_share
                        if _is_non_textbook_skill_point(kp):
                            _add_weighted_point(question_non_textbook_points, kp, w)
                            continue
                        knowledge_points_weighted[kp] = knowledge_points_weighted.get(kp, 0) + w
                        kp_with_weights.append((kp, w))
                for kp, data in question_non_textbook_points.items():
                    adjusted_weight = _diminished_non_textbook_weight(
                        data["weighted_score"],
                        total_score_val,
                        data["occurrences"],
                    )
                    _add_weighted_point(
                        non_textbook_points_weighted,
                        kp,
                        adjusted_weight,
                        data["occurrences"],
                    )
            elif "knowledge_points" in analysis:
                # === fallback: 旧逻辑等分（同样过滤能力词） ===
                kp_list = analysis["knowledge_points"]
                kp_list_canonical = []
                for kp in kp_list:
                    if not isinstance(kp, str) or not kp.strip():
                        continue
                    raw_kp = kp.strip()
                    if _is_non_textbook_skill_point(raw_kp):
                        kp_list_canonical.append(raw_kp)
                        continue
                    kp_list_canonical.append(
                        canonicalize_knowledge_point(raw_kp, knowledge_mapper=knowledge_mapper)[0]
                    )
                kp_list_canonical = [kp for kp in kp_list_canonical if kp]
                kp_list_filtered = [
                    kp for kp in kp_list_canonical
                    if not _is_non_textbook_skill_point(kp)
                ]
                excluded_weight = total_score_val / len(kp_list_canonical) if kp_list_canonical else 0
                for kp in kp_list_canonical:
                    if _is_non_textbook_skill_point(kp):
                        _add_weighted_point(non_textbook_points_weighted, kp, excluded_weight)
                kp_weight = excluded_weight
                for kp in kp_list_filtered:
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

        mapped_count = 0
        unmapped_weighted = {}
        for i, mapped in enumerate(mapped_points):
            weight = kp_weight_list[i] if i < len(kp_weight_list) else 0
            original = (
                mapped.get("original")
                or (all_knowledge_points[i] if i < len(all_knowledge_points) else "")
                or "未标注知识点"
            )
            if mapped["mapped"]:
                textbook = mapped["textbook"]
                chapter = mapped["chapter"]
                mapped_count += 1
                textbook_distribution[textbook]["weighted_score"] += weight

                if chapter not in textbook_distribution[textbook]["chapters"]:
                    textbook_distribution[textbook]["chapters"][chapter] = {
                        "name": mapped["chapter_name"],
                        "weighted_score": 0.0,
                    }
                textbook_distribution[textbook]["chapters"][chapter]["weighted_score"] += weight
            else:
                detail = unmapped_weighted.setdefault(
                    original,
                    {"name": original, "weighted_score": 0.0, "occurrences": 0},
                )
                detail["weighted_score"] += weight
                detail["occurrences"] += 1

        # 计算教材占比
        total_mapped_weight = sum(item["weighted_score"] for item in textbook_distribution.values())
        for textbook in textbook_distribution:
            textbook_distribution[textbook]["percentage"] = (
                round((textbook_distribution[textbook]["weighted_score"] / total_mapped_weight * 100), 1)
                if total_mapped_weight > 0 else 0
            )

        unmapped_count = sum(1 for m in mapped_points if not m["mapped"])
        unmapped_points = _weighted_point_list(unmapped_weighted)
        non_textbook_points = _weighted_point_list(non_textbook_points_weighted)
        logger.info(f"[知识点映射] 完成映射，加权总分 {total_mapped_weight:.1f}，未映射 {unmapped_count}/{len(all_knowledge_points)}")

        # 知识点排序（前10，按分值加权）
        top_knowledge_points = sorted(
            knowledge_points_weighted.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # 细粒度分配统计
        allocation_stats = _compute_allocation_stats(questions)

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
            "knowledge_unmapped_count": unmapped_count,
            "knowledge_mapped_count": mapped_count,
            "knowledge_unmapped_points": unmapped_points[:20],
            "knowledge_total_count": len(all_knowledge_points),
            "knowledge_non_textbook_count": sum(item["occurrences"] for item in non_textbook_points),
            "knowledge_non_textbook_points": non_textbook_points[:20],
            "competency_distribution": competency_summary,
            "bloom_distribution": bloom_distribution,
            "allocation_stats": allocation_stats,
            "score_quality": {
                "valid_score_questions": valid_score_questions,
                "invalid_score_questions": len(score_issue_questions),
                "score_issue_questions": score_issue_questions,
            },
            "bloom_quality": {
                "missing_bloom_questions": missing_bloom_questions,
            },
        }

    except Exception as e:
        logger.error(f"[整卷统计] 失败: {str(e)}", exc_info=True)
        raise RuntimeError(f"exam statistics generation failed: {e}") from e



def _compute_allocation_stats(questions: List[Dict]) -> Dict:
    """计算 SEU 分配置信度统计。

    返回 dict 包含:
    - total_seus: SEU 总数
    - total_dus: DU 总数
    - avg_allocation_confidence: 平均分配置信度
    - inferred_score_pct: 推断（非 explicit）分配的分值占比 (%)
    """
    total_seus = 0
    total_dus = 0
    confidence_sum = 0.0
    inferred_score = 0.0
    total_score = 0.0

    for q in questions:
        fg = _analysis_dict(q).get("_fine_grained")
        if not fg or not fg.get("scoring_units"):
            continue
        q_score, _ = _score_record(q)
        for seu in fg["scoring_units"]:
            total_seus += 1
            confidence_sum += seu.get("allocation_confidence", 0.5)
            share = seu.get("score_share", 0)
            if seu.get("allocation_source") == "inferred":
                inferred_score += q_score * share
            total_score += q_score * share
        total_dus += len(fg.get("diagnostic_units", []))

    return {
        "total_seus": total_seus,
        "total_dus": total_dus,
        "avg_allocation_confidence": round(confidence_sum / total_seus, 2) if total_seus > 0 else 0,
        "inferred_score_pct": round(inferred_score / total_score * 100, 1) if total_score > 0 else 0,
    }


def _build_competency_list(questions):
    """构建带 _total_score 和 _fine_grained 的素养列表，供分值加权聚合"""
    result = []
    for q in questions:
        if "error" not in q.get("competency", {}):
            comp = dict(q.get("competency", {}))
            comp["_total_score"], score_issue = _score_record(q)
            comp["_score_status"] = score_issue["reason"] if score_issue else "valid"
            fg = _analysis_dict(q).get("_fine_grained")
            if fg:
                comp["_fine_grained"] = fg
            result.append(comp)
    return result
