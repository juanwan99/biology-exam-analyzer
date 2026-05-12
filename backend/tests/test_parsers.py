"""Golden tests for document parsers."""
import pytest
from parsers.document_parsers import chinese_to_num, parse_docx, parse_pdf


class TestChineseToNum:
    def test_basic(self):
        assert chinese_to_num("一") == 1
        assert chinese_to_num("五") == 5
        assert chinese_to_num("十") == 10

    def test_unknown(self):
        assert chinese_to_num("百") == 0


class TestParseDocx:
    def test_empty_bytes(self):
        result = parse_docx(b"")
        assert result == []

    def test_invalid_bytes(self):
        result = parse_docx(b"not a docx file")
        assert result == []


class TestParsePdf:
    def test_empty_bytes(self):
        result = parse_pdf(b"")
        assert result == []

    def test_invalid_bytes(self):
        result = parse_pdf(b"not a pdf file")
        assert result == []
