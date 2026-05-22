from report_product_html import render_report_product_html
from test_report_commercial_html import _commercial_model


def test_render_report_product_html_explains_failures_in_teacher_language():
    model = _commercial_model()
    explanation = {
        "question_id": 21,
        "code": "insufficient_stem",
        "stage": "题面完整性检查",
        "title": "题面不完整",
        "reason": "系统只识别到第21题的（2）（3）小问，未识别到（1）问。",
        "impact": "第21题不纳入逐题难度排名、平均难度计算和高风险题排序。",
        "action": "请核对原始试卷或Word/PDF抽取结果，补齐第（1）问后重新生成报告。",
        "severity": "blocked",
        "display": "失败阶段：题面完整性检查；原因：系统只识别到第21题的（2）（3）小问，未识别到（1）问。；影响：第21题不纳入逐题难度排名、平均难度计算和高风险题排序。；处理：请核对原始试卷或Word/PDF抽取结果，补齐第（1）问后重新生成报告。",
    }
    model.setdefault("evidence_integrity", {})["failure_explanations"] = [explanation]
    model["deep_dives"] = [
        {
            "question_id": 21,
            "headline": "Q21 数据不足",
            "diagnosis": "题面不完整。",
            "seu_breakdown": [],
            "du_diagnostics": [],
            "su_context": [],
            "revision_plan": ["补齐题面后重跑。"],
            "metadata_trace": {"confidence": 0, "purposes": [], "warnings": []},
            "evidence_integrity": {
                "analysis_failed": True,
                "failure_reason": "insufficient_stem",
                "difficulty_flags": ["big_question_structure_failed"],
                "difficulty_source": "analysis_failed",
                "failure_explanations": [explanation],
            },
        }
    ]

    html = render_report_product_html(model)
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "题面完整性检查" in visible_html
    assert "未识别到（1）问" in visible_html
    assert "不纳入逐题难度排名" in visible_html
    assert "请核对原始试卷" in visible_html


def test_render_report_product_html_uses_commercial_report_structure():
    html = render_report_product_html(_commercial_model())
    visible_html = html.split('<script id="productData"', 1)[0]

    assert "整卷总览" not in html
    assert "命题质量诊断" not in html
    assert "执行摘要" in html
    assert "题目组合诊断" in html
    assert "LLM 调用与方法论" in html
    assert "来源：报告数据：难度梯度" in visible_html
    assert "commercial_report.v1" in html
