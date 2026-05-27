import pytest
import httpx


@pytest.mark.asyncio
async def test_rank_records_posts_expected_request():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
    )

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"records": [{"id": "k1", "score": 0.91}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        result = await client.rank_records(
            query="这道题考查哪些核心知识点？",
            records=[{"id": "k1", "title": "遗传规律", "content": "分离定律"}],
            top_n=5,
        )

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/rankingConfigs/default_ranking_config:rank"
    )
    assert captured["headers"]["authorization"] == "Bearer test-token"
    assert captured["headers"]["x-goog-user-project"] == "my-project"
    assert captured["json"] == {
        "model": "semantic-ranker-default@latest",
        "query": "这道题考查哪些核心知识点？",
        "topN": 5,
        "records": [{"id": "k1", "title": "遗传规律", "content": "分离定律"}],
    }
    assert result["records"][0]["score"] == 0.91


@pytest.mark.asyncio
async def test_check_grounding_posts_expected_request():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
    )

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={
            "supportScore": 0.82,
            "claims": [{"claimText": "本题考查分离定律"}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        result = await client.check_grounding(
            answer="本题考查孟德尔分离定律，难度中等。",
            facts=[{"factText": "题干包含一对相对性状杂交。", "attributes": {"source": "rubric"}}],
            citation_threshold=0.7,
        )

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/groundingConfigs/default_grounding_config:check"
    )
    assert captured["json"] == {
        "answerCandidate": "本题考查孟德尔分离定律，难度中等。",
        "facts": [{"factText": "题干包含一对相对性状杂交。", "attributes": {"source": "rubric"}}],
        "groundingSpec": {"citationThreshold": 0.7},
    }
    assert result["supportScore"] == 0.82


@pytest.mark.asyncio
async def test_generate_grounded_content_posts_expected_request():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
    )

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={
            "candidates": [{
                "content": {"parts": [{"text": "{\"ok\": true}"}]},
                "groundingScore": 0.91,
            }],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(
                project_id="my-project",
                project_number="123456",
                credentials_file="/tmp/sa.json",
            ),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        result = await client.generate_grounded_content(
            prompt="只返回 JSON",
            grounding_facts=[{"factText": "题目文本", "attributes": {"source": "question"}}],
            model_id="gemini-3.1-pro-preview",
            system_instruction="你是审题专家",
            max_output_tokens=1024,
        )

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/123456/"
        "locations/global:generateGroundedContent"
    )
    assert captured["json"]["generationSpec"]["modelId"] == "gemini-3.1-pro-preview"
    assert captured["json"]["generationSpec"]["maxOutputTokens"] == 1024
    assert captured["json"]["groundingSpec"]["groundingSources"][0]["inlineSource"]["groundingFacts"][0]["factText"] == "题目文本"
    assert result["candidates"][0]["groundingScore"] == 0.91


@pytest.mark.asyncio
async def test_answer_query_posts_expected_request():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
    )

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={
            "answer": {
                "answerText": "本题考查孟德尔分离定律。",
                "citations": [{"startIndex": 0, "endIndex": 4}],
            }
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(
                project_id="my-project",
                credentials_file="/tmp/sa.json",
                engine_id="biology-review-engine",
            ),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        result = await client.answer_query(
            query="这道题考查哪些核心知识点？",
            user_pseudo_id="exam-review-smoke",
        )

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/collections/default_collection/engines/biology-review-engine/"
        "servingConfigs/default_search:answer"
    )
    assert captured["json"] == {
        "query": {"text": "这道题考查哪些核心知识点？"},
        "answerGenerationSpec": {
            "ignoreAdversarialQuery": True,
            "ignoreNonAnswerSeekingQuery": False,
            "includeCitations": True,
        },
        "userPseudoId": "exam-review-smoke",
    }
    assert result["answer"]["answerText"] == "本题考查孟德尔分离定律。"


@pytest.mark.asyncio
async def test_answer_query_requires_engine_id():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
        DiscoveryEngineConfigError,
    )

    client = DiscoveryEngineClient(
        DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
        token_provider=lambda: "test-token",
    )

    with pytest.raises(DiscoveryEngineConfigError, match="DISCOVERY_ENGINE_ENGINE_ID"):
        await client.answer_query(query="审题")


