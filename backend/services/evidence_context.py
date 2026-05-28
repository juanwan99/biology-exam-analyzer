"""Build ranked evidence context blocks for exam-review LLM prompts."""
from __future__ import annotations

import os
from hashlib import sha256
from typing import Any

from services.discovery_engine_client import DiscoveryEngineError
from services.evidence_gateway import EvidenceGateway


TRUE_VALUES = {"1", "true", "yes", "on"}


def evidence_ranking_enabled(value: bool | str | None = None) -> bool:
    if value is not None:
        if isinstance(value, str):
            return value.strip().lower() in TRUE_VALUES
        return bool(value)
    return os.environ.get("EVIDENCE_RANKING_ENABLED", "").strip().lower() in TRUE_VALUES


def evidence_ranking_top_n(value: int | str | None = None) -> int:
    raw = value if value is not None else os.environ.get("EVIDENCE_RANKING_TOP_N", "5")
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = 5
    return max(1, min(parsed, 10))


class StaticQuestionEvidenceCorpus:
    """Small built-in corpus for the first modular Ranking integration point.

    It is intentionally conservative: these are review rubrics and curriculum
    lenses, not invented facts about the current question.
    """

    def records_for_question(
        self,
        *,
        question_text: str,
        question_type: str = "unknown",
        section_header: str | None = None,
    ) -> list[dict[str, str]]:
        type_hint = question_type or "unknown"
        section = section_header or "未提供分节信息"
        return [
            {
                "id": "quality-language-risk",
                "title": "审题质量：语言、边界与风险",
                "content": (
                    "检查题干是否有歧义、条件是否充分、设问边界是否清楚、"
                    "术语是否符合高中生物表达习惯，并识别可能造成误读或舆论风险的表述。"
                ),
            },
            {
                "id": "rubric-closure",
                "title": "评分细则与采分点闭合",
                "content": (
                    "非选择题需要核对小问、采分点、分值、答案要点和评分标准是否闭合；"
                    "如果分值不明或采分点无法对齐，应标记人工复核，不能用默认分值伪装正常。"
                ),
            },
            {
                "id": "difficulty-construct",
                "title": "绝对难度构成",
                "content": (
                    "难度应基于工作记忆负荷、推理链长度、知识跨度、材料信息密度、"
                    "设问开放度和干扰陷阱强度综合判断，不能简单累加问题数量。"
                ),
            },
            {
                "id": "competency-coverage",
                "title": "核心素养覆盖",
                "content": (
                    "从生命观念、科学思维、科学探究、社会责任四个一级素养判断考查重心；"
                    "允许同一采分点支持多个素养，但需要说明主要素养和二级聚类依据。"
                ),
            },
            {
                "id": "gaokao-trend-fit",
                "title": "高考趋势贴合度",
                "content": (
                    "关注真实情境、图表材料、实验探究、证据推理、模型解释和跨模块综合；"
                    "同时检查题目是否符合本校学生当前学情和讲评成本。"
                ),
            },
            {
                "id": "student-misconception",
                "title": "学生误区与干扰项诊断",
                "content": (
                    "识别学生可能卡在概念边界、图表读取、实验变量、因果推理、"
                    "遗传概率或生态过程建模等位置，并区分误区强度。"
                ),
            },
            {
                "id": "question-local-context",
                "title": f"当前题目上下文：{type_hint}",
                "content": (
                    f"分节信息：{section}。题目摘要：{_compact_text(question_text, 260)}"
                ),
            },
        ]


class TextbookKnowledgeEvidenceCorpus:
    """Convert textbook chapter structure into Ranking API records."""

    def __init__(self, *, textbook_structure: dict[str, Any] | None = None, max_records: int = 80):
        self.textbook_structure = textbook_structure if textbook_structure is not None else self._load_default_structure()
        self.max_records = max(1, max_records)

    @classmethod
    def _load_default_structure(cls) -> dict[str, Any]:
        try:
            from knowledge_mapper import KnowledgeMapper

            return getattr(KnowledgeMapper, "TEXTBOOK_STRUCTURE", {}) or {}
        except Exception:
            return {}

    def records_for_question(
        self,
        *,
        question_text: str,
        question_type: str = "unknown",
        section_header: str | None = None,
    ) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for book_key, book in (self.textbook_structure or {}).items():
            if not isinstance(book, dict):
                continue
            book_name = str(book.get("name") or book_key)
            chapters = book.get("chapters") or {}
            if not isinstance(chapters, dict):
                continue
            for chapter_key, chapter in chapters.items():
                if not isinstance(chapter, dict):
                    continue
                chapter_name = str(chapter.get("name") or chapter_key)
                sections = chapter.get("sections") or {}
                if isinstance(sections, dict) and sections:
                    section_text = "；".join(
                        f"{section_id} {section_name}"
                        for section_id, section_name in sections.items()
                    )
                else:
                    section_text = "未列出具体节"
                record_key = f"{book_key}-{chapter_key}"
                records.append({
                    "id": f"textbook-{_safe_id(record_key)}",
                    "title": f"{book_name} / {chapter_name}",
                    "content": (
                        f"教材模块：{book_name}。章节：{chapter_name}。"
                        f"相关小节：{section_text}。"
                        "用于判断题目涉及的知识边界、跨模块程度和课程目标覆盖。"
                    ),
                })
                if len(records) >= self.max_records:
                    return records
        return records


