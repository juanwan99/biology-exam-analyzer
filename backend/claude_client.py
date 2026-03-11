"""AIProxy Anthropic 端点客户端封装。

使用 anthropic SDK，指向 AIProxy 中转站的 Anthropic 端点。
Kiro 分组：0.2x 倍率，支持 claude-sonnet-4-5-20250929 / claude-haiku-4-5-20251001。
"""
import os
import anthropic


def _get_client():
    """创建 Anthropic 客户端，指向 AIProxy。"""
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    api_base = os.environ.get(
        "CLAUDE_API_BASE",
        "https://aiproxy.superaichao.xin/api/v1/anthropic",
    )
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY 环境变量未设置")
    return anthropic.Anthropic(api_key=api_key, base_url=api_base)


async def send_message(
    prompt: str,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 256,
    temperature: float = 0.7,
) -> str:
    """发送单条消息到 Claude，返回文本响应。

    用于模拟学生作答（高 temperature 增加随机性）和评判（低 temperature）。
    使用同步 SDK 在 asyncio 中通过 run_in_executor 调用。
    """
    import asyncio

    client = _get_client()
    loop = asyncio.get_running_loop()

    def _call():
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

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

    client = _get_client()
    loop = asyncio.get_running_loop()

    def _call():
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{
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
        )
        return response.content[0].text

    return await loop.run_in_executor(None, _call)
