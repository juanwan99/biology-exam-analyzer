"""LLM 统一客户端测试 — fallback 链 + 格式转换。"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import httpx


# ── 辅助 ──────────────────────────────────────────────────────────

def _mock_providers(count=3):
    """生成 N 个测试 provider 配置。"""
    formats = ["anthropic", "openai_responses", "openai_chat"]
    return [
        {
            "name": f"provider-{i}",
            "model": f"model-{i}",
            "api_format": formats[i],
            "base_url_env": None,
            "base_url_default": f"https://api-{i}.test/v1",
            "key_env": f"TEST_KEY_{i}",
            "max_tokens": 8192,
            "semaphore_limit": 3,
            "retry_count": 1,
        }
        for i in range(count)
    ]


_FAKE_REQ = httpx.Request("POST", "https://test.local/v1")


def _anthropic_ok():
    return httpx.Response(200, json={
        "content": [{"text": "hello from anthropic"}],
        "stop_reason": "end_turn",
    }, request=_FAKE_REQ)


def _responses_ok():
    return httpx.Response(200, json={
        "output": [{"content": [{"type": "output_text", "text": "hello from gpt"}]}],
        "status": "completed",
    }, request=_FAKE_REQ)


def _chat_ok():
    return httpx.Response(200, json={
        "choices": [{"message": {"content": "hello from gemini"}, "finish_reason": "stop"}],
    }, request=_FAKE_REQ)


def _error(status):
    return httpx.Response(status, json={"error": "fail"}, request=_FAKE_REQ)


# ── Config 测试 ───────────────────────────────────────────────────

class TestLlmConfig:
    def test_get_providers_filters_missing_keys(self):
        import os, tempfile
        from llm_config import get_providers, PROVIDERS
        # Find a key_env provider (skip sa_file_env like vertex)
        key_providers = [p for p in PROVIDERS if p.get("key_env")]
        if key_providers:
            env = {key_providers[0]["key_env"]: "test-key"}
            with patch.dict(os.environ, env, clear=False):
                result = get_providers()
                assert len(result) >= 1
        else:
            # All providers use sa_file_env; test with temp SA file
            sa_provider = [p for p in PROVIDERS if p.get("sa_file_env")][0]
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                f.write(b"{}")
                sa_path = f.name
            env = {sa_provider["sa_file_env"]: sa_path}
            with patch.dict(os.environ, env, clear=False):
                result = get_providers()
                assert len(result) >= 1
            import os as _os; _os.unlink(sa_path)

    def test_get_providers_empty_when_no_keys(self):
        import os
        from llm_config import get_providers, PROVIDERS
        clear = {}
        for p in PROVIDERS:
            if p.get("key_env"):
                clear[p["key_env"]] = ""
            if p.get("sa_file_env"):
                clear[p["sa_file_env"]] = ""
        with patch.dict(os.environ, clear):
            result = get_providers()
            assert result == []


# ── Fallback 测试 ─────────────────────────────────────────────────

class TestFallback:
    @pytest.fixture(autouse=True)
    def setup_env(self):
        import os
        env = {"TEST_KEY_0": "k0", "TEST_KEY_1": "k1", "TEST_KEY_2": "k2"}
        with patch.dict(os.environ, env):
            yield

    @pytest.mark.asyncio
    async def test_first_provider_success(self):
        from llm_client import llm_call
        providers = _mock_providers()
        with patch("llm_client._http_post", new_callable=AsyncMock, return_value=_anthropic_ok()):
            with patch("llm_client.get_providers", return_value=providers):
                result = await llm_call([{"role": "user", "content": "hi"}])
                assert "hello" in result

    @pytest.mark.asyncio
    async def test_fallback_to_second(self):
        from llm_client import llm_call
        providers = _mock_providers()
        call_count = 0

        async def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise httpx.HTTPStatusError("fail", request=MagicMock(), response=_error(500))
            return _responses_ok()

        with patch("llm_client._http_post", side_effect=mock_post):
            with patch("llm_client.get_providers", return_value=providers):
                result = await llm_call([{"role": "user", "content": "hi"}])
                assert "hello" in result

    @pytest.mark.asyncio
    async def test_all_fail(self):
        from llm_client import llm_call, AllProvidersFailed
        providers = _mock_providers()

        async def mock_post(url, **kwargs):
            raise httpx.HTTPStatusError("fail", request=MagicMock(), response=_error(500))

        with patch("llm_client._http_post", side_effect=mock_post):
            with patch("llm_client.get_providers", return_value=providers):
                with pytest.raises(AllProvidersFailed):
                    await llm_call([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_no_fallback_on_400(self):
        from llm_client import llm_call
        providers = _mock_providers()

        async def mock_post(url, **kwargs):
            raise httpx.HTTPStatusError("bad", request=MagicMock(), response=_error(400))

        with patch("llm_client._http_post", side_effect=mock_post):
            with patch("llm_client.get_providers", return_value=providers):
                with pytest.raises(httpx.HTTPStatusError):
                    await llm_call([{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_403_model_not_found_does_fallback(self):
        from llm_client import llm_call
        providers = _mock_providers()
        call_urls = []

        async def mock_post(url, **kwargs):
            call_urls.append(url)
            if "api-0" in url:
                resp = httpx.Response(403, json={"error": {"message": "model not found"}}, request=_FAKE_REQ)
                raise httpx.HTTPStatusError("forbidden", request=MagicMock(), response=resp)
            return _responses_ok()

        with patch("llm_client._http_post", side_effect=mock_post):
            with patch("llm_client.get_providers", return_value=providers):
                result = await llm_call([{"role": "user", "content": "hi"}])
                assert "hello" in result
                assert any("api-1" in u for u in call_urls)


# ── 格式转换测试 ──────────────────────────────────────────────────

class TestFormatConversion:
    def test_anthropic_text_only(self):
        from llm_client import _build_request_body
        provider = _mock_providers()[0]
        messages = [{"role": "user", "content": "hello"}]
        body = _build_request_body(provider, messages, 4096, 0)
        assert body["model"] == "model-0"
        assert body["messages"][0]["content"][0]["type"] == "text"

    def test_anthropic_with_image(self):
        from llm_client import _build_request_body
        provider = _mock_providers()[0]
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ"}}
        ]}]
        body = _build_request_body(provider, messages, 4096, 0)
        content = body["messages"][0]["content"]
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image"
        assert content[1]["source"]["type"] == "base64"

    def test_responses_text_only(self):
        from llm_client import _build_request_body
        provider = _mock_providers()[1]
        messages = [{"role": "user", "content": "hello"}]
        body = _build_request_body(provider, messages, 4096, 0)
        assert body["model"] == "model-1"
        assert "input" in body

    def test_chat_text_only(self):
        from llm_client import _build_request_body
        provider = _mock_providers()[2]
        messages = [{"role": "user", "content": "hello"}]
        body = _build_request_body(provider, messages, 4096, 0)
        assert body["model"] == "model-2"
        assert body["messages"][0]["content"] == "hello"


class TestResponseExtraction:
    def test_extract_anthropic(self):
        from llm_client import _extract_text
        data = {"content": [{"text": "result"}], "stop_reason": "end_turn"}
        assert _extract_text("anthropic", data) == "result"

    def test_extract_responses(self):
        from llm_client import _extract_text
        data = {"output": [{"content": [{"type": "output_text", "text": "result"}]}]}
        assert _extract_text("openai_responses", data) == "result"

    def test_extract_chat(self):
        from llm_client import _extract_text
        data = {"choices": [{"message": {"content": "result"}}]}
        assert _extract_text("openai_chat", data) == "result"
