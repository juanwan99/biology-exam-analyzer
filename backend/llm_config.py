"""LLM Provider 配置 — DeepSeek V4 Pro（主力） + Gemini 3 Pro（视觉 fallback）。

所有 LLM 调用通过 llm_client.py 统一路由，按此列表顺序尝试。
"""
import os

PROVIDERS = [
    {
        "name": "deepseek",
        "model": "deepseek-v4-pro",
        "api_format": "openai_chat",
        "base_url_env": "DEEPSEEK_API_BASE",
        "base_url_default": "https://api.deepseek.com/v1/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "max_tokens": 8192,
        "semaphore_limit": 5,
        "retry_count": 2,
    },
    {
        "name": "gemini",
        "model": "gemini-3-pro-preview",
        "api_format": "openai_chat",
        "base_url_env": None,
        "base_url_default": "https://aiberm.com/v1/chat/completions",
        "key_env": "GEMINI_RELAY_KEY",
        "max_tokens": 8192,
        "semaphore_limit": 5,
        "retry_count": 2,
    },
]


def get_providers() -> list:
    """返回已配置 API key 的 provider 列表。"""
    return [p for p in PROVIDERS if os.environ.get(p["key_env"], "")]
