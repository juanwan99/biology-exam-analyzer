"""LLM Provider 配置 — 多 provider fallback 链。

所有 LLM 调用通过 llm_client.py 统一路由，按此列表顺序尝试。
支持多 provider fallback 链，按优先级自动切换。
"""
import os

VISION_PROVIDER_ENV = "LLM_VISION_PROVIDER"
QWEN_TEXT_FALLBACK_ENV = "LLM_ENABLE_QWEN_TEXT_FALLBACK"

QWEN_VISION_PROVIDER_NAMES = {"qwen", "qwen_vision", "dashscope"}
TEXT_REVIEW_PURPOSES = {
    "big_question_feature_extraction",
    "competency_analysis",
    "feature_extraction",
    "missing_evidence_repair",
    "question_analysis",
    "question_analysis_retry",
    "report_insights",
    "report_teaching_suggestions",
}

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
        "name": "deepseek",
        "model_env": "DEEPSEEK_MODEL",
        "model": "deepseek-v4-pro",
        "api_format": "openai_chat",
        "base_url_env": "DEEPSEEK_API_BASE",
        "base_url_default": "https://api.deepseek.com/v1/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model_role": "analysis_text",
        "model_policy": "exam-review-deepseek-primary",
        "reasoning_effort": "medium",
        "response_format": "json_object",
        "max_tokens": 16384,
        "subq_max_tokens": 65536,
        "semaphore_limit": 30,
        "retry_count": 2,
        "no_proxy": True,
    },
    {
        "name": "qwen_text",
        "model_env": "QWEN_TEXT_MODEL",
        "model_default": "qwen-plus",
        "api_format": "openai_chat",
        "base_url_env": "QWEN_API_BASE",
        "base_url_default": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_path": "/chat/completions",
        "key_envs": ["QWEN_API_KEY", "DASHSCOPE_API_KEY"],
        "model_role": "analysis_text",
        "model_policy": "exam-review-qwen-text",
        "max_tokens": 8192,
        "semaphore_limit": 6,
        "retry_count": 1,
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
    if not env_name:
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


def _env_truthy(env_name: str) -> bool:
    return os.environ.get(env_name, "").strip().lower() in {"1", "true", "yes", "on"}


def _qwen_text_fallback_enabled() -> bool:
    return _env_truthy(QWEN_TEXT_FALLBACK_ENV)


def _skip_by_vision_preference(provider: dict, requires_images: bool) -> bool:
    if not requires_images:
        return False

    configured = os.environ.get(VISION_PROVIDER_ENV, "auto").strip().lower() or "auto"
    if configured in QWEN_VISION_PROVIDER_NAMES:
        return provider.get("name") != "qwen_vision"
    if _qwen_key_configured():
        return provider.get("name") != "qwen_vision"
    return False


def _apply_purpose_preference(
    providers: list[dict],
    purpose: str | None,
    requires_images: bool,
) -> list[dict]:
    if requires_images:
        return providers

    normalized = (purpose or "").strip()
    if not _qwen_text_fallback_enabled():
        providers = [
            provider for provider in providers
            if provider.get("name") != "qwen_text"
        ]
    if normalized in TEXT_REVIEW_PURPOSES:
        priority = {"deepseek": 0, "qwen_text": 1}
        return sorted(
            providers,
            key=lambda provider: priority.get(provider.get("name"), 50),
        )
    return providers


def get_providers(
    purpose: str | None = None,
    model_override: str | None = None,
    requires_images: bool = False,
) -> list:
    """返回已配置 API key/credentials 的 provider 列表。"""
    result = []

    for template in PROVIDERS:
        p = dict(template)
        if purpose in ("question_analysis_subquestion", "report_insights", "report_teaching_suggestions", "report_grounding_check") and p.get("subq_max_tokens"):
            p["max_tokens"] = p["subq_max_tokens"]
        if p.get("vision_only") and not requires_images:
            continue
        if requires_images and not p.get("supports_images", False):
            continue
        if _skip_by_vision_preference(p, requires_images):
            continue

        _apply_non_native_model_env(p)

        configured_key_env = _select_configured_key_env(p)
        if configured_key_env:
            p["key_env"] = configured_key_env
            result.append(p)
    result = _filter_vision_providers(result, requires_images)
    return _apply_purpose_preference(result, purpose, requires_images)
