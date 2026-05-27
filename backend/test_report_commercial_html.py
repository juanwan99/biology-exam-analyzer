from report_product_html import render_report_product_html, render_report_product_pdf_html
from report_product_model import build_report_product_model
from test_report_commercial_model import sample_report_data, sample_report_data_with_full_units


def _commercial_model():
    return {
        "cover": {
            "title": "AI 审题与审卷质量诊断报告",
            "exam_name": "一模生物试卷",
            "subject": "biology",
            "generated_at": "2026-05-16T21:30:00",
            "report_version": "commercial_report.v1",
        },
        "credibility": {
            "analysis_scope": {"questions": 2, "total_score": 20},
            "metadata_status": "warning",
            "llm_calls_total": 6,
            "method_note": "基于题目元数据、结构化分析和规则化证据链生成。",
        },
        "executive_summary": {
            "lead_judgment": "整卷难度可控，但高风险题需要优先复核。",
            "overall_verdict": {
                "label": "建议修改后使用",
                "stance": "watch",
                "teacher_takeaway": "本卷整体结构可用，但第 1 题需要先复核科学性和设问边界。",
            },
            "teacher_priorities": [
                {
                    "title": "优先复核题",
                    "summary": "建议先复核第 1 题的科学性、设问边界和评分标准。",
                },
                {
                    "title": "优先讲评点",
                    "summary": "讲评重点放在信息提取和干扰项辨析，避免只讲答案。",
                },
                {
                    "title": "使用建议",
                    "summary": "适合作为阶段诊断卷；普通班建议拆解讲评后使用。",
                },
            ],
            "student_fit": {
                "fit_level": "基本适配",
                "teacher_note": "整体适配高三学生，但高压力题需要配套讲评。",
            },
            "evidence_scale": {
                "questions": 2,
                "scoring_units": 3,
                "diagnostic_units": 2,
                "reviewed_risk_items": 1,
            },
            "big_calls": [
                {
                    "id": "quality_risk",
                    "title": "1 道题进入高风险复核清单",
                    "stance": "risk",
                    "why_it_matters": "高风险题会直接影响整卷科学性和评分稳定性。",
                    "evidence_refs": ["question:1", "metadata:warning_questions"],
                    "recommended_action": "先复核 Q1 的科学性与元数据完整性。",
                }
            ],
        },
        "at_a_glance": [
            {
                "metric": "平均难度",
                "value": "6.2",
                "interpretation": "难度处于中高区间。",
                "evidence_ref": "metric:avg_difficulty",
            }
        ],
        "chapters": [
            {
                "id": "exam_structure",
                "title": "试卷可用性与学情适配",
                "thesis": "难度梯度显示后段压力集中，需要判断是否适合当前学生整卷使用。",
                "figures": [
                    {
                        "id": "difficulty_gradient",
                        "title": "难度梯度决定是否适合整卷使用",
                        "takeaway": "后段题组承压更高。",
                        "data": {"gradient_type": "前易后难", "avg_difficulty": 6.2},
                        "source": "report_data.difficulty_gradient",
                        "notes": "基于结构化 difficulty_gradient 字段。",
                    }
                ],
                "implications": ["复核末段题组的分值和难度匹配。"],
            }
        ],
        "question_portfolio": {
            "thesis": "高风险题目集中在科学性与元数据不确定性。",
            "rows": [
                {
                    "question_id": 1,
                    "risk_level": "high",
                    "quality_level": "硬伤",
                    "difficulty": 7.1,
                    "score": 6,
                    "metadata_confidence": 0.66,
                    "primary_issue": "科学性表述存在明显问题",
                    "action": "进入命题复核清单。",
                    "evidence_refs": ["question:1.quality", "question:1.metadata"],
                }
            ],
        },
        "deep_dives": [
            {
                "question_id": 1,
                "headline": "Q1 的科学性风险需要先处理",
                "diagnosis": "题干边界不清，可能造成评分分歧。",
                "seu_breakdown": [{"label": "判断光反应场所", "score_share": 1.0}],
                "du_diagnostics": [{"option": "A", "misconception": "混淆场所"}],
                "revision_plan": ["重写设问边界。", "复核标准答案。"],
                "metadata_trace": {
                    "purposes": ["question_analysis", "feature_extraction"],
                    "confidence": 0.66,
                    "warnings": ["缺少局部图像锚点"],
                },
            }
        ],
        "methodology": {
            "llm_call_summary": {
                "total": 6,
                "purpose_counts": {"question_analysis": 2, "feature_extraction": 2},
            },
            "prompt_inventory": [
                {
                    "purpose": "question_analysis",
                    "prompt": "分析题目质量、难度、知识点、核心素养与元数据置信度。",
                    "parsed_fields": ["quality_score", "difficulty", "knowledge_points"],
                    "records": 2,
                }
            ],
            "parsed_fields": ["quality_score", "difficulty", "metadata_confidence"],
            "quality_gates": ["metadata envelope required"],
            "limitations": ["本报告不替代人工终审。"],
        },
    }


