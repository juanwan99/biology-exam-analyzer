"""report_data 数据聚合层测试"""
import pytest


def _make_question(qid, difficulty, bloom, total_score, knowledge_points=None,
                   competency=None, analysis=None):
    """构造完整题目 dict"""
    features = {"bloom": bloom, "reasoning_steps": 4, "knowledge_breadth": 2,
                "info_density": 2, "novelty": 2, "representation_complexity": 1}
    return {
        "id": qid,
        "total_score": total_score,
        "question_type": "single_choice",
        "difficulty": {
            "final_difficulty": difficulty,
            "difficulty_label": "中等",
            "cognitive_level": round(bloom / 6.0 * 10.0, 1),
            "confidence": 0.85,
            "features": features,
            "score_distribution_by_difficulty": {},
        },
        "analysis": {
            "knowledge_points": knowledge_points or ["光合作用"],
            "detailed_analysis": "解题步骤...",
            "common_mistakes": ["常见错误1"],
            "total_score": total_score,
        },
        "competency": competency or {
            "生命观念": {"涉及": True, "权重": 0.3, "具体维度": ["结构与功能观"], "分析说明": "..."},
            "科学思维": {"涉及": False, "权重": 0, "具体维度": [], "分析说明": ""},
            "科学探究": {"涉及": False, "权重": 0, "具体维度": [], "分析说明": ""},
            "社会责任": {"涉及": False, "权重": 0, "具体维度": [], "分析说明": ""},
            "primary_competency": "生命观念",
            "competency_level": "中",
        },
    }


from report_data import aggregate_report_data


def _minimal_statistics(avg_difficulty=5.0):
    return {
        "avg_difficulty": avg_difficulty,
        "avg_cognitive_level": 5.0,
        "difficulty_distribution": {},
        "difficulty_distribution_by_score": {},
        "bloom_distribution": {},
        "difficulty_curve": [],
        "top_knowledge_points": [],
        "knowledge_textbook_distribution": {},
        "competency_distribution": {},
    }


