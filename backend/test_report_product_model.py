from report_product_model import (
    build_report_product_model,
    _infer_sub_competency,
    _question_evidence_integrity_trace,
)
from report_commercial_narrative import contains_risk_text, metadata_status
from report_teacher_review_narrative import (
    classify_overall_verdict,
    summarize_student_fit,
    summarize_teacher_priorities,
)
from test_report_commercial_model import sample_report_data, sample_report_data_with_full_units


def test_product_model_uses_single_commercial_report_contract():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    assert "meta" not in model
    assert "hero_conclusions" not in model
    assert set(model) >= {
        "cover",
        "credibility",
        "executive_summary",
        "at_a_glance",
        "chapters",
        "question_portfolio",
        "deep_dives",
        "methodology",
    }
    assert model["cover"]["report_version"] == "commercial_report.v1"
    assert model["credibility"]["llm_calls_total"] == 63
    assert model["executive_summary"]["big_calls"][0]["evidence_refs"]
    assert model["question_portfolio"]["rows"][0]["metadata_confidence"] is not None


def test_product_model_exposes_report_grounding_status_in_evidence_integrity():
    insights = {
        "_grounding_status": "needs_review",
        "_grounding_checks": [
            {
                "status": "needs_review",
                "support_score": 0.42,
                "threshold": 0.6,
                "claim_count": 2,
                "cited_chunk_count": 0,
            }
        ],
    }

    model = build_report_product_model(sample_report_data(), insights)

    item_by_id = {
        item.get("id"): item
        for item in model["evidence_integrity"]["items"]
        if isinstance(item, dict)
    }
    assert item_by_id["report_grounding"]["severity"] == "warning"
    assert item_by_id["report_grounding"]["value"] == "0.42"
    assert "needs_review" in model["evidence_integrity"]["grounding_status"]


def test_metadata_status_fails_closed_for_quality_gate_gaps():
    assert metadata_status({
        "blocked_questions": [{"id": 21, "reason": "big_question_structure_failed"}],
    }) == "blocked"
    assert metadata_status({
        "missing_purpose_questions": [{"id": 12, "purpose": "competency_analysis"}],
    }) == "blocked"
    assert metadata_status({
        "evidence_gap_questions": [{"id": 21, "reason": "diagnostic_units_missing"}],
    }) == "blocked"
    assert metadata_status({
        "retry_questions": [{"id": 21, "purpose": "question_analysis"}],
    }) == "warning"


def test_quality_issue_low_score_remains_review_warning_not_blocked():
    data = sample_report_data()
    question = data["questions"][0]
    question["quality_score"] = 2
    question["difficulty"] = {
        "final_difficulty": 6.0,
        "difficulty_label": "中等",
        "flags": ["quality_issue_low_score"],
        "features": {"quality_score": 2, "quality_issue_low_score": True},
    }

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]
    integrity = _question_evidence_integrity_trace(question)
    explanations = integrity["failure_explanations"]

    assert row["risk_level"] == "high"
    assert row["difficulty_display"] == "6.0"
    assert "quality_issue_low_score" in integrity["difficulty_flags"]
    assert any(item["severity"] == "warning" for item in explanations)


def test_classify_overall_verdict_uses_teacher_language():
    result = classify_overall_verdict(
        high_risk_count=1,
        language_risk_count=0,
        scientific_risk_count=1,
        student_fit_level="medium",
    )

    assert result["label"] == "建议修改后使用"
    assert result["stance"] == "watch"
    assert "复核" in result["teacher_takeaway"]
    assert "SEU" not in result["teacher_takeaway"]
    assert "metadata" not in result["teacher_takeaway"].lower()


def test_summarize_teacher_priorities_are_actionable_for_teachers():
    priorities = summarize_teacher_priorities(
        risk_question_ids=[17, 18, 19],
        weak_dimensions=["信息提取", "干扰项辨析"],
        use_case="阶段诊断卷",
    )

    joined = " ".join(item["summary"] for item in priorities)
    assert "第 17-19 题" in joined
    assert "讲评" in joined
    assert "阶段诊断卷" in joined


def test_summarize_teacher_priorities_does_not_drop_sixth_review_question():
    priorities = summarize_teacher_priorities(
        risk_question_ids=[1, 3, 6, 9, 10, 19],
        weak_dimensions=["表述边界"],
        use_case="阶段诊断卷",
    )

    joined = " ".join(item["summary"] for item in priorities)
    for question_id in [1, 3, 6, 9, 10, 19]:
        assert f"第 {question_id} 题" in joined


def test_summarize_student_fit_distinguishes_use_scenarios():
    fit = summarize_student_fit(avg_difficulty=5.6, high_pressure_count=3, target_group="高三普通班")

    assert fit["fit_level"] in {"适配", "基本适配", "需拆解使用"}
    assert "普通班" in fit["teacher_note"]
    assert "怎么用" not in fit["teacher_note"]


def test_summarize_student_fit_uses_basic_fit_for_mid_difficulty():
    fit = summarize_student_fit(avg_difficulty=5.57, high_pressure_count=0, target_group="高三学生")

    assert fit["fit_level"] == "基本适配"
    assert "较友好" not in fit["teacher_note"]


def test_summary_distinguishes_model_risk_from_priority_review_candidates():
    data = sample_report_data()
    data["metrics"]["avg_difficulty"] = 5.57
    data["difficulty_gradient"]["gradient_type"] = "前易后难"
    data["questions"][0]["difficulty"] = 5.57
    data["questions"][1].update({
        "quality_score": 5,
        "quality_scientific": "C选项对脱毒原理的解释不准确，需人工复核。",
        "metadata_confidence": 1.0,
        "metadata_warnings": [],
        "difficulty": 5.57,
    })

    model = build_report_product_model(data, {"recommendations": []})
    rows = model["question_portfolio"]["rows"]
    summary = model["executive_summary"]
    quality_chapter = next(chapter for chapter in model["chapters"] if chapter["id"] == "quality_metadata")

    assert {row["risk_level"] for row in rows} == {"low"}
    assert summary["evidence_scale"]["reviewed_risk_items"] == 1
    assert "1 道人工优先复核题" in summary["lead_judgment"]
    assert "模型高风险" in quality_chapter["thesis"]
    assert "另有 1 道人工优先复核题" in quality_chapter["thesis"]
    assert summary["student_fit"]["fit_level"] in {"基本适配", "需拆解使用"}