def test_render_commercial_report_has_consulting_report_structure():
    html = render_report_product_html(_commercial_model())

    assert '<nav class="top-nav" aria-label="报告导航">' in html
    assert 'id="hero"' in html
    assert "AI 审题与审卷质量诊断报告" in html
    assert "执行摘要" in html
    assert "一页速览" in html
    assert "试卷可用性与学情适配" in html
    assert "题目组合诊断" in html
    assert "单题审查明细" in html
    assert "LLM 调用与方法论" in html


def test_hero_exam_name_can_wrap_long_file_names_on_mobile():
    html = render_report_product_html(_commercial_model())
    exam_name_rule = html.split(".exam-name {", 1)[1].split("}", 1)[0]

    assert "max-width: 100%;" in exam_name_rule
    assert "overflow-wrap: anywhere;" in exam_name_rule
    assert "word-break: break-word;" in exam_name_rule


def test_integrity_trace_wraps_long_internal_markers():
    html = render_report_product_html(_commercial_model())
    trace_rule = html.split(".integrity-trace {", 1)[1].split("}", 1)[0]
    trace_li_rule = html.split(".integrity-trace li {", 1)[1].split("}", 1)[0]

    assert "overflow-wrap: anywhere;" in trace_rule
    assert "word-break: break-word;" in trace_rule
    assert "overflow-wrap: anywhere;" in trace_li_rule
    assert "word-break: break-word;" in trace_li_rule


def test_chapter_number_column_has_room_for_icon_and_number():
    html = render_report_product_html(_commercial_model())
    chapter_rule = html.split(".chapter {", 1)[1].split("}", 1)[0]

    assert "grid-template-columns: 96px 1fr;" in chapter_rule


def test_executive_summary_reads_like_teacher_review_report():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "总体使用建议" in visible_html
    assert "优先复核题" in visible_html
    assert "优先讲评点" in visible_html
    assert "使用建议" in visible_html
    assert "证据规模" in visible_html
    assert "学情适配" in visible_html
    assert "评分证据 1" not in visible_html
    assert "第 1 题：评分证据" not in visible_html
    assert "SEU/DU" not in visible_html
    assert "SEU 证据" not in visible_html
    assert "DU 诊断" not in visible_html
    assert "SU 情境" not in visible_html


def test_report_branding_uses_teacher_review_positioning_consistently():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "AI 审题与审卷质量诊断报告" in visible_html
    assert "审题与审卷质量诊断" in visible_html
    assert "试卷质量智能报告" not in visible_html
    assert "专业试卷质量诊断" not in visible_html


def test_executive_summary_does_not_render_pseudo_clickable_evidence_chips():
    html = render_report_product_html(_commercial_model())
    summary = html.split('id="summary"', 1)[1].split('id="glance"', 1)[0]

    assert 'class="evidence-chip"' not in summary
    assert "覆盖题目" in summary
    assert "采分点" in summary
    assert "误区诊断点" in summary