@pytest.mark.asyncio
async def test_answer_query_retries_quota_429_before_failing_closed():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
    )

    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={
                "error": {"message": "Quota exceeded for answer_query"}
            })
        return httpx.Response(200, json={
            "answer": {
                "answerText": "审题证据可用于判断评分边界。",
                "citations": [{"startIndex": 0, "endIndex": 4}],
            }
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(
                project_id="my-project",
                credentials_file="/tmp/sa.json",
                engine_id="biology-review-engine",
                answer_query_retries=1,
                answer_query_retry_base_delay=0,
            ),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        result = await client.answer_query(query="审题证据如何用于评分边界？")

    assert calls == 2
    assert result["answer"]["answerText"] == "审题证据可用于判断评分边界。"


@pytest.mark.asyncio
async def test_answer_query_quota_error_reports_tuning_hint():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
        DiscoveryEngineError,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={
            "error": {"message": "Quota exceeded for answer_query"}
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(
                project_id="my-project",
                credentials_file="/tmp/sa.json",
                engine_id="biology-review-engine",
                answer_query_retries=1,
                answer_query_retry_base_delay=0,
            ),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        with pytest.raises(DiscoveryEngineError, match="DISCOVERY_ENGINE_ANSWER_QPM"):
            await client.answer_query(query="审题证据如何用于评分边界？")


@pytest.mark.asyncio
async def test_create_data_store_posts_expected_request():
    from services.discovery_engine_client import DiscoveryEngineClient, DiscoveryEngineConfig

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"name": "operations/create-data-store"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        result = await client.create_data_store(
            data_store_id="biology-review-kb",
            display_name="Biology Review KB",
        )

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/collections/default_collection/dataStores"
        "?dataStoreId=biology-review-kb"
    )
    assert captured["json"] == {
        "displayName": "Biology Review KB",
        "industryVertical": "GENERIC",
        "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
        "contentConfig": "CONTENT_REQUIRED",
    }
    assert result["name"] == "operations/create-data-store"


@pytest.mark.asyncio
async def test_get_data_store_uses_collection_path():
    from services.discovery_engine_client import DiscoveryEngineClient, DiscoveryEngineConfig

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"name": "data-store"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )
        result = await client.get_data_store(data_store_id="biology-review-kb")

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/collections/default_collection/dataStores/biology-review-kb"
    )
    assert result["name"] == "data-store"


@pytest.mark.asyncio
async def test_list_data_stores_uses_location_inventory_path():
    from services.discovery_engine_client import DiscoveryEngineClient, DiscoveryEngineConfig

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"dataStores": [{"name": "data-store"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )
        result = await client.list_data_stores()

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/dataStores"
    )
    assert result["dataStores"][0]["name"] == "data-store"


@pytest.mark.asyncio
async def test_create_engine_posts_expected_request():
    from services.discovery_engine_client import DiscoveryEngineClient, DiscoveryEngineConfig

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"name": "operations/create-engine"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        result = await client.create_engine(
            engine_id="biology-review-engine",
            display_name="Biology Review Engine",
            data_store_ids=["biology-review-kb"],
        )

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/collections/default_collection/engines"
        "?engineId=biology-review-engine"
    )
    assert captured["json"]["solutionType"] == "SOLUTION_TYPE_SEARCH"
    assert captured["json"]["searchEngineConfig"]["searchTier"] == "SEARCH_TIER_ENTERPRISE"
    assert captured["json"]["searchEngineConfig"]["searchAddOns"] == ["SEARCH_ADD_ON_LLM"]
    assert captured["json"]["dataStoreIds"] == ["biology-review-kb"]
    assert result["name"] == "operations/create-engine"


@pytest.mark.asyncio
async def test_get_engine_uses_collection_path():
    from services.discovery_engine_client import DiscoveryEngineClient, DiscoveryEngineConfig

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"name": "engine"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )
        result = await client.get_engine(engine_id="biology-review-engine")

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/collections/default_collection/engines/biology-review-engine"
    )
    assert result["name"] == "engine"


@pytest.mark.asyncio
async def test_list_engines_uses_collection_path():
    from services.discovery_engine_client import DiscoveryEngineClient, DiscoveryEngineConfig

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"engines": [{"name": "engine"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )
        result = await client.list_engines()

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/collections/default_collection/engines"
    )
    assert result["engines"][0]["name"] == "engine"


