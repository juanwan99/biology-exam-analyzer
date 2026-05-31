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
        "choices": [{"message": {"content": "hello from deepseek"}, "finish_reason": "stop"}],
    }, request=_FAKE_REQ)


def _error(status):
    return httpx.Response(status, json={"error": "fail"}, request=_FAKE_REQ)


# ── Config 测试 ───────────────────────────────────────────────────

class TestLlmConfig:
    def test_get_providers_filters_missing_keys(self):
        import os, tempfile
        from llm_config import get_providers, PROVIDERS
        # Find a key_env provider
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
            for env_name in p.get("key_envs") or []:
                clear[env_name] = ""
            if p.get("sa_file_env"):
                clear[p["sa_file_env"]] = ""
        with patch.dict(os.environ, clear):
            result = get_providers()
            assert result == []

    def test_native_provider_requires_sdk_module(self):
        import os
        import tempfile
        from llm_config import get_providers

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b"{}")
            sa_path = f.name
        env = {
            "LLM_SA_CREDENTIALS": sa_path,
            "LLM_SDK_MODULE": "",
            "LLM_EXAM_REVIEW_FLASH_MODEL": "flash-model-preview",
            "LLM_EXAM_REVIEW_PRO_MODEL": "pro-model-preview",
            "DEEPSEEK_API_KEY": "",
        }
        try:
            with patch.dict(os.environ, env, clear=False):
                result = get_providers()
                assert all(provider.get("api_format") != "native_sdk" for provider in result)
        finally:
            os.unlink(sa_path)





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
        from llm_client import get_last_llm_call_metadata, llm_call
        providers = _mock_providers()
        with patch("llm_client._http_post", new_callable=AsyncMock, return_value=_anthropic_ok()):
            with patch("llm_client.get_providers", return_value=providers):
                result = await llm_call([{"role": "user", "content": "hi"}])
                assert "hello" in result
                metadata = get_last_llm_call_metadata()
                assert metadata["status"] == "ok"
                assert metadata["provider"] == "provider-0"
                assert metadata["fallback_count"] == 0

    @pytest.mark.asyncio
    async def test_llm_call_records_model_policy_metadata(self):
        from llm_client import get_last_llm_call_metadata, llm_call
        providers = _mock_providers(1)
        providers[0]["model_role"] = "flash"
        providers[0]["model_policy"] = "exam-review-primary"

        with patch("llm_client._http_post", new_callable=AsyncMock, return_value=_anthropic_ok()):
            with patch("llm_client.get_providers", return_value=providers) as get_providers:
                await llm_call(
                    [{"role": "user", "content": "hi"}],
                    purpose="question_split",
                    model="flash-model-preview",
                )
                get_providers.assert_called_once_with(
                    purpose="question_split",
                    model_override="flash-model-preview",
                    requires_images=False,
                )
                metadata = get_last_llm_call_metadata()
                assert metadata["purpose"] == "question_split"
                assert metadata["model_role"] == "flash"
                assert metadata["model_policy"] == "exam-review-primary"

    @pytest.mark.asyncio
    async def test_app_builder_alias_uses_model_generation_with_evidence_channel_metadata(self):
        from llm_client import (
            get_last_llm_call_metadata,
            llm_call,
            reset_llm_review_channel,
            set_llm_review_channel,
        )

        token = set_llm_review_channel("app_builder")
        try:
            with patch("llm_client._http_post", return_value=_anthropic_ok()):
                with patch("llm_client.get_providers", return_value=_mock_providers(1)) as get_providers:
                    result = await llm_call(
                        [{"role": "user", "content": "只返回 JSON"}],
                        purpose="question_analysis",
                    )
        finally:
            reset_llm_review_channel(token)

        assert result == "hello from anthropic"
        get_providers.assert_called_once()
        metadata = get_last_llm_call_metadata()
        assert metadata["provider"] == "provider-0"
        assert metadata["review_channel"] == "evidence"
        assert metadata.get("operation") is None

    @pytest.mark.asyncio
    async def test_grounded_generation_channel_uses_evidence_grounded_generation(self, monkeypatch):
        monkeypatch.setenv("LLM_EXAM_REVIEW_FLASH_MODEL", "flash-model-preview")
        monkeypatch.setenv("LLM_EXAM_REVIEW_PRO_MODEL", "pro-model-preview")
        from llm_client import (
            get_last_llm_call_metadata,
            llm_call,
            reset_llm_review_channel,
            set_llm_review_channel,
        )

        class FakeGateway:
            def __init__(self):
                self.calls = []

            async def generate_grounded_content(self, **kwargs):
                self.calls.append(kwargs)
                return {
                    "text": "{\"ok\": true}",
                    "grounding_score": 0.9,
                    "metadata": {
                        "provider": "evidence_service",
                        "operation": "generate_grounded_content",
                    },
                }

        gateway = FakeGateway()
        token = set_llm_review_channel("grounded_generation")
        try:
            with patch("llm_client._get_evidence_gateway", return_value=gateway):
                with patch("llm_client.get_providers") as get_providers:
                    result = await llm_call(
                        [{"role": "user", "content": "只返回 JSON"}],
                        purpose="question_analysis",
                    )
        finally:
            reset_llm_review_channel(token)

        assert result == "{\"ok\": true}"
        assert get_providers.call_count == 0
        assert gateway.calls[0]["model_id"] == "pro-model-preview"
        metadata = get_last_llm_call_metadata()
        assert metadata["provider"] == "evidence_service"
        assert metadata["operation"] == "generate_grounded_content"
        assert metadata["review_channel"] == "grounded_generation"
        assert metadata["model_policy"] == "exam-review-app-builder-grounded-generation"

    @pytest.mark.asyncio
    async def test_grounded_generation_channel_rejects_image_inputs_without_model_fallback(self):
        from llm_client import llm_call, reset_llm_review_channel, set_llm_review_channel

        token = set_llm_review_channel("grounded_generation")
        try:
            with patch("llm_client.get_providers") as get_providers:
                with pytest.raises(RuntimeError, match="does not support image_url"):
                    await llm_call([{"role": "user", "content": [
                        {"type": "text", "text": "describe"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abcd"}},
                    ]}])
        finally:
            reset_llm_review_channel(token)

        assert get_providers.call_count == 0

    @pytest.mark.asyncio
    async def test_fallback_to_second(self):
        from llm_client import get_last_llm_call_metadata, llm_call
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
                metadata = get_last_llm_call_metadata()
                assert metadata["status"] == "ok"
                assert metadata["provider"] == "provider-1"
                assert metadata["fallback_count"] == 1
                assert metadata["provider_errors"][0]["provider"] == "provider-0"

    @pytest.mark.asyncio
    async def test_all_fail(self):
        from llm_client import llm_call, AllProvidersFailed, get_last_llm_call_metadata
        providers = _mock_providers()

        async def mock_post(url, **kwargs):
            raise httpx.HTTPStatusError("fail", request=MagicMock(), response=_error(500))

        with patch("llm_client._http_post", side_effect=mock_post):
            with patch("llm_client.get_providers", return_value=providers):
                with pytest.raises(AllProvidersFailed):
                    await llm_call([{"role": "user", "content": "hi"}])
                metadata = get_last_llm_call_metadata()
                assert metadata["status"] == "provider_failed"
                assert metadata["fallback_count"] == len(providers)

    @pytest.mark.asyncio
    async def test_400_records_body_in_provider_errors(self):
        from llm_client import AllProvidersFailed, get_last_llm_call_metadata, llm_call
        providers = _mock_providers()

        async def mock_post(url, **kwargs):
            response = httpx.Response(
                400,
                json={"error": {"message": "bad payload"}},
                request=_FAKE_REQ,
            )
            raise httpx.HTTPStatusError("bad", request=MagicMock(), response=response)

        with patch("llm_client._http_post", side_effect=mock_post):
            with patch("llm_client.get_providers", return_value=providers):
                with pytest.raises(AllProvidersFailed):
                    await llm_call([{"role": "user", "content": "hi"}])
                metadata = get_last_llm_call_metadata()
                assert metadata["status"] == "provider_failed"
                assert "bad payload" in metadata["provider_errors"][0]["message"]

    @pytest.mark.asyncio
    async def test_direct_400_status_error_records_metadata(self):
        from llm_client import AllProvidersFailed, get_last_llm_call_metadata, llm_call
        providers = _mock_providers(1)
        response = httpx.Response(
            400,
            json={"error": {"message": "image payload rejected"}},
            request=_FAKE_REQ,
        )
        error = httpx.HTTPStatusError("bad request", request=MagicMock(), response=response)

        with patch("llm_client._call_single_provider", side_effect=error):
            with patch("llm_client.get_providers", return_value=providers):
                with pytest.raises(AllProvidersFailed):
                    await llm_call([{"role": "user", "content": "hi"}])

                metadata = get_last_llm_call_metadata()
                assert metadata["status"] == "provider_failed"
                assert metadata["fallback_count"] == 1
                assert metadata["provider_errors"][0]["provider"] == "provider-0"
                assert "image payload rejected" in metadata["provider_errors"][0]["message"]

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

    def test_chat_text_array_is_flattened(self):
        from llm_client import _build_request_body
        provider = _mock_providers()[2]
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "line 1"},
            {"type": "text", "text": "line 2"},
        ]}]
        body = _build_request_body(provider, messages, 4096, 0)
        assert body["messages"][0]["content"] == "line 1\nline 2"

    def test_qwen_vision_body_preserves_image_and_requests_json(self):
        from llm_client import _build_request_body

        provider = {
            "name": "qwen_vision",
            "model": "qwen3-vl-plus",
            "api_format": "openai_chat",
            "max_tokens": 8192,
            "response_format": "json_object",
        }
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "return json"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abcd"}},
        ]}]

        body = _build_request_body(provider, messages, 4096, 0)

        assert body["model"] == "qwen3-vl-plus"
        assert body["response_format"] == {"type": "json_object"}
        assert body["messages"][0]["content"][1]["type"] == "image_url"

    def test_qwen_base_url_gets_chat_completions_path(self, monkeypatch):
        from llm_client import _get_url

        provider = {
            "base_url_env": "QWEN_API_BASE",
            "base_url_default": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_path": "/chat/completions",
        }
        monkeypatch.setenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")

        assert _get_url(provider) == (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        )




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

    def test_extract_chat_rejects_length_finish(self):
        from llm_client import _extract_text
        data = {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]}
        with pytest.raises(RuntimeError, match="provider_incomplete_response"):
            _extract_text("openai_chat", data)

    def test_extract_anthropic_rejects_max_tokens(self):
        from llm_client import _extract_text
        data = {"content": [{"text": "partial"}], "stop_reason": "max_tokens"}
        with pytest.raises(RuntimeError, match="provider_incomplete_response"):
            _extract_text("anthropic", data)

    def test_extract_responses_rejects_incomplete_status(self):
        from llm_client import _extract_text
        data = {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [{"content": [{"type": "output_text", "text": "partial"}]}],
        }
        with pytest.raises(RuntimeError, match="provider_incomplete_response"):
            _extract_text("openai_responses", data)