def test_portfolio_evidence_renders_as_plain_text_not_pseudo_buttons():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]
    portfolio = visible_html.split('id="portfolio"', 1)[1].split('id="deep-dives"', 1)[0]

    assert 'class="evidence-chip"' not in portfolio
    assert "证据：" in portfolio
    assert "第 1 题：质量" not in portfolio


def test_render_commercial_report_surfaces_sources_and_evidence():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "来源：报告数据：逐题难度" in visible_html
    assert "指标：平均难度" in visible_html
    assert "证据：" in visible_html
    assert "元数据置信度：0.66" in visible_html
    assert "purpose_counts" in html
    assert '<script id="productData" type="application/json">' in html
    assert "commercial_report.v1" in html
    assert "商业报告 v1" not in visible_html


def test_render_commercial_report_has_no_mojibake_fragments():
    html = render_report_product_html(_commercial_model())

    mojibake_fragments = [
        "鏈",
        "绋",
        "鐢",
        "闅",
        "歿",
        "銆",
        "寰",
        "鍏冩",
        "棰",
        "璇",
    ]
    assert not [fragment for fragment in mojibake_fragments if fragment in html]


def test_render_commercial_report_uses_icon_system_across_sections():
    html = render_report_product_html(_commercial_model())

    assert html.count('class="report-icon ') >= 12
    assert 'icon-executive' in html
    assert 'icon-glance' in html
    assert 'icon-figure' in html
    assert 'icon-risk-high' in html
    assert 'icon-methodology' in html


def test_render_commercial_report_uses_chinese_visible_labels():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]

    forbidden_visible_labels = [
        "Commercial Exam Quality Report",
        "Exam Intelligence",
        "At a Glance",
        "Action",
        "Source:",
        "Implications",
        "LLM call summary",
        "Parsed fields",
        "Quality gates",
        "Limitations",
        "<th>purpose</th>",
        "<th>records</th>",
        "<th>parsed fields</th>",
        "<th>prompt</th>",
        ">Exhibit<",
        ">Evidence<",
        "Portfolio Exhibit",
        "Methodology Exhibit",
    ]
    assert not [label for label in forbidden_visible_labels if label in visible_html]


def test_render_commercial_report_contains_advanced_svg_charts():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert html.count('class="report-chart ') >= 10
    for chart_id in [
        "chart-difficulty-gradient",
        "chart-bloom-distribution",
        "chart-knowledge-top-points",
        "chart-competency-distribution",
        "chart-question-risk-distribution",
        "chart-metadata-quality",
        "chart-fine-grained-heatmap",
        "chart-seu-competency-matrix",
        "chart-du-trap-map",
        "chart-question-portfolio",
        "chart-methodology-llm",
    ]:
        assert chart_id in html
    assert "采分点与误区诊断矩阵" in html
    assert "题目组合气泡图" in html
    assert "LLM 调用结构图" in html


def test_portfolio_bubble_labels_all_points_and_exposes_data_gaps():
    from report_product_charts import render_portfolio_bubble

    html = render_portfolio_bubble(
        [
            {"question_id": 1, "risk_level": "low", "difficulty": 4.2, "score": 2, "pressure_index": 35},
            {"question_id": 19, "risk_level": "medium", "difficulty": 9.8, "score": 12, "pressure_index": 55},
            {"question_id": 20, "risk_level": "medium", "difficulty": 9.7, "score": 12, "pressure_index": 54},
            {"question_id": 21, "risk_level": "data_gap", "difficulty": None, "score": 14, "pressure_index": 0},
        ]
    )

    assert html.count('data-role="bubble-label"') == 3
    assert ">1</text>" in html
    assert ">19</text>" in html
    assert ">20</text>" in html
    assert 'data-role="data-gap-panel"' in html
    assert 'data-role="data-gap-label"' in html
    assert 'data-role="data-gap-legend"' in html
    assert "Q21" in html
    assert "数据阻断" in html


