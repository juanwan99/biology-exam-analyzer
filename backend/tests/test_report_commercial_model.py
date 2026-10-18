from report_product_model import build_report_product_model


def sample_report_data():
    return {
        "exam_info": {
            "name": "真实高三生物试卷",
            "total_questions": 21,
            "total_score": 100,
            "mode": "deep",
        },
        "metrics": {
            "avg_difficulty": 6.4,
            "avg_cognitive_level": 4.8,
            "bloom_distribution": {"分析": 0.4},
        },
        "difficulty_gradient": {
            "front": 4.2,
            "middle": 6.1,
            "back": 7.8,
            "gradient_type": "前易后难",
        },
        "knowledge": {
            "top_points": [{"name": "遗传", "weighted_score": 18}],
            "unmapped_count": 1,
        },
        "competency": {
            "distribution": {
                "生命观念": {"占比": 0.45},
                "科学思维": {"占比": 0.35},
                "科学探究": {"占比": 0.2},
                "社会责任": {"占比": 0},
            }
        },
        "fine_grained_summary": {
            "total_seus": 44,
            "total_dus": 19,
            "avg_allocation_confidence": 0.86,
        },
        "metadata_quality": {
            "total_questions": 21,
            "missing_envelope_questions": [],
            "low_confidence_questions": [7],
            "warning_questions": [{"id": 7, "warnings": ["feature_status:partial"]}],
            "llm_call_counts": {
                "question_analysis": 21,
                "feature_extraction": 21,
                "competency_analysis": 21,
            },
        },
        "questions": [
            {
                "id": 1,
                "total_score": 6,
                "question_type": "single_choice",
                "difficulty": 4.2,
                "difficulty_label": "中等",
                "quality_score": 5,
                "metadata_confidence": 0.95,
                "metadata_warnings": [],
                "metadata_call_purposes": [
                    "question_analysis",
                    "feature_extraction",
                    "competency_analysis",
                ],
                "knowledge_points": ["光合作用"],
                "primary_competency": "生命观念",
                "seu_knowledge_breakdown": [
                    {"label": "识别光反应场所", "score_share": 1.0}
                ],
                "diagnostic_highlights": [],
            },
            {
                "id": 7,
                "total_score": 12,
                "question_type": "short_answer",
                "difficulty": 7.8,
                "difficulty_label": "困难",
                "quality_score": 2,
                "quality_scientific": "科学性表述存在风险",
                "metadata_confidence": 0.62,
                "metadata_warnings": ["feature_status:partial"],
                "metadata_call_purposes": [
                    "question_analysis",
                    "feature_extraction",
                    "competency_analysis",
                ],
                "knowledge_points": ["遗传"],
                "primary_competency": "科学思维",
                "seu_knowledge_breakdown": [
                    {"label": "推断遗传方式", "score_share": 0.5}
                ],
                "diagnostic_highlights": [
                    {
                        "option": "step_2",
                        "misconception": "混淆显隐性",
                        "trap_strength": 3,
                    }
                ],
            },
        ],
    }