def test_model_corrects_multiple_choice_section_scores_to_exam_total():
    data = sample_report_data()
    data["exam_info"]["total_score"] = 100
    data["questions"] = [
        {
            "id": qid,
            "total_score": 2,
            "question_type": "single_choice" if qid <= 12 else "multiple_choice" if qid <= 16 else "short_answer",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
        }
        for qid in range(1, 17)
    ] + [
        {"id": 17, "total_score": 11, "question_type": "short_answer", "difficulty": 5.0, "quality_score": 5, "metadata_confidence": 1.0, "metadata_warnings": []},
        {"id": 18, "total_score": 11, "question_type": "short_answer", "difficulty": 5.0, "quality_score": 5, "metadata_confidence": 1.0, "metadata_warnings": []},
        {"id": 19, "total_score": 12, "question_type": "short_answer", "difficulty": 5.0, "quality_score": 5, "metadata_confidence": 1.0, "metadata_warnings": []},
        {"id": 20, "total_score": 12, "question_type": "short_answer", "difficulty": 5.0, "quality_score": 5, "metadata_confidence": 1.0, "metadata_warnings": []},
        {"id": 21, "total_score": 14, "question_type": "short_answer", "difficulty": 5.0, "quality_score": 5, "metadata_confidence": 1.0, "metadata_warnings": []},
    ]

    model = build_report_product_model(data, {"recommendations": []})
    by_id = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert model["credibility"]["analysis_scope"]["total_score"] == 100
    assert sum(row["score"] for row in model["question_portfolio"]["rows"]) == 100
    assert [by_id[qid]["score"] for qid in range(13, 17)] == [4, 4, 4, 4]
    assert model["evidence_integrity"]["score_adjustment_questions"] == [13, 14, 15, 16]
    assert any(
        item["title"] == "分值规范化提示" and "Q13" in item["detail"]
        for item in model["evidence_integrity"]["items"]
    )


def test_score_remainder_guard_does_not_create_nonpositive_question_score():
    data = sample_report_data()
    data["exam_info"]["total_score"] = 20
    data["questions"] = [
        {
            "id": qid,
            "total_score": 2,
            "question_type": "single_choice" if qid <= 12 else "multiple_choice",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
        }
        for qid in range(1, 17)
    ] + [
        {"id": 21, "total_score": 1, "question_type": "short_answer", "difficulty": 5.0, "quality_score": 5, "metadata_confidence": 1.0, "metadata_warnings": []},
    ]

    model = build_report_product_model(data, {"recommendations": []})

    assert min(row["score"] for row in model["question_portfolio"]["rows"]) > 0


def test_model_recomputes_bloom_distribution_from_weighted_scoring_units():
    data = sample_report_data()
    data["exam_info"]["total_score"] = 10
    data["exam_info"]["total_questions"] = 2
    data["metrics"]["bloom_distribution"] = {"创造": 1.0}
    data["questions"] = [
        {
            "id": 1,
            "total_score": 4,
            "question_type": "single_choice",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "knowledge_points": ["生态"],
            "primary_competency": "生命观念",
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "理解概念", "score_share": 0.5, "bloom_level": 2},
                    {"label": "分析情境", "score_share": 0.5, "bloom_level": 4},
                ]
            },
        },
        {
            "id": 2,
            "total_score": 6,
            "question_type": "short_answer",
            "difficulty": 7.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "knowledge_points": ["遗传"],
            "primary_competency": "科学思维",
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "评价方案", "score_share": 0.5, "bloom_level": 5},
                    {"label": "设计方案", "score_share": 0.5, "bloom_level": 6},
                ]
            },
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    bloom_figure = next(
        figure
        for chapter in model["chapters"]
        for figure in chapter["figures"]
        if figure["id"] == "bloom_distribution"
    )

    assert bloom_figure["data"] == {"理解": 0.2, "分析": 0.2, "评价": 0.3, "创造": 0.3}
    assert bloom_figure["source"] == "fine_grained_exhibits.seu_rows"


def test_model_builds_competency_diagnosis_with_subdimensions():
    model = build_report_product_model(sample_report_data_with_full_units(), {"recommendations": []})
    competency_figure = next(
        figure
        for chapter in model["chapters"]
        for figure in chapter["figures"]
        if figure["id"] == "competency_distribution"
    )

    assert competency_figure["title"] == "核心素养覆盖诊断定位课程目标缺口"
    assert competency_figure["source"] == "fine_grained_exhibits.competency_detail_rows"
    data = competency_figure["data"]
    assert set(data) >= {"distribution", "detail_rows", "gap_rows", "summary"}

    detail_rows = data["detail_rows"]
    assert any(
        row["competency"] == "科学思维"
        and row["sub_competency"] == "证据推理"
        and 7 in row["question_ids"]
        for row in detail_rows
    )
    assert any(
        row["competency"] == "科学探究"
        and row["sub_competency"] == "实验设计"
        and row["source"] in {"explicit", "rule_inferred"}
        for row in detail_rows
    )
    assert data["gap_rows"]
    assert {row["competency"] for row in data["gap_rows"]} == {"社会责任"}


