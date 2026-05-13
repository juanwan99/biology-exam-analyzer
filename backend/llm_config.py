"""LLM Provider 配置 — Vertex AI Gemini 2.5 Pro（主力） + DeepSeek V4 Pro（fallback）。

所有 LLM 调用通过 llm_client.py 统一路由，按此列表顺序尝试。
Vertex AI 走 HTTPS_PROXY 环境变量代理到 Google API（GCP $1000 赠金）。
"""
import os

PROVIDERS = [
    {
        "name": "vertex",
        "model": "gemini-2.5-pro",
        "api_format": "vertex_genai",
        "sa_file_env": "GOOGLE_APPLICATION_CREDENTIALS",
        "project_env": "VERTEX_AI_PROJECT",
        "location": "us-central1",
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
