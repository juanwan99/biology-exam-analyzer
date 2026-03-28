---
type: handoff
created: 2026-03-28 11:00:06
project_dir: /home/ubuntu/biology-exam-analyzer
design: /home/ubuntu/biology-exam-analyzer/docs/plans/2026-03-28-difficulty-v3-design.md
plan: 待编写（v3.1 大题结构化拆分评估计划）
gpt_consult: /home/ubuntu/biology-exam-analyzer/docs/plans/.codex-difficulty-v3-consult-raw.log
---

# 交接卡：biology-exam-analyzer 难度评分 v3.1 + 遗留修复

## 本会话完成的工作（Commits: d54426d..fc2c549）

### 1. LLM Fallback 链（已上线）
- 统一 LLM 客户端 `llm_client.py`，内置 Opus 4.6 → GPT 5.4 → Gemini 3 Pro 逐调用 fallback
- `gemini_analyzer.py` / `claude_client.py` / `competency_analyzer.py` 全部迁移到统一客户端
- Vecto API key 已配置，docker-compose 已传入
- 80 tests pass（14 llm_client + 37 core + 28 feature + 1 report）
- **已知问题**：Opus 4.6 在 AIProxy 被限流（404/500），当前全部降级到 GPT 5.4 运行

### 2. 难度评分 v3（已上线）
- bloom 降为报告标签，不参与评分
- 删除 qtype_factor 双重计分
- 新增 3 个评分维度：working_memory（0.28权重）、chain_coupling（耦合乘数）、trap_density（0.18权重）
- 选择题评分基本合理（4.2-8.8），非选择题分布 7.6-10.0

### 3. 命题质量 quality_sensitivity（已上线）
- 政治敏感性/舆情风险审查维度，嵌入 feature_extractor prompt

### 4. Bug 修复
- `competency_analyzer.py` 调用已删除的 `_call_with_retry()` → 素养分析全挂回退默认"科学思维"（已修复）
- `analysis_router.py:445` 缺少 `await`（已修复）
- `deps.py` 检查错误的 `GEMINI_API_KEY`（已修正为 `get_providers()`）

### 5. 文档
- CLAUDE.md + WHAT_IS_THIS.md 基于实际代码全面校准

## 约束与偏好（design.md 未记录的增量信息）

### T3 流程

### 用户核心关切
- **"每道题都必须分析成功"** — 这是 fallback 链的设计动机，任何改动不能破坏这个保证
- **"难度打分不能形式化"** — 用户明确反对 Bloom 分类法驱动评分，要求基于"学生做错概率"而非"认知层级高低"
- **"改 prompt 是钝器"** — 用户指出 prompt 调整影响所有题目，大题低估不能靠 prompt 修

### GPT 5.4 设计咨询共识（Claude×GPT）
完整输出 → `/home/ubuntu/biology-exam-analyzer/docs/plans/.codex-difficulty-v3-consult-raw.log`

核心结论：
1. **不改 prompt，改输出结构** — 大题仍整题输入，但输出拆成"小问特征 + 依赖图"
2. **废弃 `steps × coupling_multiplier`** — 大题改用关键路径模型：`effective_steps = critical_path_steps + 0.35 × (total_steps - critical_path_steps)`
3. **wm 用峰值 + 跨问保持** — `wm = clip(max(各小问wm) + 0.4×(路径长-1) + 0.3×shared_context_load, 1, 5)`
4. **novelty 拆分** — 区分"内容新颖"和"方法新颖"（In-Fusion 技术 vs 番茄红素知识）
5. **Q19 偏高（9.9 应为 8-9）** — 步骤多但不是全链死锁，当前公式对高 steps 放大过强
6. **选择题扎堆同分** — 5.4 出现 6 次，特征分辨率不足

### 遗留的已知问题
| 问题 | 优先级 | 说明 |
|------|--------|------|
| Opus 限流 | 低 | AIProxy Kiro 分组对 Opus 限流严格，fallback 到 GPT 正常工作，不阻塞功能 |
| 素养分析修复验证 | 中 | competency_analyzer 已修复，用户尚未从浏览器验证效果 |
| 选择题分辨率 | 低 | 10/16 道选择题只有 4.6 和 5.4 两个分数，需要调整映射曲线或特征粒度 |
| 量表天花板 | 低 | Q20=10.0 顶格，更难的题无分辨空间，GPT 建议分题型校准 |

### 远程操作约定
- 代码在京东云：`ssh jdcloud`，路径 `~/biology-exam-analyzer/`
- Docker 部署：`docker-compose up -d --build backend`（清华 pip 镜像已配置）
- 测试：`docker-compose exec -T backend python -m pytest test_llm_client.py test_core_modules.py test_feature_difficulty.py -v`
- 日志：`docker logs biology_backend 2>&1 | grep ...`

## 下一步待执行任务

### 优先级 1：难度 v3.1 — 大题结构化拆分评估
- 设计文档：`/home/ubuntu/biology-exam-analyzer/docs/plans/2026-03-28-difficulty-v3-design.md`
- GPT 咨询：`/home/ubuntu/biology-exam-analyzer/docs/plans/.codex-difficulty-v3-consult-raw.log`
- 需要：写 v3.1 设计文档（大题 JSON schema + 聚合规则）→ plan → 实现
- 改动范围：`feature_extractor.py`（大题 prompt 分支）+ `rule_scorer.py`（大题聚合公式）+ `difficulty_pipeline.py`（题型分流）

### 优先级 2：用户浏览器验证
- 请用户上传试卷，确认：素养分析不再全是"科学思维"、难度 v3 评分分布合理、fallback 日志正常

## 启动 Prompt

```
[biology-exam-analyzer] Executor | {粘贴当前时间}
项目: /home/ubuntu/biology-exam-analyzer（京东云 ssh jdcloud）
读取 /home/ubuntu/biology-exam-analyzer/docs/plans/2026-03-28-difficulty-v3-handoff.md，
参考设计 /home/ubuntu/biology-exam-analyzer/docs/plans/2026-03-28-difficulty-v3-design.md，
参考 GPT 咨询 /home/ubuntu/biology-exam-analyzer/docs/plans/.codex-difficulty-v3-consult-raw.log。

任务：实现难度评分 v3.1 — 大题结构化拆分评估。
核心改动：大题（分值≥8）输出小问特征+依赖图，聚合后再走现有评分公式。
GPT 建议的关键路径模型：effective_steps = critical_path_steps + 0.35 × (total_steps - critical_path_steps)。

先写 v3.1 设计文档，再用 writing-plans skill 写实现计划。完成后输出审查交接单。使用 codex-review skill 进行 GPT 代码审查。
```
