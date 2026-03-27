# LLM 逐题 Fallback 链 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Opus 4.6 → GPT 5.4 → Gemini 3 Pro 逐题 fallback 链，确保每道题分析都成功。

**Architecture:** 统一 LLM 客户端层（llm_client.py）内置 fallback 逻辑，所有调用方（gemini_analyzer / feature_extractor / report_insights）通过统一接口调用，自动享受三级降级。

**Tech Stack:** Python 3.11, httpx, asyncio, FastAPI, Docker Compose

**远程操作约定:** 代码在京东云服务器（`ssh jdcloud`，`~/biology-exam-analyzer/`）。文件写入本地 `/tmp/` 然后 SCP，测试通过 `ssh jdcloud 'cd ~/biology-exam-analyzer && docker-compose exec -T backend python -m pytest ...'`。

---

### Task 1: Provider 配置（llm_config.py 重写）

**Files:**
- Modify: `backend/llm_config.py`

**测试契约:**
1. get_providers() 返回已配置 key 的 provider 列表
   - 入口: `from llm_config import get_providers`
   - 反例: 如果不过滤无 key 的 provider，会在调用时 RuntimeError
   - 边界: 全部 key 缺失 → 空列表；只有 1 个 key → 单元素列表
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_llm_client.py::TestLlmConfig -v`

**审查清单:**
- ✓ PROVIDERS 列表包含 3 个 provider，顺序 opus → gpt → gemini
- ✓ get_providers() 过滤掉 key_env 未配置的 provider
- ✗ 不应有硬编码 API key

- [ ] **Step 1: 写 llm_config.py**

```python
"""LLM Provider 配置 — fallback 链：Opus 4.6 → GPT 5.4 → Gemini 3 Pro。

所有 LLM 调用通过 llm_client.py 统一路由，按此列表顺序尝试。
"""
import os

PROVIDERS = [
    {
        "name": "claude-opus",
        "model": "claude-opus-4-6",
        "api_format": "anthropic",
        "base_url_env": "CLAUDE_API_BASE",
        "base_url_default": "https://aiproxy.superaichao.xin/api/v1/anthropic/v1/messages",
        "key_env": "CLAUDE_API_KEY",
        "max_tokens": 8192,
        "semaphore_limit": 3,
        "retry_count": 2,
    },
    {
        "name": "gpt",
        "model": "gpt-5.4",
        "api_format": "openai_responses",
        "base_url_env": None,
        "base_url_default": "https://aiproxy.superaichao.xin/api/v1/openai/v1/responses",
        "key_env": "AIPROXY_OAI_KEY",
        "max_tokens": 16384,
        "semaphore_limit": 5,
        "retry_count": 2,
    },
    {
        "name": "gemini-vecto",
        "model": "gemini-3-pro-preview",
        "api_format": "openai_chat",
        "base_url_env": "VECTO_API_BASE",
        "base_url_default": "https://api.vectorengine.ai/v1/chat/completions",
        "key_env": "VECTO_API_KEY",
        "max_tokens": 8192,
        "semaphore_limit": 5,
        "retry_count": 2,
    },
]


def get_providers() -> list:
    """返回已配置 API key 的 provider 列表（保持优先级顺序）。"""
    result = []
    for p in PROVIDERS:
        key = os.environ.get(p["key_env"], "")
        if key:
            result.append(p)
    return result
