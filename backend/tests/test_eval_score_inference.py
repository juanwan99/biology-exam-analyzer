import json
import sys
from types import SimpleNamespace

import pytest

from score_rules import paper_score, scale_section_scores
from scripts import eval_score_inference as evaluation
from utils import infer_question_type


def test_strip_scores_removes_head_section_and_subquestion_marks():
    question = {
        "content": "17．（本题满分10分）题干\n（1）第一问（2分）\n（2）第二问 (2.5 分)；另计 1.5 分",
        "_section_header": "三、非选择题：共5小题，每题 10 分，共50分；加试另计 3分",
        "_group_material": "阅读材料（8分），回答下列问题",
    }
    assert paper_score(question) == (10.0, "paper")

    assert evaluation.strip_scores(question) == 2
    assert paper_score(question) == (None, None)
    assert question["content"] == "17．题干\n（1）第一问\n（2）第二问 ；另计 1.5 分"
    assert question["_section_header"] == "三、非选择题：共5小题，，；加试另计 3分"
    assert question["_group_material"] == "阅读材料，回答下列问题"


def test_cli_measures_both_formats_and_summarizes_attempts(monkeypatch, tmp_path, capsys):
    word = tmp_path / "example.docx"
    pdf = tmp_path / "example.pdf"
    output = tmp_path / "scores.json"
    word_questions = [
        {"id": 1, "content": "1. 题干", "_section_header": "一、单选题：每小题2分"},
        {"id": 2, "content": "2.（10分）回答问题", "_section_header": "二、非选择题：共10分"},
        {"id": 3, "content": "3. 无卷面标分", "_section_header": None},
    ]
    pdf_media = [{"type": "image", "base64": "cGRm"}]
    pdf_questions = [
        {"id": 1, "content": "1.（3分）题干", "_section_header": "一、单选题", "_media_for_ai": pdf_media},
        {"id": 2, "content": "2.（12分）回答问题", "_section_header": "二、非选择题", "_media_for_ai": pdf_media},
    ]

    def split_word(path, *, subject):
        assert (path, subject) == (str(word), "biology")
        return {"questions": word_questions}

    def split_pdf(path):
        assert path == str(pdf)
        return {"questions": pdf_questions}

    def process_docx(path):
        assert path == str(word)
        return ["word-image"]

    def images_to_bytes(images):
        assert images == ["word-image"]
        return [b"word"]

    scores = {
        "word": {1: iter([1, 4]), 2: iter([8, 6]), 3: iter([99, 1])},
        "pdf": {1: iter([5, 4]), 2: iter([8, 12])},
    }

    async def analyze_question(question, image_bytes, mode, *, subject):
        assert (mode, subject) == ("deep", "biology")
        assert paper_score(question) == (None, None)
        assert "total_score" not in question
        if image_bytes:
            assert image_bytes == [b"word"]
            kind = "word"
        else:
            assert question["_media_for_ai"] == pdf_media
            kind = "pdf"
        question.update(
            question_type=infer_question_type(question),
            total_score=next(scores[kind][question["id"]]),
            score_source="model",
            score_status="valid",
        )
        return question

    monkeypatch.setattr(evaluation, "split_word_with_visual", split_word)
    monkeypatch.setattr(evaluation.deps, "get_pdf_splitter", lambda: SimpleNamespace(split=split_pdf))
    monkeypatch.setattr(evaluation.deps, "get_doc_processor", lambda: SimpleNamespace(
        process_docx=process_docx, images_to_bytes=images_to_bytes,
    ))
    monkeypatch.setattr(evaluation.deps, "get_analysis_service", lambda: SimpleNamespace(
        analyze_question=analyze_question,
    ))
    monkeypatch.setattr(sys, "argv", ["eval_score_inference.py", str(word), str(pdf), "--json", str(output)])

    evaluation.main()

    printed = capsys.readouterr().out.splitlines()
    assert printed.count("example.docx 残留分值字样 0 处") == 1
    assert printed.count("example.pdf 残留分值字样 0 处") == 1
    assert "example.docx 第 1 次 第 1 题 single_choice 真值 2.0 推断 1.0 差 -1.0 model" in printed
    assert "example.docx 第 2 次 第 1 题 single_choice 真值 2.0 推断 4.0 差 +2.0 model" in printed
    assert [line for line in printed if "整卷总分" in line] == [
        "example.docx 第 1 次 整卷总分 真值 12.0 推断 9.0",
        "example.docx 第 2 次 整卷总分 真值 12.0 推断 10.0",
        "example.pdf 第 1 次 整卷总分 真值 15.0 推断 13.0",
        "example.pdf 第 2 次 整卷总分 真值 15.0 推断 16.0",
    ]
    # 选择题差 −1、+2、+2、+1；非选择题差 −2、−4、−4、0。
    assert printed[-3:] == [
        "选择题 MAE 1.5 平均偏差 +1.0",
        "非选择题 MAE 2.5 平均偏差 -2.5",
        "同题多次推断的最大差 4.0",
    ]

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert len(rows) == 10
    assert rows[0] == {
        "paper": "example.docx", "run": 1, "question_id": 1, "question_type": "single_choice",
        "paper_score": 2.0, "total_score": 1.0, "difference": -1.0,
        "score_source": "model", "score_status": "valid",
    }
    assert rows[2]["paper_score"] is None and rows[2]["difference"] is None