def test_big_question_difficulty_uses_scoring_unit_estimates():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 20,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 5.08,
            "difficulty_label": "中等",
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "综合实验设计", "score_share": 0.5, "difficulty_estimate": 6.8},
                    {"label": "结果推理", "score_share": 0.5, "difficulty_estimate": 7.2},
                ],
                "diagnostic_units": [],
            },
        },
        {
            "id": 21,
            "total_score": 14,
            "question_type": "short_answer",
            "difficulty": 5.08,
            "difficulty_label": "中等",
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "复杂情境建模", "score_share": 0.4, "difficulty_estimate": 7.4},
                    {"label": "跨模块推理", "score_share": 0.6, "difficulty_estimate": 7.8},
                ],
                "diagnostic_units": [],
            },
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    by_id = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert by_id[20]["difficulty"] >= 6.8
    assert by_id[20]["difficulty_label"] == "困难"
    assert by_id[21]["difficulty"] >= 7.6
    assert by_id[21]["difficulty_label"] == "困难"


def test_diagnostic_traps_do_not_accumulate_into_cognitive_difficulty():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 101,
            "total_score": 8,
            "question_type": "short_answer",
            "difficulty": 6.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "core inference", "score_share": 0.5, "difficulty_estimate": 6.5},
                    {"label": "evidence explanation", "score_share": 0.5, "difficulty_estimate": 6.5},
                ],
                "diagnostic_units": [],
            },
        },
        {
            "id": 102,
            "total_score": 8,
            "question_type": "short_answer",
            "difficulty": 6.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "core inference", "score_share": 0.5, "difficulty_estimate": 6.5},
                    {"label": "evidence explanation", "score_share": 0.5, "difficulty_estimate": 6.5},
                ],
                "diagnostic_units": [
                    {"option_or_trap": "trap_a", "misconception": "wrong boundary", "trap_strength": 3},
                    {"option_or_trap": "trap_b", "misconception": "partial truth", "trap_strength": 3},
                    {"option_or_trap": "trap_c", "misconception": "language confusion", "trap_strength": 3},
                ],
            },
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    by_id = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert by_id[102]["difficulty"] == by_id[101]["difficulty"]
    assert by_id[102]["pressure_index"] > by_id[101]["pressure_index"]


def test_scoring_unit_count_does_not_accumulate_into_difficulty():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 201,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 6.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "single integrated rubric", "score_share": 1.0, "difficulty_estimate": 6.5},
                ],
                "diagnostic_units": [],
            },
        },
        {
            "id": 202,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 6.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": f"rubric part {index}", "score_share": 0.2, "difficulty_estimate": 6.5}
                    for index in range(5)
                ],
                "diagnostic_units": [],
            },
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    by_id = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert by_id[202]["difficulty"] == by_id[201]["difficulty"]


def test_complete_unit_evidence_bounds_overstated_base_difficulty():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 301,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 9.2,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "entry concept", "score_share": 0.2, "difficulty_estimate": 4.0},
                    {"label": "main inference", "score_share": 0.4, "difficulty_estimate": 6.5},
                    {"label": "explanation", "score_share": 0.4, "difficulty_estimate": 7.0},
                ],
                "diagnostic_units": [],
            },
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = next(item for item in model["question_portfolio"]["rows"] if item["question_id"] == 301)

    assert row["difficulty"] < 8.0


def test_data_gap_is_not_counted_as_question_quality_risk():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 9,
            "total_score": 2,
            "question_type": "single_choice",
            "difficulty": None,
            "difficulty_label": "未评估",
            "quality_score": None,
            "feature_status": "failed",
            "metadata_confidence": 0.0,
            "metadata_warnings": ["feature_status:failed"],
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert row["risk_level"] == "data_gap"
    assert row["quality_level"] == "数据不足"
    assert row["difficulty"] is None
    assert row["difficulty_display"] == "未评估"
    assert model["executive_summary"]["evidence_scale"]["reviewed_risk_items"] == 0


