"""统一 LLM 客户端 — 内置多 provider fallback 链。

所有 LLM 调用都通过 llm_call() 入口，自动按 llm_config.PROVIDERS 顺序尝试。
每次调用独立 fallback，不是整卷切换。
"""
import os
import asyncio
import httpx
from contextvars import ContextVar
from logger import get_logger
from llm_config import get_providers

logger = get_logger()

_clients: dict[str, httpx.AsyncClient] = {}
_semaphores: dict[str, asyncio.Semaphore] = {}
_last_call_metadata: ContextVar[dict] = ContextVar("last_llm_call_metadata", default={})
# GOAL #8 成本计量:成功 provider 的 token usage 旁路回传,经 llm_call 并入 _last_call_metadata
_last_provider_usage: ContextVar = ContextVar("last_provider_usage", default=None)


def get_last_llm_call_metadata() -> dict:
    """Return audit metadata for the last llm_call in the current async context."""
    return dict(_last_call_metadata.get({}) or {})


def _provider_error_message(error: Exception) -> str:
    message = str(error)
    if isinstance(error, httpx.HTTPStatusError):
        try:
            status = error.response.status_code
            body_text = (error.response.text or "")[:500]
            if body_text:
                message = f"HTTP {status}: {body_text}"
            else:
                message = f"HTTP {status}: {message}"
        except Exception:
            pass
    return message[:500]


def _provider_error_summary(errors: list) -> list[dict]:
    return [
        {
            "provider": str(name),
            "error_type": type(error).__name__,
            "message": _provider_error_message(error),
        }
        for name, error in errors
    ]


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
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
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
            return _append_api_path(url, provider.get("api_path"))
    return _append_api_path(provider["base_url_default"], provider.get("api_path"))


def _append_api_path(url: str, api_path: str | None) -> str:
    if not api_path:
        return url
    normalized_url = str(url or "").rstrip("/")
    normalized_path = "/" + str(api_path or "").strip("/")
    if normalized_url.endswith(normalized_path):
        return normalized_url
    return normalized_url + normalized_path


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


def _convert_content_chat(content):
    """OpenAI Chat-compatible content. Text-only arrays are flattened."""
    if isinstance(content, str):
        return content
    text_parts = []
    passthrough = []
    for item in content:
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
        else:
            passthrough.append(item)
    if not passthrough:
        return "\n".join(part for part in text_parts if part)
    return content


def _messages_include_images(messages: list) -> bool:
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for item in content:
                if item.get("type") == "image_url":
                    return True
    return False


def _finish_reason_to_text(finish_reason) -> str:
    if finish_reason is None:
        return ""
    return str(
        getattr(finish_reason, "value", None)
        or getattr(finish_reason, "name", None)
        or finish_reason
    )


def _raise_if_incomplete_finish(provider_name: str, finish_reason):
    reason = _finish_reason_to_text(finish_reason)
    if not reason:
        return
    normalized = reason.lower()
    if normalized in {"stop", "end_turn"}:
        return
    raise RuntimeError(
        f"{provider_name} provider_incomplete_response: finish_reason={reason}"
    )


def _deterministic_seed(provider: dict) -> int:
    """确定性复现 seed（temperature<=0 时使用）。统一各 provider 的 seed 注入路径，
    确保可复现性（RC2 根因修复）。"""
    seed = provider.get("deterministic_seed")
    if seed is None:
        seed = os.environ.get("LLM_DETERMINISTIC_SEED", "20260526")
    try:
        return int(seed)
    except (TypeError, ValueError):
        return 20260526


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
        converted = []
        for msg in messages:
            converted.append({
                "role": msg["role"],
                "content": _convert_content_chat(msg["content"]),
            })
        body = {
            "model": model,
            "messages": converted,
            "max_tokens": capped_tokens,
            "temperature": temperature,
        }
        if provider.get("response_format") == "json_object":
            body["response_format"] = {"type": "json_object"}
        # RC2: 确定性 seed 注入 openai_chat 路径（此前仅 native 有 seed，DeepSeek
        # 主审没接 -> temperature=0 仍跨跑漂移）。与 native 共用同一 helper。
        try:
            if float(temperature) <= 0:
                body["seed"] = _deterministic_seed(provider)
        except (TypeError, ValueError):
            pass
        # 推理模型 reasoning budget 约束: deepseek-v4-pro 不传 reasoning_effort 时
        # 渠道默认高档推理, reasoning 烧光 max_tokens 致 output 截断
        # (实测 reasoning_tokens=16000/output=0/finish=length; medium 档 reasoning 5505/output 正常)。
        if provider.get("reasoning_effort"):
            body["reasoning_effort"] = provider["reasoning_effort"]
        return body