```

- [ ] **Step 2: Commit**

```bash
cd ~/biology-exam-analyzer
git add backend/llm_config.py
git commit -m "refactor: llm_config.py 重写为 3-provider fallback 链配置"
```

---

### Task 2: 统一 LLM 客户端（llm_client.py + 测试）

**Files:**
- Create: `backend/llm_client.py`
- Create: `backend/test_llm_client.py`

**测试契约:**
1. 首选 provider 成功 → 直接返回
   - 入口: `await llm_call([{"role":"user","content":"hi"}])`
   - 反例: 如果 fallback 逻辑错误会跳过首选 provider
   - 边界: 单条文本消息
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_llm_client.py::TestFallback::test_first_provider_success -v`
2. 首选失败 → fallback 到第二个
   - 入口: `await llm_call(...)` 当第一个 provider 返回 500
   - 反例: 不 fallback 直接抛异常
   - 边界: 500/502/503/429 都应触发 fallback
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_llm_client.py::TestFallback::test_fallback_to_second -v`
3. 全部失败 → 抛 AllProvidersFailed
   - 入口: 3 个 provider 都返回 500
   - 反例: 静默返回空字符串
   - 边界: 3 个全挂
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_llm_client.py::TestFallback::test_all_fail -v`
4. 400 错误 → 不 fallback，直接抛
   - 入口: 首选 provider 返回 400
   - 反例: 400 也 fallback（浪费，prompt 问题换模型也不行）
   - 边界: 400/401
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_llm_client.py::TestFallback::test_no_fallback_on_400 -v`
5. Anthropic 格式转换正确
   - 入口: `_build_anthropic_request(messages, ...)`
   - 反例: 图片格式错误导致 400
   - 边界: 纯文本 / 文本+图片 / 多图
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_llm_client.py::TestFormatConversion -v`

**审查清单:**
- ✓ fallback 循环遍历所有 provider
- ✓ 跳过未配置 key 的 provider
- ✓ 每个 provider 独立 semaphore
- ✓ 指数退避重试
- ✓ 三种 API 格式正确转换（anthropic / responses / chat）
- ✓ 响应文本提取覆盖三种格式
- ✗ 不应在 400 时 fallback（403 model-not-found 除外）

**边界条件:**
- 空 messages 列表 → 期望: 直接调用，由 API 返回 400
- 超大 max_tokens → 期望: 每个 provider 内部 cap 到 provider.max_tokens
- 所有 key 都未配置 → 期望: 抛 AllProvidersFailed（无可用 provider）

- [ ] **Step 1: 写测试 test_llm_client.py**

```python
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
            "retry_count": 1,  # 测试时只重试 1 次，加速
        }
        for i in range(count)
    ]


def _anthropic_ok():
    return httpx.Response(200, json={
        "content": [{"text": "hello from anthropic"}],
        "stop_reason": "end_turn",
    })


def _responses_ok():
    return httpx.Response(200, json={
        "output": [{"content": [{"type": "output_text", "text": "hello from gpt"}]}],
        "status": "completed",
    })


def _chat_ok():
    return httpx.Response(200, json={
        "choices": [{"message": {"content": "hello from gemini"}, "finish_reason": "stop"}],
    })


def _error(status):
    return httpx.Response(status, json={"error": "fail"})


# ── Config 测试 ───────────────────────────────────────────────────

class TestLlmConfig:
    def test_get_providers_filters_missing_keys(self):
        import os
        from llm_config import get_providers, PROVIDERS
        # 只设置第一个 key
        env = {PROVIDERS[0]["key_env"]: "test-key"}
        with patch.dict(os.environ, env, clear=False):
            result = get_providers()
            assert len(result) >= 1
            assert result[0]["name"] == PROVIDERS[0]["name"]

    def test_get_providers_empty_when_no_keys(self):
        import os
        from llm_config import get_providers, PROVIDERS
        clear = {p["key_env"]: "" for p in PROVIDERS}
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
        from llm_client import _call_single_provider
        providers = _mock_providers()
        with patch("llm_client._http_post", new_callable=AsyncMock, return_value=_anthropic_ok()):
            from llm_client import llm_call
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
            if call_count <= 2:  # provider 0 的 retry_count+1 次调用都失败
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
                resp = httpx.Response(403, json={"error": {"message": "model not found"}})
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
        provider = _mock_providers()[0]  # anthropic
        messages = [{"role": "user", "content": "hello"}]
        body = _build_request_body(provider, messages, 4096, 0)
        assert body["model"] == "model-0"
        assert body["messages"][0]["content"][0]["type"] == "text"

    def test_anthropic_with_image(self):
        from llm_client import _build_request_body
        provider = _mock_providers()[0]  # anthropic
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
        provider = _mock_providers()[1]  # openai_responses
        messages = [{"role": "user", "content": "hello"}]
        body = _build_request_body(provider, messages, 4096, 0)
        assert body["model"] == "model-1"
        assert "input" in body

    def test_chat_text_only(self):
        from llm_client import _build_request_body
        provider = _mock_providers()[2]  # openai_chat
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
ssh jdcloud 'cd ~/biology-exam-analyzer && docker-compose exec -T backend python -m pytest test_llm_client.py -v'
```
Expected: FAIL（`llm_client` 模块不存在）