@pytest.mark.asyncio
async def test_import_documents_posts_inline_documents():
    from services.discovery_engine_client import DiscoveryEngineClient, DiscoveryEngineConfig

    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"name": "operations/import-documents"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        result = await client.import_documents(
            data_store_id="biology-review-kb",
            documents=[{"id": "rubric-1", "structData": {"title": "评分边界"}}],
        )

    assert captured["url"] == (
        "https://discoveryengine.googleapis.com/v1/projects/my-project/"
        "locations/global/collections/default_collection/dataStores/biology-review-kb/"
        "branches/default_branch/documents:import"
    )
    assert captured["json"] == {
        "inlineSource": {"documents": [{"id": "rubric-1", "structData": {"title": "评分边界"}}]},
        "reconciliationMode": "INCREMENTAL",
    }
    assert result["name"] == "operations/import-documents"


@pytest.mark.asyncio
async def test_discovery_engine_http_error_fails_closed_with_context():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
        DiscoveryEngineError,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "permission denied"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(project_id="my-project", credentials_file="/tmp/sa.json"),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        with pytest.raises(DiscoveryEngineError, match="rank failed.*403.*permission denied"):
            await client.rank_records(
                query="query",
                records=[{"id": "k1", "title": "t", "content": "c"}],
            )


@pytest.mark.asyncio
async def test_grounded_generation_404_explains_unavailable_method():
    from services.discovery_engine_client import (
        DiscoveryEngineClient,
        DiscoveryEngineConfig,
        DiscoveryEngineError,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "Method not found."}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = DiscoveryEngineClient(
            DiscoveryEngineConfig(
                project_id="my-project",
                project_number="123456",
                credentials_file="/tmp/sa.json",
            ),
            http_client=http_client,
            token_provider=lambda: "test-token",
        )

        with pytest.raises(DiscoveryEngineError, match="Grounded Generation is not enabled"):
            await client.generate_grounded_content(
                prompt="prompt",
                grounding_facts=[{"factText": "fact"}],
                model_id="gemini-2.5-flash",
            )


def test_config_from_env_prefers_discovery_engine_vars(monkeypatch):
    from services.discovery_engine_client import DiscoveryEngineConfig

    monkeypatch.setenv("DISCOVERY_ENGINE_PROJECT_ID", "search-project")
    monkeypatch.setenv("LLM_PROJECT", "llm-project")
    monkeypatch.setenv("DISCOVERY_ENGINE_CREDENTIALS", "/secure/search-sa.json")
    monkeypatch.setenv("DISCOVERY_ENGINE_PROJECT_NUMBER", "123456")
    monkeypatch.setenv("DISCOVERY_ENGINE_DATA_STORE_ID", "data-store-a")
    monkeypatch.setenv("DISCOVERY_ENGINE_ENGINE_ID", "engine-a")
    monkeypatch.setenv("DISCOVERY_ENGINE_COLLECTION", "collection-a")
    monkeypatch.setenv("DISCOVERY_ENGINE_SERVING_CONFIG", "serving-a")
    monkeypatch.setenv("LLM_SA_CREDENTIALS", "/secure/llm-sa.json")

    config = DiscoveryEngineConfig.from_env()

    assert config.project_id == "search-project"
    assert config.project_number == "123456"
    assert config.data_store_id == "data-store-a"
    assert config.engine_id == "engine-a"
    assert config.collection == "collection-a"
    assert config.serving_config == "serving-a"
    assert config.credentials_file == "/secure/search-sa.json"
    assert config.location == "global"
    assert config.answer_query_qpm == 12
    assert config.answer_query_retries == 3
    assert config.answer_query_retry_base_delay == 20


def test_config_from_env_requires_project_id(monkeypatch):
    from services.discovery_engine_client import DiscoveryEngineConfigError, DiscoveryEngineConfig

    monkeypatch.delenv("DISCOVERY_ENGINE_PROJECT_ID", raising=False)
    monkeypatch.delenv("LLM_PROJECT", raising=False)

    with pytest.raises(DiscoveryEngineConfigError, match="DISCOVERY_ENGINE_PROJECT_ID"):
        DiscoveryEngineConfig.from_env()
