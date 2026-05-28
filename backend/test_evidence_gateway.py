import pytest


class FakeDiscoveryClient:
    def __init__(
        self,
        *,
        rank_response=None,
        grounding_response=None,
        generation_response=None,
        answer_response=None,
    ):
        self.rank_response = rank_response or {}
        self.grounding_response = grounding_response or {}
        self.generation_response = generation_response or {}
        self.answer_response = answer_response or {}
        self.calls = []

    async def rank_records(self, **kwargs):
        self.calls.append(("rank_records", kwargs))
        return self.rank_response

    async def check_grounding(self, **kwargs):
        self.calls.append(("check_grounding", kwargs))
        return self.grounding_response

    async def generate_grounded_content(self, **kwargs):
        self.calls.append(("generate_grounded_content", kwargs))
        return self.generation_response

    async def answer_query(self, **kwargs):
        self.calls.append(("answer_query", kwargs))
        return self.answer_response


@pytest.mark.asyncio
async def test_rank_evidence_returns_ranked_records_and_audit():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(rank_response={
        "records": [
            {"id": "k2", "score": 0.93},
            {"id": "k1", "score": 0.78},
        ]
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.rank_evidence(
        query="这道题考查哪些知识点？",
        candidates=[{"id": "k1", "title": "遗传", "content": "分离定律"}],
        top_n=2,
    )

    assert result["status"] == "ok"
    assert result["ranked_count"] == 2
    assert result["records"][0]["id"] == "k2"
    assert result["metadata"]["provider"] == "discovery_engine"
    assert client.calls[0][1]["top_n"] == 2


@pytest.mark.asyncio
async def test_check_grounding_marks_low_support_as_needs_review():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(grounding_response={
        "supportScore": 0.41,
        "claims": [{"claimText": "本题难度中等"}],
        "citedChunks": [],
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.check_grounding(
        answer="本题难度中等。",
        facts=[{"factText": "实际涉及复杂遗传推理。"}],
        min_support=0.6,
    )

    assert result["status"] == "needs_review"
    assert result["support_score"] == 0.41
    assert result["claim_count"] == 1
    assert result["cited_chunk_count"] == 0


@pytest.mark.asyncio
async def test_check_grounding_accepts_supported_answer():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(grounding_response={
        "supportScore": 0.86,
        "claims": [{"claimText": "考查分离定律"}],
        "citedChunks": [{"chunkText": "一对相对性状杂交"}],
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.check_grounding(
        answer="本题考查分离定律。",
        facts=[{"factText": "题干包含一对相对性状杂交。"}],
        min_support=0.6,
    )

    assert result["status"] == "ok"
    assert result["support_score"] == 0.86
    assert result["cited_chunk_count"] == 1


@pytest.mark.asyncio
async def test_generate_grounded_content_extracts_text_and_audit():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(generation_response={
        "candidates": [{
            "content": {"parts": [{"text": "{\"analysis\":\"ok\"}"}]},
            "groundingScore": 0.88,
        }],
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.generate_grounded_content(
        prompt="审题",
        grounding_facts=[{"factText": "题目文本"}],
        model_id="gemini-3.1-pro-preview",
        max_output_tokens=1024,
    )

    assert result["status"] == "ok"
    assert result["text"] == "{\"analysis\":\"ok\"}"
    assert result["metadata"]["operation"] == "generate_grounded_content"
    assert client.calls[0][0] == "generate_grounded_content"


@pytest.mark.asyncio
async def test_answer_query_extracts_answer_and_citation_count():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(answer_response={
        "answer": {
            "answerText": "本题考查孟德尔分离定律。",
            "citations": [{"startIndex": 0, "endIndex": 5}],
        }
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.answer_query(
        query="这道题考查哪些知识点？",
        user_pseudo_id="exam-review",
    )

    assert result["status"] == "ok"
    assert result["text"] == "本题考查孟德尔分离定律。"
    assert result["citation_count"] == 1
    assert result["metadata"]["operation"] == "answer_query"
    assert client.calls[0][0] == "answer_query"


@pytest.mark.asyncio
async def test_answer_query_missing_text_is_structured_error():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(answer_response={"answer": {"citations": []}})
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.answer_query(query="审题")

    assert result["status"] == "error"
    assert result["error"] == "answer_query response missing answer text"
    assert result["metadata"]["operation"] == "answer_query"


@pytest.mark.asyncio
async def test_answer_query_skipped_reason_is_structured_error():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(answer_response={
        "answer": {
            "state": "SUCCEEDED",
            "answerText": "无法为您的搜索查询生成摘要。下面是一些搜索结果。",
            "answerSkippedReasons": ["OUT_OF_DOMAIN_QUERY_IGNORED"],
        }
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.answer_query(query="审题")

    assert result["status"] == "error"
    assert result["skipped_reasons"] == ["OUT_OF_DOMAIN_QUERY_IGNORED"]
    assert "OUT_OF_DOMAIN_QUERY_IGNORED" in result["error"]


@pytest.mark.asyncio
async def test_answer_query_requires_citations_when_requested():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(answer_response={
        "answer": {
            "answerText": "本题需要关注评分边界。",
            "citations": [],
        }
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.answer_query(query="审题", include_citations=True)

    assert result["status"] == "error"
    assert result["error"] == "answer_query response missing citations"
    assert result["metadata"]["error"] == "missing_citations"


@pytest.mark.asyncio
async def test_check_grounding_missing_support_score_is_structured_error():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(grounding_response={"claims": []})
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.check_grounding(
        answer="本题考查分离定律。",
        facts=[{"factText": "题干包含杂交。"}],
    )

    assert result["status"] == "error"
    assert result["support_score"] == 0.0
    assert result["error"] == "check_grounding response missing supportScore"
    assert result["raw"] == {"claims": []}


@pytest.mark.asyncio
async def test_check_grounding_uses_exact_fact_match_for_unchecked_short_claim():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(grounding_response={
        "claims": [
            {
                "claimText": "科学思维中演绎与推理包含18题。",
                "groundingCheckRequired": False,
            }
        ]
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.check_grounding(
        answer="科学思维中演绎与推理包含18题。",
        facts=[
            {
                "factText": "competency_evidence: 科学思维中演绎与推理包含18题；生命观念中结构与功能观包含14题。",
                "attributes": {"source": "report.evidence_card.competency"},
            }
        ],
    )

    assert result["status"] == "ok"
    assert result["support_score"] == 1.0
    assert result["metadata"]["provider"] == "deterministic_fact_match"
    assert result["metadata"]["matched_source"] == "report.evidence_card.competency"


@pytest.mark.asyncio
async def test_check_grounding_uses_exact_fact_match_when_discovery_score_is_low():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(grounding_response={
        "supportScore": 0.57,
        "claims": [
            {
                "claimText": "科学思维占比最高，为44.8%。",
                "groundingCheckRequired": True,
            }
        ],
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.check_grounding(
        answer="科学思维占比最高，为44.8%。",
        facts=[
            {
                "factText": "competency_evidence: 科学思维占比最高，为44.8%；生命观念占比为40.2%。",
                "attributes": {"source": "report.evidence_card.competency"},
            }
        ],
    )

    assert result["status"] == "ok"
    assert result["support_score"] == 1.0
    assert result["metadata"]["discovery_support_score"] == 0.57


@pytest.mark.asyncio
async def test_check_grounding_exact_match_normalizes_fine_grained_wording():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(grounding_response={
        "claims": [
            {
                "claimText": "科学探究细分中，得出结论包含7题。",
                "groundingCheckRequired": False,
            }
        ]
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.check_grounding(
        answer="科学探究细分中，得出结论包含7题。",
        facts=[
            {
                "factText": "competency_evidence: 科学探究中得出结论包含7题。",
                "attributes": {"source": "report.evidence_card.competency"},
            }
        ],
    )

    assert result["status"] == "ok"
    assert result["metadata"]["provider"] == "deterministic_fact_match"


@pytest.mark.asyncio
async def test_check_grounding_does_not_exact_match_when_fact_absent():
    from services.evidence_gateway import EvidenceGateway

    client = FakeDiscoveryClient(grounding_response={
        "claims": [
            {
                "claimText": "科学思维中演绎与推理包含18题。",
                "groundingCheckRequired": False,
            }
        ]
    })
    gateway = EvidenceGateway(discovery_client=client)

    result = await gateway.check_grounding(
        answer="科学思维中演绎与推理包含18题。",
        facts=[{"factText": "competency_evidence: 科学思维中演绎与推理包含12题。"}],
    )

    assert result["status"] == "error"
    assert result["metadata"]["error"] == "missing_supportScore"
