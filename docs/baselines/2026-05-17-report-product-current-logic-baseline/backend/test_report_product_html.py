from report_product_html import render_report_product_html
from test_report_commercial_html import _commercial_model


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
