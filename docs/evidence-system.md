# 审题证据系统接入说明

本文档记录当前 GenAI App Builder / Discovery Engine 在审题系统中的真实边界。它不是把 Google/Gemini 文本生成伪装成赠金渠道，而是把 Discovery Engine 用作证据排序、Agent Search 引用和 grounding 校验层；文本审题主力是 DeepSeek V4 Pro，Qwen 默认只用于图片/视觉题面预处理。

## 通道语义

`model`

- 只走普通模型链路。
- 不要求 Discovery Engine Ranking、Agent Search answer 或 Check Grounding。

`evidence`

- 普通 LLM 生成走 DeepSeek V4 Pro；Qwen text fallback 默认关闭，只有显式 `LLM_ENABLE_QWEN_TEXT_FALLBACK=true` 才允许作为可审计 fallback。
- 每题分析前使用 Discovery Engine Ranking API 重排证据。
- 报告生成后使用 Check Grounding API 校验关键结论。
- `app_builder`、`genai_app_builder`、`discovery`、`grant`、`1000_grant` 都归一化为 `evidence`。

`agent_search`

- 在 `evidence` 的基础上，每题额外调用 Agent Search `answer_query`。
- answer 必须带 citations；没有引用不能算成功。
- 当前默认通道，适合最终质量验收和对外成品报告。

`grounded_generation`

- 保留为实验通道。
- 当前不是主链路，不允许作为默认路线。

## 模块边界

- `services/review_channel.py`
  - 统一通道归一化。
  - 防止把 `app_builder` 错误解释成 Discovery Engine 生成。

- `services/discovery_engine_client.py`
  - Discovery Engine HTTP 客户端。
  - 负责 Ranking、Check Grounding、Agent Search answer_query。
  - 失败抛结构化错误，不生成假数据。

- `services/evidence_gateway.py`
  - 业务网关。
  - 提供 `rank_evidence()`、`answer_question()`、`check_grounding()`。
  - no citation / skipped answer / low support 都显式返回或失败。

- `services/evidence_context.py`
  - 题目级证据上下文构建器。
  - 用题目文本做 Ranking，用安全的证据主题 query 调 Agent Search，避免原题被判定 out-of-domain。

- `services/evidence_audit.py`
  - 汇总每题 Ranking、Agent Search、citation、grounding 的使用情况。
  - 生成 `channel_usage`，用于 E2E no-silent-failure gate。

- `report_insights.py`
  - 对报告结论执行 Check Grounding。
  - 支撑不足时标记或失败，不静默输出假结论。

- `report_product_model.py`
  - 将证据完整性、失败原因、数据缺口渲染到报告可见位置。

## 关键环境变量

```bash
EXAM_REVIEW_CHANNEL=agent_search
DEEPSEEK_MODEL=deepseek-v4-pro
QWEN_TEXT_MODEL=qwen-plus
LLM_LOCATION=global
LLM_ENABLE_QWEN_TEXT_FALLBACK=false
LLM_ENABLE_NATIVE_TEXT_FALLBACK=false
LLM_EXAM_REVIEW_FLASH_MODEL=publishers/google/models/gemini-3-flash-preview
LLM_EXAM_REVIEW_PRO_MODEL=publishers/google/models/gemini-3.1-pro-preview
LLM_VISION_PROVIDER=qwen
QWEN_API_KEY=
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_VISION_MODEL=qwen3-vl-plus

DISCOVERY_ENGINE_PROJECT_ID=
DISCOVERY_ENGINE_CREDENTIALS=
DISCOVERY_ENGINE_LOCATION=global
DISCOVERY_ENGINE_RANKING_CONFIG=default_ranking_config
DISCOVERY_ENGINE_GROUNDING_CONFIG=default_grounding_config
DISCOVERY_ENGINE_ENGINE_ID=biology-review-engine

DISCOVERY_ENGINE_ANSWER_QPM=12
DISCOVERY_ENGINE_ANSWER_RETRIES=3
DISCOVERY_ENGINE_ANSWER_RETRY_BASE_DELAY=20
DISCOVERY_ENGINE_TIMEOUT=90
```

如果 `DISCOVERY_ENGINE_PROJECT_ID` 或 `DISCOVERY_ENGINE_CREDENTIALS` 为空，客户端复用 `LLM_PROJECT` 和 `LLM_SA_CREDENTIALS`。

`LLM_EXAM_REVIEW_FLASH_MODEL` / `LLM_EXAM_REVIEW_PRO_MODEL` 只控制显式开启的 native Google 文本 fallback 或 experimental grounded generation。正常审题 LLM 分析不应因为 Google service account 存在就静默切到 Gemini。

