# LLM 逐题 Fallback 链设计文档

> snapshot: 2026-03-27
> 状态: 设计确认，待实现
> 决策方法: 深度代码审查 → 方案讨论 → 确认

## §0 覆盖声明

本设计解决 biology-exam-analyzer 的以下问题：
- 无 fallback 机制导致单题分析失败
- 模型 ID 过期风险
- 两套 LLM 客户端不统一
- `/api/analyze` 缺少 await bug

## §1 核心决策摘要

| 决策 | 结论 | 理由 |
|------|------|------|
| fallback 层级 | LLM 客户端层（每次调用独立 fallback） | 3 个调用点自动受益，粒度最细 |
| fallback 链 | Opus 4.6 → GPT 5.4 → Gemini 3 Pro | 质量优先，成本递减 |
| 统一客户端 | 合并 gemini_analyzer 和 claude_client 的 httpx 逻辑 | 消除重复，统一重试/fallback |
| Gemini 接入 | Vecto 中转（OpenAI Chat 格式） | AIProxy Gemini 全挂，Vecto 稳定 |
| 不 fallback 条件 | 400 Bad Request | prompt 问题，换模型无效 |

## §2 Provider 配置

```python
PROVIDERS = [
    {
        "name": "claude-opus",
        "model": "claude-opus-4-6",
        "api_format": "anthropic",
        "base_url_env": "CLAUDE_API_BASE",
        "base_url_default": "https://aiproxy.superaichao.xin/api/v1/anthropic/v1/messages",
        "key_env": "CLAUDE_API_KEY",
        "auth_header": "x-api-key",
        "extra_headers": {"anthropic-version": "2023-06-01"},
        "max_tokens": 8192,
        "semaphore": 3,
        "retry_count": 2,
        "supports_vision": True,
    },
    {
        "name": "gpt",
        "model": "gpt-5.4",
        "api_format": "openai_responses",
        "base_url_env": None,
        "base_url_default": "https://aiproxy.superaichao.xin/api/v1/openai/v1/responses",
        "key_env": "AIPROXY_OAI_KEY",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "max_tokens": 16384,
        "semaphore": 5,
        "retry_count": 2,
        "supports_vision": True,
    },
    {
        "name": "gemini-vecto",
        "model": "gemini-3-pro-preview",
        "api_format": "openai_chat",
        "base_url_env": "VECTO_API_BASE",
        "base_url_default": "https://api.vectorengine.ai/v1/chat/completions",
        "key_env": "VECTO_API_KEY",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "max_tokens": 8192,
        "semaphore": 5,
        "retry_count": 2,
        "supports_vision": True,
    },
]
```

## §3 统一客户端接口

### 3.1 对外接口

```python
async def llm_call(
    messages: list[dict],    # [{"role": "user", "content": str | list}]
    max_tokens: int = 4096,
    temperature: float = 0,
    timeout: float = 120.0,
) -> str:
    """统一 LLM 调用，内置 fallback。返回纯文本响应。"""
```

- `messages` 使用 OpenAI Chat 格式作为内部标准
- 客户端内部根据 `api_format` 自动转换为各 provider 的格式
- 图片统一用 `{"type": "image_url", "image_url": {"url": "data:...;base64,..."}}`

### 3.2 Fallback 逻辑

```
for provider in PROVIDERS:
    if provider.key not configured:
        skip (log debug)
    try:
        return _call_single(provider, messages, max_tokens, temperature, timeout)
    except HTTP 400/401/403:
        if 403 and "model not found":
            log error "模型 ID 可能过期"
            continue  # 可能是模型 ID 问题，尝试下一个
        raise  # 其他 4xx 不 fallback
    except (timeout / 429 / 5xx / network):
        log warning f"Provider {name} failed: {error}, trying next"
        continue
raise AllProvidersFailed(last_errors)
```

### 3.3 单 provider 重试

每个 provider 内部重试 `retry_count` 次（默认 2），指数退避：
- 429/503: wait 2^attempt + 2s
- 500/502/529: wait 2^attempt
- 网络错误: wait 2^attempt

### 3.4 格式适配（_call_single 内部）

**请求转换：**