- [ ] **Step 3: 写 llm_client.py 实现**

```python
"""统一 LLM 客户端 — 内置 Opus→GPT→Gemini fallback 链。

所有 LLM 调用都通过 llm_call() 入口，自动按 llm_config.PROVIDERS 顺序尝试。
每次调用独立 fallback，不是整卷切换。
"""
import os
import asyncio
import httpx
from logger import get_logger
from llm_config import get_providers

logger = get_logger()

_client: httpx.AsyncClient | None = None
_semaphores: dict[str, asyncio.Semaphore] = {}


class AllProvidersFailed(Exception):
    """所有 provider 都失败。"""
    def __init__(self, errors: list):
        self.errors = errors
        names = [e[0] for e in errors]
        super().__init__(f"All LLM providers failed: {names}")


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=120.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


def _get_semaphore(provider: dict) -> asyncio.Semaphore:
    name = provider["name"]
    if name not in _semaphores:
        _semaphores[name] = asyncio.Semaphore(provider["semaphore_limit"])
    return _semaphores[name]


def _get_headers(provider: dict) -> dict:
    key = os.environ.get(provider["key_env"], "")
    fmt = provider["api_format"]
    headers = {"Content-Type": "application/json"}
    if fmt == "anthropic":
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _get_url(provider: dict) -> str:
    env_key = provider.get("base_url_env")
    if env_key:
        url = os.environ.get(env_key, "")
        if url:
            return url
    return provider["base_url_default"]


# ── 格式转换 ──────────────────────────────────────────────────────

def _convert_content_anthropic(content):
    """OpenAI Chat 格式 → Anthropic Messages 格式。"""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    result = []
    for item in content:
        if item.get("type") == "text":
            result.append({"type": "text", "text": item["text"]})
        elif item.get("type") == "image_url":
            url = item["image_url"]["url"]
            if url.startswith("data:"):
                header, b64data = url.split(",", 1)
                media_type = header.split(";")[0].split(":")[1]
                result.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64data},
                })
            else:
                result.append({"type": "image", "source": {"type": "url", "url": url}})
    return result


def _convert_content_responses(content):
    """OpenAI Chat 格式 → OpenAI Responses 格式。"""
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    result = []
    for item in content:
        if item.get("type") == "text":
            result.append({"type": "input_text", "text": item["text"]})
        elif item.get("type") == "image_url":
            result.append({"type": "input_image", "image_url": item["image_url"]["url"]})
    return result


def _build_request_body(provider: dict, messages: list, max_tokens: int,
                        temperature: float) -> dict:
    """根据 provider 格式构建请求体。messages 使用 OpenAI Chat 格式作为内部标准。"""
    fmt = provider["api_format"]
    model = provider["model"]
    capped_tokens = min(max_tokens, provider["max_tokens"])

    if fmt == "anthropic":
        converted = []
        for msg in messages:
            converted.append({
                "role": msg["role"],
                "content": _convert_content_anthropic(msg["content"]),
            })
        return {
            "model": model,
            "messages": converted,
            "max_tokens": capped_tokens,
            "temperature": temperature,
        }
    elif fmt == "openai_responses":
        converted_input = []
        for msg in messages:
            converted_input.append({
                "role": msg["role"],
                "content": _convert_content_responses(msg["content"]),
            })
        return {
            "model": model,
            "input": converted_input,
            "max_output_tokens": capped_tokens,
            "temperature": temperature,
        }
    else:  # openai_chat
        return {
            "model": model,
            "messages": messages,
            "max_tokens": capped_tokens,
            "temperature": temperature,
        }


def _extract_text(api_format: str, data: dict) -> str:
    """从 API 响应中提取文本。"""
    if api_format == "anthropic":
        return data["content"][0]["text"]
    elif api_format == "openai_responses":
        return data["output"][0]["content"][0]["text"]
    else:  # openai_chat
        return data["choices"][0]["message"]["content"]


# ── HTTP 调用 ─────────────────────────────────────────────────────

async def _http_post(url: str, headers: dict, json: dict,
                     timeout: float) -> httpx.Response:
    """可被测试 mock 的 HTTP POST。"""
    client = await _get_client()
    return await client.post(url, headers=headers, json=json, timeout=timeout)


async def _call_single_provider(provider: dict, messages: list, max_tokens: int,
                                temperature: float, timeout: float) -> str:
    """调用单个 provider（含内部重试）。"""
    url = _get_url(provider)
    headers = _get_headers(provider)
    body = _build_request_body(provider, messages, max_tokens, temperature)
    retries = provider.get("retry_count", 2)
    retryable = {429, 500, 502, 503, 529}
    sem = _get_semaphore(provider)

    async with sem:
        last_err = None
        for attempt in range(retries + 1):
            try:
                resp = await _http_post(url, headers=headers, json=body, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                return _extract_text(provider["api_format"], data)
            except httpx.HTTPStatusError as e:
                last_err = e
                status = e.response.status_code
                # 400 不重试（prompt 问题）
                if status == 400:
                    raise
                # 403 可能是模型 ID 过期，不重试但允许 fallback
                if status in (401, 403):
                    raise
                # 可重试错误
                if status in retryable and attempt < retries:
                    wait = 2 ** attempt + (2 if status == 429 else 0)
                    logger.warning(f"[LLM] {provider['name']} HTTP {status}, "
                                   f"retry {attempt+1}/{retries} in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                raise
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                last_err = e
                if attempt < retries:
                    wait = 2 ** attempt
                    logger.warning(f"[LLM] {provider['name']} 网络错误, "
                                   f"retry {attempt+1}/{retries} in {wait}s: {str(e)[:80]}")
                    await asyncio.sleep(wait)
                    continue
                raise
        raise last_err


# ── 对外接口 ──────────────────────────────────────────────────────

async def llm_call(
    messages: list,
    max_tokens: int = 4096,
    temperature: float = 0,
    timeout: float = 120.0,
) -> str:
    """统一 LLM 调用入口，内置 fallback 链。

    Args:
        messages: OpenAI Chat 格式 [{"role": "user", "content": str | list}]
        max_tokens: 最大输出 token
        temperature: 温度
        timeout: 单次 HTTP 超时（秒）

    Returns:
        str: LLM 响应文本

    Raises:
        AllProvidersFailed: 所有 provider 都失败
        httpx.HTTPStatusError: 400 Bad Request（不 fallback）
    """
    providers = get_providers()
    if not providers:
        raise AllProvidersFailed([("none", RuntimeError("无可用 LLM provider，请检查 API key 配置"))])

    errors = []
    for provider in providers:
        try:
            result = await _call_single_provider(
                provider, messages, max_tokens, temperature, timeout
            )
            if len(errors) > 0:
                logger.info(f"[LLM] Fallback 成功: {provider['name']} "
                            f"(前 {len(errors)} 个 provider 失败)")
            return result
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            # 400 不 fallback
            if status == 400:
                raise
            # 403 可能是模型 ID 过期，尝试下一个
            if status == 403:
                body_text = ""
                try:
                    body_text = e.response.text[:200]
                except Exception:
                    pass
                logger.warning(f"[LLM] {provider['name']} 403 (可能模型 ID 过期): {body_text}")
                errors.append((provider["name"], e))
                continue
            # 401 key 问题
            if status == 401:
                logger.warning(f"[LLM] {provider['name']} 401 认证失败")
                errors.append((provider["name"], e))
                continue
            # 其他可重试错误（已在 _call_single_provider 内重试过）
            logger.warning(f"[LLM] {provider['name']} HTTP {status} 最终失败, 尝试下一个")
            errors.append((provider["name"], e))
            continue
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            logger.warning(f"[LLM] {provider['name']} 网络错误最终失败: {str(e)[:80]}, 尝试下一个")
            errors.append((provider["name"], e))
            continue
        except Exception as e:
            logger.error(f"[LLM] {provider['name']} 未知错误: {e}")
            errors.append((provider["name"], e))
            continue

    raise AllProvidersFailed(errors)


# ── 兼容接口 ──────────────────────────────────────────────────────

async def send_message_gpt(
    prompt: str,
    model: str = None,
    max_tokens: int = 512,
    temperature: float = 0,
) -> str:
    """兼容旧 claude_client.send_message_gpt() 接口。"""
    return await llm_call(
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )


async def send_message(
    prompt: str,
    model: str = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """兼容旧 claude_client.send_message() 接口。"""
    return await send_message_gpt(prompt, model=model, max_tokens=max_tokens,
                                  temperature=temperature)


async def send_message_with_image(
    prompt: str,
    image_base64: str,
    media_type: str = "image/png",
    model: str = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """兼容旧 claude_client.send_message_with_image() 接口。"""
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {
            "url": f"data:{media_type};base64,{image_base64}"}},
        {"type": "text", "text": prompt},
    ]}]
    return await llm_call(messages, max_tokens=max_tokens, temperature=temperature)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
ssh jdcloud 'cd ~/biology-exam-analyzer && docker-compose exec -T backend python -m pytest test_llm_client.py -v'
```
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/biology-exam-analyzer
git add backend/llm_client.py backend/test_llm_client.py
git commit -m "feat: 统一 LLM 客户端 + fallback 链（Opus→GPT→Gemini）"
```

---

### Task 3: claude_client.py 改为兼容垫片

**Files:**
- Modify: `backend/claude_client.py`

**审查清单:**
- ✓ 所有旧接口（send_message_gpt / send_message / send_message_with_image）保留
- ✓ import 此模块的代码无需改动
- ✗ 不应有重复的 httpx/fallback 逻辑

- [ ] **Step 1: 重写 claude_client.py 为兼容垫片**

```python
"""兼容垫片 — 保留旧 import 路径，实际逻辑已迁移到 llm_client.py。"""
from llm_client import (  # noqa: F401
    llm_call,
    send_message_gpt,
    send_message,
    send_message_with_image,
    AllProvidersFailed,
)
```

- [ ] **Step 2: 验证现有测试不受影响**

```bash
ssh jdcloud 'cd ~/biology-exam-analyzer && docker-compose exec -T backend python -m pytest test_core_modules.py test_feature_difficulty.py -v'
```
Expected: 全部 PASS（feature_extractor import from claude_client 不受影响）

- [ ] **Step 3: Commit**

```bash
cd ~/biology-exam-analyzer
git add backend/claude_client.py
git commit -m "refactor: claude_client.py 改为 llm_client 兼容垫片"
```

---

### Task 4: gemini_analyzer.py 改造

**Files:**
- Modify: `backend/gemini_analyzer.py`

**审查清单:**
- ✓ split_questions() / analyze_question() 签名不变
- ✓ 删除 _call_with_retry / _convert_content / _get_client / self._client
- ✓ 改用 llm_client.llm_call()
- ✓ 保留 extract_json() 和 prompt 构建逻辑
- ✗ 不应有 httpx.AsyncClient 实例

- [ ] **Step 1: 改造 gemini_analyzer.py**

删除以下代码：
- `_ResponseCompat` 类
- `__init__` 中的 `self._api_key`, `self._api_url`, `self._client`, `self._semaphore`, `self.analysis_model`, `self.flash_model`
- `_get_client()` 方法
- `_convert_content()` 方法
- `_call_with_retry()` 方法

修改以下方法：
- `__init__`: 只保留 prompt 目录加载
- `split_questions()`: 用 `llm_client.llm_call(messages)` 替换 `self._call_with_retry(**kwargs)`
- `analyze_question()`: 同上

```python
# __init__ 改为:
def __init__(self, api_key: str = None, api_base: str = None):
    """初始化分析器。api_key/api_base 参数保留兼容性，实际不使用。"""
    from logger import get_logger
    self.logger = get_logger()
    self.logger.info("LLM 分析器初始化完成（统一 fallback 客户端）")

