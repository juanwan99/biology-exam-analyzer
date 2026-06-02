"""Tests for pipeline schemas and DTO conversions."""
import pytest
from pipeline.schemas import (
    DocumentArtifact, QuestionDraft, QuestionAnalysis,
    ReportData, StepResult, StepStatus, AnalysisRun,
)


class TestDocumentArtifact:
    def test_page_count(self):
        doc = DocumentArtifact(filename="test.pdf", image_bytes=[b"img1", b"img2"])
        assert doc.page_count == 2

    def test_empty(self):
        doc = DocumentArtifact(filename="empty.pdf")
        assert doc.page_count == 0


class TestQuestionDraft:
    def test_from_dict(self):
        d = {"id": 1, "content": "test", "total_score": 6, "_section_header": "选择题"}
        draft = QuestionDraft.from_dict(d)
        assert draft.id == 1
        assert draft.section_header == "选择题"
        assert draft.total_score == 6

    def test_to_dict_preserves_raw(self):
        d = {"id": 1, "content": "test", "extra_field": "kept"}
        draft = QuestionDraft.from_dict(d)
        result = draft.to_dict()
        assert result["extra_field"] == "kept"
        assert result["id"] == 1


class TestQuestionAnalysis:
    def test_is_success_true(self):
        qa = QuestionAnalysis(question_id=1, analysis={"answer": "A"})
        assert qa.is_success

    def test_is_success_false_on_error(self):
        qa = QuestionAnalysis(question_id=1, error="LLM failed")
        assert not qa.is_success

    def test_is_success_false_on_analysis_error(self):
        qa = QuestionAnalysis(question_id=1, analysis={"error": "timeout"})
        assert not qa.is_success

    def test_to_question_dict(self):
        draft = QuestionDraft(id=1, content="q1", total_score=6)
        qa = QuestionAnalysis(
            question_id=1,
            analysis={"answer": "A"},
            difficulty={"final_difficulty": 3.0},
            competency={"primary_competency": "生命观念"},
        )
        result = qa.to_question_dict(draft)
        assert result["analysis"]["answer"] == "A"
        assert result["difficulty"]["final_difficulty"] == 3.0


class TestReportData:
    def test_auto_calc(self):
        rd = ReportData(
            questions=[
                {"total_score": 6},
                {"total_score": 4},
            ]
        )
        assert rd.question_count == 2
        assert rd.total_score == 10


class TestAnalysisRun:
    def test_progress(self):
        run = AnalysisRun(
            steps=[
                StepResult("ingest", StepStatus.SUCCESS),
                StepResult("segment", StepStatus.SUCCESS),
                StepResult("analyze", StepStatus.RUNNING),
                StepResult("aggregate", StepStatus.PENDING),
            ]
        )
        assert run.progress == 0.5

    def test_failed_questions(self):
        run = AnalysisRun(
            analyses=[
                QuestionAnalysis(question_id=1, analysis={"answer": "A"}),
                QuestionAnalysis(question_id=2, error="failed"),
                QuestionAnalysis(question_id=3, analysis={"answer": "C"}),
            ]
        )
        assert run.failed_questions == [2]