def test_structure_and_difficulty_warnings_are_teacher_visible():
    data = sample_report_data()
    data["exam_info"]["total_questions"] = 2
    data["exam_info"]["total_score"] = 23
    data["questions"] = [
        {
            "id": 18,
            "total_score": 11,
            "question_type": "short_answer",
            "content": "18.（11分）（1）分析食物网。（2）解释生态工程。",
            "difficulty": 7.3,
            "confidence": 0.57,
            "difficulty_flags": ["rule_llm_mismatch"],
            "_difficulty_authoritative": True,
            "quality_score": 5,
            "metadata_confidence": 0.94,
            "metadata_warnings": [],
        },
        {
            "id": 19,
            "total_score": 12,
            "question_type": "short_answer",
            "content": "19.（12分）（1）概念判断。（2）机制分析。（3）实验处理。（3）结果解释。",
            "difficulty": 8.0,
            "quality_score": 5,
            "metadata_confidence": 0.97,
            "metadata_warnings": [],
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    rows = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert rows[18]["risk_level"] == "medium"
    assert rows[18]["quality_level"] == "需复核"
    assert "难度评估需复核" in rows[18]["primary_issue"]
    assert "0.57" in rows[18]["primary_issue"]
    assert "LLM" in rows[18]["primary_issue"]
    assert "难度评估证据和采分点负荷" in rows[18]["action"]
    assert "题面结构" not in rows[18]["action"]
    assert rows[19]["risk_level"] == "medium"
    assert rows[19]["quality_level"] == "需复核"
    assert "题面结构需复核" in rows[19]["primary_issue"]
    assert "编号重复" in rows[19]["primary_issue"]
    assert "题面小问编号、材料边界和评分口径" in rows[19]["action"]
    assert model["executive_summary"]["evidence_scale"]["reviewed_risk_items"] == 2
    assert model["evidence_integrity"]["difficulty_review_questions"] == [18]
    assert model["evidence_integrity"]["structure_warning_questions"] == [19]


def test_blocked_questions_are_placed_first_in_executive_summary():
    data = sample_report_data()
    data["exam_info"]["total_questions"] = 1
    data["exam_info"]["total_score"] = 14
    data["metadata_quality"] = {
        "blocked_questions": [{"id": 21, "reason": "insufficient_stem"}],
        "llm_call_counts": {"question_analysis": 1},
    }
    data["questions"] = [
        {
            "id": 21,
            "total_score": 14,
            "question_type": "short_answer",
            "content": "21.（14分）表1材料。（2）分析实验失败原因。（3）鉴定阳性克隆。",
            "difficulty": {
                "final_difficulty": None,
                "analysis_failed": True,
                "failure_reason": "insufficient_stem",
                "flags": ["big_question_structure_failed"],
                "features": {"_feature_status": "failed"},
            },
            "quality_score": None,
            "metadata_confidence": 0.0,
            "metadata_warnings": ["analysis_failed:insufficient_stem"],
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    summary = model["executive_summary"]
    row = model["question_portfolio"]["rows"][0]

    assert row["risk_level"] == "data_gap"
    assert row["difficulty"] is None
    assert summary["blocking_questions"] == [21]
    assert summary["teacher_priorities"][0]["title"] == "阻断题先处理"
    assert "不得展示推断难度" in summary["teacher_priorities"][0]["summary"]
    assert summary["evidence_scale"]["blocked_items"] == 1
    assert "阻断题" in summary["lead_judgment"]


def test_score_remainder_does_not_require_question_21():
    data = sample_report_data()
    data["exam_info"] = {"name": "20 question paper", "total_questions": 2, "total_score": 10}
    data["questions"] = [
        {
            "id": 1,
            "total_score": 2,
            "question_type": "single_choice",
            "difficulty": 4.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
        },
        {
            "id": 20,
            "total_score": 5,
            "question_type": "short_answer",
            "difficulty": 7.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    scores = {row["question_id"]: row["score"] for row in model["question_portfolio"]["rows"]}

    assert sum(scores.values()) == 10
    assert scores[20] == 8


def test_unresolved_score_remainder_fails_loudly():
    data = sample_report_data()
    data["exam_info"] = {"name": "objective only mismatch", "total_questions": 1, "total_score": 10}
    data["questions"] = [
        {
            "id": 1,
            "total_score": 2,
            "question_type": "single_choice",
            "difficulty": 4.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
        }
    ]

    import pytest

    with pytest.raises(ValueError, match="score total mismatch"):
        build_report_product_model(data, {"recommendations": []})


def test_priority_review_uses_same_risk_text_semantics_as_risk_level():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 12,
            "total_score": 4,
            "question_type": "short_answer",
            "difficulty": 6.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "primary_issue": "暂无完整替代方案，但存在评分边界风险，需要复核。",
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert row["risk_level"] == "low"
    assert row["stance"] == "watch"
    assert model["executive_summary"]["evidence_scale"]["reviewed_risk_items"] == 1


def test_distractor_error_wording_is_not_treated_as_question_quality_risk():
    assert not contains_risk_text(
        "无明显问题。各选项涉及的生物学事实陈述清晰，正确选项C的表述准确，"
        "干扰项A、B、D的错误设置符合科学事实。"
    )
    assert not contains_risk_text(
        "C选项的错误性逻辑严谨且唯一，答案唯一且科学准确。"
    )
    assert not contains_risk_text(
        "无明显问题。A选项表述错误，B、C、D选项表述正确，"
        "符合现代生物进化理论，答案唯一且科学准确。"
    )
    assert not contains_risk_text(
        "D选项用词'mRNA'不够严谨，但该瑕疵不影响核心逻辑和答案唯一性。"
        "整体无明显科学性错误。"
    )
    assert not contains_risk_text(
        "无明显问题。C选项的表述“没有影响”在科学上是错误的，"
        "这正是本题的考查意图，答案唯一且明确。"
    )
    assert contains_risk_text(
        "存在严重科学性错误：提供的正确答案C是错误的，答案与事实不符。"
    )
    assert not contains_risk_text(
        "学生典型错误路径：混淆核心概念并误选错误选项，教学中应加强对比。"
    )


def test_executive_summary_does_not_list_stable_distractor_items_as_priority_review():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 1,
            "total_score": 2,
            "question_type": "single_choice",
            "difficulty": 6.1,
            "quality_score": 5,
            "metadata_confidence": 0.97,
            "metadata_warnings": [],
            "primary_issue": (
                "无明显问题。各选项涉及的生物学事实陈述清晰，正确选项C的表述准确，"
                "干扰项A、B、D的错误设置符合科学事实。"
            ),
        },
        {
            "id": 7,
            "total_score": 2,
            "question_type": "single_choice",
            "difficulty": None,
            "quality_score": 1,
            "metadata_confidence": 0.7,
            "metadata_warnings": [],
            "failure_reason": "quality_score_too_low",
            "quality_scientific": "存在严重科学性错误：提供的正确答案C是错误的，答案与事实不符。",
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    rows = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert rows[1]["risk_level"] == "low"
    assert rows[1]["stance"] == "positive"
    assert rows[7]["risk_level"] == "high"
    assert model["executive_summary"]["evidence_scale"]["reviewed_risk_items"] == 0
    assert "第 1 题" not in model["executive_summary"]["lead_judgment"]
    assert all(
        "第 1 题" not in item.get("summary", "")
        for item in model["executive_summary"]["teacher_priorities"]
    )


def test_teacher_comment_student_mistakes_do_not_become_quality_issue():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 1,
            "total_score": 2,
            "question_type": "single_choice",
            "difficulty": 6.1,
            "quality_score": 5,
            "quality_scientific": "无明显问题。",
            "quality_language": "表述清晰。",
            "metadata_confidence": 0.97,
            "metadata_warnings": [],
            "teacher_comment": (
                "本题难点在于多个强干扰项。学生典型错误路径："
                "混淆概念并误选错误选项。教学中应加强对比。"
            ),
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert row["risk_level"] == "low"
    assert row["stance"] == "positive"
    assert row["primary_issue"] == "未发现显性质量问题"
    assert model["executive_summary"]["evidence_scale"]["reviewed_risk_items"] == 0


def test_high_difficulty_stable_item_is_teaching_focus_not_priority_review_issue():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 20,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 8.8,
            "quality_score": 5,
            "quality_scientific": "未发现显性质量问题",
            "metadata_confidence": 0.97,
            "metadata_warnings": [],
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert row["risk_level"] == "low"
    assert row["quality_level"] == "稳定"
    assert row["difficulty"] == 8.8
    assert model["executive_summary"]["evidence_scale"]["reviewed_risk_items"] == 0


def test_difficulty_dict_missing_confidence_uses_top_level_confidence():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 18,
            "total_score": 11,
            "question_type": "short_answer",
            "content": "18.（11分）（1）分析食物网。（2）解释生态工程。",
            "difficulty": {
                "final_difficulty": 7.3,
                "flags": ["rule_llm_mismatch"],
                "features": {"_feature_status": "ok"},
            },
            "confidence": 0.57,
            "quality_score": 5,
            "metadata_confidence": 0.94,
            "metadata_warnings": [],
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert "难度置信度偏低：0.57" in row["primary_issue"]
    assert "0.00" not in row["primary_issue"]


def test_subquestion_structure_detection_covers_circled_and_dot_numbering():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 31,
            "total_score": 8,
            "question_type": "short_answer",
            "content": "31.（8分）①判断概念。②分析机制。③解释结果。③提出建议。",
            "difficulty": 6.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
        },
        {
            "id": 32,
            "total_score": 8,
            "question_type": "short_answer",
            "content": "32.（8分）1. 判断概念。2. 分析机制。2. 解释结果。",
            "difficulty": 6.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    rows = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert "编号重复" in rows[31]["primary_issue"]
    assert "编号重复" in rows[32]["primary_issue"]


def test_subquestion_structure_detection_ignores_nested_labels_and_table_decimals():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 18,
            "total_score": 11,
            "question_type": "short_answer",
            "content": (
                "18.（11分）研究湖泊食物网。\n"
                "（1）上述四种生物中属于第三营养级的有______。\n"
                "（2）人工浮床治理污染。\n"
                "①植物特点是______。②处理目的______。③生态工程优点______。"
            ),
            "difficulty": 6.9,
            "quality_score": 4,
            "metadata_confidence": 0.95,
            "metadata_warnings": [],
        },
        {
            "id": 19,
            "total_score": 12,
            "question_type": "short_answer",
            "content": (
                "19.（12分）槟榔碱机制研究。\n"
                "（1）判断代谢产物类型。\n"
                "（2）推断神经递质相关变化。\n"
                "（3）表格数据：1.04、1.18、3.11。\n"
                "（3）重新设计四组实验。\n"
                "（4）综合说明原因。"
            ),
            "difficulty": 9.9,
            "quality_score": 4,
            "metadata_confidence": 0.97,
            "metadata_warnings": [],
        },
        {
            "id": 20,
            "total_score": 12,
            "question_type": "short_answer",
            "content": (
                "20.（12分）基因群K包含：①M；②P；③R。\n"
                "（1）推导花粉基因型。\n"
                "（2）分析生产和生态影响。\n"
                "（3）该育种体系包含过程①和过程②。"
            ),
            "difficulty": 10.0,
            "quality_score": 5,
            "metadata_confidence": 0.97,
            "metadata_warnings": [],
        },
        {
            "id": 21,
            "total_score": 14,
            "question_type": "short_answer",
            "content": (
                "21.（14分）构建融合蛋白。\n"
                "（1）判断终止密码子。\n"
                "（2）①推测失败原因。②提出解决方案。\n"
                "（3）①正向插入条带大小。②反向插入结果。"
            ),
            "difficulty": 10.0,
            "quality_score": 4,
            "metadata_confidence": 0.97,
            "metadata_warnings": [],
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    rows = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert "题面结构需复核" not in rows[18]["primary_issue"]
    assert rows[19]["primary_issue"] == "题面结构需复核：题面小问编号重复：（3）"
    assert "题面小问编号、材料边界和评分口径" in rows[19]["action"]
    assert "题面结构需复核" not in rows[20]["primary_issue"]
    assert "题面结构需复核" not in rows[21]["primary_issue"]


def test_large_hard_tail_raises_difficulty_by_share_not_by_problem_count():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 401,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "routine setup", "score_share": 0.34, "difficulty_estimate": 5.5},
                    {"label": "routine explanation", "score_share": 0.33, "difficulty_estimate": 6.0},
                    {"label": "decisive hard inference", "score_share": 0.33, "difficulty_estimate": 9.5},
                ],
                "diagnostic_units": [
                    {"option_or_trap": f"trap_{index}", "misconception": "review issue", "trap_strength": 3}
                    for index in range(6)
                ],
            },
        },
        {
            "id": 402,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "routine setup", "score_share": 0.34, "difficulty_estimate": 5.5},
                    {"label": "routine explanation", "score_share": 0.33, "difficulty_estimate": 6.0},
                    {"label": "decisive hard inference", "score_share": 0.33, "difficulty_estimate": 9.5},
                ],
                "diagnostic_units": [],
            },
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    by_id = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert by_id[402]["difficulty"] == by_id[401]["difficulty"]
    assert by_id[402]["difficulty"] > 7.0


