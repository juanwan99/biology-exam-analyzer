"""LLM Provider 配置 — 多 provider fallback 链。

所有 LLM 调用通过 llm_client.py 统一路由，按此列表顺序尝试。
支持多 provider fallback 链，按优先级自动切换。
"""
import os
from llm_policy import resolve_model_profile

LEGACY_NATIVE_MODEL_OVERRIDE_ENV = "LLM_ALLOW_NATIVE_MODEL_OVERRIDE"

PROVIDERS = [
    {
        "name": "primary",
        "model_env": "LLM_NATIVE_MODEL",
        "model_default": "",
        "api_format": "native_sdk",
        "sdk_module_env": "LLM_SDK_MODULE",
        "cloud_mode": os.environ.get("LLM_CLOUD_MODE", "false").lower() == "true",
        "sa_file_env": "LLM_SA_CREDENTIALS",
        "project_env": "LLM_PROJECT",
        "location_env": "LLM_LOCATION",
        "supports_images": True,
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


def get_providers(purpose: str | None = None, model_override: str | None = None) -> list:
    """返回已配置 API key/credentials 的 provider 列表。"""
    result = []
    profile = resolve_model_profile(purpose=purpose, model_override=model_override)
    for template in PROVIDERS:
        p = dict(template)
        if p.get("model_env"):
            legacy_env_model = os.environ.get(p["model_env"], "").strip()
            legacy_override_enabled = (
                os.environ.get(LEGACY_NATIVE_MODEL_OVERRIDE_ENV, "").lower()
                in {"1", "true", "yes", "on"}
            )
            configured_model = legacy_env_model if legacy_override_enabled else ""
            p["model"] = configured_model or profile.model or p.get("model_default", "")
            p["model_role"] = "custom" if configured_model else profile.role
            p["model_policy"] = profile.policy_id
            p["purpose"] = profile.purpose
            if legacy_env_model and not legacy_override_enabled:
                p["legacy_model_env_ignored"] = p["model_env"]
        if p.get("sdk_module_env"):
            p["sdk_module"] = os.environ.get(p["sdk_module_env"], "")
        if p.get("api_format") == "native_sdk":
            p["cloud_mode"] = os.environ.get("LLM_CLOUD_MODE", "false").lower() == "true"

        if p.get("key_env") and os.environ.get(p["key_env"], ""):
            result.append(p)
        elif p.get("sa_file_env"):
            sa_path = os.environ.get(p["sa_file_env"], "")
            if (
                sa_path
                and os.path.exists(sa_path)
                and p.get("sdk_module")
                and p.get("model")
            ):
                result.append(p)
    return result
