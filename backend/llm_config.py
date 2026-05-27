"""LLM Provider 配置 — 多 provider fallback 链。

所有 LLM 调用通过 llm_client.py 统一路由，按此列表顺序尝试。
支持多 provider fallback 链，按优先级自动切换。
"""
import os
from llm_policy import resolve_model_profile

LEGACY_NATIVE_MODEL_OVERRIDE_ENV = "LLM_ALLOW_NATIVE_MODEL_OVERRIDE"
VISION_PROVIDER_ENV = "LLM_VISION_PROVIDER"

QWEN_VISION_PROVIDER_NAMES = {"qwen", "qwen_vision", "dashscope"}
NATIVE_VISION_PROVIDER_NAMES = {"native", "gemini", "google", "primary"}

PROVIDERS = [
    {
        "name": "qwen_vision",
        "model_env": "QWEN_VISION_MODEL",
        "model_default": "qwen3-vl-plus",
        "api_format": "openai_chat",
        "base_url_env": "QWEN_API_BASE",
        "base_url_default": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_path": "/chat/completions",
        "key_envs": ["QWEN_API_KEY", "DASHSCOPE_API_KEY"],
        "supports_images": True,
        "vision_only": True,
        "response_format": "json_object",
        "model_role": "vision",
        "model_policy": "exam-review-qwen-vision",
        "max_tokens": 8192,
        "semaphore_limit": 6,
        "retry_count": 1,
        "no_proxy": True,
    },
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


def _provider_key_envs(provider: dict) -> list[str]:
    envs = []
    if provider.get("key_env"):
        envs.append(provider["key_env"])
    envs.extend(provider.get("key_envs") or [])
    return list(dict.fromkeys(envs))


def _select_configured_key_env(provider: dict) -> str | None:
    for env_name in _provider_key_envs(provider):
        if os.environ.get(env_name, ""):
            return env_name
    return None


def _apply_non_native_model_env(provider: dict) -> None:
    env_name = provider.get("model_env")
    if not env_name or provider.get("api_format") == "native_sdk":
        return
    provider["model"] = (
        os.environ.get(env_name, "").strip()
        or provider.get("model")
        or provider.get("model_default", "")
    )


def _filter_vision_providers(providers: list[dict], requires_images: bool) -> list[dict]:
    if not requires_images:
        return providers

    configured = os.environ.get(VISION_PROVIDER_ENV, "auto").strip().lower() or "auto"
    if configured in QWEN_VISION_PROVIDER_NAMES:
        return [p for p in providers if p.get("name") == "qwen_vision"]
    if configured in NATIVE_VISION_PROVIDER_NAMES:
        return [p for p in providers if p.get("api_format") == "native_sdk"]

    qwen = [p for p in providers if p.get("name") == "qwen_vision"]
    if qwen:
        return qwen
    return providers


def _qwen_key_configured() -> bool:
    for template in PROVIDERS:
        if template.get("name") != "qwen_vision":
            continue
        return _select_configured_key_env(template) is not None
    return False


def _skip_by_vision_preference(provider: dict, requires_images: bool) -> bool:
    if not requires_images:
        return False

    configured = os.environ.get(VISION_PROVIDER_ENV, "auto").strip().lower() or "auto"
    if configured in QWEN_VISION_PROVIDER_NAMES:
        return provider.get("name") != "qwen_vision"
    if configured in NATIVE_VISION_PROVIDER_NAMES:
        return provider.get("api_format") != "native_sdk"
    if _qwen_key_configured():
        return provider.get("name") != "qwen_vision"
    return False


def get_providers(
    purpose: str | None = None,
    model_override: str | None = None,
    requires_images: bool = False,
) -> list:
    """返回已配置 API key/credentials 的 provider 列表。"""
    result = []
    profile = None

    def native_profile():
        nonlocal profile
        if profile is None:
            profile = resolve_model_profile(purpose=purpose, model_override=model_override)
        return profile

    for template in PROVIDERS:
        p = dict(template)
        if p.get("vision_only") and not requires_images:
            continue
        if requires_images and not p.get("supports_images", False):
            continue
        if _skip_by_vision_preference(p, requires_images):
            continue

        _apply_non_native_model_env(p)
        if p.get("model_env"):
            legacy_env_model = os.environ.get(p["model_env"], "").strip()
            legacy_override_enabled = (
                os.environ.get(LEGACY_NATIVE_MODEL_OVERRIDE_ENV, "").lower()
                in {"1", "true", "yes", "on"}
            )
            if p.get("api_format") == "native_sdk":
                resolved_profile = native_profile()
                configured_model = legacy_env_model if legacy_override_enabled else ""
                p["model"] = configured_model or resolved_profile.model or p.get("model_default", "")
                p["model_role"] = "custom" if configured_model else resolved_profile.role
                p["model_policy"] = resolved_profile.policy_id
                p["purpose"] = resolved_profile.purpose
                if legacy_env_model and not legacy_override_enabled:
                    p["legacy_model_env_ignored"] = p["model_env"]
        if p.get("sdk_module_env"):
            p["sdk_module"] = os.environ.get(p["sdk_module_env"], "")
        if p.get("api_format") == "native_sdk":
            p["cloud_mode"] = os.environ.get("LLM_CLOUD_MODE", "false").lower() == "true"

        configured_key_env = _select_configured_key_env(p)
        if configured_key_env:
            p["key_env"] = configured_key_env
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
    return _filter_vision_providers(result, requires_images)