def test_constructed_response_load_can_outweigh_compact_choice_cognitive_estimate():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 501,
            "total_score": 4,
            "question_type": "multiple_choice",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "compact inference", "score_share": 0.6, "difficulty_estimate": 7.8},
                    {"label": "option elimination", "score_share": 0.4, "difficulty_estimate": 7.2},
                ],
                "diagnostic_units": [],
            },
        },
        {
            "id": 502,
            "total_score": 11,
            "question_type": "short_answer",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": f"rubric demand {index}", "score_share": 1 / 7, "difficulty_estimate": 4.8}
                    for index in range(7)
                ],
                "diagnostic_units": [],
            },
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    by_id = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert by_id[502]["difficulty"] > by_id[501]["difficulty"]


def test_many_independent_scoring_units_do_not_overrank_decisive_hard_tail():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 601,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": f"independent part {index}", "score_share": 1 / 7, "difficulty_estimate": 6.8}
                    for index in range(7)
                ],
                "diagnostic_units": [],
            },
        },
        {
            "id": 602,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": 5.0,
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "routine setup", "score_share": 0.34, "difficulty_estimate": 5.5},
                    {"label": "routine explanation", "score_share": 0.33, "difficulty_estimate": 6.0},
                    {"label": "decisive hard inference", "score_share": 0.33, "difficulty_estimate": 9.5},
                ],
                "diagnostic_units": [],
            },
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    by_id = {row["question_id"]: row for row in model["question_portfolio"]["rows"]}

    assert by_id[602]["difficulty"] > by_id[601]["difficulty"]