# split_questions 中替换调用:
# 旧: response = await self._call_with_retry(model=..., messages=[...], ...)
# 新:
from llm_client import llm_call
response_text = await llm_call(
    messages=[{"role": "user", "content": message_content}],
    max_tokens=8192,
    temperature=0,
    timeout=120.0,
)

# analyze_question 中同样替换
```

- [ ] **Step 2: 验证现有测试通过**

```bash
ssh jdcloud 'cd ~/biology-exam-analyzer && docker-compose exec -T backend python -m pytest test_core_modules.py test_feature_difficulty.py -v'
```

- [ ] **Step 3: Commit**

```bash
cd ~/biology-exam-analyzer
git add backend/gemini_analyzer.py
git commit -m "refactor: gemini_analyzer 改用统一 llm_client（删除自建 httpx）"
```

---

### Task 5: deps.py 修正 + analysis_router.py await bug fix

**Files:**
- Modify: `backend/deps.py`
- Modify: `backend/analysis_router.py`

**审查清单:**
- ✓ deps.py: 检查任意 provider 可用，不再检查 GEMINI_API_KEY
- ✓ analysis_router.py:445: 补 await
- ✗ 不应改动其他路由逻辑

- [ ] **Step 1: 修改 deps.py**

```python
# 旧:
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# ...
def get_gemini_analyzer():
    global _gemini_analyzer
    if _gemini_analyzer is None:
        if not GEMINI_API_KEY:
            logger.warning("未配置GEMINI_API_KEY，AI 分析功能不可用")
            return None
        from gemini_analyzer import GeminiAnalyzer
        _gemini_analyzer = GeminiAnalyzer(GEMINI_API_KEY, api_base=GEMINI_API_BASE)
    return _gemini_analyzer

