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
