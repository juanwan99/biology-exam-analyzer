import pytest

from services.discovery_engine_client import DiscoveryEngineError
from services.evidence_context import (
    CompositeQuestionEvidenceCorpus,
    QuestionEvidenceContextBuilder,
    StaticQuestionEvidenceCorpus,
    TextbookKnowledgeEvidenceCorpus,
)


@pytest.mark.asyncio
async def test_question_evidence_context_ranks_candidates_and_renders_prompt_block():
    class FakeGateway:
        def __init__(self):
            self.calls = []

        async def rank_evidence(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "status": "ok",
                "records": [
                    {
                        "id": "rubric-closure",
                        "title": "评分细则与采分点闭合",
                        "content": "检查小问、采分点、分值和答案边界是否闭合。",
                        "score": 0.91,
                    }
                ],
                "metadata": {
                    "provider": "discovery_engine",
                    "operation": "rank",
                    "top_n": kwargs["top_n"],
                    "candidate_count": len(kwargs["candidates"]),
                },
            }

    gateway = FakeGateway()
    builder = QuestionEvidenceContextBuilder(evidence_gateway=gateway)

    result = await builder.build_question_context(
        question_text="分析遗传实验结果并说明亲本基因型。",
        question_type="short_answer",
        section_header="非选择题，每题 12 分",
        top_n=3,
    )

    assert gateway.calls
    assert gateway.calls[0]["top_n"] == 3
    assert len(gateway.calls[0]["candidates"]) >= 5
    assert "遗传实验结果" in gateway.calls[0]["query"]
    assert "评分细则与采分点闭合" in result["context_text"]
    assert "rubric-closure" in result["metadata"]["record_ids"]
    assert result["metadata"]["provider"] == "discovery_engine"
    assert result["metadata"]["operation"] == "rank"


@pytest.mark.asyncio
async def test_question_evidence_context_fails_closed_when_ranking_returns_no_records():
    class EmptyGateway:
        async def rank_evidence(self, **kwargs):
            return {"status": "ok", "records": [], "metadata": {"operation": "rank"}}

    builder = QuestionEvidenceContextBuilder(evidence_gateway=EmptyGateway())

    with pytest.raises(DiscoveryEngineError, match="returned no records"):
        await builder.build_question_context(
            question_text="分析生态系统能量流动。",
            question_type="short_answer",
        )


@pytest.mark.asyncio
async def test_question_evidence_context_adds_agent_search_answer_when_enabled():
    class FakeGateway:
        def __init__(self):
            self.calls = []

        async def rank_evidence(self, **kwargs):
            self.calls.append(("rank", kwargs))
            return {
                "status": "ok",
                "records": [{
                    "id": "difficulty-construct",
                    "title": "difficulty",
                    "content": "difficulty evidence",
                    "score": 0.9,
                }],
                "metadata": {"provider": "discovery_engine", "operation": "rank"},
            }

        async def answer_query(self, **kwargs):
            self.calls.append(("answer", kwargs))
            return {
                "status": "ok",
                "text": "Search App says the item checks experimental design and scoring boundary.",
                "citation_count": 2,
            }

    gateway = FakeGateway()
    builder = QuestionEvidenceContextBuilder(evidence_gateway=gateway)

    result = await builder.build_question_context(
        question_text="Analyze experimental design.",
        question_id=21,
        question_type="short_answer",
        agent_search_enabled=True,
    )

    assert [call[0] for call in gateway.calls] == ["rank", "answer"]
    assert "Analyze experimental design" not in gateway.calls[1][1]["query"]
    assert "证据主题" in gateway.calls[1][1]["query"]
    assert "Agent Search evidence answer" in result["context_text"]
    assert "experimental design" in result["context_text"]
    agent_answer = result["metadata"]["agent_search_answer"]
    assert agent_answer["operation"] == "answer_query"
    assert agent_answer["citation_count"] == 2
    assert agent_answer["query_strategy"] == "ranked_corpus_topics"
    assert agent_answer["text_hash"]