# 新:
def get_gemini_analyzer():
    global _gemini_analyzer
    if _gemini_analyzer is None:
        from llm_config import get_providers
        if not get_providers():
            logger.warning("无可用 LLM provider（请检查 API key 配置），AI 分析功能不可用")
            return None
        from gemini_analyzer import GeminiAnalyzer
        _gemini_analyzer = GeminiAnalyzer()
    return _gemini_analyzer
```

- [ ] **Step 2: 修改 analysis_router.py:445 补 await**

```python
# 旧 (line 445):
questions = gemini_analyzer.split_questions(image_bytes, extracted_text=extracted_text)

# 新:
questions = await gemini_analyzer.split_questions(image_bytes, extracted_text=extracted_text)
```

- [ ] **Step 3: Commit**

```bash
cd ~/biology-exam-analyzer
git add backend/deps.py backend/analysis_router.py
git commit -m "fix: deps.py 修正 key 检查 + analysis_router 补 await"
```

---

### Task 6: 环境配置（.env + docker-compose.yml）

**Files:**
- Modify: `.env`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**审查清单:**
- ✓ .env 新增 VECTO_API_KEY 和 VECTO_API_BASE
- ✓ docker-compose.yml 传入新环境变量
- ✗ 不应包含明文密钥在 .env.example

- [ ] **Step 1: 从 zhixue-server 复制 Vecto key 到 .env**

```bash
# 获取 Vecto key
ssh jdcloud 'grep LLM_API_KEY ~/zhixue-server/.env | head -1'
# 追加到 biology-exam-analyzer .env
ssh jdcloud 'bash -s' << 'SCRIPT'
VECTO_KEY=$(grep LLM_API_KEY ~/zhixue-server/.env | head -1 | cut -d= -f2)
echo "" >> ~/biology-exam-analyzer/.env
echo "# Vecto (Gemini fallback)" >> ~/biology-exam-analyzer/.env
echo "VECTO_API_KEY=$VECTO_KEY" >> ~/biology-exam-analyzer/.env
echo "VECTO_API_BASE=https://api.vectorengine.ai/v1/chat/completions" >> ~/biology-exam-analyzer/.env
SCRIPT
```

- [ ] **Step 2: 修改 docker-compose.yml 新增环境变量**

在 backend service 的 environment 段追加:
```yaml
      - VECTO_API_KEY=${VECTO_API_KEY}
      - VECTO_API_BASE=${VECTO_API_BASE:-https://api.vectorengine.ai/v1/chat/completions}
```

- [ ] **Step 3: 更新 .env.example**

追加:
```
VECTO_API_KEY=your-vecto-api-key
VECTO_API_BASE=https://api.vectorengine.ai/v1/chat/completions
```

- [ ] **Step 4: Commit**

```bash
cd ~/biology-exam-analyzer
git add docker-compose.yml .env.example
git commit -m "config: 新增 Vecto 环境变量（Gemini fallback 第三级）"
```

---

### Task 7: 集成验证

**Files:** 无新增

- [ ] **Step 1: 重建并重启 backend**

```bash
ssh jdcloud 'cd ~/biology-exam-analyzer && docker-compose up -d --build backend'
```

- [ ] **Step 2: 检查容器启动正常**

```bash
ssh jdcloud 'cd ~/biology-exam-analyzer && docker-compose logs --tail 20 backend'
```
Expected: 看到 "LLM 分析器初始化完成" 日志，无 import error

- [ ] **Step 3: 运行全量单元测试**

```bash
ssh jdcloud 'cd ~/biology-exam-analyzer && docker-compose exec -T backend python -m pytest test_core_modules.py test_feature_difficulty.py test_llm_client.py -v'
```
Expected: 全部 PASS

- [ ] **Step 4: curl 验证 health**

```bash
ssh jdcloud 'curl -s http://127.0.0.1:8001/health | python3 -m json.tool'
```

- [ ] **Step 5: 通知用户从浏览器上传试卷验证**

不声称完成，输出: "服务端已重建，请从浏览器上传一份试卷验证所有题目分析成功。"

---

### Task 8: CLAUDE.md 文档同步

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 更新 AI 配置段**

更新 CLAUDE.md 的 "当前项目 AI 配置" 段落，反映 fallback 链:
- 首选: claude-opus-4-6（AIProxy Kiro）
- 次选: gpt-5.4（AIProxy CodeX）
- 兜底: gemini-3-pro-preview（Vecto）
- 统一入口: llm_client.py → llm_call()
- 旧 claude_client.py 保留为兼容垫片

更新项目结构树:
- 新增 llm_client.py 说明
- claude_client.py 标注为兼容垫片
- gemini_analyzer.py 删除"Semaphore=3"注释

更新已知技术债:
- 删除"gemini_analyzer.py 命名误导"（已改造）
- 删除"两套 LLM 客户端"（已统一）

- [ ] **Step 2: Commit**

```bash
cd ~/biology-exam-analyzer
git add CLAUDE.md
git commit -m "docs: CLAUDE.md 同步 LLM fallback 链改造"
```
