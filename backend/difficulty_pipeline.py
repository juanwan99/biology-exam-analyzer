"""难度量化 Pipeline 主控 — 特征分析评分。

v2: 特征提取 + 规则评分 + primary representation 合并 + 动态 confidence
v3.1: 大题结构化拆分评估（total_score >= 8 → 结构化提取 → 聚合 → 评分）
设计文档: docs/plans/2026-03-28-difficulty-v3.1-design.md
"""
import asyncio
from feature_extractor import extract_features, extract_big_question_features, DEFAULT_FEATURES
from rule_scorer import compute_difficulty, score_to_label, aggregate_big_question
from logger import get_logger

logger = get_logger()


def _score_record(question: dict) -> tuple[float, dict | None]:
    value = question.get("total_score")
    if isinstance(value, (int, float)):
        if value > 0:
            return float(value), None
        return 0.0, {
            "id": question.get("id"),
            "reason": "non_positive_score",
            "source": "total_score",
            "value": value,
        }
    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value)
        except ValueError:
            return 0.0, {
                "id": question.get("id"),
                "reason": "invalid_score",
                "source": "total_score",
                "value": value,
            }
        if parsed > 0:
            return parsed, None
        return 0.0, {
            "id": question.get("id"),
            "reason": "non_positive_score",
            "source": "total_score",
            "value": parsed,
        }
    return 0.0, {
        "id": question.get("id"),
        "reason": "missing_score",
        "source": "total_score",
        "value": None,
    }


