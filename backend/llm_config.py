"""LLM Provider 配置 — DeepSeek 单 provider。

所有 LLM 调用通过 llm_client.py 统一路由。
"""
import os

PROVIDERS = [
    {
        "name": "deepseek",
        "model": "deepseek-chat",
        "api_format": "openai_chat",
        "base_url_env": "DEEPSEEK_API_BASE",
        "base_url_default": "https://api.deepseek.com/v1/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "max_tokens": 8192,
        "semaphore_limit": 5,
        "retry_count": 2,
    },
]


def get_providers() -> list:
    """返回已配置 API key 的 provider 列表。"""
    return [p for p in PROVIDERS if os.environ.get(p["key_env"], "")]
