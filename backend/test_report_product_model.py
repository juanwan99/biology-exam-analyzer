from report_product_model import build_report_product_model
from report_commercial_narrative import metadata_status
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
    assert rows[19]["risk_level"] == "medium"
    assert rows[19]["quality_level"] == "需复核"
    assert "题面结构需复核" in rows[19]["primary_issue"]
    assert "编号重复" in rows[19]["primary_issue"]
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


def test_blocked_question_failure_reason_is_teacher_readable():
    data = sample_report_data()
    data["exam_info"]["total_questions"] = 1
    data["exam_info"]["total_score"] = 14
    data["metadata_quality"] = {
        "blocked_questions": [{"id": 21, "reason": "insufficient_stem"}],
        "evidence_gap_questions": [{"id": 21, "reason": "stimulus_units_blank"}],
        "warning_questions": [
            {
                "id": 21,
                "warnings": [
                    "analysis_failed:insufficient_stem",
                    "difficulty_blocked:big_question_structure_failed",
                    "llm_parse_failure:big_question_feature_extraction",
                ],
            }
        ],
        "llm_call_counts": {"question_analysis": 1, "big_question_feature_extraction": 1},
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
                "flags": ["big_question_structure_failed", "insufficient_stem"],
                "features": {"_feature_status": "failed"},
            },
            "quality_score": None,
            "metadata_confidence": 0.0,
            "metadata_warnings": [
                "analysis_failed:insufficient_stem",
                "difficulty_blocked:big_question_structure_failed",
                "llm_parse_failure:big_question_feature_extraction",
            ],
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    explanations = model["evidence_integrity"]["failure_explanations"]
    q21 = [item for item in explanations if item["question_id"] == 21]

    assert q21
    assert any(item["stage"] == "题面完整性检查" for item in q21)
    assert any(item["title"] == "题面不完整" for item in q21)
    assert any("未识别到（1）问" in item["reason"] for item in q21)
    assert any("不纳入逐题难度排名" in item["impact"] for item in q21)
    assert any("核对原始试卷" in item["action"] for item in q21)

    dive = model["deep_dives"][0]
    trace_items = dive["evidence_integrity"]["failure_explanations"]
    assert any(item["title"] == "题面不完整" for item in trace_items)
    assert any("失败阶段" in item["display"] for item in trace_items)


def test_points_sum_mismatch_is_teacher_readable():
    data = sample_report_data()
    data["exam_info"]["total_questions"] = 1
    data["exam_info"]["total_score"] = 12
    data["metadata_quality"] = {
        "blocked_questions": [{"id": 18, "reason": "points_sum_mismatch"}],
        "warning_questions": [
            {
                "id": 18,
                "warnings": [
                    "analysis_failed:points_sum_mismatch",
                    "difficulty_blocked:big_question_structure_failed",
                ],
            }
        ],
    }
    data["questions"] = [
        {
            "id": 18,
            "total_score": 12,
            "question_type": "short_answer",
            "content": "18.（12分）遗传大题。（1）判断。（2）分析。",
            "difficulty": {
                "final_difficulty": None,
                "analysis_failed": True,
                "failure_reason": "points_sum_mismatch",
                "flags": ["big_question_structure_failed", "points_sum_mismatch"],
                "features": {"_feature_status": "failed", "errors": ["points_sum=8, total_score=12"]},
            },
            "quality_score": None,
            "metadata_confidence": 0.0,
            "metadata_warnings": ["analysis_failed:points_sum_mismatch"],
        },
    ]

    model = build_report_product_model(data, {"recommendations": []})
    explanations = model["evidence_integrity"]["failure_explanations"]

    assert any(item["code"] == "points_sum_mismatch" for item in explanations)
    assert any(item["title"] == "小问分值不闭合" for item in explanations)
    assert any("分值合计与题目总分不一致" in item["reason"] for item in explanations)
    assert not any(item["title"] == "未归类的数据异常" for item in explanations)


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


def test_question_portfolio_uses_pipeline_final_difficulty_as_authority():
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

    assert row["difficulty"] == 9.4
    assert row["difficulty_display"] == "9.4"


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
