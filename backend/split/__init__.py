"""Question-splitting package boundary.

Hot path for the UI is WordQuestionSplitter (word_splitter.py) plus visual OCR.
PDFQuestionSplitter remains for API compatibility but is not advertised in the UI.
"""
from word_splitter import WordQuestionSplitter
from pdf_splitter import PDFQuestionSplitter

__all__ = ["WordQuestionSplitter", "PDFQuestionSplitter"]