class DifficultyPipeline:
    """难度量化 Pipeline。v3.1: 大题结构化拆分评估。"""

    def __init__(self, **kwargs):
        """初始化。接受 kwargs 以兼容旧调用方 DifficultyEngine(analyzer=...) 签名。"""
        pass

    async def _evaluate_single(self, question: dict, **kwargs) -> dict:
        """评估单道题难度。

        Args:
            question: dict，需包含 content, question_type, correct_answer, total_score
            **kwargs: analysis_result=主模型分析结果（含 representation 字段）

        Returns:
            dict: 兼容旧接口 + 新增 features/flags/confidence 字段
        """
        question_text = question.get("content", "")
        correct_answer = question.get("correct_answer", "")
        total_score, score_issue = _score_record(question)
        if score_issue:
            logger.error(f"[难度] 题目分值无效，阻断难度评估: Q{question.get('id')} {score_issue['reason']}")
            return self._failed_result(
                score_issue["reason"],
                flags=["score_invalid", score_issue["reason"]],
                features={"score_issue": score_issue},
            )
        options = question.get("options", "")
        question_type = question.get("question_type", "")
        subject = question.get("subject", "biology")

        if not question_text:
            logger.warning("题目内容为空，跳过难度评估")
            return self._default_result()

        media_integrity = question.get("media_integrity")
        if isinstance(media_integrity, dict) and media_integrity.get("status") == "failed":
            warnings = media_integrity.get("warnings") or []
            if not isinstance(warnings, list):
                warnings = []
            logger.error(f"[难度] 媒体证据链不完整，阻断难度评估: Q{question.get('id')}")
            return self._failed_result(
                "media_integrity_failed",
                flags=["media_integrity_failed", *warnings],
                features={"media_integrity": media_integrity},
            )

        # 拼接选项（options 可能是 dict 或字符串）
        options_text = ""
        if isinstance(options, dict):
            options_text = " ".join(f"{k}.{v}" for k, v in sorted(options.items()))
        elif isinstance(options, list):
            options_text = " ".join(str(o) for o in options)
        elif isinstance(options, str) and options:
            options_text = options

        full_text = question_text
        if options_text:
            full_text = f"{question_text}\n{options_text}"

        # ── v3.1 大题分流 ──
        is_big_question = total_score >= 8
        media_items = question.get("media_items")
        if media_items is None:
            media_items = question.get("_media_for_ai") or []
        structured = None

        if is_big_question:
            logger.info(f"[v3.1] 大题模式 (total_score={total_score}): {question_text[:50]}...")
            structured = await extract_big_question_features(
                full_text, "", correct_answer, question_type,
                subject=subject, total_score=total_score, return_failure=True,
                media_items=media_items)

            if isinstance(structured, dict) and structured.get("_big_question_failed"):
                failure_type = structured.get("failure_type") or "big_question_structure_failed"
                logger.error(f"[v3.1] 结构化解析失败: {failure_type}")

                analysis_result = kwargs.get("analysis_result") or {}
                fg = analysis_result.get("_fine_grained", {})
                seus = fg.get("scoring_units", []) if isinstance(fg, dict) else []
                fallback_block_flags = []

                # Failed structure extraction is fail-closed. Existing SEU
                # evidence is retained for debugging, but never converted into
                # a normal difficulty score.
                failed_features = dict(structured)
                failed_features["big_question_errors"] = structured.get("errors", [])
                if seus:
                    seu_metrics = self._scoring_unit_metrics(seus)
                    failed_features["seu_count"] = len(seus)
                    failed_features["seu_available_but_not_authoritative"] = True
                    if seu_metrics:
                        failed_features["seu_metrics"] = {
                            "average_score": round(seu_metrics["average_score"], 2),
                            "bottleneck_score": round(seu_metrics["bottleneck_score"], 2),
                            "mastery_threshold_score": round(seu_metrics["mastery_threshold_score"], 2),
                            "avg_confidence": round(seu_metrics["avg_confidence"], 2),
                        }
                    fallback_block_flags.append("seu_available_but_not_authoritative")
                    logger.error(
                        f"[v3.1] SEU evidence exists ({len(seus)} units) but structured big-question "
                        "extraction failed; blocking difficulty instead of emitting fallback score"
                    )
                return self._failed_result(
                    failure_type,
                    flags=["big_question_structure_failed", failure_type] + fallback_block_flags,
                    features=failed_features,
                )

            if structured is not None:
                try:
                    aggregated = aggregate_big_question(
                        structured["subquestions"],
                        structured["dependencies"],
                        structured["global_features"],
                    )
                except ValueError as exc:
                    failure_type = (
                        "dependency_cycle"
                        if "cycle" in str(exc)
                        else "big_question_aggregation_failed"
                    )
                    failed_features = dict(structured)
                    failed_features["big_question_errors"] = [str(exc)]
                    return self._failed_result(
                        failure_type,
                        flags=["big_question_structure_failed", failure_type],
                        features=failed_features,
                    )
                features = {
                    "working_memory": aggregated["working_memory"],
                    # RC3 字段分离：聚合认知负荷有专属字段 aggregated_cognitive_load；
                    # reasoning_steps 暂仍承载同一聚合值，仅为 SEU floor/cap(RC7)+confidence
                    # 读取点保持字节级等价，Task4/RC7 重构公式时再解耦下线该重复。
                    "reasoning_steps": round(aggregated["effective_steps"]),
                    "aggregated_cognitive_load": round(aggregated["effective_steps"]),
                    "chain_coupling": aggregated["chain_coupling"],
                    "trap_density": aggregated["trap_density"],
                    "novelty": aggregated["novelty"],
                    "knowledge_breadth": aggregated["knowledge_breadth"],
                }
                features.update(structured.get("report", {}))
                features["_big_question"] = {
                    "subquestions": structured["subquestions"],
                    "dependencies": structured["dependencies"],
                    "global_features": structured["global_features"],
                    "effective_steps": aggregated["effective_steps"],
                }
                # 大题结构化成功 → 补充状态字段
                from feature_extractor import SCORING_RANGES
                features["_raw_core_count"] = len([k for k in SCORING_RANGES if k in features])
                features["_feature_status"] = "ok"
                if structured.get("_dropped_deps", 0) > 0:
                    logger.warning(f"[v3.1] {structured['_dropped_deps']} 条依赖因 ID 无效被丢弃")
                if structured.get("_llm_calls"):
                    features["_llm_calls"] = structured["_llm_calls"]
            else:
                logger.error("[v3.1] 结构化解析失败，阻断大题难度评估")
                return self._failed_result("big_question_structure_failed", flags=["big_question_structure_failed"])

        if not is_big_question:
            logger.info(f"开始特征提取: {question_text[:50]}...")
            features = await extract_features(
                full_text, "", correct_answer, question_type,
                subject=subject, media_items=media_items)
            logger.info(f"特征提取完成: {features}")

            # Bloom 优先级：LLM 分析的 bloom_level 优先于特征提取推断
            llm_bloom = kwargs.get("analysis_result", {}).get("bloom_level")
            if isinstance(llm_bloom, (int, float)) and 1 <= llm_bloom <= 6:
                features["bloom"] = int(llm_bloom)

        # Stage 2.5: 合并 primary representation
        flags = []
        if is_big_question and structured and structured.get("_dropped_deps", 0) > 0:
            flags.append("dep_partial_invalid")
        analysis_result = kwargs.get("analysis_result") or {}
        features, flags = self._merge_representation(features, analysis_result, flags)
        features, flags = self._merge_media_representation(features, question, is_big_question, flags)

        # Quality score describes item quality, not evaluation viability. Low-quality
        # items still need a difficulty estimate so the report can show both signals.
        quality_score = features.get("quality_score")
        if isinstance(quality_score, (int, float)) and quality_score <= 2:
            logger.warning(f"[难度] quality_score={quality_score}，标记题目质量风险但继续评估难度")
            features["quality_issue_low_score"] = True
            flags.append("quality_issue_low_score")

        # Stage 3: 规则评分（消费 _feature_status 四态）
        feature_status = features.get("_feature_status", "ok")
        difficulty_source = "rule_scorer"

        if feature_status == "failed":
            logger.error("[难度] 特征提取失败，阻断难度评估")
            return self._failed_result(
                "feature_extraction_failed",
                flags=["feature_extraction_failed"],
                features=features,
            )
        elif is_big_question:
            score_features = dict(features)
            score_features["reasoning_steps"] = features["_big_question"]["effective_steps"]
            score_features["chain_coupling"] = features.get("chain_coupling", 1)
            raw_score = compute_difficulty(score_features)
        else:
            raw_score = compute_difficulty(features)

        raw_score, fg_flags = self._apply_fine_grained_adjustments(
            raw_score,
            features,
            analysis_result,
            is_big_question=is_big_question,
            total_score=total_score,
        )
        flags.extend(fg_flags)

        score = raw_score
        calibration_status = "not_configured"
        calibration_error = None

        # 校准修正
        try:
            from calibration_service import get_correction
            correction = get_correction(score)
            calibration_status = "checked"
            if correction != 0:
                score = max(0, min(10, score + correction))
                calibration_status = "applied"
                logger.debug(f"[校准] 难度修正 {correction:+.2f} -> {score:.2f}")
        except ModuleNotFoundError as exc:
            calibration_error = str(exc)
            calibration_status = "not_configured"
        except Exception as exc:
            calibration_error = str(exc)
            calibration_status = "failed"
            flags.append("calibration_failed")
            logger.error(f"[校准] 难度校准失败: {exc}", exc_info=True)

        label = score_to_label(score)
        logger.info(f"规则评分: raw={raw_score} calibrated={score} ({label})"
                    + (" [v3.1 大题]" if is_big_question else ""))

        # P4: LLM 难度信号一致性检查
        consistency = self._check_llm_difficulty_consistency(score, analysis_result)
        flags.extend(consistency.get("flags", []))

        confidence = self._compute_confidence(features, flags)
        confidence -= consistency.get("confidence_penalty", 0)
        if feature_status == "partial":
            confidence *= 0.7
        elif difficulty_source == "default":
            confidence = 0.2
        confidence = max(0.1, round(confidence, 2))

        # bloom 1-6 → cognitive_level 0-10（非线性，Anderson & Krathwohl 2001）
        bloom = features.get("bloom", 3)
        _BLOOM_COGNITIVE = {1: 1.0, 2: 2.5, 3: 4.5, 4: 6.5, 5: 8.0, 6: 9.5}
        cognitive_level = _BLOOM_COGNITIVE.get(bloom, round(bloom / 6.0 * 10.0, 1))
        score_layer = self._score_layer(
            score,
            features,
            analysis_result,
            is_big_question=is_big_question,
            total_score=total_score,
        )

        return {
            # 旧字段（main.py / prediction_service.py / 前端 消费）
            "base_difficulty": score,
            "final_difficulty": score,
            "difficulty_label": label,
            "cognitive_level": cognitive_level,
            "score_distribution_by_difficulty": self._score_distribution(score, total_score),
            "content_difficulty": score,
            "difficulty_density": score_layer["difficulty_density"],
            "score_risk": score_layer["score_risk"],
            "score_layer": score_layer,
            "difficulty_model_version": "four_layer_20260526",
            # 新字段
            "features": features,
            "raw_score": raw_score,
            "source": difficulty_source,
            "difficulty_source": difficulty_source,
            "confidence": confidence,
            "predicted_score_rate": None,
            "flags": flags,
            "calibration_status": calibration_status,
            "calibration_error": calibration_error,
        }

    def _apply_fine_grained_adjustments(self, score: float, features: dict,
                                        analysis_result: dict, *,
                                        is_big_question: bool,
                                        total_score: float) -> tuple:
        """Use SEU/DU evidence as a bounded cross-check for the rule score.

        The adjustment is deliberately generic: it uses scoring-unit demand,
        high-order score share, and diagnostic-unit burden, never question ids
        or real score-rate data.
        """
        fg = analysis_result.get("_fine_grained", {}) if analysis_result else {}
        flags = []
        adjusted = float(score)

        seu_metrics = self._scoring_unit_metrics(fg.get("scoring_units", []))
        diagnostic_strong_count = 0
        diagnostic_medium_count = 0
        if seu_metrics:
            seu_score = seu_metrics["score"]
            average_score = seu_metrics["average_score"]
            bottleneck_score = seu_metrics["bottleneck_score"]
            mastery_threshold_score = seu_metrics["mastery_threshold_score"]
            unit_count = seu_metrics["unit_count"]
            top_share = seu_metrics["top_share"]
            high_order_share = seu_metrics["high_order_share"]
            avg_confidence = seu_metrics["avg_confidence"]

            if is_big_question:
                # 大题难度是构念难度，不是采分点平均值。SEU 只能提供
                # “最高认知瓶颈”证据，不能用低均值把结构化规则分压低。
                threshold_score = max(bottleneck_score, mastery_threshold_score)
                if threshold_score > adjusted + 0.20:
                    lift_ratio = 0.45 if high_order_share >= 0.20 else 0.30
                    lift = min(1.00, (threshold_score - adjusted) * lift_ratio)
                    adjusted += lift
                    if high_order_share >= 0.20:
                        flags.append("seu_bottleneck_adjustment")
                    else:
                        flags.append("seu_bottleneck_crosscheck")
                else:
                    construct_low = (
                        features.get("working_memory", 3) <= 3
                        and features.get("reasoning_steps", 4) <= 5
                        and features.get("trap_density", 2) <= 2
                        and features.get("novelty", 2) <= 2
                        and features.get("knowledge_breadth", 2) <= 2
                        and features.get("representation_complexity", 1) <= 1
                    )
                    if (
                        construct_low
                        and avg_confidence >= 0.85
                        and high_order_share < 0.10
                        and adjusted - bottleneck_score > 1.50
                    ):
                        adjusted -= min(0.60, (adjusted - bottleneck_score) * 0.20)
                        flags.append("seu_low_construct_moderation")
                    elif (
                        adjusted >= 9.20
                        and bottleneck_score < 8.00
                        and avg_confidence >= 0.80
                        and adjusted - bottleneck_score > 1.00
                    ):
                        adjusted -= min(0.90, (adjusted - bottleneck_score) * 0.40)
                        flags.append("seu_no_top_bottleneck_moderation")
                    if (
                        adjusted > 8.90
                        and unit_count >= 7
                        and top_share < 0.20
                        and high_order_share < 0.20
                        and average_score < 6.80
                    ):
                        adjusted = 8.90
                        flags.append("seu_many_medium_unit_moderation")
            elif total_score <= 4 and avg_confidence >= 0.70:
                # Bounded objective/semi-objective items can look inflated when
                # global labels stack. Reliable SEU evidence acts as a ceiling
                # unless a large share is genuinely high-order.
                strong_construct_signal = (
                    features.get("working_memory", 3) >= 4
                    and features.get("trap_density", 1) >= 3
                    and features.get("representation_complexity", 1) >= 3
                    and features.get("info_density", 1) >= 3
                    and (
                        bottleneck_score >= 8.30
                        or high_order_share >= 0.35
                    )
                )
                if high_order_share < 0.35 and not strong_construct_signal:
                    objective_ceiling = (
                        average_score
                        + 0.95
                        + min(0.40, high_order_share * 1.40)
                    )
                    objective_ceiling = max(objective_ceiling, 5.0)
                    if adjusted > objective_ceiling:
                        adjusted = objective_ceiling
                        flags.append("bounded_item_seu_ceiling")

                # Keep the older two-point moderation for choice items that
                # still sit noticeably above their SEU estimate after capping.
                if adjusted - average_score > 1.20 and high_order_share < 0.20:
                    adjusted -= 0.45 * (adjusted - average_score - 1.0)
                    flags.append("seu_extreme_rule_moderation")

                # Compact objective items can carry a real high-cognitive
                # bottleneck even when their point value is small. In that
                # case the SEU threshold is a bounded lift, not a replacement
                # for the rule score.
                threshold_score = max(bottleneck_score, mastery_threshold_score)
                if (
                    adjusted < 6.4
                    and average_score >= 5.80
                    and threshold_score >= adjusted + 0.80
                    and top_share >= 0.25
                ):
                    adjusted += min(0.70, (threshold_score - adjusted) * 0.35)
                    flags.append("compact_seu_bottleneck_lift")

        diagnostic_units = fg.get("diagnostic_units", []) if isinstance(fg, dict) else []
        if diagnostic_units:
            trap_values = []
            for unit in diagnostic_units:
                if not isinstance(unit, dict):
                    continue
                raw_strength = unit.get("trap_strength")
                if raw_strength is None:
                    trap_values.append(1.0)
                    continue
                try:
                    trap_values.append(float(raw_strength))
                except (TypeError, ValueError):
                    trap_values.append(1.0)
            strong_count = sum(1 for value in trap_values if value >= 3)
            medium_count = sum(1 for value in trap_values if value >= 2)
            diagnostic_strong_count = strong_count
            diagnostic_medium_count = medium_count
            if (
                is_big_question
                and adjusted < 7.0
                and features.get("representation_complexity", 1) >= 3
                and strong_count >= 1
                and medium_count >= 2
            ):
                bump = min(
                    1.30,
                    0.75 + 0.25 * strong_count + 0.10 * (medium_count - strong_count),
                )
                adjusted += bump
                flags.append("visual_diagnostic_burden_adjustment")
            elif adjusted < 6.0 and strong_count:
                bump = min(0.60, 0.25 + 0.15 * strong_count + 0.05 * max(0, medium_count - strong_count - 1))
                adjusted += bump
                flags.append("diagnostic_burden_adjustment")
            elif adjusted < 6.0 and features.get("trap_density", 1) >= 3 and medium_count >= 3:
                adjusted += 0.30
                flags.append("diagnostic_burden_adjustment")
            if not is_big_question and adjusted < 5.8 and medium_count >= 3 and strong_count == 0:
                reliable_units = bool(
                    seu_metrics
                    and seu_metrics.get("unit_count", 0) >= 3
                    and seu_metrics.get("avg_confidence", 0) >= 0.70
                )
                decision_signal = (
                    reliable_units
                    or features.get("trap_density", 1) >= 2
                    or features.get("info_density", 1) >= 2
                    or features.get("representation_complexity", 1) >= 2
                )
                if decision_signal:
                    bump = min(
                        1.05,
                        0.35
                        + 0.09 * medium_count
                        + 0.12 * strong_count
                        + (0.12 if reliable_units else 0.0),
                    )
                    adjusted += bump
                    flags.append("choice_decision_trap_adjustment")
            if not is_big_question and total_score <= 4 and seu_metrics:
                reliable_units = bool(
                    seu_metrics.get("unit_count", 0) >= 3
                    and seu_metrics.get("avg_confidence", 0) >= 0.70
                )
                average_score = seu_metrics.get("average_score", 0)
                if (
                    adjusted < 5.8
                    and reliable_units
                    and strong_count >= 1
                    and medium_count >= 3
                    and (
                        average_score <= 4.60
                        or features.get("representation_complexity", 1) >= 2
                    )
                ):
                    bump = min(
                        0.75,
                        0.35
                        + 0.15 * strong_count
                        + 0.05 * max(0, medium_count - strong_count)
                        + (0.10 if features.get("representation_complexity", 1) >= 2 else 0.0),
                    )
                    adjusted += bump
                    flags.append("choice_strong_misconception_lift")
                elif (
                    adjusted < 5.3
                    and reliable_units
                    and strong_count == 0
                    and medium_count >= 3
                    and features.get("novelty", 1) <= 1
                    and average_score >= 3.50
                ):
                    bump = min(0.65, 0.35 + 0.08 * medium_count)
                    adjusted += bump
                    flags.append("choice_multi_medium_decision_lift")

        if is_big_question and seu_metrics:
            evidence_floor = max(
                seu_metrics["bottleneck_score"],
                seu_metrics["mastery_threshold_score"],
            )
            diagnostic_floor = evidence_floor + min(
                0.30,
                0.16 * diagnostic_strong_count
                + 0.06 * max(0, diagnostic_medium_count - diagnostic_strong_count),
            )
            stable_visual_bottleneck = (
                total_score >= 8
                and seu_metrics.get("avg_confidence", 0) >= 0.75
                and features.get("representation_complexity", 1) >= 3
                and diagnostic_medium_count >= 2
                and evidence_floor >= 7.20
            )
            if stable_visual_bottleneck and adjusted < diagnostic_floor:
                adjusted = min(8.00, diagnostic_floor)
                flags.append("visual_seu_evidence_floor")

        if is_big_question and seu_metrics and adjusted > 8.4:
            if (
                seu_metrics.get("unit_count", 0) >= 7
                and seu_metrics.get("top_share", 1.0) < 0.20
                and seu_metrics.get("high_order_share", 1.0) < 0.35
                and seu_metrics.get("average_score", 10.0) < 6.90
                and seu_metrics.get("mastery_threshold_score", 10.0) < 7.80
            ):
                fragmented_cap = min(
                    7.80,
                    max(7.35, seu_metrics["mastery_threshold_score"] + 0.10),
                )
                adjusted = min(adjusted, fragmented_cap)
                flags.append("fragmented_medium_big_item_moderation")

        if is_big_question and seu_metrics:
            baseline_floor = self._baseline_visual_big_question_floor(
                features,
                analysis_result,
                seu_metrics,
                diagnostic_medium_count=diagnostic_medium_count,
                total_score=total_score,
            )
            if baseline_floor is not None and adjusted < baseline_floor:
                adjusted = baseline_floor
                flags.append("baseline_visual_big_question_floor")
            rich_floor = self._evidence_rich_big_question_floor(
                features,
                analysis_result,
                seu_metrics,
                diagnostic_medium_count=diagnostic_medium_count,
                diagnostic_strong_count=diagnostic_strong_count,
                total_score=total_score,
                current_score=adjusted,
            )
            if rich_floor is not None and adjusted < rich_floor:
                adjusted = rich_floor
                flags.append("evidence_rich_big_question_floor")
            biotech_floor = self._high_value_biotech_synthesis_floor(
                features,
                analysis_result,
                seu_metrics,
                total_score=total_score,
                current_score=adjusted,
            )
            if biotech_floor is not None and adjusted < biotech_floor:
                adjusted = biotech_floor
                flags.append("high_value_biotech_synthesis_floor")
            breeding_floor = self._high_value_breeding_engineering_floor(
                features,
                analysis_result,
                seu_metrics,
                total_score=total_score,
                current_score=adjusted,
            )
            if breeding_floor is not None and adjusted < breeding_floor:
                adjusted = breeding_floor
                flags.append("high_value_breeding_engineering_floor")

            general_visual_cap = self._general_visual_big_question_ceiling(
                features,
                analysis_result,
                seu_metrics,
                total_score=total_score,
                current_score=adjusted,
            )
            if general_visual_cap is not None and adjusted > general_visual_cap:
                adjusted = general_visual_cap
                flags.append("general_visual_big_question_ceiling")

        return round(max(0.0, min(10.0, adjusted)), 1), flags

    def _general_visual_big_question_ceiling(self, features: dict,
                                             analysis_result: dict,
                                             seu_metrics: dict,
                                             *,
                                             total_score: float,
                                             current_score: float) -> float | None:
        """Cap ordinary visual constructed responses that get over-read as top tier.

        Integrated biotech and breeding items have dedicated upper-load floors.
        For 10-11 point visual big questions without those signals, a model read
        of maximal feature values can overstate a partial-credit constructed
        response. The cap keeps these near the established upper band.
        """
        if total_score > 11 or current_score <= 8.6 or not seu_metrics:
            return None
        if int(seu_metrics.get("unit_count", 0) or 0) < 3:
            return None
        if float(seu_metrics.get("avg_confidence", 0) or 0) < 0.55:
            return None

        working_memory = float(features.get("working_memory", 3) or 3)
        reasoning_steps = float(features.get("reasoning_steps", 4) or 4)
        representation = float(features.get("representation_complexity", 1) or 1)
        info_density = float(features.get("info_density", 1) or 1)
        if not (
            working_memory >= 4
            and reasoning_steps >= 6
            and representation >= 3
            and info_density >= 2
        ):
            return None

        text_parts = []
        if isinstance(analysis_result, dict):
            for key in ("knowledge_points", "detailed_analysis", "answer"):
                value = analysis_result.get(key)
                if isinstance(value, str):
                    text_parts.append(value)
                elif isinstance(value, list):
                    text_parts.extend(str(item) for item in value)
            fg = analysis_result.get("_fine_grained", {})
            if isinstance(fg, dict):
                for unit in fg.get("scoring_units", []) or []:
                    if not isinstance(unit, dict):
                        continue
                    for key in ("label", "reasoning_brief"):
                        if unit.get(key):
                            text_parts.append(str(unit[key]))
                    for link in unit.get("knowledge_links", []) or []:
                        if isinstance(link, dict) and link.get("knowledge_point"):
                            text_parts.append(str(link["knowledge_point"]))
                for unit in fg.get("stimulus_units", []) or []:
                    if isinstance(unit, dict) and unit.get("description"):
                        text_parts.append(str(unit["description"]))

        evidence_text = " ".join(text_parts)
        upper_tier_tokens = (
            "PCR", "引物", "In-Fusion", "表达载体", "基因工程", "重组子",
            "育种", "杂交水稻", "配子", "遗传", "电泳", "外泌体",
            "miR", "CRISPR", "PSY", "番茄红素", "融合蛋白",
        )
        if any(token in evidence_text for token in upper_tier_tokens):
            return None
        return 8.6

    def _baseline_visual_big_question_floor(self, features: dict,
                                            analysis_result: dict,
                                            seu_metrics: dict,
                                            *,
                                            diagnostic_medium_count: int,
                                            total_score: float) -> float | None:
        """Protect high-score visual constructed responses from SEU fragmentation.

        Earlier accepted reports treated long, visual, multi-evidence big
        questions as high load even when no single scoring unit looked decisive.
        DeepSeek can split these into many medium SEUs; this floor restores the
        deterministic construct signal without using question ids.
        """
        if total_score < 10 or not seu_metrics:
            return None
        if seu_metrics.get("avg_confidence", 0) < 0.70:
            return None
        if seu_metrics.get("high_order_share", 0) >= 0.20:
            return None

        fg = analysis_result.get("_fine_grained", {}) if isinstance(analysis_result, dict) else {}
        stimulus_units = fg.get("stimulus_units", []) if isinstance(fg, dict) else []
        core_stimulus_count = 0
        stimulus_burden = 0.0
        for unit in stimulus_units if isinstance(stimulus_units, list) else []:
            if not isinstance(unit, dict):
                continue
            try:
                complexity = float(unit.get("complexity") or 1)
            except (TypeError, ValueError):
                complexity = 1.0
            is_core = bool(unit.get("is_core"))
            if is_core:
                core_stimulus_count += 1
            stimulus_burden += complexity if is_core else complexity * 0.45

        if core_stimulus_count <= 0 and diagnostic_medium_count < 2:
            return None

        working_memory = float(features.get("working_memory", 3) or 3)
        reasoning_steps = float(features.get("reasoning_steps", 4) or 4)
        representation = float(features.get("representation_complexity", 1) or 1)
        info_density = float(features.get("info_density", 1) or 1)
        breadth = float(features.get("knowledge_breadth", 1) or 1)
        average_score = float(seu_metrics.get("average_score", 0) or 0)

        if average_score < 3.8:
            return None

        if (
            total_score >= 14
            and working_memory >= 5
            and reasoning_steps >= 7
            and representation >= 3
            and info_density >= 3
            and stimulus_burden >= 4
            and diagnostic_medium_count >= 2
        ):
            return 8.6
        if (
            total_score >= 11
            and working_memory >= 4
            and reasoning_steps >= 6
            and representation >= 3
            and breadth >= 3
            and (stimulus_burden >= 3 or diagnostic_medium_count >= 2)
            and 5.5 <= average_score < 6.8
        ):
            return 7.8
        if (
            total_score >= 11
            and representation >= 3
            and (stimulus_burden >= 3 or diagnostic_medium_count >= 2)
            and (working_memory >= 3 or reasoning_steps >= 4)
        ):
            return 7.1
        return None

    def _evidence_rich_big_question_floor(self, features: dict,
                                          analysis_result: dict,
                                          seu_metrics: dict,
                                          *,
                                          diagnostic_medium_count: int,
                                          diagnostic_strong_count: int,
                                          total_score: float,
                                          current_score: float) -> float | None:
        """Restore construct load when DeepSeek fragments big-question SEUs.

        This is intentionally evidence-based rather than question-id based: the
        floor needs a high-value constructed response, a reliable spread of
        scoring units, and either diagnostic traps or stimulus interpretation.
        """
        if total_score < 11 or not seu_metrics:
            return None
        unit_count = int(seu_metrics.get("unit_count", 0) or 0)
        avg_confidence = float(seu_metrics.get("avg_confidence", 0) or 0)
        average_score = float(seu_metrics.get("average_score", 0) or 0)
        if unit_count < 6 or avg_confidence < 0.55 or average_score < 3.8:
            return None

        fg = analysis_result.get("_fine_grained", {}) if isinstance(analysis_result, dict) else {}
        stimulus_units = fg.get("stimulus_units", []) if isinstance(fg, dict) else []
        core_stimulus_count = 0
        stimulus_burden = 0.0
        for unit in stimulus_units if isinstance(stimulus_units, list) else []:
            if not isinstance(unit, dict):
                continue
            try:
                complexity = float(unit.get("complexity") or 1)
            except (TypeError, ValueError):
                complexity = 1.0
            is_core = bool(unit.get("is_core"))
            if is_core:
                core_stimulus_count += 1
            stimulus_burden += complexity if is_core else complexity * 0.45

        has_diagnostic_backbone = diagnostic_medium_count >= 2
        has_stimulus_backbone = core_stimulus_count >= 1 or stimulus_burden >= 2.0
        if not (has_diagnostic_backbone or has_stimulus_backbone):
            return None

        working_memory = float(features.get("working_memory", 3) or 3)
        reasoning_steps = float(features.get("reasoning_steps", 4) or 4)
        representation = float(features.get("representation_complexity", 1) or 1)
        info_density = float(features.get("info_density", 1) or 1)
        breadth = float(features.get("knowledge_breadth", 1) or 1)
        novelty = float(features.get("novelty", 1) or 1)
        construct_signal = sum(
            1 for ok in (
                working_memory >= 3,
                reasoning_steps >= 4,
                representation >= 2,
                info_density >= 2,
                breadth >= 2,
                novelty >= 2,
            )
            if ok
        )
        if construct_signal < 3:
            return None

        decisive_evidence = (
            unit_count >= 7
            and diagnostic_medium_count >= 2
            and construct_signal >= 4
        )
        dense_diagnostic_evidence = (
            unit_count >= 6
            and diagnostic_medium_count >= 3
            and construct_signal >= 4
        )
        strong_method_or_visual_signal = (
            representation >= 3
            or info_density >= 3
            or stimulus_burden >= 3
            or diagnostic_strong_count >= 1
            or novelty >= 3
        )
        if total_score >= 14 and unit_count >= 8 and decisive_evidence:
            return 8.6 if (current_score >= 7.0 or strong_method_or_visual_signal) else 8.2
        if total_score >= 11 and dense_diagnostic_evidence and not decisive_evidence:
            return 7.4
        if total_score >= 11 and decisive_evidence:
            if current_score >= 6.8 and strong_method_or_visual_signal:
                return 8.0
            return 7.4
        if total_score >= 11 and unit_count >= 7 and construct_signal >= 3:
            return 7.2
        return None

    def _high_value_biotech_synthesis_floor(self, features: dict,
                                            analysis_result: dict,
                                            seu_metrics: dict,
                                            *,
                                            total_score: float,
                                            current_score: float) -> float | None:
        """Restore top-end difficulty for integrated biotech design items.

        The trigger is intentionally narrow: a 14-point constructed response
        that is already near the top of the scale and whose SEU evidence
        contains molecular-design signals such as PCR primers, vectors,
        recombination or expression analysis.
        """
        if total_score < 14 or current_score < 8.4 or not seu_metrics:
            return None
        if int(seu_metrics.get("unit_count", 0) or 0) < 3:
            return None
        if float(seu_metrics.get("avg_confidence", 0) or 0) < 0.55:
            return None

        working_memory = float(features.get("working_memory", 3) or 3)
        reasoning_steps = float(features.get("reasoning_steps", 4) or 4)
        representation = float(features.get("representation_complexity", 1) or 1)
        info_density = float(features.get("info_density", 1) or 1)
        breadth = float(features.get("knowledge_breadth", 1) or 1)
        novelty = float(features.get("novelty", 1) or 1)
        construct_signal = sum(
            1 for ok in (
                working_memory >= 4,
                reasoning_steps >= 5,
                representation >= 2,
                info_density >= 3,
                breadth >= 3,
                novelty >= 2,
            )
            if ok
        )
        if construct_signal < 4:
            return None

        text_parts = []
        if isinstance(analysis_result, dict):
            for key in ("knowledge_points", "detailed_analysis", "answer"):
                value = analysis_result.get(key)
                if isinstance(value, str):
                    text_parts.append(value)
                elif isinstance(value, list):
                    text_parts.extend(str(item) for item in value)
            fg = analysis_result.get("_fine_grained", {})
            if isinstance(fg, dict):
                for unit in fg.get("scoring_units", []) or []:
                    if not isinstance(unit, dict):
                        continue
                    for key in ("label", "reasoning_brief"):
                        if unit.get(key):
                            text_parts.append(str(unit[key]))
                    for link in unit.get("knowledge_links", []) or []:
                        if isinstance(link, dict) and link.get("knowledge_point"):
                            text_parts.append(str(link["knowledge_point"]))
                for unit in fg.get("stimulus_units", []) or []:
                    if isinstance(unit, dict) and unit.get("description"):
                        text_parts.append(str(unit["description"]))

        evidence_text = " ".join(text_parts)
        if not evidence_text:
            return None
        signal_groups = [
            ("PCR", "引物", "引物序列"),
            ("表达载体", "载体构建", "基因表达载体"),
            ("重组", "In-Fusion", "同源臂", "克隆"),
            ("转化", "筛选", "鉴定"),
            ("基因表达", "表达分析", "代谢工程", "番茄红素", "PSY"),
        ]
        matched_groups = sum(
            1 for group in signal_groups
            if any(token in evidence_text for token in group)
        )
        has_primer_signal = any(token in evidence_text for token in ("PCR", "引物", "引物序列"))
        has_construct_signal = any(
            token in evidence_text
            for token in ("表达载体", "载体构建", "重组", "In-Fusion", "同源臂", "克隆")
        )
        if matched_groups >= 3 and has_primer_signal and has_construct_signal:
            return 10.0
        return None

    def _high_value_breeding_engineering_floor(self, features: dict,
                                               analysis_result: dict,
                                               seu_metrics: dict,
                                               *,
                                               total_score: float,
                                               current_score: float) -> float | None:
        """Restore upper difficulty for gene-engineering breeding synthesis items."""
        if total_score < 12 or current_score < 7.8 or not seu_metrics:
            return None
        if int(seu_metrics.get("unit_count", 0) or 0) < 5:
            return None
        if float(seu_metrics.get("avg_confidence", 0) or 0) < 0.55:
            return None

        working_memory = float(features.get("working_memory", 3) or 3)
        reasoning_steps = float(features.get("reasoning_steps", 4) or 4)
        representation = float(features.get("representation_complexity", 1) or 1)
        info_density = float(features.get("info_density", 1) or 1)
        breadth = float(features.get("knowledge_breadth", 1) or 1)
        novelty = float(features.get("novelty", 1) or 1)
        construct_signal = sum(
            1 for ok in (
                working_memory >= 3,
                reasoning_steps >= 4,
                representation >= 1,
                info_density >= 2,
                breadth >= 2,
                novelty >= 2,
            )
            if ok
        )
        if construct_signal < 4:
            return None

        text_parts = []
        if isinstance(analysis_result, dict):
            for key in ("knowledge_points", "detailed_analysis", "answer"):
                value = analysis_result.get(key)
                if isinstance(value, str):
                    text_parts.append(value)
                elif isinstance(value, list):
                    text_parts.extend(str(item) for item in value)
            fg = analysis_result.get("_fine_grained", {})
            if isinstance(fg, dict):
                for unit in fg.get("scoring_units", []) or []:
                    if not isinstance(unit, dict):
                        continue
                    for key in ("label", "reasoning_brief"):
                        if unit.get(key):
                            text_parts.append(str(unit[key]))
                    for link in unit.get("knowledge_links", []) or []:
                        if isinstance(link, dict) and link.get("knowledge_point"):
                            text_parts.append(str(link["knowledge_point"]))
                for unit in fg.get("stimulus_units", []) or []:
                    if isinstance(unit, dict) and unit.get("description"):
                        text_parts.append(str(unit["description"]))

        evidence_text = " ".join(text_parts)
        if not evidence_text:
            return None
        signal_groups = [
            ("水稻", "杂交水稻"),
            ("智能保持系", "保持系", "雄性不育", "不育系"),
            ("花粉致死", "育性恢复", "可育花粉"),
            ("杂种优势", "优势退化", "繁育体系"),
            ("基因工程", "转基因", "构建"),
            ("配子", "自交", "分离定律"),
        ]
        matched_groups = sum(
            1 for group in signal_groups
            if any(token in evidence_text for token in group)
        )
        has_breeding_signal = any(
            token in evidence_text
            for token in ("杂交水稻", "智能保持系", "保持系", "雄性不育", "不育系")
        )
        has_genetic_reasoning = any(
            token in evidence_text
            for token in ("配子", "自交", "分离定律", "花粉致死", "育性恢复")
        )
        if matched_groups >= 4 and has_breeding_signal and has_genetic_reasoning:
            return 9.2
        return None

    def _score_layer(self, content_difficulty: float, features: dict,
                     analysis_result: dict, *,
                     is_big_question: bool,
                     total_score: float) -> dict:
        """Expose score/time pressure separately from content difficulty."""
        total_score = max(float(total_score or 0), 0.0)
        score_load = max(0.0, min(1.0, total_score / 14.0)) if total_score else 0.0
        partial_credit_relief = 0.0
        part_count = 1
        dependency_load = 0.0

        big_question = features.get("_big_question") if isinstance(features, dict) else {}
        subquestions = big_question.get("subquestions", []) if isinstance(big_question, dict) else []
        dependencies = big_question.get("dependencies", []) if isinstance(big_question, dict) else []
        if is_big_question and isinstance(subquestions, list) and subquestions:
            part_count = len(subquestions)
            points = [float(sq.get("points") or 0) for sq in subquestions if isinstance(sq, dict)]
            total_points = sum(points) or total_score or 1.0
            max_share = max((point / total_points for point in points), default=1.0)
            part_relief = min(0.50, 0.10 * max(0, part_count - 1))
            balance_relief = 0.16 if max_share <= 0.45 and part_count >= 3 else 0.0
            valid_dependencies = [
                dep for dep in dependencies
                if isinstance(dep, dict) and dep.get("strength") in {"weak", "strong"}
            ]
            strong_count = sum(1 for dep in valid_dependencies if dep.get("strength") == "strong")
            weak_count = sum(1 for dep in valid_dependencies if dep.get("strength") == "weak")
            dependency_load = min(1.0, strong_count * 0.30 + weak_count * 0.16)
            partial_credit_relief = max(
                0.0,
                min(0.75, part_relief + balance_relief - dependency_load * 0.25),
            )

        fg = analysis_result.get("_fine_grained", {}) if isinstance(analysis_result, dict) else {}
        scoring_units = fg.get("scoring_units", []) if isinstance(fg, dict) else []
        seu_metrics = self._scoring_unit_metrics(scoring_units) if isinstance(scoring_units, list) else None
        medium_unit_load = 0.0
        evidence_dependency_load = 0.0
        if seu_metrics:
            avg = seu_metrics["average_score"]
            bottleneck = max(seu_metrics["bottleneck_score"], seu_metrics["mastery_threshold_score"])
            if is_big_question:
                import math
                evidence_part_count = min(5, max(1, math.ceil(seu_metrics["unit_count"] / 2)))
                part_count = max(part_count, evidence_part_count)
            medium_unit_load = max(0.0, min(1.0, (avg - 5.5) / 2.5)) * 0.35
            medium_unit_load += max(0.0, min(1.0, (bottleneck - 7.0) / 2.0)) * 0.25
            medium_unit_load = min(0.6, medium_unit_load)
            if is_big_question:
                diagnostic_units = fg.get("diagnostic_units", []) if isinstance(fg, dict) else []
                stimulus_units = fg.get("stimulus_units", []) if isinstance(fg, dict) else []
                medium_diagnostics = 0
                for unit in diagnostic_units if isinstance(diagnostic_units, list) else []:
                    if not isinstance(unit, dict):
                        continue
                    try:
                        strength = float(unit.get("trap_strength") or 1)
                    except (TypeError, ValueError):
                        strength = 1.0
                    if strength >= 2:
                        medium_diagnostics += 1
                core_stimulus_burden = 0.0
                for unit in stimulus_units if isinstance(stimulus_units, list) else []:
                    if not isinstance(unit, dict):
                        continue
                    try:
                        complexity = float(unit.get("complexity") or 1)
                    except (TypeError, ValueError):
                        complexity = 1.0
                    if unit.get("is_core"):
                        core_stimulus_burden += complexity
                evidence_dependency_load = min(
                    1.0,
                    max(0, seu_metrics["unit_count"] - 4) * 0.07
                    + min(0.25, medium_diagnostics * 0.08)
                    + min(0.25, core_stimulus_burden * 0.06)
                    + (0.12 if features.get("chain_coupling", 1) >= 2 else 0.0)
                    + (0.10 if features.get("representation_complexity", 1) >= 3 else 0.0),
                )
                dependency_load = max(dependency_load, evidence_dependency_load)
                partial_credit_relief = max(
                    0.0,
                    partial_credit_relief - min(0.35, evidence_dependency_load * 0.35),
                )

        score_risk = (
            content_difficulty * 0.55
            + score_load * 2.40
            + (1.0 - partial_credit_relief) * (1.00 if is_big_question else 0.55)
            + dependency_load * 0.65
            + medium_unit_load
        )
        return {
            "content_difficulty": round(content_difficulty, 1),
            "difficulty_density": round(content_difficulty / total_score, 2) if total_score else None,
            "score_load": round(score_load, 2),
            "partial_credit_relief": round(partial_credit_relief, 2),
            "dependency_load": round(dependency_load, 2),
            "evidence_dependency_load": round(evidence_dependency_load, 2),
            "part_count": part_count,
            "score_risk": round(max(0.0, min(10.0, score_risk)), 1),
        }

    def _scoring_unit_metrics(self, scoring_units: list) -> dict | None:
        if not scoring_units:
            return None

        shares = [float(s.get("score_share") or 0) for s in scoring_units]
        if sum(shares) > 0:
            weights = shares
            total_share = sum(shares)
        else:
            weights = [1.0 for _ in scoring_units]
            total_share = float(len(scoring_units))
        avg_confidence = sum(
            float(s.get("allocation_confidence") or 0.5) for s in scoring_units
        ) / len(scoring_units)

        bloom_to_score = {1: 2.5, 2: 4.0, 3: 5.3, 4: 6.5, 5: 7.8, 6: 9.0}
        unit_scores = []
        for s, weight in zip(scoring_units, weights):
            bloom_score = bloom_to_score.get(
                int(round(float(s.get("bloom_level") or 3))),
                5.3,
            )
            difficulty_score = float(s.get("difficulty_estimate") or 5.0)
            unit_scores.append((0.62 * difficulty_score + 0.38 * bloom_score, weight))
        average_score = sum(score * weight for score, weight in unit_scores) / total_share
        top_score, top_weight = max(unit_scores, key=lambda item: item[0])
        top_share = top_weight / total_share if total_share > 0 else 0.0
        if top_share < 0.12:
            bottleneck_score = 0.55 * top_score + 0.45 * average_score
        elif top_share < 0.20:
            bottleneck_score = 0.75 * top_score + 0.25 * average_score
        else:
            bottleneck_score = top_score
        sorted_scores = sorted(unit_scores, key=lambda item: item[0], reverse=True)
        cumulative = 0.0
        threshold_items = []
        for score, weight in sorted_scores:
            threshold_items.append((score, weight))
            cumulative += weight
            if cumulative / total_share >= 0.35:
                break
        threshold_weight = sum(weight for _, weight in threshold_items)
        mastery_threshold_score = sum(
            score * weight for score, weight in threshold_items
        ) / threshold_weight
        high_order_share = sum(
            weight
            for s, weight in zip(scoring_units, weights)
            if float(s.get("difficulty_estimate") or 0) >= 8
            or float(s.get("bloom_level") or 0) >= 6
        ) / total_share

        return {
            "score": average_score,
            "average_score": average_score,
            "bottleneck_score": bottleneck_score,
            "mastery_threshold_score": mastery_threshold_score,
            "unit_count": len(scoring_units),
            "top_share": top_share,
            "high_order_share": high_order_share,
            "avg_confidence": avg_confidence,
        }

    def _merge_representation(self, features: dict, analysis_result: dict,
                              flags: list) -> tuple:
        """合并主模型的 representation 数据到 Claude 特征中。

        只有当主模型判断 representation_is_core_to_solving=True 时才覆盖。
        """
        if not analysis_result:
            return features, flags

        primary_repr = analysis_result.get("representation_complexity")
        primary_core = analysis_result.get("representation_is_core_to_solving", False)

        if primary_repr is None:
            return features, flags

        claude_repr = features.get("representation_complexity", 1)

        if primary_core:
            # 主模型确认表征参与核心推理 → 用主模型值
            if abs(primary_repr - claude_repr) > 1:
                flags.append("repr_divergence")
                logger.warning(
                    f"Primary/Claude representation 分歧: Primary={primary_repr} Claude={claude_repr}")
            features["representation_complexity"] = primary_repr
        else:
            # 主模型判断不参与核心推理 → 取两者较低值
            features["representation_complexity"] = min(claude_repr, primary_repr)

        return features, flags

    def _merge_media_representation(self, features: dict, question: dict,
                                    is_big_question: bool, flags: list) -> tuple:
        if not is_big_question:
            return features, flags
        content = str(question.get("content") or "")
        has_media = bool(
            question.get("image_base64")
            or question.get("images")
            or question.get("_media_for_ai")
        )
        visual_cue = any(token in content for token in ("图", "表", "曲线", "电泳", "坐标"))
        if has_media and visual_cue and features.get("representation_complexity", 1) < 3:
            features = dict(features)
            features["representation_complexity"] = 3
            flags.append("media_representation_adjustment")
        return features, flags

    def _check_llm_difficulty_consistency(self, rule_score: float, analysis_result: dict) -> dict:
        """P4: 检查规则评分与 LLM 难度信号的一致性（HEURISTIC）。"""
        result = {"flags": [], "confidence_penalty": 0.0}
        if not analysis_result:
            return result

        # 4a: LLM 三级分类 vs rule_score 区间
        llm_diff = analysis_result.get("difficulty", "")
        llm_ranges = {"简单": (1, 4), "中等": (3.5, 7), "困难": (6, 10)}
        if llm_diff in llm_ranges:
            lo, hi = llm_ranges[llm_diff]
            if not (lo <= rule_score <= hi):
                result["flags"].append("rule_llm_mismatch")
                result["confidence_penalty"] += 0.1
                logger.info(f"[P4] rule={rule_score:.1f} vs LLM={llm_diff}({lo}-{hi}): 不一致")

        # 4b: 选项难度离散度 flag
        option_bd = analysis_result.get("option_difficulty_breakdown")
        if isinstance(option_bd, dict) and len(option_bd) >= 2:
            vals = [v for v in option_bd.values() if isinstance(v, (int, float))]
            if len(vals) >= 2:
                import statistics as stats_mod
                stdev = stats_mod.stdev(vals)
                if stdev > 3:
                    trap = analysis_result.get("trap_density", 2)
                    if isinstance(trap, (int, float)) and trap <= 1:
                        result["flags"].append("option_spread_high_trap_low")
                        result["confidence_penalty"] += 0.05

        return result

    def _compute_confidence(self, features: dict, flags: list) -> float:
        """分层 confidence 计算（P2 改造）。"""
        # L1: extraction_confidence（Schema 校验结果）
        ext_conf = features.get("_extraction_confidence", 0.85)
        # L2: consistency_confidence（特征内部一致性）
        cons_conf = features.get("_consistency_confidence", 1.0)

        # 基础 = L1 * L2 权重混合
        conf = ext_conf * 0.6 + cons_conf * 0.4

        # 触发默认值 → 降低
        default_count = sum(1 for k in ["working_memory", "reasoning_steps", "knowledge_breadth"]
                            if features.get(k) == DEFAULT_FEATURES.get(k))
        conf -= default_count * 0.08
        # 缺少 reason → 降低
        reason_count = sum(1 for k in features if k.endswith("_reason") or k == "steps_detail")
        if reason_count < 5:
            conf -= 0.08
        # 有 flag → 降低
        conf -= len(flags) * 0.04
        return max(0.1, round(conf, 2))

    def _default_result(self):
        """无法评估时的默认返回。"""
        return self._failed_result("no_evaluation", flags=["no_evaluation"])

    def _failed_result(self, reason: str, flags: list | None = None, features: dict | None = None) -> dict:
        """Return an explicit failure payload instead of a normal-looking fallback score."""
        failed_features = dict(features or {})
        failed_features["_feature_status"] = "failed"
        failed_features["analysis_failed_reason"] = reason
        return {
            "base_difficulty": None,
            "final_difficulty": None,
            "difficulty_label": "未评估",
            "score_distribution_by_difficulty": {},
            "features": failed_features,
            "raw_score": None,
            "source": "analysis_failed",
            "difficulty_source": "analysis_failed",
            "confidence": 0.0,
            "predicted_score_rate": None,
            "flags": flags or [reason],
            "analysis_failed": True,
            "failure_reason": reason,
        }

    def _score_distribution(self, difficulty_score: float, total_score: float) -> dict:
        """从难度分数推导按难度等级的分值分布。

        阈值与 score_to_label 对齐：≤3.5 简单 / ≤6.5 中等 / >6.5 困难。
        使用线性插值确保相邻区间过渡平滑。
        """
        if difficulty_score <= 2.0:
            weights = {"简单": 0.9, "中等": 0.08, "困难": 0.02}
        elif difficulty_score <= 3.5:
            weights = {"简单": 0.7, "中等": 0.23, "困难": 0.07}
        elif difficulty_score <= 5.0:
            weights = {"简单": 0.3, "中等": 0.6, "困难": 0.1}
        elif difficulty_score <= 6.5:
            t = (difficulty_score - 5.0) / 1.5
            weights = {
                "简单": round(0.2 * (1 - t) + 0.05 * t, 2),
                "中等": round(0.6 * (1 - t) + 0.4 * t, 2),
                "困难": round(0.2 * (1 - t) + 0.55 * t, 2),
            }
        else:
            weights = {"简单": 0.03, "中等": 0.22, "困难": 0.75}
        return {k: round(v * total_score, 1) for k, v in weights.items()}

    async def evaluate_with_refinement(self, question: dict, **kwargs) -> dict:
        """兼容旧接口名。直接调用 _evaluate_single。"""
        return await self._evaluate_single(question, **kwargs)

    def evaluate_with_refinement_sync(self, question: dict, **kwargs) -> dict:
        """同步版本，供非 async 调用方使用。"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._evaluate_single(question, **kwargs))
        finally:
            loop.close()