def test_missing_quality_score_uses_teacher_facing_label_not_unassessed():
    data = sample_report_data()
    data["questions"][0].pop("quality_score", None)
    data["questions"][0]["quality_scientific"] = "无明显问题"

    model = build_report_product_model(data, {"recommendations": []})
    row = next(item for item in model["question_portfolio"]["rows"] if item["question_id"] == 1)
    dive = next(item for item in model["deep_dives"] if item["question_id"] == 1)

    assert row["quality_level"] == "未见显性问题"
    assert "未评估" not in str(model["question_portfolio"])
    assert "未评估" not in dive["headline"]


def test_product_model_exposes_teacher_review_positioning():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    assert model["review_positioning"]["report_type"] == "审题 / 审卷质量诊断报告"
    assert "命题教师" in model["review_positioning"]["audience"]
    assert "能否使用" in model["review_positioning"]["use_case"]


def test_executive_summary_is_teacher_readable_not_internal_trace():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    summary = model["executive_summary"]

    assert "overall_verdict" in summary
    assert "teacher_priorities" in summary
    assert "student_fit" in summary
    assert "evidence_scale" in summary
    rendered_text = str(summary)
    assert "评分证据 1" not in rendered_text
    assert "SEU/DU" not in rendered_text
    assert "metadata envelope" not in rendered_text


def test_chapter_narrative_matches_teacher_review_report_scope():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    titles = [chapter["title"] for chapter in model["chapters"]]

    assert "试卷可用性与学情适配" in titles
    assert "知识覆盖与高考趋势适配" in titles
    assert "题目质量风险审查" in titles

    narrative_bits = []
    for chapter in model["chapters"]:
        narrative_bits.extend([chapter.get("title", ""), chapter.get("thesis", "")])
        narrative_bits.extend(chapter.get("implications", []))
        for figure in chapter.get("figures", []):
            narrative_bits.extend([
                figure.get("title", ""),
                figure.get("takeaway", ""),
                figure.get("notes", ""),
            ])
    narrative = " ".join(str(bit) for bit in narrative_bits)

    assert "学情" in narrative
    assert "高考趋势" in narrative
    assert "语言" in narrative
    assert "舆论" in narrative
    assert "可行性" in narrative
    assert "SEU" not in narrative
    assert "DU" not in narrative


def test_question_portfolio_uses_pipeline_final_difficulty_as_baseline_not_short_circuit():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 88,
            "total_score": 12,
            "question_type": "short_answer",
            "difficulty": {
                "final_difficulty": 9.4,
                "difficulty_label": "hard",
                "features": {"_feature_status": "ok"},
            },
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "routine setup", "score_share": 0.5, "difficulty_estimate": 4.0},
                    {"label": "routine explanation", "score_share": 0.5, "difficulty_estimate": 5.0},
                ],
                "diagnostic_units": [],
            },
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert 6.8 <= row["difficulty"] <= 7.8
    assert row["difficulty_display"] != "9.4"
    assert row["score_risk"] > 0