def test_portfolio_table_allocates_width_to_teacher_text_columns():
    html = render_report_product_html(_commercial_model())

    assert ".portfolio-table th:nth-child(7), .portfolio-table td:nth-child(7) { width: 36%; }" in html
    assert ".portfolio-table th:nth-child(8), .portfolio-table td:nth-child(8) { width: 18%; }" in html
    assert ".portfolio-table th:nth-child(-n + 6)," in html
    assert ".portfolio-table td:nth-child(7) .evidence-links" in html
    assert ".portfolio-table th:nth-child(n),\n  .portfolio-table td:nth-child(n) {\n    width: 100%;" in html


def test_report_visual_system_uses_consulting_palette_and_exhibit_surfaces():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert "--bain-red: #cc0000" in html
    assert "--bain-red-2: #cc2027" in html
    assert "--bain-gray-300: #d2d3d1" in html
    assert "--bain-gray-700: #777877" in html
    assert "--paper: #ffffff" in html
    assert "background: #cc0000" in html
    assert "--oxblood:" not in html
    assert "--sage:" not in html
    assert "class=\"exhibit-label\"" in html
    assert "class=\"chart-kicker\"" in html
    assert "filter=\"url(#" in html


def test_bain_style_charts_include_exhibit_analysis_primitives():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert 'data-style="bain-exhibit"' in html
    assert html.count('data-role="benchmark-line"') >= 6
    assert html.count('data-role="highlight"') >= 8
    assert html.count('data-role="callout"') >= 8
    assert html.count('data-role="chart-note"') >= 10
    assert html.count('data-role="baseline"') >= 2
    assert html.count('fill="#cc0000"') >= 5
    assert html.count('fill="#d2d3d1"') >= 5
    assert "阈值" in html


def test_du_trap_chart_aggregates_by_question_to_avoid_identical_trap_rows():
    from report_product_charts import render_du_trap_map

    html = render_du_trap_map([
        {"question_id": 1, "option_or_trap": "A", "trap_strength": 3, "misconception": "概念混淆"},
        {"question_id": 1, "option_or_trap": "B", "trap_strength": 3, "misconception": "条件遗漏"},
        {"question_id": 20, "option_or_trap": "trap_1", "trap_strength": 2, "misconception": "变量控制不足"},
        {"question_id": 20, "option_or_trap": "trap_2", "trap_strength": 2, "misconception": "图表信息误读"},
        {"question_id": 20, "option_or_trap": "trap_3", "trap_strength": 1, "misconception": "表达不完整"},
    ])

    assert "学生误区负荷图" in html
    assert "Q1" in html
    assert "Q20" in html
    assert "误区 2 个" in html
    assert "误区 3 个" in html
    assert "负荷 " in html
    assert "均强 " in html
    assert html.count("Q1 A") == 0
    assert 'x="618"' not in html
    assert "文字第二行列出误区数" in html
    assert "chart-du-trap-mobile-list" in html
    assert "学生误区负荷图移动端列表" in html


def test_truncated_chart_figures_offer_expandable_full_details():
    model = build_report_product_model(sample_report_data_with_full_units(), {"recommendations": []})
    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    assert visible_html.count("<summary>展开完整明细</summary>") >= 3
    assert 'class="figure-details"' in visible_html
    assert "完整误区诊断点" in visible_html
    assert "完整采分点明细" in visible_html
    assert "完整知识点明细" in visible_html
    assert "误区卡点 a" in visible_html
    assert "K-inheritance" in visible_html
    assert "experiment explanation" in visible_html


def test_charts_surface_deeper_analysis_fields():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert "压力指数" in html
    assert "主导压力" in html
    assert "证据密度" in html
    assert "元数据缺口" in html
    assert "题数" in html


def test_rendered_executive_findings_have_no_empty_none_copy():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert "<p>None</p>" not in html
    assert ">None<" not in html