@pytest.mark.asyncio
async def test_question_evidence_context_fails_closed_when_agent_search_answer_missing():
    class FakeGateway:
        async def rank_evidence(self, **kwargs):
            return {
                "status": "ok",
                "records": [{"id": "r", "title": "ranked", "content": "context"}],
                "metadata": {"provider": "discovery_engine", "operation": "rank"},
            }

        async def answer_query(self, **kwargs):
            return {"status": "error", "text": "", "error": "missing answer text"}

    builder = QuestionEvidenceContextBuilder(evidence_gateway=FakeGateway())

    with pytest.raises(DiscoveryEngineError, match="agent search answer failed"):
        await builder.build_question_context(
            question_text="Analyze experimental design.",
            question_id=21,
            agent_search_enabled=True,
        )


@pytest.mark.asyncio
async def test_question_evidence_context_falls_back_to_broad_agent_search_query():
    class FakeGateway:
        def __init__(self):
            self.answer_calls = []

        async def rank_evidence(self, **kwargs):
            return {
                "status": "ok",
                "records": [{
                    "id": "difficulty-construct",
                    "title": "难度评估四层结构",
                    "content": "难度应区分绝对难度、分值负荷、难度密度和学生适配。",
                    "score": 0.9,
                }],
                "metadata": {"provider": "discovery_engine", "operation": "rank"},
            }

        async def answer_query(self, **kwargs):
            self.answer_calls.append(kwargs)
            if len(self.answer_calls) == 1:
                return {
                    "status": "error",
                    "text": "无法为您的搜索查询生成摘要。",
                    "citation_count": 0,
                    "error": "answer_query skipped: OUT_OF_DOMAIN_QUERY_IGNORED",
                }
            return {
                "status": "ok",
                "text": "审题时应关注评分边界和难度结构。",
                "citation_count": 2,
            }

    gateway = FakeGateway()
    builder = QuestionEvidenceContextBuilder(evidence_gateway=gateway)

    result = await builder.build_question_context(
        question_text="Analyze In-Fusion primer design.",
        question_id=21,
        question_type="short_answer",
        section_header="non-choice",
        agent_search_enabled=True,
    )

    assert len(gateway.answer_calls) == 2
    assert "Analyze In-Fusion primer design" not in gateway.answer_calls[0]["query"]
    assert "证据主题" in gateway.answer_calls[0]["query"]
    assert "证据主题" not in gateway.answer_calls[1]["query"]
    agent_answer = result["metadata"]["agent_search_answer"]
    assert agent_answer["citation_count"] == 2
    assert agent_answer["query_strategy"] == "broad_review_corpus"
    assert agent_answer["retry"]["query_strategy"] == "broad_review_corpus"


def test_textbook_knowledge_corpus_flattens_textbook_structure_into_rankable_records():
    corpus = TextbookKnowledgeEvidenceCorpus(
        textbook_structure={
            "必修2": {
                "name": "遗传与进化",
                "chapters": {
                    "第1章": {
                        "name": "遗传因子的发现",
                        "sections": {
                            "1.1": "孟德尔的豌豆杂交实验（一）",
                            "1.2": "孟德尔的豌豆杂交实验（二）",
                        },
                    }
                },
            }
        }
    )

    records = corpus.records_for_question(
        question_text="豌豆杂交实验中亲本基因型推断",
        question_type="short_answer",
    )

    assert records
    assert records[0]["id"].startswith("textbook-")
    assert "遗传与进化" in records[0]["title"]
    assert "孟德尔的豌豆杂交实验" in records[0]["content"]


def test_composite_evidence_corpus_combines_static_and_textbook_records():
    textbook = TextbookKnowledgeEvidenceCorpus(
        textbook_structure={
            "必修1": {
                "name": "分子与细胞",
                "chapters": {"第5章": {"name": "细胞呼吸", "sections": {"5.3": "细胞呼吸原理"}}},
            }
        }
    )
    corpus = CompositeQuestionEvidenceCorpus([
        StaticQuestionEvidenceCorpus(),
        textbook,
    ])

    records = corpus.records_for_question(
        question_text="分析细胞呼吸实验",
        question_type="short_answer",
    )

    ids = {record["id"] for record in records}
    assert "difficulty-construct" in ids
    assert any(record_id.startswith("textbook-") for record_id in ids)