class CompositeQuestionEvidenceCorpus:
    """Combine multiple evidence corpora into one de-duplicated candidate list."""

    def __init__(self, corpora: list[Any] | None = None):
        self.corpora = corpora or [
            StaticQuestionEvidenceCorpus(),
            TextbookKnowledgeEvidenceCorpus(),
        ]

    def records_for_question(
        self,
        *,
        question_text: str,
        question_type: str = "unknown",
        section_header: str | None = None,
    ) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        seen: set[str] = set()
        for corpus in self.corpora:
            for record in corpus.records_for_question(
                question_text=question_text,
                question_type=question_type,
                section_header=section_header,
            ):
                record_id = str(record.get("id") or "")
                if not record_id or record_id in seen:
                    continue
                seen.add(record_id)
                records.append(record)
        return records


class QuestionEvidenceContextBuilder:
    def __init__(
        self,
        *,
        evidence_gateway: EvidenceGateway | None = None,
        corpus: StaticQuestionEvidenceCorpus | None = None,
    ):
        self.evidence_gateway = evidence_gateway or EvidenceGateway()
        self.corpus = corpus or CompositeQuestionEvidenceCorpus()

    async def build_question_context(
        self,
        *,
        question_text: str,
        question_id: int | None = None,
        question_type: str = "unknown",
        section_header: str | None = None,
        top_n: int | str | None = None,
        agent_search_enabled: bool | str | None = None,
    ) -> dict[str, Any]:
        candidates = self.corpus.records_for_question(
            question_text=question_text,
            question_type=question_type,
            section_header=section_header,
        )
        if not candidates:
            raise DiscoveryEngineError("evidence ranking candidate corpus is empty")

        query = _build_query(
            question_text=question_text,
            question_type=question_type,
            section_header=section_header,
        )
        ranked = await self.evidence_gateway.rank_evidence(
            query=query,
            candidates=candidates,
            top_n=evidence_ranking_top_n(top_n),
        )
        records = [_normalize_record(record) for record in ranked.get("records") or []]
        records = [record for record in records if record.get("content") or record.get("title")]
        if not records:
            raise DiscoveryEngineError("evidence ranking returned no records")

        context_text = _render_context_text(records)
        agent_answer_metadata: dict[str, Any] | None = None
        if _truthy(agent_search_enabled):
            answer = await self._answer_from_ranked_corpus(
                records=records,
                question_id=question_id,
            )
            context_text = "\n\n".join([
                context_text,
                _render_agent_search_answer(answer),
            ])
            agent_answer_metadata = {
                "provider": "discovery_engine",
                "operation": "answer_query",
                "status": answer.get("status"),
                "citation_count": answer.get("citation_count"),
                "query_strategy": answer.get("query_strategy") or "ranked_corpus_topics",
                "text_hash": sha256(str(answer.get("text") or "").encode("utf-8")).hexdigest(),
            }
            if answer.get("retry"):
                agent_answer_metadata["retry"] = answer.get("retry")
        metadata = {
            "provider": ranked.get("metadata", {}).get("provider", "discovery_engine"),
            "operation": ranked.get("metadata", {}).get("operation", "rank"),
            "question_id": question_id,
            "record_ids": [record.get("id") for record in records if record.get("id")],
            "ranked_count": len(records),
            "candidate_count": len(candidates),
            "context_hash": sha256(context_text.encode("utf-8")).hexdigest(),
        }
        if agent_answer_metadata:
            metadata["agent_search_answer"] = agent_answer_metadata
        return {
            "context_text": context_text,
            "records": records,
            "metadata": metadata,
        }

    async def _answer_from_ranked_corpus(
        self,
        *,
        records: list[dict[str, Any]],
        question_id: int | None,
    ) -> dict[str, Any]:
        topic_query = _build_agent_search_corpus_query(records=records)
        topic_answer = await self.evidence_gateway.answer_query(
            query=topic_query,
            user_pseudo_id=f"exam-review-q{question_id or 'unknown'}-topics",
        )
        if _answer_is_cited(topic_answer):
            return {
                **topic_answer,
                "query_strategy": "ranked_corpus_topics",
            }

        broad_query = _build_agent_search_broad_query()
        broad_answer = await self.evidence_gateway.answer_query(
            query=broad_query,
            user_pseudo_id=f"exam-review-q{question_id or 'unknown'}-broad",
        )
        if _answer_is_cited(broad_answer):
            return {
                **broad_answer,
                "query_strategy": "broad_review_corpus",
                "retry": {
                    "reason": topic_answer.get("error") or topic_answer.get("status") or "ranked_topic_answer_not_cited",
                    "primary_status": topic_answer.get("status"),
                    "primary_citation_count": topic_answer.get("citation_count"),
                    "query_strategy": "broad_review_corpus",
                },
            }

        raise DiscoveryEngineError(
            f"agent search answer failed for question {question_id}: "
            f"ranked_topics={topic_answer.get('error') or topic_answer.get('status')}; "
            f"broad_corpus={broad_answer.get('error') or broad_answer.get('status')}"
        )