def test_web_charts_scale_inside_mobile_viewport():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert ".report-chart {\n  display: block;\n  width: 100%;" in html
    assert "overflow-x: auto;" in html
    assert "overflow-x: visible;" in html
    assert ".chart-du-trap-map {\n    display: none;" in html
    assert ".chart-du-trap-mobile-list {\n    display: grid;" in html
    assert ".chart-difficulty-gradient {\n    display: none;" in html
    assert "chart-difficulty-mobile-list" in html
    assert "逐题难度移动端重点列表" in html
    assert "min-width: 560px;" not in html
    assert "min-width: 720px;" not in html
    assert ".wide-chart-frame .report-chart,\n  .wide-figure .chart-frame .report-chart" in html
    assert ".report-section, .report-figure, .chapter, .portfolio-section, .deep-section" in html


def test_visible_evidence_labels_hide_internal_reference_ids():
    model = build_report_product_model(sample_report_data_with_full_units(), {"recommendations": []})
    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "seu:" not in visible_html
    assert "question:Q" not in visible_html
    assert "metadata:Q" not in visible_html
    assert "fine grained exhibits" not in visible_html
    assert "weighted score" not in visible_html
    assert "purpose_counts" not in visible_html
    assert "采分点 a" in visible_html
    assert "误区卡点 a" in visible_html
    assert "元数据置信度" in visible_html


def test_deep_dives_render_evidence_cards_instead_of_raw_unit_tables():
    model = build_report_product_model(sample_report_data_with_full_units(), {"recommendations": []})
    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    assert 'class="evidence-unit-grid"' in visible_html
    assert 'class="evidence-unit-card"' in visible_html
    assert 'class="du-unit-card"' in visible_html
    assert "<th>competency weights</th>" not in visible_html
    assert "<th>knowledge links</th>" not in visible_html
    assert "知识点权重" in visible_html
    assert "素养权重" in visible_html


def test_deep_dives_render_source_excerpt_markdown_table_as_visible_table():
    data = sample_report_data_with_full_units()
    data["questions"][1]["content"] = (
        "Q7 experiment stem\n"
        "| group | treatment | result |\n"
        "| --- | --- | --- |\n"
        "| A | light | high |\n"
        "| B | dark | low |"
    )
    model = build_report_product_model(data, {"recommendations": []})

    html = render_report_product_html(model)

    assert 'class="source-evidence"' in html
    assert 'class="source-table"' in html
    assert "<td>A</td>" in html
    assert "<td>light</td>" in html


def test_report_surfaces_evidence_integrity_audit_in_visible_html():
    model = _commercial_model()
    model["evidence_integrity"] = {
        "difficulty_fallback_questions": [17, 18, 19, 20, 21],
        "question_text_missing_count": 21,
        "answer_missing_count": 21,
        "missing_purpose_questions": [{"id": 12, "purpose": "competency_analysis"}],
        "source_counts": {
            "seu_allocation": {"inferred": 65, "rubric": 6},
            "competency_subtype": {"rule_inferred": 119, "fallback": 47},
        },
        "items": [
            {
                "title": "大题结构化回退",
                "value": "5题",
                "detail": "Q17, Q18, Q19, Q20, Q21",
                "severity": "warning",
            },
            {
                "title": "原题/答案摘录缺失",
                "value": "21 / 21",
                "detail": "需回看原卷确认",
                "severity": "warning",
            },
            {
                "title": "二级素养规则推断",
                "value": "119条",
                "detail": "非直接标注，仅作分布参考",
                "severity": "info",
            },
            {
                "title": "Report generation failure",
                "value": "report_teaching_suggestions",
                "detail": "teaching suggestion timeout",
                "severity": "warning",
            },
        ],
    }
    model["methodology"]["evidence_integrity"] = model["evidence_integrity"]

    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "证据完整性提示" in visible_html
    assert "大题结构化回退" in visible_html
    assert "规则推断" in visible_html
    assert "原题/答案摘录缺失" in visible_html
    assert "Report generation failure" in visible_html
    assert "teaching suggestion timeout" in visible_html
    assert "Q12" in visible_html


