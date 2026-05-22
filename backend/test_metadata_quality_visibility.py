import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.modules["weasyprint"] = MagicMock()

from report_generator import _render_html
from services.analysis_service import AnalysisService


def _call(purpose):
    return {
        "call_id": purpose,
        "purpose": purpose,
        "prompt_id": f"biology.{purpose}",
        "prompt_hash": "a" * 64,
        "provider": "llm_client",
        "model": "configured_provider_chain",
        "input_refs": {},
        "parsed_schema": "Schema",
        "confidence": 0.9,
        "validation_errors": [],
        "fallback_count": 0,
        "retry_count": 0,
        "metadata": {},
    }


def _question(question_id=1, overall=0.55):
    calls = [_call("question_analysis"), _call("feature_extraction"), _call("competency_analysis")]
    return {
        "id": question_id,
        "content": "题干",
        "total_score": 2,
        "analysis": {"knowledge_points": ["酶"], "answer": "A"},
        "difficulty": {"final_difficulty": 5.0, "features": {"_feature_status": "partial"}},
        "competency": {"primary_competency": "科学思维"},
        "_metadata_envelope": {
            "question": {"id": question_id},
            "llm_calls": calls,
            "analysis_units": {},
            "derived": {},
            "confidence": {"overall": overall, "analysis": 0.9, "features": 0.55, "competency": 0.9},
            "lineage": {
                "knowledge_points": "analysis.knowledge_points",
                "difficulty_features": "difficulty.features",
                "competency": "competency",
            },
            "warnings": ["feature_status:partial"],
        },
    }


class FakeWordSplitter:
    def split(self, file_path):
        return {"questions": [{"id": 1, "content": "题干"}]}


class FakeDocProcessor:
    def process_docx(self, file_path):
        return []


@pytest.mark.asyncio
async def test_auto_analysis_returns_metadata_quality_summary():
    service = AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=FakeDocProcessor(),
        word_splitter=FakeWordSplitter(),
        pdf_splitter=None,
    )

    async def fake_analyze_questions_batch(questions, image_bytes, mode, subject="biology"):
        return [_question(1, overall=0.55)]

    service.analyze_questions_batch = fake_analyze_questions_batch
    service.build_competency_summary = lambda questions: {}
    service.aggregate_statistics = lambda questions, competency_summary: {}

    result = await service.run_auto_analysis("exam.docx", "exam.docx", b"", generate_report=False)

    assert result["metadata_quality"]["low_confidence_questions"] == [1]
    assert result["metadata_quality"]["warning_questions"] == [
        {"id": 1, "warnings": ["feature_status:partial"]}
    ]


@pytest.mark.asyncio
async def test_auto_analysis_returns_html_report_url_when_report_generated(tmp_path):
    service = AnalysisService(
        analyzer=None,
        difficulty_engine=None,
        competency_analyzer=None,
        knowledge_mapper=None,
        doc_processor=FakeDocProcessor(),
        word_splitter=FakeWordSplitter(),
        pdf_splitter=None,
    )

    async def fake_analyze_questions_batch(questions, image_bytes, mode, subject="biology"):
        return [_question(1, overall=0.9)]

    async def fake_generate_report(
        questions,
        competency_summary,
        exam_statistics,
        exam_info,
        mode="full",
        output_path=None,
    ):
        pdf_path = Path(output_path)
        pdf_path.write_bytes(b"%PDF")
        pdf_path.with_suffix(".html").write_text("<html>product report</html>", encoding="utf-8")
        return output_path

    service.analyze_questions_batch = fake_analyze_questions_batch
    service.build_competency_summary = lambda questions: {}
    service.aggregate_statistics = lambda questions, competency_summary: {}
    service.generate_report = fake_generate_report

    result = await service.run_auto_analysis(
        "exam.docx",
        "exam.docx",
        b"",
        generate_report=True,
        reports_dir=str(tmp_path),
        exam_id="exam-1",
    )

    assert result["report_url"] == "/api/reports/exam-1.pdf"
    assert result["html_report_url"] == "/api/reports/exam-1.html"


def test_report_html_renders_metadata_quality_summary():
    data = {
        "exam_info": {"name": "测试卷", "total_questions": 1, "total_score": 2, "mode": "deep"},
        "metrics": {
            "avg_difficulty": 5.0,
            "avg_cognitive_level": 4.0,
            "difficulty_distribution": {},
            "bloom_distribution": {},
        },
        "difficulty_curve": [],
        "difficulty_gradient": {"front": 5.0, "middle": 5.0, "back": 5.0, "gradient_type": "题目过少"},
        "knowledge": {"top_points": [], "textbook_distribution": {}},
        "competency": {"distribution": {}, "primary_distribution": {}},
        "feature_profile": {"avg_per_dimension": {}, "top_difficulty_factors": []},
        "fine_grained_summary": {},
        "metadata_quality": {
            "total_questions": 1,
            "low_confidence_questions": [1],
            "warning_questions": [{"id": 1, "warnings": ["feature_status:partial"]}],
            "llm_call_counts": {"question_analysis": 1, "feature_extraction": 1, "competency_analysis": 1},
        },
        "questions": [],
    }
    insights = {
        "overall_assessment": "总评",
        "recommendations": [],
        "difficulty_analysis": "",
        "knowledge_analysis": "",
        "competency_analysis": "",
        "bloom_analysis": "",
    }

    charts = {
        "curve": "data:image/png;base64,CURVE",
        "distribution": "data:image/png;base64,DIST",
        "competency_pie": "data:image/png;base64,PIE",
        "bloom": "data:image/png;base64,BLOOM",
        "gradient": "data:image/png;base64,GRAD",
        "radar": "data:image/png;base64,RADAR",
        "competency_bar": "data:image/png;base64,BAR",
        "knowledge_pie": "data:image/png;base64,KPIE",
    }

    html = _render_html(data, insights, charts=charts, mode="brief")

    assert "元数据治理" in html
    assert "低置信度题目" in html
    assert "Q1" in html
    assert "feature_status:partial" in html