class TestAggregateReportData:
    def test_failed_exam_statistics_is_not_silently_rendered_as_zero_metrics(self):
        q = _make_question(1, 5.0, 3, 2)

        with pytest.raises(ValueError, match="exam statistics failed"):
            aggregate_report_data(
                [q],
                {},
                {"error": "difficulty aggregation crashed"},
                {"name": "t", "total": 1, "mode": "deep"},
            )

    def test_score_status_reports_non_positive_without_defaulting_to_one(self):
        q = _make_question(1, 5.0, 3, 0)
        statistics = {
            "avg_difficulty": 0,
            "avg_cognitive_level": 0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})

        assert result["exam_info"]["total_score"] == 0
        assert result["questions"][0]["total_score"] == 0
        assert result["questions"][0]["score_status"] == "non_positive_score"
        assert {
            "id": 1,
            "reason": "non_positive_score",
            "source": "total_score",
            "value": 0,
        } in result["metadata_quality"]["score_issue_questions"]


    def test_total_score_from_analysis_fallback(self):
        """total_score 在 analysis 子字典中时也能正确取到"""
        # 模拟实际数据结构：total_score 在 analysis 中，不在顶层
        q = {
            "id": 1,
            "question_type": "single_choice",
            "analysis": {
                "total_score": 6,
                "knowledge_points": ["光合作用"],
                "detailed_analysis": "...",
                "common_mistakes": [],
            },
            "difficulty": {
                "final_difficulty": 5.0, "difficulty_label": "中等",
                "cognitive_level": 5.0, "confidence": 0.85,
                "features": {"bloom": 3, "reasoning_steps": 4, "knowledge_breadth": 2,
                             "info_density": 2, "novelty": 2, "representation_complexity": 1},
                "score_distribution_by_difficulty": {},
            },
            "competency": {"primary_competency": "生命观念", "competency_level": "中"},
        }
        statistics = {
            "avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
            "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
            "bloom_distribution": {}, "difficulty_curve": [],
            "top_knowledge_points": [], "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }
        result = aggregate_report_data([q], {}, statistics,
                                       {"name": "t", "total": 1, "mode": "fast"})
        assert result["exam_info"]["total_score"] == 6  # 不是 0
        assert result["questions"][0]["total_score"] == 6  # 不是 0

    def test_fine_grained_summary_tolerates_none_analysis(self):
        """analysis=None 不应阻断报告数据聚合。"""
        q = _make_question(1, 5.0, 3, 2)
        q["analysis"] = None
        statistics = {
            "avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
            "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
            "bloom_distribution": {}, "difficulty_curve": [],
            "top_knowledge_points": [], "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics,
                                       {"name": "t", "total": 1, "mode": "fast"})

        assert result["questions"][0]["knowledge_points"] == []
        assert result["fine_grained_summary"]["total_seus"] == 0

    def test_preserves_full_fine_grained_units_for_report_model(self):
        """完整 SEU/DU/SU 元数据必须穿透 report_data，不能只保留题目级摘要。"""
        q = _make_question(1, 6.0, 4, 10)
        q["analysis"]["_fine_grained"] = {
            "scoring_units": [
                {
                    "seu_id": "seu_1",
                    "label": "multi knowledge unit",
                    "score_share": 0.6,
                    "allocation_source": "rubric",
                    "allocation_confidence": 0.9,
                    "knowledge_links": [
                        {"knowledge_point": "K1", "share": 0.7},
                        {"knowledge_point": "K2", "share": 0.3},
                    ],
                    "competency_weights": {
                        "生命观念": 0.2,
                        "科学思维": 0.6,
                        "科学探究": 0.2,
                        "社会责任": 0.0,
                    },
                    "bloom_level": 4,
                    "difficulty_estimate": 6.5,
                    "reasoning_brief": "evidence note",
                },
                {
                    "seu_id": "seu_2",
                    "label": "second unit",
                    "score_share": 0.4,
                    "allocation_confidence": 0.8,
                    "knowledge_links": [{"knowledge_point": "K3", "share": 1.0}],
                    "competency_weights": {"科学探究": 1.0},
                    "bloom_level": 5,
                    "difficulty_estimate": 7.0,
                },
            ],
            "diagnostic_units": [
                {
                    "du_id": "du_1",
                    "option_or_trap": "trap_a",
                    "misconception": "misread graph",
                    "trap_strength": 3,
                    "knowledge_boundary": "K1/K2",
                }
            ],
            "stimulus_units": [
                {"su_id": "su_1", "stimulus_type": "chart", "complexity": 3}
            ],
        }
        statistics = {
            "avg_difficulty": 6.0,
            "avg_cognitive_level": 5.0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})
        detail = result["questions"][0]

        assert detail["scoring_units_count"] == 2
        assert detail["diagnostic_units_count"] == 1
        assert detail["stimulus_units_count"] == 1
        assert detail["fine_grained_units"]["scoring_units"][0]["competency_weights"]["科学思维"] == 0.6
        assert detail["fine_grained_units"]["scoring_units"][0]["difficulty_estimate"] == 6.5
        assert detail["fine_grained_units"]["diagnostic_units"][0]["misconception"] == "misread graph"
        assert detail["seu_knowledge_breakdown"][0]["knowledge_links"][1]["knowledge_point"] == "K2"
        assert detail["seu_knowledge_breakdown"][0]["allocation_confidence"] == 0.9

    def test_does_not_infer_metadata_envelope_from_structured_analysis_outputs(self):
        """真实分析结果没有 envelope 时，也应从结构化产物恢复元数据口径。"""
        q = _make_question(1, 6.0, 4, 10)
        q["analysis_confidence"] = 0.94
        q["confidence"] = 0.91
        q["analysis"]["_extraction_confidence"] = 0.92
        q["analysis"]["allocation_confidence_avg"] = 0.86
        q["warnings"] = ["structured_warning"]
        statistics = {
            "avg_difficulty": 6.0,
            "avg_cognitive_level": 5.0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})

        detail = result["questions"][0]
        assert detail["metadata_confidence"] == 0
        assert detail["metadata_call_purposes"] == []
        assert detail["metadata_warnings"] == []

        quality = result["metadata_quality"]
        assert quality["missing_envelope_questions"] == [1]
        assert quality["inferred_envelope_questions"] == []
        assert quality["llm_call_counts"] == {}

    def test_accepts_direct_fine_grained_analysis_shape_from_e2e_response(self):
        q = _make_question(21, 8.8, 5, 14)
        q["analysis"]["scoring_units"] = [
            {
                "seu_id": "seu_21_1",
                "label": "genotype inference",
                "score_share": 0.45,
                "allocation_confidence": 0.91,
                "difficulty_estimate": 8.2,
                "knowledge_links": [{"knowledge_point": "genetics", "share": 1.0}],
                "competency_weights": {"scientific_thinking": 0.7, "scientific_inquiry": 0.3},
            }
        ]
        q["analysis"]["diagnostic_units"] = [
            {"du_id": "du_21_1", "option_or_trap": "hidden condition", "trap_strength": 4}
        ]
        q["analysis"]["stimulus_units"] = [
            {
                "su_id": "su_21_1",
                "stimulus_type": "multi-paragraph",
                "description": "dense genetic cross material",
                "is_core": True,
                "complexity": 4,
            }
        ]
        statistics = {
            "avg_difficulty": 8.8,
            "avg_cognitive_level": 7.0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})
        detail = result["questions"][0]

        assert detail["scoring_units_count"] == 1
        assert detail["diagnostic_units_count"] == 1
        assert detail["stimulus_units_count"] == 1
        assert detail["fine_grained_units"]["scoring_units"][0]["difficulty_estimate"] == 8.2
        assert result["fine_grained_summary"]["total_seus"] == 1
        assert result["metadata_quality"]["evidence_gap_questions"] == []

    def test_missing_difficulty_is_not_rendered_as_default_middle_score(self):
        q = _make_question(21, 6.0, 4, 14)
        q["difficulty"] = {"error": "provider failed"}
        statistics = {
            "avg_difficulty": 0,
            "avg_cognitive_level": 0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})
        detail = result["questions"][0]

        assert detail["difficulty"] is None
        assert detail["difficulty_label"] == "未评估"
        assert detail["feature_status"] == "missing"

    def test_final_difficulty_is_marked_authoritative_for_report_model(self):
        q = _make_question(20, 9.4, 5, 12)
        q["analysis"]["_fine_grained"] = {
            "scoring_units": [
                {"label": "routine setup", "score_share": 0.5, "difficulty_estimate": 4.0},
                {"label": "routine explanation", "score_share": 0.5, "difficulty_estimate": 5.0},
            ],
            "diagnostic_units": [],
            "stimulus_units": [],
        }
        statistics = {
            "avg_difficulty": 9.4,
            "avg_cognitive_level": 8.0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})
        detail = result["questions"][0]

        assert detail["difficulty"] == 9.4
        assert detail["_difficulty_authoritative"] is True

    def test_preserves_source_text_answer_and_difficulty_flags_for_report_audit(self):
        q = _make_question(21, 9.1, 5, 14)
        q["question_text"] = "第21题原题文本"
        q["correct_answer"] = "参考答案示例"
        q["difficulty"]["flags"] = ["big_question_fallback", "seu_high_order_adjustment"]
        q["difficulty"]["difficulty_source"] = "pipeline.final"
        statistics = {
            "avg_difficulty": 9.1,
            "avg_cognitive_level": 8.0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})
        detail = result["questions"][0]

        assert detail["question_text"] == "第21题原题文本"
        assert detail["answer"] == "参考答案示例"
        assert detail["difficulty_flags"] == ["big_question_fallback", "seu_high_order_adjustment"]
        assert detail["difficulty_source"] == "pipeline.final"

    def test_metadata_quality_reports_missing_prompt_purposes_and_source_gaps(self):
        q1 = _make_question(1, 5.0, 3, 2)
        q1["question_text"] = "题干"
        q1["correct_answer"] = "A"
        q1["_metadata_envelope"] = {
            "confidence": {"overall": 0.92},
            "llm_calls": [{"purpose": "question_analysis"}],
            "warnings": [],
        }
        q2 = _make_question(2, 5.0, 3, 2)
        q2["_metadata_envelope"] = {
            "confidence": {"overall": 0.91},
            "llm_calls": [
                {"purpose": "question_analysis"},
                {"purpose": "feature_extraction"},
                {"purpose": "competency_analysis"},
            ],
            "warnings": [],
        }
        statistics = {
            "avg_difficulty": 5.0,
            "avg_cognitive_level": 5.0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q1, q2], {}, statistics, {"name": "t", "total": 2, "mode": "deep"})
        quality = result["metadata_quality"]

        assert {"id": 1, "purpose": "feature_extraction"} in quality["missing_purpose_questions"]
        assert {"id": 1, "purpose": "competency_analysis"} in quality["missing_purpose_questions"]
        assert quality["question_text_missing_count"] == 1
        assert quality["answer_missing_count"] == 1

    def test_metadata_quality_accepts_big_question_feature_and_scoring_unit_competency(self):
        q = _make_question(21, 8.7, 5, 14)
        q["_metadata_envelope"] = {
            "confidence": {"overall": 0.93},
            "llm_calls": [
                {"purpose": "question_analysis"},
                {"purpose": "big_question_feature_extraction"},
            ],
            "warnings": [],
        }
        q["analysis"]["_fine_grained"] = {
            "scoring_units": [
                {
                    "label": "实验设计与结果解释",
                    "score_share": 1.0,
                    "difficulty_estimate": 8.8,
                    "competency_tags": ["科学探究", "科学思维"],
                }
            ],
            "diagnostic_units": [{"misconception": "忽略对照变量", "trap_strength": 3}],
            "stimulus_units": [
                {"description": "实验装置与结果图", "complexity": 3, "is_core": True}
            ],
        }
        statistics = {
            "avg_difficulty": 8.7,
            "avg_cognitive_level": 8.0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})
        missing = result["metadata_quality"]["missing_purpose_questions"]

        assert {"id": 21, "purpose": "feature_extraction"} not in missing
        assert {"id": 21, "purpose": "competency_analysis"} not in missing
        assert result["metadata_quality"]["llm_call_counts"]["big_question_feature_extraction"] == 1

    def test_metadata_quality_keeps_successful_evidence_repair_visible_without_retry_failure(self):
        q = _make_question(18, 6.8, 4, 12)
        q["question_text"] = "stem"
        q["correct_answer"] = "answer"
        q["analysis"]["_fine_grained"] = {
            "scoring_units": [{"label": "analysis", "score_share": 1.0, "competency_tags": ["inquiry"]}],
            "diagnostic_units": [{"du_id": "du_1", "option_or_trap": "trap", "misconception": "gap"}],
            "stimulus_units": [{"su_id": "su_1", "stimulus_type": "text", "description": "context", "complexity": 2}],
        }
        q["_metadata_envelope"] = {
            "confidence": {"overall": 0.95},
            "llm_calls": [
                {"purpose": "question_analysis"},
                {"purpose": "big_question_feature_extraction"},
                {"purpose": "competency_analysis"},
                {
                    "purpose": "missing_evidence_repair",
                    "retry_count": 1,
                    "fallback_count": 0,
                    "validation_errors": [],
                    "metadata": {
                        "validation_errors": [],
                        "repair_attempt": 1,
                        "diagnostic_units_count": 1,
                        "stimulus_units_count": 1,
                    },
                },
            ],
            "warnings": [],
        }

        result = aggregate_report_data([q], {}, _minimal_statistics(6.8), {"name": "t", "total": 1, "mode": "deep"})
        quality = result["metadata_quality"]

        assert quality["retry_questions"] == []
        assert quality["evidence_gap_questions"] == []
        assert quality["llm_call_counts"]["missing_evidence_repair"] == 1

    def test_metadata_quality_allows_successful_question_recovery_without_retry_failure(self):
        q = _make_question(21, 8.7, 5, 14)
        q["question_text"] = "stem"
        q["correct_answer"] = "answer"
        q["analysis"]["_fine_grained"] = {
            "scoring_units": [
                {"label": "基因工程推理", "score_share": 1.0, "competency_tags": ["科学思维"]}
            ],
            "diagnostic_units": [{"du_id": "du_1", "option_or_trap": "trap", "misconception": "忽略调控"}],
            "stimulus_units": [{"su_id": "su_1", "stimulus_type": "text", "description": "材料题干", "complexity": 3}],
        }
        q["_metadata_envelope"] = {
            "confidence": {"overall": 0.95},
            "llm_calls": [
                {
                    "purpose": "question_analysis",
                    "prompt_id": "biology.question_analysis.v2.ultra_compact_retry",
                    "retry_count": 2,
                    "fallback_count": 0,
                    "validation_errors": [],
                    "metadata": {
                        "initial_error": "compact_retry_failed",
                        "initial_provider_errors": ["finish_reason=length"],
                        "provider_errors": [],
                        "recovery_mode": "ultra_compact_v2",
                        "recovery_status": "ok",
                    },
                },
                {"purpose": "big_question_feature_extraction"},
                {"purpose": "competency_analysis"},
            ],
            "warnings": [],
        }

        result = aggregate_report_data([q], {}, _minimal_statistics(8.7), {"name": "t", "total": 1, "mode": "deep"})

        assert result["metadata_quality"]["retry_questions"] == []
        assert result["metadata_quality"]["evidence_gap_questions"] == []

    def test_metadata_quality_allows_successful_feature_compact_retry(self):
        q = _make_question(13, 5.9, 4, 4)
        q["question_text"] = "stem"
        q["correct_answer"] = "answer"
        q["_metadata_envelope"] = {
            "confidence": {"overall": 0.95},
            "llm_calls": [
                {"purpose": "question_analysis"},
                {
                    "purpose": "feature_extraction",
                    "prompt_id": "biology.feature_extraction",
                    "retry_count": 1,
                    "fallback_count": 0,
                    "validation_errors": [],
                    "metadata": {
                        "provider_errors": [],
                        "feature_status": "ok",
                        "recovery_mode": "api_failure_compact_retry",
                        "recovery_status": "ok",
                    },
                },
                {"purpose": "competency_analysis"},
            ],
            "warnings": [],
        }

        result = aggregate_report_data([q], {}, _minimal_statistics(5.9), {"name": "t", "total": 1, "mode": "deep"})

        assert result["metadata_quality"]["retry_questions"] == []

    def test_metadata_quality_blocks_degraded_length_recovery(self):
        q = _make_question(21, 5.0, 3, 14)
        q["question_text"] = "stem"
        q["correct_answer"] = "answer"
        q["analysis"]["_fine_grained"] = {
            "scoring_units": [],
            "diagnostic_units": [],
            "stimulus_units": [],
        }
        q["_metadata_envelope"] = {
            "confidence": {"overall": 0.95},
            "llm_calls": [
                {
                    "purpose": "question_analysis",
                    "prompt_id": "biology.question_analysis.v1.length_recovery.deterministic",
                    "retry_count": 4,
                    "fallback_count": 0,
                    "validation_errors": [],
                    "metadata": {
                        "provider_errors": [],
                        "recovery_mode": "deterministic_length_fallback",
                        "recovery_status": "degraded",
                    },
                },
                {"purpose": "big_question_feature_extraction"},
                {"purpose": "competency_analysis"},
            ],
            "warnings": [],
        }

        result = aggregate_report_data([q], {}, _minimal_statistics(5.0), {"name": "t", "total": 1, "mode": "deep"})

        assert {"id": 21, "purpose": "question_analysis"} in result["metadata_quality"]["retry_questions"]
        assert {"id": 21, "reason": "diagnostic_units_missing"} in result["metadata_quality"]["evidence_gap_questions"]

    def test_metadata_quality_blocks_failed_evidence_repair_and_not_score_normalization_notes(self):
        q = _make_question(19, 7.1, 4, 12)
        q["question_text"] = "stem"
        q["correct_answer"] = "answer"
        q["analysis"]["_fine_grained"] = {
            "scoring_units": [{"label": "analysis", "score_share": 1.0, "competency_tags": ["thinking"]}],
            "diagnostic_units": [{"du_id": "du_1", "option_or_trap": "trap", "misconception": "gap"}],
            "stimulus_units": [{"su_id": "su_1", "stimulus_type": "text", "description": "context", "complexity": 2}],
        }
        q["_metadata_envelope"] = {
            "confidence": {"overall": 0.95},
            "llm_calls": [
                {
                    "purpose": "question_analysis",
                    "metadata": {"normalization_notes": ["score_share_sum_normalized"]},
                },
                {"purpose": "big_question_feature_extraction"},
                {"purpose": "competency_analysis"},
                {
                    "purpose": "missing_evidence_repair",
                    "retry_count": 0,
                    "fallback_count": 0,
                    "validation_errors": ["diagnostic_units_empty_after_retry"],
                    "metadata": {
                        "validation_errors": ["diagnostic_units_empty_after_retry"],
                        "repair_attempt": 1,
                    },
                },
            ],
            "warnings": [],
        }

        result = aggregate_report_data([q], {}, _minimal_statistics(7.1), {"name": "t", "total": 1, "mode": "deep"})

        assert {"id": 19, "purpose": "question_analysis"} not in result["metadata_quality"]["retry_questions"]
        assert {"id": 19, "purpose": "missing_evidence_repair"} in result["metadata_quality"]["retry_questions"]

    def test_metadata_quality_blocks_failed_difficulty_and_missing_big_question_evidence(self):
        q = _make_question(21, 5.0, 4, 14)
        q["difficulty"] = {
            "final_difficulty": None,
            "difficulty_label": "未评估",
            "confidence": 0.0,
            "analysis_failed": True,
            "failure_reason": "big_question_structure_failed",
            "features": {"_feature_status": "failed"},
            "flags": ["big_question_structure_failed"],
        }
        q["analysis"]["_fine_grained"] = {
            "scoring_units": [
                {"label": "experiment design", "score_share": 1.0, "difficulty_estimate": 8.0}
            ],
            "diagnostic_units": [],
            "stimulus_units": [
                {"su_id": "21-S1", "stimulus_type": "text", "description": "", "complexity": 1, "is_core": False}
            ],
        }
        q["_metadata_envelope"] = {
            "confidence": {"overall": 0.95},
            "llm_calls": [
                {"purpose": "question_analysis"},
                {"purpose": "feature_extraction"},
                {"purpose": "competency_analysis"},
            ],
            "warnings": [],
        }
        statistics = {
            "avg_difficulty": 0,
            "avg_cognitive_level": 0,
            "difficulty_distribution": {},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {},
            "difficulty_curve": [],
            "top_knowledge_points": [],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }

        result = aggregate_report_data([q], {}, statistics, {"name": "t", "total": 1, "mode": "deep"})
        quality = result["metadata_quality"]

        assert {"id": 21, "reason": "big_question_structure_failed"} in quality["blocked_questions"]
        assert {"id": 21, "reason": "diagnostic_units_missing"} in quality["evidence_gap_questions"]
        assert {"id": 21, "reason": "stimulus_units_blank"} in quality["evidence_gap_questions"]

    def test_returns_all_top_level_keys(self):
        """返回值包含所有必需的顶层 key"""
        questions = [_make_question(1, 5.0, 3, 6)]
        statistics = {
            "avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
            "difficulty_distribution": {"简单": 0, "中等": 1, "困难": 0},
            "difficulty_distribution_by_score": {},
            "bloom_distribution": {"识记": 0, "理解": 0, "应用": 1.0, "分析": 0, "评价": 0, "创造": 0},
            "difficulty_curve": [{"question_id": 1, "difficulty": 5.0, "total_score": 6}],
            "top_knowledge_points": [{"name": "光合作用", "weighted_score": 6.0}],
            "knowledge_textbook_distribution": {},
            "competency_distribution": {},
        }
        result = aggregate_report_data(
            questions=questions,
            competency_summary={},
            exam_statistics=statistics,
            exam_info={"name": "测试卷", "total": 1, "mode": "fast"},
        )
        assert set(result.keys()) == {
            "exam_info", "metrics", "difficulty_curve", "difficulty_gradient",
            "knowledge", "competency", "feature_profile", "questions",
            "metadata_quality", "fine_grained_summary",
        }

    def test_feature_profile_averages_6_dimensions(self):
        """feature_profile 聚合 6 维均值（排除 question_type_factor）"""
        questions = [
            _make_question(1, 5.0, 4, 6),
            _make_question(2, 3.0, 2, 4),
        ]
        # bloom: (4+2)/2=3, reasoning_steps: (4+4)/2=4, etc.
        statistics = {"avg_difficulty": 4.2, "avg_cognitive_level": 5.0,
                      "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
                      "bloom_distribution": {}, "difficulty_curve": [],
                      "top_knowledge_points": [], "knowledge_textbook_distribution": {},
                      "competency_distribution": {}}
        result = aggregate_report_data(questions, {}, statistics,
                                       {"name": "t", "total": 2, "mode": "fast"})
        avg = result["feature_profile"]["avg_per_dimension"]
        assert avg["bloom"] == 3.0
        assert "question_type_factor" not in avg

    def test_difficulty_gradient_three_segments(self):
        """difficulty_gradient 计算前中后三段"""
        questions = [_make_question(i, float(i), 3, 2) for i in range(1, 10)]
        curve = [{"question_id": i, "difficulty": float(i), "total_score": 2} for i in range(1, 10)]
        statistics = {"avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
                      "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
                      "bloom_distribution": {}, "difficulty_curve": curve,
                      "top_knowledge_points": [], "knowledge_textbook_distribution": {},
                      "competency_distribution": {}}
        result = aggregate_report_data(questions, {}, statistics,
                                       {"name": "t", "total": 9, "mode": "fast"})
        grad = result["difficulty_gradient"]
        assert grad["front"] < grad["back"]  # 递增
        assert grad["gradient_type"] in ["前易后难（递增）", "前难后易（递减）", "难度均衡", "难度波动较大"]

    def test_question_details_extract_all_fields(self):
        """逐题详情提取全部字段"""
        questions = [_make_question(1, 5.0, 3, 6)]
        statistics = {"avg_difficulty": 5.0, "avg_cognitive_level": 5.0,
                      "difficulty_distribution": {}, "difficulty_distribution_by_score": {},
                      "bloom_distribution": {}, "difficulty_curve": [],
                      "top_knowledge_points": [], "knowledge_textbook_distribution": {},
                      "competency_distribution": {}}
        result = aggregate_report_data(questions, {}, statistics,
                                       {"name": "t", "total": 1, "mode": "fast"})
        q = result["questions"][0]
        assert q["id"] == 1
        assert q["bloom"] == 3
        assert q["bloom_reason"] is not None
        assert q["knowledge_points"] == ["光合作用"]
        assert q["detailed_analysis"] == "解题步骤..."
        assert q["primary_competency"] == "生命观念"
