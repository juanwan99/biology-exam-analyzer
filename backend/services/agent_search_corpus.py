"""Build Agent Search documents from the exam-review evidence corpus."""
from __future__ import annotations

import base64
from hashlib import sha256
import re
from typing import Any


DEFAULT_CORPUS_QUERY = (
    "高中生物审题：题目质量、评分细则、难度评估、核心素养、知识点覆盖、"
    "高考趋势、学生误区和学情适配。"
)


def build_agent_search_documents(*, max_documents: int = 100) -> list[dict[str, Any]]:
    """Return Discovery Engine Document objects for the default review corpus."""
    from services.evidence_context import CompositeQuestionEvidenceCorpus

    corpus = CompositeQuestionEvidenceCorpus()
    records = corpus.records_for_question(
        question_text=DEFAULT_CORPUS_QUERY,
        question_type="exam_review",
        section_header="审题知识库",
    )
    records.extend(_policy_records())
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if len(documents) >= max_documents:
            break
        doc = _record_to_document(record)
        if doc["id"] in seen:
            continue
        seen.add(doc["id"])
        documents.append(doc)
    return documents


def _policy_records() -> list[dict[str, str]]:
    return [
        {
            "id": "review-agent-policy-no-silent-fallback",
            "title": "审题智能体策略：禁止静默失败",
            "content": (
                "任何 LLM 调用失败、解析失败、证据排序失败、Grounding 校验失败或题面结构缺口，"
                "都必须进入显式失败或人工复核状态。不得用默认值、平均值或旧报告数据伪装成功。"
            ),
        },
        {
            "id": "review-agent-policy-difficulty",
            "title": "审题智能体策略：难度评估四层结构",
            "content": (
                "难度评估应区分绝对难度、分值/时间负荷、单位分值难度密度和学生适配系数。"
                "题目空数、采分点数、问题数量不能简单累加为难度；选择题还需单独评估决策难度，"
                "包括干扰项相似度、反直觉概念、信息密度、图表读数、负向表述和跨知识点判断。"
            ),
        },
        {
            "id": "review-agent-policy-grounding",
            "title": "审题智能体策略：结论必须可证据校验",
            "content": (
                "整卷报告中的事实、数字和关键判断必须能被题面、评分细则、知识点证据、"
                "学生数据或审题规则直接支撑。Check Grounding 支撑分不足时，报告不能正式输出。"
            ),
        },
    ]


def _record_to_document(record: dict[str, Any]) -> dict[str, Any]:
    title = str(record.get("title") or record.get("id") or "审题证据")
    content = str(record.get("content") or "")
    record_id = _document_id(record.get("id") or title)
    text = f"{title}\n\n{content}".strip()
    raw = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return {
        "id": record_id,
        "structData": {
            "title": title,
            "source": "biology_exam_review_corpus",
            "category": _category_for_record(record_id, title),
            "content_hash": sha256(text.encode("utf-8")).hexdigest(),
        },
        "content": {
            "rawBytes": raw,
            "mimeType": "text/plain",
        },
    }


def _document_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = "doc"
    digest = sha256(str(value).encode("utf-8")).hexdigest()[:10]
    candidate = f"{text[:50].strip('-')}-{digest}".strip("-")
    return candidate[:63]


def _category_for_record(record_id: str, title: str) -> str:
    text = f"{record_id} {title}"
    if "difficulty" in text or "难度" in text:
        return "difficulty"
    if "competency" in text or "素养" in text:
        return "competency"
    if "rubric" in text or "评分" in text:
        return "rubric"
    if "quality" in text or "质量" in text:
        return "quality"
    if "textbook" in text or "教材" in text:
        return "textbook"
    if "policy" in text or "策略" in text:
        return "policy"
    return "review"


__all__ = ["build_agent_search_documents"]
