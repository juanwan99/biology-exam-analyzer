# 审题证据系统接入说明

本文档记录当前 GenAI App Builder / Discovery Engine 在审题系统中的真实边界。它不是把 Gemini 生成伪装成赠金渠道，而是把 Discovery Engine 用作证据排序、Agent Search 引用和 grounding 校验层。

## 通道语义

`model`

- 只走普通模型链路。
- 不要求 Discovery Engine Ranking、Agent Search answer 或 Check Grounding。

`evidence`

- 普通 Gemini 生成仍然存在。
- 每题分析前使用 Discovery Engine Ranking API 重排证据。
- 报告生成后使用 Check Grounding API 校验关键结论。
- `app_builder`、`genai_app_builder`、`discovery`、`grant`、`1000_grant` 都归一化为 `evidence`。

`agent_search`

- 在 `evidence` 的基础上，每题额外调用 Agent Search `answer_query`。
- answer 必须带 citations；没有引用不能算成功。
- 适合最终质量验收和对外成品报告。

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
EXAM_REVIEW_CHANNEL=app_builder
LLM_LOCATION=global
LLM_EXAM_REVIEW_FLASH_MODEL=publishers/google/models/gemini-3-flash-preview
LLM_EXAM_REVIEW_PRO_MODEL=publishers/google/models/gemini-3.1-pro-preview

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

## 失败策略

系统禁止静默降级。

- Ranking 调用失败：题目分析失败，记录 Discovery Engine Ranking 错误。
- Ranking 返回空记录：失败，不继续假装有证据。
- Agent Search answer skipped：失败或进入人工复核。
- Agent Search answer 无 citation：不计为成功。
- Check Grounding 调用失败：报告生成失败。
- Check Grounding 支撑分不足：标记 `needs_review`，关键结论不得伪装为已校验。
- LLM 结构化解析失败：记录解析失败，不用旧数据或平均值填充。

## 移除路径

如果以后要整体移除 Discovery Engine / GenAI App Builder：

1. 将 `EXAM_REVIEW_CHANNEL` 改成 `model`。
2. 保留 Gemini 生成链路和难度算法。
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
592 passed, 8 warnings
```

最新报告视觉 QA：

```text
zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf
pages=15
problem_count=0
```

最新报告位置：

```text
远端：
/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.html
/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf

本机：
C:\Users\Administrator\Documents\New project\api\reports\zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.html
C:\Users\Administrator\Documents\New project\api\reports\zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf
```

本机干净代码副本：

```text
C:\Users\Administrator\Documents\New project\remote_edit\biology-exam-analyzer-clean-20260527
```

旧目录 `C:\Users\Administrator\Documents\New project\remote_edit\biology-exam-analyzer` 保留历史工作痕迹，当前不再作为架构基准使用。