def test_deep_dive_empty_units_render_as_data_failures_not_normal_absence():
    model = _commercial_model()
    model["deep_dives"] = [
        {
            "question_id": 21,
            "headline": "Q21 数据不足",
            "diagnosis": "结构化证据缺失。",
            "seu_breakdown": [],
            "du_diagnostics": [],
            "su_context": [
                {"su_id": "21-S1", "stimulus_type": "text", "description": "", "complexity": 1, "is_core": False}
            ],
            "revision_plan": ["重新分析后再定稿。"],
            "metadata_trace": {"purposes": ["question_analysis"], "confidence": 0.0, "warnings": []},
            "evidence_integrity": {
                "difficulty_flags": ["big_question_structure_failed"],
                "difficulty_source": "analysis_failed",
                "difficulty_confidence": 0.0,
            },
        }
    ]

    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "暂无误区诊断" not in visible_html
    assert "用于支撑题目情境和信息加工" not in visible_html
    assert "无元数据告警" not in visible_html
    assert "误区诊断未抽取成功" in visible_html
    assert "材料描述缺失" in visible_html
    assert "证据链异常" in visible_html


def test_deep_dive_adjustment_flags_do_not_render_as_evidence_chain_failure():
    model = _commercial_model()
    model["deep_dives"] = [
        {
            "question_id": 20,
            "headline": "Q20 stable",
            "diagnosis": "No explicit quality issue.",
            "seu_breakdown": [{"seu_id": "seu_1", "label": "reasoning", "score_share": 1.0}],
            "du_diagnostics": [
                {
                    "du_id": "du_1",
                    "option_or_trap": "trap 1",
                    "distractor_type": "calculation_trap",
                    "misconception": "trap",
                    "trap_strength": 3,
                }
            ],
            "su_context": [{"su_id": "su_1", "stimulus_type": "multi", "description": "context"}],
            "revision_plan": ["keep"],
            "metadata_trace": {"purposes": ["question_analysis"], "confidence": 0.97, "warnings": []},
            "evidence_integrity": {
                "difficulty_flags": ["bounded_item_seu_ceiling"],
                "difficulty_source": "rule_scorer",
                "difficulty_confidence": 0.97,
            },
        }
    ]

    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "证据链异常" not in visible_html
    assert "未闭合的数据缺口" not in visible_html
    assert "bounded_item_seu_ceiling" not in visible_html
    assert "rule_scorer" not in visible_html
    assert "calculation_trap" not in visible_html
    assert "trap 1" not in visible_html


def test_web_and_pdf_use_distinct_report_layouts():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    web_html = render_report_product_html(model)
    pdf_html = render_report_product_pdf_html(model)

    assert '<nav class="top-nav" aria-label="报告导航">' in web_html
    assert 'class="pdf-report"' not in web_html
    assert '<main class="pdf-report">' in pdf_html
    assert '<nav class="top-nav"' not in pdf_html
    assert "@page" in pdf_html
    assert pdf_html.count('class="pdf-page ') >= 6
    assert pdf_html.count('class="report-chart ') >= 7
    assert "PDF 专用版式" in pdf_html
    assert "pdf-figure-spread" in pdf_html
    assert ".pdf-figure .chart-mobile-list" in pdf_html
    assert "display: none !important;" in pdf_html


def test_pdf_chart_matrix_uses_explicit_single_chart_pages():
    model = _commercial_model()
    base = model["chapters"][0]["figures"][0]
    model["chapters"][0]["figures"] = [
        {**base, "title": f"chart {index}", "source": f"source:{index}"}
        for index in range(6)
    ]

    pdf_html = render_report_product_pdf_html(model)

    assert 'pdf-grid-3 pdf-figure-matrix' not in pdf_html
    sections = pdf_html.split('<section class="pdf-page pdf-content pdf-core-chart-page"')[1:]
    assert len(sections) == 6
    for section in sections:
        body = section.split("</section>", 1)[0]
        assert "pdf-grid-2 pdf-figure-spread" in body
        assert body.count('<article class="pdf-figure">') == 1


