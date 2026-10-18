"""Regression tests for Word question media binding."""
from pathlib import Path

import pytest
from docx import Document
from PIL import Image

from difficulty_pipeline import DifficultyPipeline
from document_processor import DocumentProcessor
from word_splitter import WordQuestionSplitter


def _tiny_png(path: Path, color: str) -> Path:
    Image.new("RGB", (32, 20), color=color).save(path)
    return path


def _add_blank_image_paragraph(doc: Document, image_path: Path) -> None:
    paragraph = doc.add_paragraph()
    paragraph.add_run().add_picture(str(image_path))


def _build_media_docx(tmp_path: Path) -> Path:
    image_a = _tiny_png(tmp_path / "a.png", "red")
    image_b = _tiny_png(tmp_path / "b.png", "green")
    image_c = _tiny_png(tmp_path / "c.png", "blue")

    doc = Document()
    doc.add_paragraph("16. 表型正常的材料如下图所示。")
    _add_blank_image_paragraph(doc, image_a)

    doc.add_paragraph("18. 生态关系结果如下表所示。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "生物种类"
    table.cell(0, 1).text = "鱼甲"
    table.cell(1, 0).text = "消化道内食物组成"
    table.cell(1, 1).text = "河虾"
    doc.add_paragraph("装置如下图。")
    _add_blank_image_paragraph(doc, image_b)

    doc.add_paragraph("19. 实验结果如下表所示。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "组别"
    table.cell(0, 1).text = "α-SMA蛋白相对表达量"
    table.cell(1, 0).text = "第一组"
    table.cell(1, 1).text = "1.04"
    doc.add_paragraph("图1")
    _add_blank_image_paragraph(doc, image_c)

    path = tmp_path / "media.docx"
    doc.save(path)
    return path


def _by_id(questions):
    return {question["id"]: question for question in questions}


def test_word_splitter_keeps_images_from_blank_paragraphs(tmp_path):
    docx_path = _build_media_docx(tmp_path)

    questions = _by_id(WordQuestionSplitter().split(str(docx_path))["questions"])

    assert [item["type"] for item in questions[16]["_media_for_ai"]] == ["image"]
    assert [item["type"] for item in questions[18]["_media_for_ai"]] == ["table", "image"]
    assert [item["type"] for item in questions[19]["_media_for_ai"]] == ["table", "image"]


def test_document_processor_matches_structured_content_by_question_boundary(tmp_path):
    docx_path = _build_media_docx(tmp_path)
    questions = WordQuestionSplitter().split(str(docx_path))["questions"]
    elements = DocumentProcessor.extract_word_content(str(docx_path))["elements"]

    DocumentProcessor.match_elements_to_questions(questions, elements)
    by_id = _by_id(questions)

    assert [item["type"] for item in by_id[16]["structured_content"]] == ["image"]

    q18_structured = by_id[18]["structured_content"]
    assert [item["type"] for item in q18_structured] == ["table", "image"]
    assert "生物种类" in q18_structured[0]["markdown"]

    q19_structured = by_id[19]["structured_content"]
    assert [item["type"] for item in q19_structured] == ["table", "image"]
    assert "α-SMA" in q19_structured[0]["markdown"]


def test_word_splitter_marks_missing_media_for_explicit_image_cue(tmp_path):
    doc = Document()
    doc.add_paragraph("18. 装置如下图。")
    path = tmp_path / "missing-image.docx"
    doc.save(path)

    question = WordQuestionSplitter().split(str(path))["questions"][0]

    assert question["media_integrity"]["status"] == "failed"
    assert "image_media_missing" in question["warnings"]


def test_word_splitter_marks_table_render_failure(monkeypatch, tmp_path):
    def fail_render(self, rows_data):
        raise RuntimeError("render boom")

    monkeypatch.setattr(WordQuestionSplitter, "_render_table_as_image", fail_render)

    doc = Document()
    doc.add_paragraph("18. 实验结果如下表所示。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    table.cell(1, 0).text = "1"
    table.cell(1, 1).text = "2"
    path = tmp_path / "broken-table-render.docx"
    doc.save(path)

    question = WordQuestionSplitter().split(str(path))["questions"][0]

    assert question["media_integrity"]["status"] == "failed"
    assert "table_media_render_failed" in question["warnings"]
    assert all(item["type"] != "table" for item in question["_media_for_ai"])


@pytest.mark.asyncio
async def test_difficulty_fails_closed_when_media_integrity_failed(monkeypatch):
    async def should_not_call(*args, **kwargs):
        raise AssertionError("difficulty extraction should not run with broken media integrity")

    monkeypatch.setattr("difficulty_pipeline.extract_big_question_features", should_not_call)

    result = await DifficultyPipeline().evaluate_with_refinement(
        {
            "id": 18,
            "content": "18. 装置如下图。",
            "total_score": 11,
            "media_integrity": {"status": "failed", "warnings": ["image_media_missing"]},
        },
        analysis_result={},
    )

    assert result["analysis_failed"] is True
    assert result["failure_reason"] == "media_integrity_failed"


# ── 题干「如图」却无位图：用 MathType / OLE 预览图兜底 ──
def _png_bytes() -> bytes:
    import io
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color="white").save(buf, format="PNG")
    return buf.getvalue()


def _fake_soffice(monkeypatch, calls, ok=True):
    import subprocess

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        outdir = cmd[cmd.index("--outdir") + 1]
        if ok:
            Path(outdir, "preview.pdf").write_bytes(b"%PDF-1.4 fake")
        return subprocess.CompletedProcess(cmd, 0 if ok else 1, "", "" if ok else "boom")

    monkeypatch.setattr("word_splitter.subprocess.run", fake_run)
    monkeypatch.setattr("word_splitter._pdf_to_png", lambda path: _png_bytes())


def _question(content, previews):
    from word_splitter import Question
    return Question(id=23, content=content, images=[], tables=[], media=[], warnings=[],
                    section_header="三、非选择题", ole_previews=previews)


def test_missing_figure_falls_back_to_largest_ole_preview(monkeypatch):
    calls = []
    _fake_soffice(monkeypatch, calls)
    small, big = (b"\x01" * 3100, ".wmf"), (b"\x02" * 5700, ".wmf")
    result = WordQuestionSplitter()._question_to_dict(_question("23. 反射调节如图所示。", [small, big]))
    assert result["media_integrity"]["status"] == "ok"
    assert result["media_integrity"]["actual_images"] == 1
    assert "image_from_ole_preview" in result["warnings"]
    assert len(calls) == 1 and calls[0][-1].endswith("preview.rtf")


def test_no_ole_render_when_question_needs_no_figure(monkeypatch):
    calls = []
    _fake_soffice(monkeypatch, calls)
    result = WordQuestionSplitter()._question_to_dict(_question("5. 下列叙述正确的是", [(b"\x02" * 5700, ".wmf")]))
    assert result["_media_for_ai"] == [] and calls == []


def test_ole_render_failure_keeps_missing_warning(monkeypatch):
    calls = []
    _fake_soffice(monkeypatch, calls, ok=False)
    result = WordQuestionSplitter()._question_to_dict(_question("23. 如图所示。", [(b"\x02" * 5700, ".wmf")]))
    assert result["media_integrity"]["status"] == "failed"
    assert "image_media_missing" in result["media_integrity"]["warnings"]


def test_metafile_rtf_strips_placeable_header_and_sizes_page():
    import struct
    from word_splitter import _metafile_rtf
    body = b"\x01\x00\x09\x00" + b"\xab" * 10
    # placeable 头：bbox 0,0 → 2304×1152 逻辑单位，2304 单位/英寸 → 1440×720 twips
    header = b"\xd7\xcd\xc6\x9a" + b"\x00\x00" + struct.pack("<hhhhH", 0, 0, 2304, 1152, 2304) + b"\x00" * 6
    rtf = _metafile_rtf(header + body, ".wmf")
    assert "\\wmetafile8\\picwgoal1440\\pichgoal720 " + body.hex() in rtf
    assert "d7cdc69a" not in rtf
    assert "\\paperw2160\\paperh1440" in rtf