def test_cli_apportions_full_mark_after_rescaling_sections(monkeypatch, tmp_path):
    word = tmp_path / "example.docx"
    output = tmp_path / "scores.json"
    questions = [
        {"id": 1, "content": "1.（2分）题干", "question_type": "single_choice"},
        {"id": 2, "content": "2.（12分）简答", "question_type": "short_answer"},
        {"id": 3, "content": "3.（86分）简答", "question_type": "short_answer"},
    ]

    async def split_paper(path):
        assert path == word
        return questions, [b"word"]

    async def analyze_question(question, image_bytes, mode, *, subject):
        assert paper_score(question) == (None, None)
        assert "total_score" not in question
        question.update(total_score=2 if question["id"] == 1 else 8, score_source="model", score_status="valid")
        return question

    async def rescale_section_scores(analyzed, image_bytes, mode):
        assert (image_bytes, mode) == ([b"word"], "deep")
        assert [q["total_score"] for q in analyzed] == [2, 8, 8]
        # 模拟分析后有一道可按分节小计缩放的题。
        analyzed[1]["_section_header"] = "二、共1题，共12分"
        return scale_section_scores(analyzed)

    monkeypatch.setattr(evaluation, "split_paper", split_paper)
    monkeypatch.setattr(evaluation.deps, "get_analysis_service", lambda: SimpleNamespace(
        analyze_question=analyze_question, rescale_section_scores=rescale_section_scores,
    ))
    monkeypatch.setattr(sys, "argv", [
        "eval_score_inference.py", str(word), "--full-mark", "100", "--runs", "2", "--json", str(output),
    ])

    evaluation.main()

    rows = json.loads(output.read_text(encoding="utf-8"))
    assert [row["total_score"] for row in rows] == [2, 12, 86] * 2
    assert [row["score_source"] for row in rows] == ["model", "section_scaled", "full_mark_scaled"] * 2
    assert [row["difference"] for row in rows] == [0] * 6


@pytest.mark.parametrize("returns_failure", [False, True])
async def test_evaluation_stops_on_analysis_failure(monkeypatch, tmp_path, returns_failure):
    async def split_paper(path):
        return [{"id": 1, "content": "1.（2分）题干"}], []

    async def analyze_question(question, image_bytes, mode, *, subject):
        if returns_failure:
            return {**question, "analysis_failed": True, "analysis_failure_reason": "分析出错"}
        raise RuntimeError("分析出错")

    monkeypatch.setattr(evaluation, "split_paper", split_paper)
    monkeypatch.setattr(evaluation.deps, "get_analysis_service", lambda: SimpleNamespace(
        analyze_question=analyze_question,
    ))

    with pytest.raises(RuntimeError, match="分析出错"):
        await evaluation.evaluate_paper(tmp_path / "example.docx", runs=2)