def _extract_text(api_format: str, data: dict) -> str:
    """从 API 响应中提取文本。空内容视为失败抛出异常。"""
    text = None
    if api_format == "anthropic":
        _raise_if_incomplete_finish("anthropic", data.get("stop_reason"))
        text = data["content"][0]["text"]
    elif api_format == "openai_responses":
        status = data.get("status")
        if status and status not in {"completed", "complete"}:
            raise RuntimeError(
                f"openai_responses provider_incomplete_response: status={status}, "
                f"details={data.get('incomplete_details')}"
            )
        for item in data.get("output", []):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        text = block["text"]
                        break
                if text is not None:
                    break
        if text is None:
            text = data["output"][0]["content"][0]["text"]
    else:  # openai_chat
        choice = data["choices"][0]
        _raise_if_incomplete_finish("openai_chat", choice.get("finish_reason"))
        text = choice["message"]["content"]
    if not text or not text.strip():
        raise RuntimeError("LLM 返回空内容，视为失败触发 fallback")
    return text


def _extract_usage(api_format: str, data: dict):
    """从响应提取 token usage(GOAL #8 成本计量)。None-safe,无 usage 返回 None。
    deepseek 多 reasoning_tokens 与前缀缓存命中数;qwen/responses 缺则为 None。纯落盘,不改任何调用。"""
    if not isinstance(data, dict):
        return None
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    out = {
        "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
        "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict) and details.get("reasoning_tokens") is not None:
        out["reasoning_tokens"] = details.get("reasoning_tokens")
    for k in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
        if usage.get(k) is not None:
            out[k] = usage.get(k)
    return out


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
    if _messages_include_images(messages) and not provider.get("supports_images", False):
        raise RuntimeError(
            f"{provider['name']} provider_unsupported_media: image_url is not supported"
        )

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
                _last_provider_usage.set(_extract_usage(provider["api_format"], data))
                return _extract_text(provider["api_format"], data)
            except httpx.HTTPStatusError as e:
                last_err = e
                status = e.response.status_code
                if status == 400:
                    body_text = ""
                    try:
                        body_text = e.response.text[:500]
                    except Exception:
                        pass
                    raise RuntimeError(
                        f"{provider['name']} HTTP 400 Bad Request: {body_text}"
                    ) from e
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
    purpose: str | None = None,
    model: str | None = None,
) -> str:
    """统一 LLM 调用入口，内置 fallback 链。"""
    _last_call_metadata.set({})
    _last_provider_usage.set(None)
    requires_images = _messages_include_images(messages)
    providers = get_providers(
        purpose=purpose,
        model_override=model,
        requires_images=requires_images,
    )
    if not providers:
        _last_call_metadata.set({
            "status": "provider_failed",
            "provider": None,
            "model": None,
            "purpose": purpose,
            "model_role": None,
            "model_policy": None,
            "fallback_count": 0,
            "provider_errors": [{"provider": "none", "error_type": "ConfigError", "message": "no providers"}],
        })
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
            _last_call_metadata.set({
                "status": "ok",
                "provider": provider.get("name"),
                "model": provider.get("model"),
                "purpose": purpose or provider.get("purpose"),
                "model_role": provider.get("model_role"),
                "model_policy": provider.get("model_policy"),
                "fallback_count": len(errors),
                "provider_errors": _provider_error_summary(errors),
                "usage": _last_provider_usage.get(),
            })
            return result
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 400:
                body_text = ""
                try:
                    body_text = e.response.text[:200]
                except Exception:
                    pass
                logger.warning(f"[LLM] {provider['name']} 400: {body_text}")
                errors.append((provider["name"], e))
                continue
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

    _last_call_metadata.set({
        "status": "provider_failed",
        "provider": None,
        "model": None,
        "purpose": purpose,
        "model_role": None,
        "model_policy": None,
        "fallback_count": len(errors),
        "provider_errors": _provider_error_summary(errors),
    })
    raise AllProvidersFailed(errors)


# ── 兼容接口 ──────────────────────────────────────────────────────

async def send_message_gpt(
    prompt: str,
    model: str = None,
    max_tokens: int = 512,
    temperature: float = 0,
    purpose: str | None = None,
) -> str:
    return await llm_call(
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        purpose=purpose,
        model=model,
    )


async def send_message(
    prompt: str,
    model: str = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
    purpose: str | None = None,
) -> str:
    return await send_message_gpt(prompt, model=model, max_tokens=max_tokens,
                                  temperature=temperature, purpose=purpose)


async def send_message_with_image(
    prompt: str,
    image_base64: str,
    media_type: str = "image/png",
    model: str = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
    purpose: str | None = None,
) -> str:
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {
            "url": f"data:{media_type};base64,{image_base64}"}},
        {"type": "text", "text": prompt},
    ]}]
    return await llm_call(
        messages,
        max_tokens=max_tokens,
        temperature=temperature,
        purpose=purpose,
        model=model,
    )