def _build_query(*, question_text: str, question_type: str, section_header: str | None) -> str:
    parts = [
        f"题型：{question_type or 'unknown'}",
        f"分节：{section_header}" if section_header else "",
        "任务：为高中生物审题选择最相关的质量、评分、难度、素养和学生误区证据。",
        f"题目：{_compact_text(question_text, 500)}",
    ]
    return "\n".join(part for part in parts if part)


def _render_context_text(records: list[dict[str, Any]]) -> str:
    lines = [
        "【审题证据上下文】",
        "以下材料由 Discovery Engine Ranking API 重排，仅用于约束审题关注点；不得替代题面、答案或评分细则。",
    ]
    for index, record in enumerate(records, 1):
        score = record.get("score")
        score_part = f"，score={score:.3f}" if isinstance(score, (int, float)) else ""
        lines.append(f"{index}. {record.get('title') or record.get('id')}{score_part}")
        if record.get("content"):
            lines.append(_compact_text(str(record["content"]), 420))
    return "\n".join(lines)


def _render_agent_search_answer(answer: dict[str, Any]) -> str:
    text = _compact_text(str(answer.get("text") or ""), 900)
    citation_count = answer.get("citation_count")
    return "\n".join([
        "[Agent Search evidence answer]",
        "The following answer comes from Discovery Engine Search App and must be treated as cited evidence, not as the final review conclusion.",
        text,
        f"citation_count={citation_count}",
    ])


def _build_agent_search_corpus_query(
    *,
    records: list[dict[str, Any]],
) -> str:
    titles = "；".join(
        str(record.get("title") or record.get("id") or "").strip()
        for record in records[:5]
        if str(record.get("title") or record.get("id") or "").strip()
    )
    return (
        "请只基于高中生物审题知识库回答：这些审题证据主题如何用于判断题目质量、评分边界、"
        "难度、核心素养和学生误区？不要评价具体试题答案，只概括这些证据主题的审题用途。"
        f" 证据主题={titles or '通用审题证据'}。"
    )


def _build_agent_search_broad_query() -> str:
    return (
        "请只基于高中生物审题知识库，概括审题证据如何用于题目质量、评分边界、"
        "绝对难度、核心素养覆盖和学生误区诊断，并给出可引用依据。"
    )


def _answer_is_cited(answer: dict[str, Any]) -> bool:
    return (
        answer.get("status") == "ok"
        and bool(str(answer.get("text") or "").strip())
        and int(answer.get("citation_count") or 0) > 0
    )


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("record") if isinstance(record.get("record"), dict) else record
    score = (
        record.get("score")
        or record.get("rankingScore")
        or record.get("rankScore")
        or source.get("score")
    )
    try:
        score = float(score) if score is not None else None
    except (TypeError, ValueError):
        score = None
    return {
        "id": str(source.get("id") or record.get("id") or ""),
        "title": str(source.get("title") or record.get("title") or ""),
        "content": str(source.get("content") or record.get("content") or ""),
        "score": score,
    }


def _compact_text(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _safe_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    digest = sha256(text.encode("utf-8")).hexdigest()[:12]
    return digest


def _truthy(value: bool | str | None) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in TRUE_VALUES
    return bool(value)


__all__ = [
    "CompositeQuestionEvidenceCorpus",
    "QuestionEvidenceContextBuilder",
    "StaticQuestionEvidenceCorpus",
    "TextbookKnowledgeEvidenceCorpus",
    "evidence_ranking_enabled",
    "evidence_ranking_top_n",
]
