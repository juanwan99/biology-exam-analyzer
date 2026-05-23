"""LLM Provider 配置 — 多 provider fallback 链。

所有 LLM 调用通过 llm_client.py 统一路由，按此列表顺序尝试。
支持多 provider fallback 链，按优先级自动切换。
"""
import os

PROVIDERS = [
    {
        "name": "primary",
        "model": "deepseek-chat",
        "api_format": "native_sdk",
        "sdk_module": os.environ.get("LLM_SDK_MODULE", ""),
        "cloud_mode": os.environ.get("LLM_CLOUD_MODE", "false").lower() == "true",
        "sa_file_env": "LLM_SA_CREDENTIALS",
        "project_env": "LLM_PROJECT",
        "location_env": "LLM_LOCATION",
        "max_tokens": 16384,
        "thinking_overhead": 3,
        "semaphore_limit": 10,
        "retry_count": 2,
    },
    {
        "name": "deepseek",
        "model": "deepseek-v4-pro",
        "api_format": "openai_chat",
        "base_url_env": "DEEPSEEK_API_BASE",
        "base_url_default": "https://api.deepseek.com/v1/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "max_tokens": 8192,
        "semaphore_limit": 10,
        "retry_count": 2,
        "no_proxy": True,
    },
]


def get_providers() -> list:
    """返回已配置 API key/credentials 的 provider 列表。"""
    result = []
    for p in PROVIDERS:
        if p.get("key_env") and os.environ.get(p["key_env"], ""):
            result.append(p)
        elif p.get("sa_file_env"):
            sa_path = os.environ.get(p["sa_file_env"], "")
            if sa_path and os.path.exists(sa_path):
                result.append(p)
    return result
