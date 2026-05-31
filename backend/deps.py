# -*- coding: utf-8 -*-
"""
全局依赖实例 — 分析器、处理器等单例。

所有组件使用惰性初始化，避免 import 循环和重复实例化。
main.py 和 analysis_router.py 均从此处获取实例。
"""
import os

from logger import get_logger

logger = get_logger()

# ============ 环境变量 ============
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "21"))

# ============ 惰性单例 ============
_analyzer_instance = None
_difficulty_engine = None
_competency_analyzer = None
_knowledge_mapper = None
_doc_processor = None
_rule_splitter = None
_word_splitter = None
_pdf_splitter = None
_report_generator = None


def get_vision_analyzer():
    global _analyzer_instance
    if _analyzer_instance is None:
        from llm_config import get_providers
        if not get_providers():
            logger.warning("无可用 LLM provider（请检查 API key 配置），AI 分析功能不可用")
            return None
        from question_analyzer import QuestionAnalyzer
        _analyzer_instance = QuestionAnalyzer()
    return _analyzer_instance


def get_difficulty_engine():
    global _difficulty_engine
    if _difficulty_engine is None:
        from difficulty_pipeline import DifficultyPipeline
        _difficulty_engine = DifficultyPipeline()
    return _difficulty_engine


def get_competency_analyzer():
    global _competency_analyzer
    if _competency_analyzer is None:
        from competency_analyzer import CompetencyAnalyzer
        _competency_analyzer = CompetencyAnalyzer()
    return _competency_analyzer


def get_knowledge_mapper():
    global _knowledge_mapper
    if _knowledge_mapper is None:
        from knowledge_mapper import KnowledgeMapper
        _knowledge_mapper = KnowledgeMapper()
    return _knowledge_mapper


def get_doc_processor():
    global _doc_processor
    if _doc_processor is None:
        from document_processor import DocumentProcessor
        _doc_processor = DocumentProcessor()
    return _doc_processor


def get_rule_splitter():
    global _rule_splitter
    if _rule_splitter is None:
        from rule_splitter import RuleSplitter
        _rule_splitter = RuleSplitter()
    return _rule_splitter


def get_word_splitter():
    global _word_splitter
    if _word_splitter is None:
        from word_splitter import WordQuestionSplitter
        _word_splitter = WordQuestionSplitter()
    return _word_splitter


def get_pdf_splitter():
    global _pdf_splitter
    if _pdf_splitter is None:
        from pdf_splitter import PDFQuestionSplitter
        _pdf_splitter = PDFQuestionSplitter()
    return _pdf_splitter


def get_report_generator():
    """Deprecated: 使用 report_generator.generate_pdf_report() 模块函数。"""
    global _report_generator
    if _report_generator is None:
        from report_generator import ReportGenerator
        _report_generator = ReportGenerator()
    return _report_generator


_analysis_service = None

def get_analysis_service():
    global _analysis_service
    if _analysis_service is None:
        from services.analysis_service import AnalysisService
        _analysis_service = AnalysisService(
            analyzer=get_vision_analyzer(),
            difficulty_engine=get_difficulty_engine(),
            competency_analyzer=get_competency_analyzer(),
            knowledge_mapper=get_knowledge_mapper(),
            doc_processor=get_doc_processor(),
            word_splitter=get_word_splitter(),
            pdf_splitter=get_pdf_splitter(),
            max_workers=MAX_WORKERS,
        )
    return _analysis_service

get_question_analyzer = get_vision_analyzer

# Backward-compat alias: some modules import get_analyzer
get_analyzer = get_vision_analyzer
