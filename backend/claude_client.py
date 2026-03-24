"""AIProxy Anthropic 端点客户端封装 — async 版本。

B2 改造：模块级 AsyncClient + Semaphore(3) 并发控制。
"""
import os
import asyncio
import httpx
from logger import get_logger

logger = get_logger()

_API_BASE = "https://aiproxy.superaichao.xin/api/v1/anthropic/v1/messages"

# 模块级连接池（复用，不每次创建）
_client: httpx.AsyncClient | None = None
_semaphore = asyncio.Semaphore(3)  # AIProxy Kiro 分组并发限制


def _get_headers():
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY 环境变量未设置")
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
        )
    return _client


async def send_message(
    prompt: str,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """发送单条消息到 Claude，返回文本响应。"""
    api_base = os.environ.get("CLAUDE_API_BASE", _API_BASE)
    if not api_base.endswith("/v1/messages"):
        api_base = api_base.rstrip("/") + "/v1/messages"

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }

    async with _semaphore:
        client = await _get_client()
        resp = await client.post(api_base, headers=_get_headers(), json=body)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


async def send_message_with_image(
    prompt: str,
    image_base64: str,
    media_type: str = "image/png",
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """发送含图片的消息到 Claude。"""
    api_base = os.environ.get("CLAUDE_API_BASE", _API_BASE)
    if not api_base.endswith("/v1/messages"):
        api_base = api_base.rstrip("/") + "/v1/messages"

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_base64,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    }

    async with _semaphore:
        client = await _get_client()
        resp = await client.post(api_base, headers=_get_headers(), json=body)
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
