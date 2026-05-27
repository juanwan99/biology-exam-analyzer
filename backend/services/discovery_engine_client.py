"""Discovery Engine client for exam-review evidence ranking and grounding."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import os
import time
from typing import Any
from urllib.parse import quote

import httpx


DISCOVERY_ENGINE_BASE_URL = "https://discoveryengine.googleapis.com/v1"
DISCOVERY_ENGINE_GROUNDED_GENERATION_BASE_URL = (
    "https://discoveryengine.googleapis.com/v1"
)
DEFAULT_LOCATION = "global"
DEFAULT_RANKING_CONFIG = "default_ranking_config"
DEFAULT_GROUNDING_CONFIG = "default_grounding_config"
DEFAULT_COLLECTION = "default_collection"
DEFAULT_SERVING_CONFIG = "default_search"
DEFAULT_BRANCH = "default_branch"
DEFAULT_RANKING_MODEL = "semantic-ranker-default@latest"
DEFAULT_GENERATION_MODEL = "gemini-2.5-flash"


class DiscoveryEngineError(RuntimeError):
    """Discovery Engine call failed and must not be hidden by fallback data."""


class DiscoveryEngineConfigError(DiscoveryEngineError):
    """Discovery Engine configuration is incomplete."""


@dataclass(frozen=True)
class DiscoveryEngineConfig:
    project_id: str
    credentials_file: str
    project_number: str | None = None
    data_store_id: str | None = None
    engine_id: str | None = None
    location: str = DEFAULT_LOCATION
    collection: str = DEFAULT_COLLECTION
    ranking_config: str = DEFAULT_RANKING_CONFIG
    grounding_config: str = DEFAULT_GROUNDING_CONFIG
    serving_config: str = DEFAULT_SERVING_CONFIG
    timeout: float = 90.0
    answer_query_qpm: float = 0.0
    answer_query_retries: int = 0
    answer_query_retry_base_delay: float = 0.0

    @classmethod
    def from_env(cls) -> "DiscoveryEngineConfig":
        project_id = (
            os.environ.get("DISCOVERY_ENGINE_PROJECT_ID", "").strip()
            or os.environ.get("LLM_PROJECT", "").strip()
        )
        if not project_id:
            raise DiscoveryEngineConfigError(
                "DISCOVERY_ENGINE_PROJECT_ID or LLM_PROJECT must be set"
            )

        credentials_file = (
            os.environ.get("DISCOVERY_ENGINE_CREDENTIALS", "").strip()
            or os.environ.get("LLM_SA_CREDENTIALS", "").strip()
            or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        )
        if not credentials_file:
            raise DiscoveryEngineConfigError(
                "DISCOVERY_ENGINE_CREDENTIALS or LLM_SA_CREDENTIALS must be set"
            )

        return cls(
            project_id=project_id,
            credentials_file=credentials_file,
            project_number=os.environ.get("DISCOVERY_ENGINE_PROJECT_NUMBER", "").strip()
            or None,
            data_store_id=os.environ.get("DISCOVERY_ENGINE_DATA_STORE_ID", "").strip()
            or None,
            engine_id=os.environ.get("DISCOVERY_ENGINE_ENGINE_ID", "").strip() or None,
            location=os.environ.get("DISCOVERY_ENGINE_LOCATION", DEFAULT_LOCATION).strip()
            or DEFAULT_LOCATION,
            collection=os.environ.get(
                "DISCOVERY_ENGINE_COLLECTION",
                DEFAULT_COLLECTION,
            ).strip()
            or DEFAULT_COLLECTION,
            ranking_config=os.environ.get(
                "DISCOVERY_ENGINE_RANKING_CONFIG",
                DEFAULT_RANKING_CONFIG,
            ).strip()
            or DEFAULT_RANKING_CONFIG,
            grounding_config=os.environ.get(
                "DISCOVERY_ENGINE_GROUNDING_CONFIG",
                DEFAULT_GROUNDING_CONFIG,
            ).strip()
            or DEFAULT_GROUNDING_CONFIG,
            serving_config=os.environ.get(
                "DISCOVERY_ENGINE_SERVING_CONFIG",
                DEFAULT_SERVING_CONFIG,
            ).strip()
            or DEFAULT_SERVING_CONFIG,
            timeout=float(os.environ.get("DISCOVERY_ENGINE_TIMEOUT", "90")),
            answer_query_qpm=float(os.environ.get("DISCOVERY_ENGINE_ANSWER_QPM", "12")),
            answer_query_retries=int(os.environ.get("DISCOVERY_ENGINE_ANSWER_RETRIES", "3")),
            answer_query_retry_base_delay=float(
                os.environ.get("DISCOVERY_ENGINE_ANSWER_RETRY_BASE_DELAY", "20")
            ),
        )


class DiscoveryEngineClient:
    _answer_query_lock: asyncio.Lock | None = None
    _answer_query_last_started_at: float = 0.0

    def __init__(
        self,
        config: DiscoveryEngineConfig | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        token_provider: Callable[[], str] | None = None,
    ):
        self.config = config or DiscoveryEngineConfig.from_env()
        self._http_client = http_client
        self._owns_http_client = http_client is None
        self._token_provider = token_provider

    async def aclose(self) -> None:
        if self._owns_http_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def rank_records(
        self,
        *,
        query: str,
        records: list[dict[str, Any]],
        top_n: int = 5,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            raise DiscoveryEngineConfigError("rank query must not be empty")
        if not records:
            raise DiscoveryEngineConfigError("rank records must not be empty")
        if top_n <= 0:
            raise DiscoveryEngineConfigError("rank top_n must be positive")

        payload = {
            "model": DEFAULT_RANKING_MODEL,
            "query": query,
            "topN": top_n,
            "records": records,
        }
        return await self._post_json(
            self._ranking_url(),
            payload,
            operation="rank",
        )

    async def check_grounding(
        self,
        *,
        answer: str,
        facts: list[dict[str, Any]],
        citation_threshold: float = 0.6,
    ) -> dict[str, Any]:
        if not answer or not answer.strip():
            raise DiscoveryEngineConfigError("grounding answer must not be empty")
        if not facts:
            raise DiscoveryEngineConfigError("grounding facts must not be empty")
        if citation_threshold < 0 or citation_threshold > 1:
            raise DiscoveryEngineConfigError("citation_threshold must be between 0 and 1")

        payload = {
            "answerCandidate": answer,
            "facts": facts,
            "groundingSpec": {"citationThreshold": citation_threshold},
        }
        return await self._post_json(
            self._grounding_url(),
            payload,
            operation="check_grounding",
        )

    async def generate_grounded_content(
        self,
        *,
        prompt: str,
        grounding_facts: list[dict[str, Any]],
        model_id: str = DEFAULT_GENERATION_MODEL,
        system_instruction: str | None = None,
        temperature: float = 0.0,
        top_p: float | None = None,
        top_k: int | None = None,
        max_output_tokens: int | None = None,
        language_code: str | None = "zh-CN",
    ) -> dict[str, Any]:
        if not prompt or not prompt.strip():
            raise DiscoveryEngineConfigError("grounded generation prompt must not be empty")
        if not grounding_facts:
            raise DiscoveryEngineConfigError("grounded generation facts must not be empty")
        model_id = str(model_id or "").strip()
        if not model_id:
            raise DiscoveryEngineConfigError("grounded generation model_id must not be empty")

        generation_spec: dict[str, Any] = {
            "modelId": model_id,
            "temperature": temperature,
        }
        if language_code:
            generation_spec["languageCode"] = language_code
        if top_p is not None:
            generation_spec["topP"] = top_p
        if top_k is not None:
            generation_spec["topK"] = top_k
        if max_output_tokens is not None:
            generation_spec["maxOutputTokens"] = max(1, int(max_output_tokens))

        payload: dict[str, Any] = {
            "contents": [{
                "role": "user",
                "parts": [{"text": prompt}],
            }],
            "groundingSpec": {
                "groundingSources": [{
                    "inlineSource": {
                        "groundingFacts": grounding_facts,
                    },
                }],
            },
            "generationSpec": generation_spec,
        }
        if system_instruction and system_instruction.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction.strip()}],
            }

        return await self._post_json(
            self._grounded_generation_url(),
            payload,
            operation="generate_grounded_content",
        )

    async def answer_query(
        self,
        *,
        query: str,
        user_pseudo_id: str | None = None,
        include_citations: bool = True,
        ignore_adversarial_query: bool = True,
        ignore_non_answer_seeking_query: bool = False,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            raise DiscoveryEngineConfigError("answer query must not be empty")
        if not self.config.engine_id:
            raise DiscoveryEngineConfigError(
                "DISCOVERY_ENGINE_ENGINE_ID is required for agent_search answer "
                "generation; create a Discovery Engine Data Store and Engine first."
            )

        payload: dict[str, Any] = {
            "query": {"text": query.strip()},
            "answerGenerationSpec": {
                "ignoreAdversarialQuery": ignore_adversarial_query,
                "ignoreNonAnswerSeekingQuery": ignore_non_answer_seeking_query,
                "includeCitations": include_citations,
            },
        }
        if user_pseudo_id:
            payload["userPseudoId"] = user_pseudo_id

        return await self._post_json(
            self._answer_url(),
            payload,
            operation="answer_query",
        )

    async def create_data_store(
        self,
        *,
        data_store_id: str,
        display_name: str,
    ) -> dict[str, Any]:
        data_store_id = _required_resource_id(data_store_id, "data_store_id")
        if not display_name or not display_name.strip():
            raise DiscoveryEngineConfigError("data store display_name must not be empty")
        payload = {
            "displayName": display_name.strip(),
            "industryVertical": "GENERIC",
            "solutionTypes": ["SOLUTION_TYPE_SEARCH"],
            "contentConfig": "CONTENT_REQUIRED",
        }
        return await self._post_json(
            f"{DISCOVERY_ENGINE_BASE_URL}/{self._collection_parent()}/dataStores",
            payload,
            operation="create_data_store",
            params={"dataStoreId": data_store_id},
        )

    async def get_data_store(self, *, data_store_id: str) -> dict[str, Any]:
        data_store_id = _required_resource_id(data_store_id, "data_store_id")
        return await self._get_json(
            f"{DISCOVERY_ENGINE_BASE_URL}/{self._data_store_name(data_store_id)}",
            operation="get_data_store",
        )

    async def list_data_stores(self) -> dict[str, Any]:
        cfg = self.config
        return await self._get_json(
            f"{DISCOVERY_ENGINE_BASE_URL}/projects/{cfg.project_id}/"
            f"locations/{cfg.location}/dataStores",
            operation="list_data_stores",
        )

    async def create_engine(
        self,
        *,
        engine_id: str,
        display_name: str,
        data_store_ids: list[str],
    ) -> dict[str, Any]:
        engine_id = _required_resource_id(engine_id, "engine_id")
        data_store_ids = [
            _required_resource_id(item, "data_store_id")
            for item in data_store_ids
        ]
        if not data_store_ids:
            raise DiscoveryEngineConfigError("engine data_store_ids must not be empty")
        if not display_name or not display_name.strip():
            raise DiscoveryEngineConfigError("engine display_name must not be empty")
        payload = {
            "displayName": display_name.strip(),
            "industryVertical": "GENERIC",
            "solutionType": "SOLUTION_TYPE_SEARCH",
            "searchEngineConfig": {
                "searchTier": "SEARCH_TIER_ENTERPRISE",
                "searchAddOns": ["SEARCH_ADD_ON_LLM"],
            },
            "dataStoreIds": data_store_ids,
        }
        return await self._post_json(
            f"{DISCOVERY_ENGINE_BASE_URL}/{self._collection_parent()}/engines",
            payload,
            operation="create_engine",
            params={"engineId": engine_id},
        )

    async def get_engine(self, *, engine_id: str) -> dict[str, Any]:
        engine_id = _required_resource_id(engine_id, "engine_id")
        return await self._get_json(
            f"{DISCOVERY_ENGINE_BASE_URL}/{self._collection_parent()}/engines/{engine_id}",
            operation="get_engine",
        )

    async def list_engines(self) -> dict[str, Any]:
        return await self._get_json(
            f"{DISCOVERY_ENGINE_BASE_URL}/{self._collection_parent()}/engines",
            operation="list_engines",
        )

    async def import_documents(
        self,
        *,
        data_store_id: str,
        documents: list[dict[str, Any]],
        reconciliation_mode: str = "INCREMENTAL",
    ) -> dict[str, Any]:
        data_store_id = _required_resource_id(data_store_id, "data_store_id")
        if not documents:
            raise DiscoveryEngineConfigError("import documents must not be empty")
        if len(documents) > 100:
            raise DiscoveryEngineConfigError("inline import supports at most 100 documents per request")
        payload = {
            "inlineSource": {"documents": documents},
            "reconciliationMode": reconciliation_mode,
        }
        return await self._post_json(
            f"{DISCOVERY_ENGINE_BASE_URL}/{self._data_store_name(data_store_id)}/"
            f"branches/{DEFAULT_BRANCH}/documents:import",
            payload,
            operation="import_documents",
        )

    async def get_operation(self, name: str) -> dict[str, Any]:
        if not name or not str(name).strip():
            raise DiscoveryEngineConfigError("operation name must not be empty")
        return await self._get_json(
            f"{DISCOVERY_ENGINE_BASE_URL}/{quote(str(name).strip(), safe='/')}",
            operation="get_operation",
        )

    def _ranking_url(self) -> str:
        cfg = self.config
        return (
            f"{DISCOVERY_ENGINE_BASE_URL}/projects/{cfg.project_id}/"
            f"locations/{cfg.location}/rankingConfigs/{cfg.ranking_config}:rank"
        )

    def _grounding_url(self) -> str:
        cfg = self.config
        return (
            f"{DISCOVERY_ENGINE_BASE_URL}/projects/{cfg.project_id}/"
            f"locations/{cfg.location}/groundingConfigs/{cfg.grounding_config}:check"
        )

    def _grounded_generation_url(self) -> str:
        cfg = self.config
        base_url = (
            os.environ.get("DISCOVERY_ENGINE_GENERATION_BASE_URL", "").strip()
            or DISCOVERY_ENGINE_GROUNDED_GENERATION_BASE_URL
        )
        return (
            f"{base_url}/projects/{cfg.project_number or cfg.project_id}/"
            f"locations/{cfg.location}:generateGroundedContent"
        )

    def _answer_url(self) -> str:
        cfg = self.config
        return (
            f"{DISCOVERY_ENGINE_BASE_URL}/projects/{cfg.project_id}/"
            f"locations/{cfg.location}/collections/{cfg.collection}/"
            f"engines/{cfg.engine_id}/servingConfigs/{cfg.serving_config}:answer"
        )

    def _collection_parent(self) -> str:
        cfg = self.config
        return (
            f"projects/{cfg.project_id}/locations/{cfg.location}/"
            f"collections/{cfg.collection}"
        )

    def _data_store_name(self, data_store_id: str) -> str:
        return f"{self._collection_parent()}/dataStores/{data_store_id}"

    async def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._access_token()
        client = self._http_client
        if client is None:
            client = httpx.AsyncClient(timeout=self.config.timeout)
            self._http_client = client

        attempts = 1
        if operation == "answer_query":
            attempts += max(0, int(self.config.answer_query_retries or 0))

        response: httpx.Response | None = None
        for attempt in range(attempts):
            if operation == "answer_query":
                await self._throttle_answer_query()
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Goog-User-Project": self.config.project_id,
                },
                json=payload,
                params=params,
                timeout=self.config.timeout,
            )
            if (
                operation == "answer_query"
                and response.status_code == 429
                and attempt < attempts - 1
            ):
                await asyncio.sleep(self._answer_query_retry_delay(response, attempt))
                continue
            break

        if response is None:
            raise DiscoveryEngineError(f"{operation} failed: no HTTP response")
        if response.status_code >= 400:
            detail = self._response_error_text(response)
            if (
                operation == "generate_grounded_content"
                and response.status_code == 404
                and "Method not found" in detail
            ):
                detail += (
                    "; Discovery Engine Grounded Generation is not enabled for "
                    "this project or the request is not using the required project "
                    "number. Ranking/Check Grounding can still work while "
                    "generateGroundedContent remains unavailable."
                )
            if operation == "answer_query" and response.status_code == 429:
                detail += (
                    f"; quota retry attempts={attempts}. "
                    "Lower DISCOVERY_ENGINE_ANSWER_QPM, increase quota, or retry later."
                )
            raise DiscoveryEngineError(
                f"{operation} failed: HTTP {response.status_code}: "
                f"{detail}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise DiscoveryEngineError(
                f"{operation} failed: response is not valid JSON"
            ) from exc

    async def _get_json(
        self,
        url: str,
        *,
        operation: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._access_token()
        client = self._http_client
        if client is None:
            client = httpx.AsyncClient(timeout=self.config.timeout)
            self._http_client = client
        response = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Goog-User-Project": self.config.project_id,
            },
            params=params,
            timeout=self.config.timeout,
        )
        if response.status_code >= 400:
            raise DiscoveryEngineError(
                f"{operation} failed: HTTP {response.status_code}: "
                f"{self._response_error_text(response)}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise DiscoveryEngineError(
                f"{operation} failed: response is not valid JSON"
            ) from exc

    def _access_token(self) -> str:
        if self._token_provider:
            token = self._token_provider()
            if not token:
                raise DiscoveryEngineConfigError("token_provider returned empty token")
            return token

        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import service_account
        except Exception as exc:
            raise DiscoveryEngineConfigError(
                "google-auth dependencies are required for Discovery Engine calls"
            ) from exc

        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.config.credentials_file,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            credentials.refresh(Request())
            return credentials.token
        except Exception as exc:
            raise DiscoveryEngineConfigError(
                f"Discovery Engine access token failed: {type(exc).__name__}: {exc}"
            ) from exc

    async def _throttle_answer_query(self) -> None:
        qpm = float(self.config.answer_query_qpm or 0.0)
        if qpm <= 0:
            return
        min_interval = 60.0 / qpm
        lock = self.__class__._answer_query_lock
        if lock is None:
            lock = asyncio.Lock()
            self.__class__._answer_query_lock = lock
        async with lock:
            now = time.monotonic()
            elapsed = now - self.__class__._answer_query_last_started_at
            delay = max(0.0, min_interval - elapsed)
            if delay > 0:
                await asyncio.sleep(delay)
            self.__class__._answer_query_last_started_at = time.monotonic()

    def _answer_query_retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), 120.0))
            except ValueError:
                pass
        base_delay = float(self.config.answer_query_retry_base_delay or 0.0)
        if base_delay <= 0:
            return 0.0
        return min(base_delay * (2 ** attempt), 120.0)

    @staticmethod
    def _response_error_text(response: httpx.Response) -> str:
        try:
            data = response.json()
            message = data.get("error", {}).get("message") if isinstance(data, dict) else None
            if message:
                return str(message)[:500]
        except ValueError:
            pass
        return response.text[:500]


def _required_resource_id(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DiscoveryEngineConfigError(f"{name} must not be empty")
    return text


__all__ = [
    "DiscoveryEngineClient",
    "DiscoveryEngineConfig",
    "DiscoveryEngineConfigError",
    "DiscoveryEngineError",
]