| 源格式（内部标准） | → Anthropic | → Responses | → Chat |
|-------------------|-------------|-------------|--------|
| `{"role":"user","content":"text"}` | `{"role":"user","content":[{"type":"text","text":"..."}]}` | `[{"role":"user","content":[{"type":"input_text","text":"..."}]}]` | 不变 |
| image_url base64 | `{"type":"image","source":{"type":"base64",...}}` | `{"type":"input_image","image_url":"data:..."}` | 不变 |

**响应提取：**

| API | 文本位置 |
|-----|---------|
| Anthropic | `response["content"][0]["text"]` |
| Responses | `response["output"][0]["content"][0]["text"]` |
| Chat | `response["choices"][0]["message"]["content"]` |

## §4 改动清单

### 4.1 `llm_config.py` — 重写

- 删除旧的 `MODEL_PROVIDER` / `_PROVIDER_CONFIG` / `get_model()` / `get_max_tokens()` / `get_api_format()`
- 新增 `PROVIDERS` 列表（§2）
- 新增 `get_providers()` → 返回已配置（key 存在）的 provider 列表

### 4.2 `claude_client.py` — 重写为 `llm_client.py`

- 新文件名 `llm_client.py`（保留 `claude_client.py` 作为兼容别名 import）
- 实现 §3 的 `llm_call()` 接口
- 删除旧的 `_call_claude()` / `_call_gpt()` 分叉逻辑
- 保留 `send_message_gpt()` 作为兼容接口，内部调用 `llm_call()`
- 保留 `send_message_with_image()` 兼容接口

### 4.3 `gemini_analyzer.py` — 改造

- 删除 `_call_with_retry()`（~60 行）
- 删除 `_convert_content()`（~25 行）
- 删除 `_get_client()`、`self._client`、`self._api_key`、`self._api_url`、`self._semaphore`
- `split_questions()` 和 `analyze_question()` 改为调用 `llm_client.llm_call(messages, ...)`
- 保留：prompt 构建、JSON 解析、业务逻辑

### 4.4 `deps.py` — 修正

- `get_gemini_analyzer()`: 删除 `GEMINI_API_KEY` 检查（改为检查任意 provider 可用）
- 构造 `GeminiAnalyzer()` 不再传 `api_key` / `api_base`

### 4.5 `analysis_router.py:445` — Bug fix

```python
# 旧（缺 await）
questions = gemini_analyzer.split_questions(image_bytes, extracted_text=extracted_text)
# 新
questions = await gemini_analyzer.split_questions(image_bytes, extracted_text=extracted_text)
```

### 4.6 `.env` — 新增

```
VECTO_API_KEY=<从 zhixue-server 复制>
VECTO_API_BASE=https://api.vectorengine.ai/v1/chat/completions
```

### 4.7 `docker-compose.yml` — 新增环境变量

```yaml
environment:
  - VECTO_API_KEY=${VECTO_API_KEY}
  - VECTO_API_BASE=${VECTO_API_BASE:-https://api.vectorengine.ai/v1/chat/completions}
```

## §5 不改动的文件

| 文件 | 原因 |
|------|------|
| `feature_extractor.py` | 已用 `send_message_gpt()`，兼容接口不变，自动受益 |
| `competency_analyzer.py` | 通过 `gemini_analyzer` 调用，自动受益 |
| `rule_scorer.py` | 纯计算，无 LLM |
| `difficulty_pipeline.py` | 编排层，不直接调 LLM |
| `report_generator.py` | PDF 渲染，无 LLM |
| `report_insights.py` | 已用 `send_message_gpt()`，自动受益 |
| 前端 | 不涉及 |

## §6 验证策略

1. **单元测试**：mock 3 个 provider，验证 fallback 链（第 1 个失败 → 第 2 个成功）
2. **集成验证**：上传一份真实试卷，确认所有题目分析成功
3. **故障注入**：临时禁用 CLAUDE_API_KEY，验证自动降级 GPT
4. **日志确认**：每次 fallback 必须有 WARNING 日志，标明哪个 provider 失败、降级到哪个

## §7 风险

| 风险 | 缓解 |
|------|------|
| Vecto key 可能有速率限制 | Semaphore(5) 控制并发，作为第 3 级兜底调用量小 |
| 三个 provider 全挂 | 极端情况，记录错误让用户知道"服务暂时不可用" |
| 模型输出格式不一致 | JSON 解析已有容错（extract_json / parse_features），不同模型的 JSON 风格差异可以容忍 |
| gemini_analyzer 改造影响面大 | 保留所有对外接口（split_questions / analyze_question 签名不变） |