def test_report_frontend_accessibility_and_mobile_contracts():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert '<a class="skip-link" href="#main-content">跳到主要内容</a>' in html
    assert '<nav class="top-nav" aria-label="报告导航">' in html
    assert '<main id="main-content" class="report-main">' in html
    assert "prefers-reduced-motion" in html
    assert ":focus-visible" in html
    assert "@media (max-width: 1024px)" in html
    assert "content: attr(data-label);" in html
    assert 'data-label="题号"' in html
    assert 'data-label="调用目的"' in html
    assert '<caption class="sr-only">题目组合诊断明细</caption>' in html
    assert '<caption class="sr-only">LLM 调用提示词清单</caption>' in html
    assert 'aria-label="题目组合诊断明细"' not in html
    assert ".table-wrap {\n  overflow: visible;" in html
    assert ".table-wrap {\n  overflow-x: auto" not in html


def test_svg_charts_have_specific_accessible_names_and_cjk_font_stack():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert '<title id="difficulty_gradient_title">逐题难度曲线</title>' in html
    assert 'aria-labelledby="difficulty_gradient_title difficulty_gradient_desc"' in html
    assert 'aria-label="报告图表"' not in html
    assert '"Noto Sans CJK SC", "Source Han Sans SC"' in html
    assert 'font-size="20"' in html


def test_report_charts_use_legible_single_column_exhibit_layout():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert ".figure-grid {\n  grid-template-columns: minmax(0, 1fr);" in html
    assert "figcaption { font-size: 22px;" in html
    assert "font-size=\"9\"" not in html
    assert "font-size=\"10\"" not in html
    assert "font-size=\"11\"" not in html
    assert 'viewBox="0 0 780 450"' in html
    assert 'viewBox="0 0 920 ' in html


def test_difficulty_chart_surfaces_per_question_curve():
    from report_product_charts import render_difficulty_gradient

    html = render_difficulty_gradient({
        "front": 4.8,
        "middle": 5.1,
        "back": 6.8,
        "avg_difficulty": 6.25,
        "question_points": [
            {"question_id": qid, "difficulty": difficulty, "score": 2}
            for qid, difficulty in [(1, 4.8), (19, 9.1), (20, 6.9), (21, 8.0)]
        ],
    })

    assert "逐题难度曲线" in html
    assert "Q20" in html
    assert "Q21" in html
    assert "三段均值仅作为背景参考" in html


def test_bloom_chart_uses_analysis_evaluation_creation_as_high_order():
    from report_product_charts import render_bloom_distribution

    html = render_bloom_distribution({
        "理解": 0.049,
        "应用": 0.158,
        "分析": 0.658,
        "评价": 0.005,
        "创造": 0.13,
    })

    assert "高阶合计 79%" in html
    assert "评价 &lt;1%" in html
    assert "口径：高阶=分析/评价/创造" in html


