"""统一 LLM 客户端 — 内置 DeepSeek + Vertex AI fallback 链。

所有 LLM 调用都通过 llm_call() 入口，自动按 llm_config.PROVIDERS 顺序尝试。
每次调用独立 fallback，不是整卷切换。
"""
import os
import asyncio
import httpx
from logger import get_logger
from llm_config import get_providers

logger = get_logger()

_clients: dict[str, httpx.AsyncClient] = {}
_semaphores: dict[str, asyncio.Semaphore] = {}
_vertex_client = None


async def close_llm_clients():
    """关闭所有缓存的 HTTP 客户端（FastAPI shutdown 时调用）。"""
    for client in _clients.values():
        if not client.is_closed:
            await client.aclose()
    _clients.clear()


class AllProvidersFailed(Exception):
    """所有 provider 都失败。"""
    def __init__(self, errors: list):
        self.errors = errors
        names = [e[0] for e in errors]
        super().__init__(f"All LLM providers failed: {names}")


async def _get_client(proxy: str = None, trust_env: bool = True) -> httpx.AsyncClient:
    key = proxy or ("__direct_no_env__" if not trust_env else "__direct__")
    client = _clients.get(key)
    if client is None or client.is_closed:
        kwargs = dict(
            timeout=120.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            trust_env=trust_env,
        )
        if proxy:
            kwargs["proxy"] = proxy
        client = httpx.AsyncClient(**kwargs)
        _clients[key] = client
    return client


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


def _get_proxy(provider: dict) -> str | None:
    env_key = provider.get("proxy_env")
    if env_key:
        return os.environ.get(env_key) or None
    return None


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
        for item in data.get("output", []):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        return block["text"]
        return data["output"][0]["content"][0]["text"]
    else:  # openai_chat
        return data["choices"][0]["message"]["content"]


# ── Vertex AI SDK ────────────────────────────────────────────────

def _get_vertex_client(provider: dict):
    global _vertex_client
    if _vertex_client is None:
        from google import genai
        project = os.environ.get(provider.get("project_env", ""), "")
        location = provider.get("location", "us-central1")
        _vertex_client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
    return _vertex_client


def _convert_messages_to_gemini(messages: list) -> tuple:
    """OpenAI Chat messages → Gemini (contents, system_instruction)。"""
    contents = []
    system_instruction = None
    for msg in messages:
        role = msg["role"]
        if role == "system":
            if isinstance(msg["content"], str):
                system_instruction = msg["content"]
            continue
        gemini_role = "model" if role == "assistant" else "user"
        parts = []
        content = msg["content"]
        if isinstance(content, str):
            parts.append({"text": content})
        else:
            for item in content:
                if item.get("type") == "text":
                    parts.append({"text": item["text"]})
                elif item.get("type") == "image_url":
                    url = item["image_url"]["url"]
                    if url.startswith("data:"):
                        header, b64data = url.split(",", 1)
                        mime_type = header.split(";")[0].split(":")[1]
                        parts.append({"inline_data": {"mime_type": mime_type, "data": b64data}})
        contents.append({"role": gemini_role, "parts": parts})
    return contents, system_instruction


async def _call_vertex_provider(provider: dict, messages: list, max_tokens: int,
                                temperature: float) -> str:
    """调用 Vertex AI Gemini（google-genai SDK）。"""
    from google.genai import types

    client = _get_vertex_client(provider)
    contents, system_instruction = _convert_messages_to_gemini(messages)
    thinking_mult = provider.get("thinking_overhead", 1)
    capped_tokens = min(max_tokens * thinking_mult, provider["max_tokens"])

    config_kwargs = {
        "max_output_tokens": capped_tokens,
        "temperature": temperature,
    }
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction

    config = types.GenerateContentConfig(**config_kwargs)
    sem = _get_semaphore(provider)

    async with sem:
        response = await client.aio.models.generate_content(
            model=provider["model"],
            contents=contents,
            config=config,
        )
        text = response.text
        if text is None:
            raise RuntimeError(f"Vertex AI returned empty response (finish_reason={response.candidates[0].finish_reason if response.candidates else 'unknown'})")
        return text


# ── HTTP 调用 ─────────────────────────────────────────────────────

async def _http_post(url: str, headers: dict, json: dict,
                     timeout: float, proxy: str = None,
                     trust_env: bool = True) -> httpx.Response:
    """可被测试 mock 的 HTTP POST。"""
    client = await _get_client(proxy, trust_env=trust_env)
    return await client.post(url, headers=headers, json=json, timeout=timeout)


async def _call_single_provider(provider: dict, messages: list, max_tokens: int,
                                temperature: float, timeout: float) -> str:
    """调用单个 provider（含内部重试）。"""
    if provider["api_format"] == "vertex_genai":
        return await _call_vertex_provider(provider, messages, max_tokens, temperature)

    url = _get_url(provider)
    headers = _get_headers(provider)
    body = _build_request_body(provider, messages, max_tokens, temperature)
    proxy = _get_proxy(provider)
    no_proxy = provider.get("no_proxy", False)
    retries = provider.get("retry_count", 2)
    retryable = {429, 500, 502, 503, 529}
    sem = _get_semaphore(provider)

    async with sem:
        last_err = None
        for attempt in range(retries + 1):
            try:
                resp = await _http_post(url, headers=headers, json=body,
                                        timeout=timeout, proxy=proxy,
                                        trust_env=not no_proxy)
                ct = resp.headers.get("content-type", "")
                if "text/html" in ct:
                    raise RuntimeError(
                        f"API returned HTML instead of JSON (URL may be invalid: {url})"
                    )
                resp.raise_for_status()
                data = resp.json()
                return _extract_text(provider["api_format"], data)
            except httpx.HTTPStatusError as e:
                last_err = e
                status = e.response.status_code
                if status == 400:
                    raise
                if status in (401, 403):
                    raise
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
    """统一 LLM 调用入口，内置 fallback 链。"""
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
            if status == 400:
                raise
            if status == 403:
                body_text = ""
                try:
                    body_text = e.response.text[:200]
                except Exception:
                    pass
                logger.warning(f"[LLM] {provider['name']} 403: {body_text}")
                errors.append((provider["name"], e))
                continue
            if status == 401:
                logger.warning(f"[LLM] {provider['name']} 401 认证失败")
                errors.append((provider["name"], e))
                continue
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
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {
            "url": f"data:{media_type};base64,{image_base64}"}},
        {"type": "text", "text": prompt},
    ]}]
    return await llm_call(messages, max_tokens=max_tokens, temperature=temperature)