def sample_report_data_with_full_units():
    data = sample_report_data()
    data["fine_grained_summary"] = {"total_seus": 3, "total_dus": 2, "avg_allocation_confidence": 0.87}
    data["questions"][1]["fine_grained_units"] = {
        "scoring_units": [
            {
                "seu_id": "seu_a",
                "label": "inheritance inference",
                "score_share": 0.6,
                "allocation_source": "rubric",
                "allocation_confidence": 0.9,
                "knowledge_links": [
                    {"knowledge_point": "K-inheritance", "share": 0.7},
                    {"knowledge_point": "K-chromosome", "share": 0.3},
                ],
                "competency_weights": {
                    "生命观念": 0.1,
                    "科学思维": 0.7,
                    "科学探究": 0.2,
                    "社会责任": 0.0,
                },
                "bloom_level": 4,
                "difficulty_estimate": 7.1,
                "reasoning_brief": "requires evidence chain",
            },
            {
                "seu_id": "seu_b",
                "label": "experiment explanation",
                "score_share": 0.4,
                "allocation_confidence": 0.84,
                "knowledge_links": [{"knowledge_point": "K-experiment", "share": 1.0}],
                "competency_weights": {"科学探究": 1.0},
                "bloom_level": 5,
                "difficulty_estimate": 7.8,
            },
        ],
        "diagnostic_units": [
            {
                "du_id": "du_a",
                "option_or_trap": "step_2",
                "misconception": "confuses dominance",
                "trap_strength": 3,
                "knowledge_boundary": "dominance/recessive",
            },
            {
                "du_id": "du_b",
                "option_or_trap": "step_3",
                "misconception": "drops control variable",
                "trap_strength": 2,
            },
        ],
        "stimulus_units": [
            {"su_id": "su_a", "stimulus_type": "table", "complexity": 3, "description": "data table"}
        ],
    }
    return data


def test_commercial_report_has_consulting_structure():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

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
    assert model["executive_summary"]["big_calls"]
    assert model["question_portfolio"]["rows"]
    assert model["methodology"]["llm_call_summary"]["purpose_counts"]["question_analysis"] == 21


def test_every_big_call_has_evidence_and_action():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    for call in model["executive_summary"]["big_calls"]:
        assert call["title"]
        assert call["why_it_matters"]
        assert call["evidence_refs"]
        assert call["recommended_action"]


def test_every_figure_has_source_and_takeaway():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    figures = [fig for chapter in model["chapters"] for fig in chapter["figures"]]
    assert figures
    for fig in figures:
        assert fig["title"]
        assert fig["takeaway"]
        assert fig["source"]


def test_question_portfolio_rows_include_metadata_confidence():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    row = next(item for item in model["question_portfolio"]["rows"] if item["question_id"] == 7)
    assert row["risk_level"] == "high"
    assert row["metadata_confidence"] == 0.62
    assert "question:7" in " ".join(row["evidence_refs"])


def test_methodology_exposes_prompt_and_parsed_field_inventory():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    methodology = model["methodology"]
    assert methodology["llm_call_summary"]["purpose_counts"]["question_analysis"] == 21
    assert "quality_score" in methodology["parsed_fields"]
    assert "metadata_confidence" in methodology["parsed_fields"]
    assert "metadata envelope required" in methodology["quality_gates"]
    assert methodology["limitations"]


def test_methodology_explains_llm_calls_dimensions_prompts_and_fields():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    methodology = model["methodology"]
    summary = methodology["llm_call_summary"]
    assert summary["total"] == 63
    assert summary["purpose_counts"]["question_analysis"] == 21

    question_prompt = next(
        item for item in methodology["prompt_inventory"]
        if item["purpose"] == "question_analysis"
    )
    assert question_prompt["records"] == 21
    assert question_prompt["prompt"]
    assert "quality" in question_prompt["analysis_dimensions"]
    assert "difficulty" in question_prompt["analysis_dimensions"]
    assert "metadata_confidence" in question_prompt["parsed_fields"]


