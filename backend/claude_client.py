"""AIProxy Anthropic 端点客户端封装。

使用 httpx 直接调用 AIProxy 的 Anthropic Messages API。
Kiro 分组：0.2x 倍率，支持 claude-sonnet-4-5-20250929 / claude-haiku-4-5-20251001。
"""
import os
import httpx


_API_BASE = "https://aiproxy.superaichao.xin/api/v1/anthropic/v1/messages"


def _get_headers():
    """构建 AIProxy Anthropic 端点请求头。"""
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY 环境变量未设置")
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _call_api(body: dict) -> str:
    """同步调用 AIProxy Anthropic Messages API，返回文本响应。"""
    api_base = os.environ.get("CLAUDE_API_BASE", _API_BASE)
    # 确保 URL 以 /v1/messages 结尾
    if not api_base.endswith("/v1/messages"):
        api_base = api_base.rstrip("/") + "/v1/messages"
    headers = _get_headers()
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(api_base, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    return data["content"][0]["text"]


async def send_message(
    prompt: str,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """发送单条消息到 Claude，返回文本响应。

    用于模拟学生作答（高 temperature 增加随机性）和评判（低 temperature）。
    使用同步 httpx 在 asyncio 中通过 run_in_executor 调用。
    """
    import asyncio

    loop = asyncio.get_running_loop()

    def _call():
        return _call_api({
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        })

    return await loop.run_in_executor(None, _call)


async def send_message_with_image(
    prompt: str,
    image_base64: str,
    media_type: str = "image/png",
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """发送含图片的消息到 Claude。用于含图题目的模拟学生作答。"""
    import asyncio

    loop = asyncio.get_running_loop()

    def _call():
        return _call_api({
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
        })

    return await loop.run_in_executor(None, _call)
