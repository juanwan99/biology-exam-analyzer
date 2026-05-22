from report_product_html import render_report_product_html, render_report_product_pdf_html
from report_product_model import build_report_product_model
from test_report_commercial_model import sample_report_data, sample_report_data_with_full_units


def _commercial_model():
    return {
        "cover": {
            "title": "AI 试卷质量诊断报告",
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
                "title": "整卷结构诊断",
                "thesis": "难度梯度显示后段压力集中。",
                "figures": [
                    {
                        "id": "difficulty_gradient",
                        "title": "难度梯度显示后段压力集中",
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
    assert "AI 试卷质量诊断报告" in html
    assert "执行摘要" in html
    assert "一页速览" in html
    assert "整卷结构诊断" in html
    assert "题目组合诊断" in html
    assert "深入诊断" in html
    assert "LLM 调用与方法论" in html


def test_render_commercial_report_surfaces_sources_and_evidence():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "来源：报告数据：难度梯度" in visible_html
    assert "指标：平均难度" in visible_html
    assert "第 1 题：元数据" in visible_html
    assert "元数据置信度：0.66" in visible_html
    assert "purpose_counts" in html
    assert '<script id="productData" type="application/json">' in html
    assert "commercial_report.v1" in html


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
    assert "细粒度证据矩阵" in html
    assert "题目组合气泡图" in html
    assert "LLM 调用结构图" in html


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


def test_web_charts_are_responsive_without_horizontal_scroll_contract():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert ".report-chart {\n  display: block;\n  width: 100%;" in html
    assert "min-width: 520px" not in html
    assert ".wide-chart-frame .report-chart { min-width:" not in html
    assert "overflow-x: auto;" not in html


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
    assert "第 7 题：评分证据" in visible_html
    assert "第 7 题：元数据审计" in visible_html


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
    assert "overflow-x: auto;" not in html


def test_svg_charts_have_specific_accessible_names_and_cjk_font_stack():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    html = render_report_product_html(model)

    assert '<title id="difficulty_gradient_title">难度梯度坡度图</title>' in html
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
    assert 'viewBox="0 0 720 340"' in html
    assert 'viewBox="0 0 920 ' in html


def test_pdf_uses_cjk_font_stack_for_report_text():
    model = build_report_product_model(sample_report_data(), {"recommendations": []})
    pdf_html = render_report_product_pdf_html(model)

    assert 'font-family: "Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei", "PingFang SC", Arial, sans-serif;' in pdf_html
