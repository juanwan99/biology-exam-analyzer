"""LLM Provider 配置 — DeepSeek V4 Pro（主力） + Gemini 3 Pro（视觉，官方直连）。

所有 LLM 调用通过 llm_client.py 统一路由，按此列表顺序尝试。
Gemini 走宿主机 sing-box 代理到 Google API（proxy_env 指定代理环境变量）。
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
        "base_url_default": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "key_env": "GEMINI_API_KEY",
        "max_tokens": 8192,
        "semaphore_limit": 5,
        "retry_count": 2,
        "proxy_env": "LLM_PROXY",
    },
]


def get_providers() -> list:
    """返回已配置 API key 的 provider 列表。"""
    return [p for p in PROVIDERS if os.environ.get(p["key_env"], "")]