def test_stable_question_with_benign_option_error_text_is_not_priority_review():
    data = sample_report_data()
    data["metadata_quality"]["low_confidence_questions"] = []
    data["metadata_quality"]["warning_questions"] = []
    data["questions"] = [
        {
            "id": 4,
            "total_score": 2,
            "question_type": "single_choice",
            "difficulty": 3.6,
            "quality_score": 5,
            "quality_scientific": "\u65e0\u660e\u663e\u95ee\u9898\u3002A\u9879\u9519\u8bef\u7ed3\u8bba\u7b26\u5408\u751f\u7269\u5b66\u4e8b\u5b9e\u3002",
            "metadata_confidence": 0.99,
            "metadata_warnings": [],
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert row["risk_level"] == "low"
    assert row["needs_priority_review"] is False
    assert model["executive_summary"]["evidence_scale"]["reviewed_risk_items"] == 0
    assert "\u590d\u6838" not in row["action"]


def test_high_difficulty_stable_question_is_teaching_focus_not_priority_review():
    data = sample_report_data()
    data["metadata_quality"]["low_confidence_questions"] = []
    data["metadata_quality"]["warning_questions"] = []
    data["questions"] = [
        {
            "id": 21,
            "total_score": 14,
            "question_type": "short_answer",
            "difficulty": {
                "final_difficulty": 9.2,
                "difficulty_label": "hard",
                "features": {"_feature_status": "ok"},
                "confidence": 0.97,
            },
            "quality_score": 5,
            "metadata_confidence": 0.97,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "primer design", "score_share": 0.5, "difficulty_estimate": 8.0},
                    {"label": "orientation inference", "score_share": 0.5, "difficulty_estimate": 8.5},
                ],
                "diagnostic_units": [],
            },
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert row["risk_level"] == "low"
    assert row["needs_priority_review"] is False
    assert model["executive_summary"]["evidence_scale"]["reviewed_risk_items"] == 0
    assert "\u590d\u6838" not in row["action"]


def test_report_model_applies_choice_decision_trap_burden_from_dus():
    data = sample_report_data()
    data["questions"] = [
        {
            "id": 7,
            "total_score": 2,
            "question_type": "single_choice",
            "difficulty": {
                "final_difficulty": 4.2,
                "difficulty_label": "medium",
                "features": {"_feature_status": "ok"},
            },
            "quality_score": 5,
            "metadata_confidence": 1.0,
            "metadata_warnings": [],
            "fine_grained_units": {
                "scoring_units": [
                    {"label": "concept boundary", "score_share": 0.25, "difficulty_estimate": 4.0},
                    {"label": "option contrast", "score_share": 0.25, "difficulty_estimate": 4.2},
                    {"label": "method purpose", "score_share": 0.25, "difficulty_estimate": 4.0},
                    {"label": "result judgement", "score_share": 0.25, "difficulty_estimate": 4.3},
                ],
                "diagnostic_units": [
                    {"trap_strength": 2},
                    {"trap_strength": 2},
                    {"trap_strength": 2},
                    {"trap_strength": 2},
                ],
            },
        }
    ]

    model = build_report_product_model(data, {"recommendations": []})
    row = model["question_portfolio"]["rows"][0]

    assert row["difficulty"] >= 5.0


def _source_audit_report_data():
    return {
        "exam_info": {"name": "source audit", "total_questions": 2, "total_score": 26},
        "metrics": {"avg_difficulty": 8.8},
        "difficulty_gradient": {"gradient_type": "后段压力集中"},
        "knowledge": {"top_points": []},
        "competency": {},
        "metadata_quality": {
            "llm_call_counts": {"question_analysis": 2, "feature_extraction": 2, "competency_analysis": 1},
            "missing_purpose_questions": [{"id": 17, "purpose": "competency_analysis"}],
            "question_text_missing_count": 1,
            "answer_missing_count": 1,
        },
        "questions": [
            {
                "id": 17,
                "total_score": 12,
                "question_type": "short_answer",
                "difficulty": 8.6,
                "_difficulty_authoritative": True,
                "difficulty_flags": ["big_question_fallback"],
                "difficulty_source": "pipeline.final",
                "quality_score": 5,
                "metadata_confidence": 0.88,
                "metadata_warnings": [],
                "metadata_call_purposes": ["question_analysis", "feature_extraction"],
                "fine_grained_units": {
                    "scoring_units": [
                        {
                            "seu_id": "Q17-SEU1",
                            "label": "遗传推理证据解释",
                            "score_share": 1.0,
                            "allocation_source": "inferred",
                            "allocation_confidence": 0.56,
                            "knowledge_links": [{"knowledge_point": "遗传推理", "share": 1.0}],
                            "competency_weights": {"科学思维": 1.0},
                            "difficulty_estimate": 8.8,
                        }
                    ],
                    "diagnostic_units": [],
                    "stimulus_units": [],
                },
            },
            {
                "id": 21,
                "total_score": 14,
                "question_type": "short_answer",
                "difficulty": 9.4,
                "_difficulty_authoritative": True,
                "difficulty_flags": [],
                "difficulty_source": "pipeline.final",
                "question_text": "第21题题干",
                "answer": "第21题答案",
                "quality_score": 5,
                "metadata_confidence": 0.92,
                "metadata_warnings": [],
                "metadata_call_purposes": ["question_analysis", "feature_extraction", "competency_analysis"],
                "fine_grained_units": {
                    "scoring_units": [
                        {
                            "seu_id": "Q21-SEU1",
                            "label": "实验方案评价",
                            "score_share": 1.0,
                            "allocation_source": "rubric",
                            "allocation_confidence": 0.9,
                            "knowledge_links": [{"knowledge_point": "实验设计", "share": 1.0}],
                            "competency_weights": {"科学探究": 1.0},
                            "difficulty_estimate": 9.4,
                        }
                    ],
                    "diagnostic_units": [],
                    "stimulus_units": [],
                },
            },
        ],
    }


def test_product_model_exposes_evidence_integrity_audit_for_fallbacks_and_inference():
    model = build_report_product_model(_source_audit_report_data(), {"recommendations": []})
    audit = model["evidence_integrity"]

    assert audit["difficulty_fallback_questions"] == [17]
    assert audit["question_text_missing_count"] == 1
    assert audit["answer_missing_count"] == 1
    assert audit["source_counts"]["seu_allocation"]["inferred"] == 1
    assert audit["source_counts"]["competency_subtype"]["rule_inferred"] >= 1
    assert {"id": 17, "purpose": "competency_analysis"} in audit["missing_purpose_questions"]
    assert any("回退" in item["title"] for item in audit["items"])
    assert model["methodology"]["evidence_integrity"]["difficulty_fallback_questions"] == [17]


def test_product_model_exposes_knowledge_mapping_gaps_with_detail():
    data = _source_audit_report_data()
    data["knowledge"] = {
        "top_points": [],
        "unmapped_count": 2,
        "total_knowledge_points": 10,
        "unmapped_points": [
            {"name": "unmapped_a", "weighted_score": 3.5, "occurrences": 2},
            {"name": "unmapped_b", "weighted_score": 1.0, "occurrences": 1},
        ],
        "non_textbook_count": 1,
        "non_textbook_points": [
            {"name": "实验设计与变量控制", "weighted_score": 2.0, "occurrences": 1},
        ],
    }

    model = build_report_product_model(data, {"recommendations": []})
    audit = model["evidence_integrity"]

    assert audit["knowledge_unmapped_count"] == 2
    assert audit["knowledge_total_count"] == 10
    assert audit["knowledge_unmapped_points"][0]["name"] == "unmapped_a"
    assert audit["knowledge_non_textbook_count"] == 1
    assert audit["knowledge_non_textbook_points"][0]["name"] == "实验设计与变量控制"
    assert any(item.get("id") == "knowledge_mapping_gap" for item in audit["items"])
    assert any(item.get("id") == "knowledge_non_textbook_scope" for item in audit["items"])


def test_domain_terms_infer_specific_sub_competency_instead_of_default():
    cases = [
        (
            {"label": "推导可育花粉基因型与分离比", "reasoning_brief": ""},
            {},
            "\u751f\u547d\u89c2\u5ff5",
            "\u9057\u4f20\u4e0e\u4fe1\u606f\u89c2",
        ),
        (
            {"label": "计算PCR产物大小并预测电泳条带", "reasoning_brief": ""},
            {},
            "\u79d1\u5b66\u601d\u7ef4",
            "\u6570\u636e\u5206\u6790",
        ),
        (
            {"label": "设计PCR引物并鉴定扩增结果", "reasoning_brief": ""},
            {},
            "\u79d1\u5b66\u63a2\u7a76",
            "\u5b9e\u9a8c\u8bbe\u8ba1",
        ),
        (
            {"label": "人工浮床治理重金属污染", "reasoning_brief": ""},
            {},
            "\u793e\u4f1a\u8d23\u4efb",
            "\u751f\u6001\u73af\u4fdd",
        ),
    ]

    for unit, question, competency, expected_sub in cases:
        sub_competency, source = _infer_sub_competency(unit, question, competency, "")
        assert sub_competency == expected_sub
        assert source == "rule_inferred"


def _deep_dive_ranking_report_data():
    questions = []
    for qid, difficulty in [
        (1, 4.2),
        (2, 4.6),
        (3, 5.0),
        (16, 9.0),
        (17, 8.7),
        (18, 8.8),
        (19, 8.4),
        (20, 9.5),
        (21, 9.6),
    ]:
        question = {
            "id": qid,
            "total_score": 2 if qid <= 16 else 12,
            "question_type": "single_choice" if qid <= 16 else "short_answer",
            "difficulty": difficulty,
            "_difficulty_authoritative": True,
            "difficulty_flags": ["big_question_fallback"] if qid >= 17 else [],
            "quality_score": 5,
            "metadata_confidence": 0.95,
            "metadata_warnings": [],
            "metadata_call_purposes": ["question_analysis", "feature_extraction", "competency_analysis"],
        }
        if qid == 1:
            question["quality_score"] = 1
            question["quality_scientific"] = "科学性表述需要复核"
        if qid in {16, 17, 18, 19, 20, 21}:
            question["fine_grained_units"] = {
                "scoring_units": [
                    {
                        "label": "高阶推理",
                        "score_share": 1.0,
                        "allocation_source": "inferred" if qid >= 17 else "rubric",
                        "allocation_confidence": 0.7,
                        "competency_weights": {"科学思维": 1.0},
                        "difficulty_estimate": difficulty,
                    }
                ],
                "diagnostic_units": [{"trap_strength": 3, "misconception": "关键条件误读"}],
                "stimulus_units": [],
            }
        questions.append(question)
    return {
        "exam_info": {"name": "ranking", "total_questions": len(questions), "total_score": 100},
        "metrics": {"avg_difficulty": 7.5},
        "difficulty_gradient": {"gradient_type": "后段压力集中"},
        "knowledge": {"top_points": []},
        "competency": {},
        "metadata_quality": {"llm_call_counts": {}},
        "questions": questions,
    }


def test_deep_dives_prioritize_high_difficulty_fallback_questions_over_low_difficulty_risk():
    model = build_report_product_model(_deep_dive_ranking_report_data(), {"recommendations": []})
    first_six = [item["question_id"] for item in model["deep_dives"][:6]]

    assert set([16, 17, 18, 19, 20, 21]).issubset(first_six)
    assert 1 not in first_six
    by_id = {item["question_id"]: item for item in model["deep_dives"]}
    assert by_id[20]["evidence_integrity"]["difficulty_flags"] == ["big_question_fallback"]
    assert by_id[21]["evidence_integrity"]["source_excerpt_status"] == "missing"


def test_deep_dives_preserve_source_excerpt_with_markdown_table_for_review():
    data = sample_report_data_with_full_units()
    data["questions"][1]["content"] = (
        "Q7 experiment stem\n"
        "| group | treatment | result |\n"
        "| --- | --- | --- |\n"
        "| A | light | high |\n"
        "| B | dark | low |"
    )

    model = build_report_product_model(data, {"recommendations": []})

    dive = next(item for item in model["deep_dives"] if item["question_id"] == 7)
    assert dive["source_excerpt"]["status"] == "available"
    assert "| group | treatment | result |" in dive["source_excerpt"]["question_text"]
    assert dive["evidence_integrity"]["source_excerpt_status"] == "available"


def test_source_excerpt_marks_truncation_when_answer_is_cut():
    data = sample_report_data_with_full_units()
    data["questions"][1]["question_text"] = "Q7 stem"
    data["questions"][1]["answer"] = "A" * 1300

    model = build_report_product_model(data, {"recommendations": []})

    dive = next(item for item in model["deep_dives"] if item["question_id"] == 7)
    assert len(dive["source_excerpt"]["answer"]) == 1200
    assert dive["source_excerpt"]["truncated"] is True