def test_competency_diagnosis_chart_combines_overview_and_subdimension_detail():
    from report_product_charts import render_competency_radar

    html = render_competency_radar({
        "distribution": {
            "生命观念": {"占比": 0.36},
            "科学思维": {"占比": 0.47},
            "科学探究": {"占比": 0.10},
            "社会责任": {"占比": 0.07},
        },
        "detail_rows": [
            {"competency": "科学思维", "sub_competency": "证据推理", "score_contribution": 12.4, "question_ids": [17, 21], "seu_count": 5},
            {"competency": "生命观念", "sub_competency": "稳态与平衡观", "score_contribution": 8.2, "question_ids": [11, 19], "seu_count": 3},
            {"competency": "科学探究", "sub_competency": "实验设计", "score_contribution": 5.0, "question_ids": [14, 19], "seu_count": 4},
        ],
        "gap_rows": [
            {"competency": "社会责任", "status": "低覆盖", "recommendation": "可通过生态治理或生物安全情境补足。"}
        ],
    })

    assert 'viewBox="0 0 720 470"' in html
    assert "核心素养结构诊断" in html
    assert "默认显示覆盖触达，切换查看主负荷" in html
    assert "覆盖触达" in html
    assert "主负荷" in html
    assert 'class="mode-button mode-coverage"' in html
    assert 'class="mode-button mode-load"' in html
    assert '<g class="mode-button mode-coverage" role="button"' not in html
    assert '<g class="mode-button mode-load" role="button"' not in html
    assert 'role="button" tabindex="0" aria-label="切换到覆盖触达"' in html
    assert 'role="button" tabindex="0" aria-label="切换到主负荷"' in html
    assert "默认：覆盖触达" in html
    assert 'onclick="this.ownerSVGElement.setAttribute(\'data-mode\',\'load\')"' in html
    assert 'svg[data-mode="load"] .load-layer' in html
    assert 'class="coverage-layer"' in html
    assert 'class="load-layer"' in html
    assert "同一采分点可同时计入多个素养" in html
    assert "默认：生命观念" in html
    assert 'class="competency-hit hit-life-concept"' in html
    assert 'class="competency-hit hit-scientific-thinking"' in html
    assert 'class="competency-hit hit-scientific-inquiry"' in html
    assert 'class="competency-hit hit-social-responsibility"' in html
    assert ".hit-scientific-thinking:hover ~ .competency-panels .panel-scientific-thinking" in html
    assert ".hit-scientific-thinking:focus ~ .competency-panels .panel-scientific-thinking" in html
    assert 'onmouseenter="this.ownerSVGElement.setAttribute(' in html
    assert 'onclick="this.ownerSVGElement.setAttribute(' in html
    assert 'svg[data-active="scientific-thinking"] .panel-scientific-thinking' in html
    assert 'class="competency-panel panel-life-concept"' in html
    assert 'class="competency-panel panel-scientific-thinking"' in html
    assert "科学思维 47%" in html
    assert "科学探究 2题" in html
    assert "触达 2题 / 4采分点" in html
    assert "主负荷 5分" in html
    assert "证据推理" in html
    assert "2题" in html
    assert "实验设计" in html
    assert "低覆盖：社会责任" in html
    assert 'class="chart-mobile-list chart-competency-mobile-list"' in html
    assert 'class="chart-mobile-card chart-competency-mobile-card"' in html
    assert "核心素养移动端二级聚类列表" in html
    assert 'fill-opacity=".12"' not in html


def test_report_summary_has_visible_overall_conclusion_label():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "总体结论" in visible_html


def test_competency_figure_uses_cluster_summary_not_scoring_unit_detail_table():
    model = build_report_product_model(sample_report_data_with_full_units(), {"recommendations": []})
    html = render_report_product_html(model)
    section = html.split('id="figure-competency-distribution"', 1)[1].split('id="quality_metadata"', 1)[0]

    assert "完整二级素养明细" not in section
    assert 'class="figure-details"' not in section
    assert "默认：覆盖触达" in section
    assert "主负荷" in section
    assert "同一采分点可同时计入多个素养" in section
    assert "默认：生命观念" in section
    assert 'class="competency-panel panel-life-concept"' in section
    assert 'class="competency-panel panel-scientific-thinking"' in section
    assert "证据推理" in section
    assert "实验设计" in section
    assert "采分点级证据见后文单题审查" in section


def test_mobile_styles_hide_competency_svg_and_show_cards_on_narrow_viewports():
    html = render_report_product_html(_commercial_model())

    competency_svg_rule = html.split(".chart-competency-distribution {", 1)[1].split("}", 1)[0]
    competency_card_rule = html.split(".chart-competency-mobile-list {", 1)[1].split("}", 1)[0]

    assert "display: none;" in competency_svg_rule
    assert "display: grid;" in competency_card_rule


def test_pdf_uses_cjk_font_stack_for_report_text():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    pdf_html = render_report_product_pdf_html(model)

    assert 'font-family: "Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "PingFang SC", Arial, sans-serif;' in pdf_html
