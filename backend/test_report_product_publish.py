from pathlib import Path

from report_product_publish import write_report_artifacts


def _report_data():
    return {
        "exam_info": {
            "name": "一模生物试卷",
            "total_questions": 1,
            "total_score": 6,
            "mode": "deep",
        },
        "metrics": {"avg_difficulty": 6.0, "avg_cognitive_level": 4.0, "bloom_distribution": {}},
        "difficulty_gradient": {"gradient_type": "前易后难"},
        "knowledge": {"top_points": []},
        "competency": {"distribution": {}},
        "feature_profile": {},
        "fine_grained_summary": {},
        "metadata_quality": {"warning_questions": []},
        "questions": [
            {
                "id": 1,
                "total_score": 6,
                "question_type": "short_answer",
                "difficulty": 6.0,
                "quality_score": 5,
                "quality_scientific": "无明显问题",
                "quality_normative": "规范",
                "quality_language": "严谨",
                "quality_context": "真实",
            }
        ],
    }


def test_write_report_artifacts_writes_html_next_to_pdf(monkeypatch, tmp_path):
    generated = []

    class FakeHTML:
        def __init__(self, string=None, base_url=None):
            generated.append((string, base_url))

        def write_pdf(self, output_path):
            Path(output_path).write_bytes(b"%PDF commercial")

    import report_product_publish

    monkeypatch.setattr(report_product_publish, "HTML", FakeHTML)

    result = write_report_artifacts(
        _report_data(),
        {"recommendations": []},
        mode="full",
        pdf_path=tmp_path / "exam.pdf",
    )

    assert generated
    assert '<main class="pdf-report">' in generated[0][0]
    assert "PDF 专用版式" in generated[0][0]
    assert Path(result["pdf_path"]).exists()
    assert Path(result["pdf_path"]).read_bytes().startswith(b"%PDF")
    html_path = Path(result["html_path"])
    assert html_path == tmp_path / "exam.html"
    html = html_path.read_text(encoding="utf-8")
    assert '<nav class="top-nav" aria-label="报告导航">' in html
    assert 'class="pdf-report"' not in html
    assert "一模生物试卷" in html
