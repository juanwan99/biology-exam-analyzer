# 2026-05-27 Agent Search 审题架构基线

## 当前结论

项目已经从“单次模型调用”推进到“证据智能体 + 结构化审题 + grounding 校验 + 显式失败”的架构雏形。

当前默认前端/后端通道仍是 `app_builder`，代码语义上等价于证据增强通道；完整智能体链路使用 `agent_search`，包括：

1. Gemini 题目结构化分析。
2. Discovery Engine Ranking API 为每题重排证据。
3. Agent Search `answer_query` 为每题生成带 citation 的证据上下文。
4. Gemini 生成报告结论。
5. Discovery Engine Check Grounding 校验报告关键结论。
6. support/citation 不足时显式进入失败或人工复核，不再静默用假数据覆盖。

## 最新通过产物

Git 基线：

- 远端分支：`clean-for-submission`
- 远端提交：以标签 `baseline-2026-05-27-agent-search-architecture` 指向的提交为准
- 远端标签：`baseline-2026-05-27-agent-search-architecture`

本地报告：

- `C:\Users\Administrator\Documents\New project\api\reports\zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.html`
- `C:\Users\Administrator\Documents\New project\api\reports\zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf`

远端报告：

- `/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.html`
- `/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf`

说明：`pdfrootfix` 是用已经通过的 E2E 响应 JSON 重放报告渲染生成的，未重新消耗 LLM；业务数据与 `zhuzhou_yimo_arch_agent_search_qualityroot_e2e_20260527.response.json` 一致，只修复 PDF/HTML 导出版式。

## 最新 E2E 证据

来源响应：

- 本地：`C:\Users\Administrator\Documents\New project\api\reports\zhuzhou_yimo_arch_agent_search_qualityroot_e2e_20260527.response.json`
- 远端：`/home/ubuntu/biology-exam-analyzer/reports/zhuzhou_yimo_arch_agent_search_qualityroot_e2e_20260527.response.json`

关键指标：

- 题目数：21
- pipeline status：`ok`
- metadata blockers：`[]`
- metadata warnings：`[]`
- failure_events：`[]`
- report_error：`None`
- report grounding：`ok`
- grounding checks：57
- model calls：66
- Discovery Ranking：21
- Agent Search answer_query：21
- Check Grounding：57
- unsupported Discovery generation：0
- direct Discovery generation：0
- evidence gap questions：`[]`
- missing rank question ids：`[]`

难度排序高压题：

- Q21：10.0，14 分
- Q20：9.1，12 分
- Q17：8.0，11 分
- Q19：7.6，12 分
- Q18：7.3，11 分

## 最新验证命令

本地 targeted report tests：

```text
python -m pytest backend/test_report_commercial_html.py backend/test_report_product_publish.py -q
41 passed in 0.36s
```

远端完整后端测试：

```text
docker exec -w /app -e PYTHONPATH=/app biology_backend python -m pytest -q
591 passed, 8 warnings in 16.67s
```

远端 PDF 重放生成：

```text
/app/reports/zhuzhou_yimo_arch_agent_search_qualityroot_pdfrootfix_20260527.pdf
pdf_size=322086
html_size=975904
```

PDF 视觉 QA：

```text
PyMuPDF render audit
pages=15
problem_count=0
metrics_path=%TEMP%\report_visual_qa_20260527_pdfrootfix_final\visual_metrics.json
```

Browser 插件说明：

- Codex Browser 对 `file://C:/Users/.../api/reports/...html` 导航被 URL policy 拦截。
- 本轮未绕过浏览器策略；改用 PDF 出版物本身做视觉 QA。

## 本轮根因修复

PDF 之前的问题不是单个图表字体，而是打印布局根因：

1. PDF 专用渲染器把 6 个核心图表和 3 个细粒度图表塞进 CSS grid，由 WeasyPrint 自动分页。
2. 图表 HTML 同时包含桌面 SVG 和移动端 fallback 卡片，PDF 样式没有隐藏移动端 fallback。
3. 结果出现空白列、标题孤页、图表残片跨页、图表被压小。

修复：

1. PDF 图表页改为显式分页。
2. 核心图表和细粒度图表改为一图一页，优先可读性和分页稳定性。
3. PDF 样式隐藏 `.chart-mobile-list`，防止移动端 fallback 混入打印版。
4. PDF 图表高度统一提高到 94mm。
5. 移除图表页后方的补充说明面板，避免大图后文本残片跨页。
6. 新增测试防止退回三列自动分页。

## 环境配置基线

远端 `.env` 当前关键项：

```text
LLM_LOCATION=global
EXAM_REVIEW_CHANNEL=app_builder
LLM_EXAM_REVIEW_FLASH_MODEL=publishers/google/models/gemini-3-flash-preview
LLM_EXAM_REVIEW_PRO_MODEL=publishers/google/models/gemini-3.1-pro-preview
DISCOVERY_ENGINE_ENGINE_ID=biology-review-engine
DISCOVERY_ENGINE_ANSWER_QPM=12
DISCOVERY_ENGINE_ANSWER_RETRIES=3
DISCOVERY_ENGINE_ANSWER_RETRY_BASE_DELAY=20
```

## 当前仍不应宣称完成的事项

1. 已有最小范围远端 commit/tag 作为架构基线，但远端工作树仍混有大量历史报告、调试脚本和无关未提交变更，不能用“整体干净工作树”证明交付。
2. `pdfrootfix` 是基于已通过响应重放渲染，不是重新跑一整份 LLM E2E。
3. 若要把 `pdfrootfix` 作为正式对外 URL，需要决定是否覆盖旧 `zhuzhou_yimo_arch_agent_search_qualityroot_e2e_20260527.html/pdf` 或保留新文件名。
4. `app_builder` 与 `agent_search` 的产品命名还需要前后端统一：日常默认可以继续 `app_builder`，但完整 Agent Search 证据智能体应明确可选。
5. 本机 `remote_edit` 仍停留在 `master`，远端部署仓库在 `clean-for-submission`；本机镜像需要后续单独整理，不能直接当部署状态。

## 建议下一步

1. 将本机 `remote_edit` 对齐到远端 `clean-for-submission` 基线，或新建干净工作树继续开发。
2. 删除或归档历史 E2E 报告/调试脚本，建立干净 artifacts 目录规则。
3. 决定正式报告 URL 使用 `pdfrootfix` 新文件还是覆盖旧 E2E 文件。
4. 在用户确认成本后，再跑一次完整 `agent_search` E2E，验证未来新报告从试卷到 PDF 全链路都走最新 PDF 版式。