def test_model_derives_fine_grained_exhibits_for_deep_analysis():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    exhibits = model["fine_grained_exhibits"]
    assert exhibits["summary"]["total_seus"] >= 2
    assert exhibits["summary"]["total_dus"] >= 1

    seu_row = next(row for row in exhibits["seu_rows"] if row["question_id"] == 7)
    assert seu_row["knowledge_point"] == "遗传"
    assert seu_row["competency"] == "科学思维"
    assert seu_row["weighted_score"] > 0
    assert seu_row["bloom_level"] >= 1

    du_row = next(row for row in exhibits["du_rows"] if row["question_id"] == 7)
    assert du_row["misconception"] == "混淆显隐性"
    assert du_row["trap_strength"] == 3

    factor_row = next(row for row in exhibits["difficulty_factor_rows"] if row["question_id"] == 7)
    assert factor_row["quality_score"] == 2
    assert factor_row["metadata_confidence"] == 0.62
    assert factor_row["risk_level"] == "high"
    assert factor_row["pressure_index"] >= 60
    assert factor_row["dominant_pressure"] in {"难度", "质量", "元数据", "陷阱", "证据密度"}
    assert factor_row["evidence_density"] >= 2

    figure_ids = [fig["id"] for chapter in model["chapters"] for fig in chapter["figures"]]
    assert "fine_grained_heatmap" in figure_ids
    assert "seu_competency_matrix" in figure_ids
    assert "du_trap_map" in figure_ids

    methodology = model["methodology"]
    feature_prompt = next(
        item for item in methodology["prompt_inventory"]
        if item["purpose"] == "feature_extraction"
    )
    assert feature_prompt["records"] == 21
    assert "quality" in feature_prompt["analysis_dimensions"]
    assert "quality_score" in feature_prompt["parsed_fields"]


def test_knowledge_chart_uses_seu_derived_depth_when_top_points_are_sparse():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})

    knowledge_figure = next(
        fig for chapter in model["chapters"] for fig in chapter["figures"]
        if fig["id"] == "knowledge_top_points"
    )

    rows = knowledge_figure["data"]
    labels = {row["name"] for row in rows}
    assert {"遗传", "光合作用"} <= labels
    assert all("weighted_score" in row for row in rows)
    assert all("question_count" in row for row in rows)
    assert all("risk_count" in row for row in rows)
    assert all("avg_bloom" in row for row in rows)


def test_model_prefers_full_fine_grained_units_over_compressed_breakdown():
    model = build_report_product_model(sample_report_data_with_full_units(), {"recommendations": []})

    exhibits = model["fine_grained_exhibits"]
    q7_seus = [row for row in exhibits["seu_rows"] if row["question_id"] == 7]
    assert len(q7_seus) == 2
    assert q7_seus[0]["knowledge_links"][1]["knowledge_point"] == "K-chromosome"
    assert q7_seus[0]["competency_weights"]["科学思维"] == 0.7
    assert q7_seus[0]["difficulty_estimate"] == 7.1
    assert q7_seus[0]["allocation_source"] == "rubric"

    knowledge_rows = [
        row for row in exhibits["knowledge_contribution_rows"]
        if row["question_id"] == 7
    ]
    assert {row["knowledge_point"] for row in knowledge_rows} == {
        "K-inheritance",
        "K-chromosome",
        "K-experiment",
    }
    assert sum(row["score_contribution"] for row in knowledge_rows) == 12.0

    competency_rows = [
        row for row in exhibits["competency_contribution_rows"]
        if row["question_id"] == 7 and row["score_contribution"] > 0
    ]
    assert {row["competency"] for row in competency_rows} >= {"科学思维", "科学探究"}

    audit = next(row for row in exhibits["metadata_audit_rows"] if row["question_id"] == 7)
    assert audit["score_share_valid"] is True
    assert audit["knowledge_share_valid"] is True
    assert audit["competency_weight_valid"] is True
    assert audit["su_count"] == 1


def test_findings_bind_summary_claims_to_local_evidence():
    model = build_report_product_model(sample_report_data_with_full_units(), {"recommendations": []})

    findings = model["findings"]
    assert findings
    assert all(finding["evidence_refs"] for finding in findings)
    assert all(finding["metrics"] for finding in findings)
    assert all(finding["recommended_action"] for finding in findings)

    summary_refs = " ".join(
        ref for call in model["executive_summary"]["big_calls"] for ref in call["evidence_refs"]
    )
    assert "seu:" in summary_refs or "metadata:" in summary_refs

    glance = next(item for item in model["at_a_glance"] if item["metric"] == "采分点 / 误区点")
    assert glance["value"] == "3 / 2"