# ── RC2: 确定性 seed 注入（native + openai_chat 统一） ──────────────
class TestDeterministicSeed:
    def test_openai_chat_injects_seed_at_zero_temp(self):
        from llm_client import _build_request_body
        provider = {"api_format": "openai_chat", "model": "deepseek", "max_tokens": 8192}
        body = _build_request_body(provider, [{"role": "user", "content": "hi"}], 1000, 0)
        assert body.get("seed") == 20260526

    def test_openai_chat_no_seed_when_hot(self):
        from llm_client import _build_request_body
        provider = {"api_format": "openai_chat", "model": "deepseek", "max_tokens": 8192}
        body = _build_request_body(provider, [{"role": "user", "content": "hi"}], 1000, 0.7)
        assert "seed" not in body

    def test_provider_seed_overrides_default(self):
        from llm_client import _build_request_body
        provider = {"api_format": "openai_chat", "model": "deepseek", "max_tokens": 8192, "deterministic_seed": 42}
        body = _build_request_body(provider, [{"role": "user", "content": "hi"}], 1000, 0)
        assert body.get("seed") == 42




# ── reasoning_effort 注入(推理 budget 约束, 治 reasoning 烧爆预算根因) ──
class TestReasoningEffortInjection:
    def test_openai_chat_injects_reasoning_effort_when_configured(self):
        from llm_client import _build_request_body
        provider = {"api_format": "openai_chat", "model": "deepseek-v4-pro", "max_tokens": 16384, "reasoning_effort": "medium"}
        body = _build_request_body(provider, [{"role": "user", "content": "hi"}], 16000, 0)
        assert body.get("reasoning_effort") == "medium"

    def test_openai_chat_omits_reasoning_effort_when_absent(self):
        from llm_client import _build_request_body
        provider = {"api_format": "openai_chat", "model": "deepseek", "max_tokens": 8192}
        body = _build_request_body(provider, [{"role": "user", "content": "hi"}], 1000, 0)
        assert "reasoning_effort" not in body