## 失败策略

系统禁止静默降级。

- Ranking 调用失败：题目分析失败，记录 Discovery Engine Ranking 错误。
- Ranking 返回空记录：失败，不继续假装有证据。
- Agent Search answer skipped：失败或进入人工复核。
- Agent Search answer 无 citation：不计为成功。
- Check Grounding 调用失败：报告生成失败。
- Check Grounding 支撑分不足：标记 `needs_review`，关键结论不得伪装为已校验。
- LLM 结构化解析失败：记录解析失败，不用旧数据或平均值填充。
- DeepSeek 文本链路失败：失败事件必须进入 metadata/report gate；只有显式 `LLM_ENABLE_QWEN_TEXT_FALLBACK=true` 或 `LLM_ENABLE_NATIVE_TEXT_FALLBACK=true` 时才允许再走对应文本 fallback。

## 移除路径

如果以后要整体移除 Discovery Engine / GenAI App Builder：

1. 将 `EXAM_REVIEW_CHANNEL` 改成 `model`。
2. 保留 DeepSeek/Qwen 生成链路和难度算法。
3. 删除或替换 `services/discovery_engine_client.py`、`services/evidence_gateway.py`、`services/evidence_context.py`、`services/evidence_audit.py`、`services/agent_search_corpus.py`。
4. 删除 `test_evidence_*`、`test_discovery_engine_client.py`、`test_review_channel.py`。
5. 移除 `.env.example` 和 `docker-compose.yml` 中的 Discovery Engine 配置项。

## 当前验证基线

远端基线标签：

```bash
baseline-2026-05-27-full-tested-architecture
```

远端基线提交：

```bash
07250fc9aefa61f22c8e9368d135835d8e98ca89
```

完整后端测试：

```bash
docker exec -w /app -e PYTHONPATH=/app biology_backend python -m pytest -q
```

当前结果：

```text
616 passed, 8 warnings
```

2026-05-28 路由验收：

```text
env_channel=agent_search
question_analysis=[deepseek]
question_analysis_retry=[deepseek]
feature_extraction=[deepseek]
competency_analysis=[deepseek]
big_question_feature_extraction=[deepseek]
missing_evidence_repair=[deepseek]
report_insights=[deepseek]
report_teaching_suggestions=[deepseek]
image_inputs=[qwen_vision]
image_flow=qwen_vision_extracts_visual_context_then_deepseek_reviews_text
native_google_text_fallback=disabled_by_default
```

最新报告视觉 QA：

```text
zhuzhou_yimo_agent_search_qwen_structured_deepseek_review_e2e_20260528_1300.pdf
html_exists=true
pdf_exists=true
response_json_exists=true
```

干净基准全新 E2E：

```text
exam_id=zhuzhou_yimo_agent_search_qwen_structured_deepseek_review_e2e_20260528_1300
channel=agent_search
questions=21
pipeline_status=ok
pipeline_blockers=0
report_error=null
report_grounding_status=ok
report_grounding_check_count=37
fallback_call_count=0
provider_error_call_count=0
parse_media_fallback_warnings=0
retry_questions=[]
evidence_gap_questions=[]
blocked_questions=[]
agent_search_answer_count=21
discovery_rank_count=21
missing_rank_question_ids=[]
unsupported_generation_count=0
```

报告 LLM 调用验收：

```text
report_insights=deepseek/deepseek-v4-pro fallback=0 errors=[]
report_grounding_check=discovery_engine/check_grounding fallback=0 errors=[]
report_teaching_suggestions=deepseek/deepseek-v4-pro fallback=0 errors=[]
```

报告文件大小：

```text
html=960K
pdf=323K
response_json=7.2M
```

最新报告位置：

```text
远端：
/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_agent_search_qwen_structured_deepseek_review_e2e_20260528_1300.html
/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_agent_search_qwen_structured_deepseek_review_e2e_20260528_1300.pdf
/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_agent_search_qwen_structured_deepseek_review_e2e_20260528_1300.response.json

本机：
E:\Asyncova-Company-Ops\15_Server_Ops\biology-exam-analyzer-remote-edit-20260528
```

本机干净代码副本：

```text
E:\Asyncova-Company-Ops\15_Server_Ops\biology-exam-analyzer-remote-edit-20260528
```

旧目录 `C:\Users\Administrator\Documents\New project\remote_edit\biology-exam-analyzer` 保留历史工作痕迹，当前不再作为架构基准使用。
