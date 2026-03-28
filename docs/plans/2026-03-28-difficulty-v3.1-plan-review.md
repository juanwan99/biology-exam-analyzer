# Plan Review: 难度评分 v3.1 大题结构化拆分评估

> GPT Reviewer | 2026-03-28 11:37:52
> Plan: docs/plans/2026-03-28-difficulty-v3.1-plan.md
> Design: docs/plans/2026-03-28-difficulty-v3.1-design.md

## 结论: FAIL

## Finding 清单

| ID | Severity | Category | Status | 处置 |
|----|----------|----------|--------|------|
| F-001 | HIGH | code-bug | verified | 修复：Task 1 增加环检测 + 负例测试 |
| F-002 | HIGH | test-gap | verified | 修复：Task 3 增加 send_message_gpt 级 mock 测试 |
| F-003 | MED | design-concern | verified | 修复：Task 3 增加 points 总和校验 |
| F-004 | MED | design-concern | verified | 修复：统一为 flags（更新设计文档） |
| F-005 | MED | test-gap | verified | 修复：Task 4 补齐边界条件和测试契约 |
| F-006 | LOW | design-concern | suggestion | 接受，记入 v3.2 backlog |

### F-001: 依赖图环检测缺失 (HIGH, code-bug)

**Evidence:** parse_big_question_features 没有环检测；find_critical_path 的拓扑排序未校验覆盖全部节点。LLM 产出 1→2, 2→1 时算法静默退化。

**处置:** verified。在 find_critical_path 中增加环检测（topo_order 长度 != ids 长度 → 返回单节点 fallback）。补 cycle/self-loop 负例测试。

### F-002: Pipeline 测试 mock 层级过高 (HIGH, test-gap)

**Evidence:** Task 3/4 的测试 mock extract_big_question_features 返回已解析结构，绕过了 build_prompt → send_message_gpt → parse 的真实链路。

**处置:** verified。Task 3 增加一个测试：mock send_message_gpt 返回原始 JSON 字符串，让 extract_big_question_features 执行真实解析，验证完整链路。

### F-003: points 总和未校验 (MED, design-concern)

**Evidence:** 设计要求 subquestions 分值之和等于整题分值，但计划中无此校验。

**处置:** verified。Pipeline 在聚合前增加 sum(points) 校验，偏差 >20% 时 fallback + warning。

### F-004: fallback 标记位置不一致 (MED, design-concern)

**Evidence:** 设计文档说 `features["big_question_fallback"] = true`，计划用 `flags` 列表。

**处置:** verified。统一为 flags（更合理的位置），更新设计文档 §9。

### F-005: Task 4 缺少边界条件和完整测试契约 (MED, test-gap)

**Evidence:** Task 4 的 test_parallel_big_question_not_overscored 缺少 5 字段测试契约，Task 4 整体缺少边界条件段。

**处置:** verified。补齐。

### F-006: 大题路径 confidence 系统性偏低 (LOW, design-concern)

**Evidence:** 大题 prompt 不要求 reason 字段，但 _compute_confidence 依赖 reason 数量。

**处置:** suggestion，接受。记入 v3.2 backlog，本次不修。

## Plan Amendments（Executor 必须遵循）

以下修正基于 GPT Plan Review finding，已部分写入 plan.md，其余由 Executor 在实现时执行。

### A-001: 环检测（F-001 修复，已写入 plan）
- `find_critical_path` 增加自环过滤（`from != to`）和环检测（`len(topo_order) < len(ids)` → 退化单节点）
- 新增 `test_cycle_returns_single_node` 和 `test_self_loop_ignored` 两个测试

### A-002: 入口级集成测试（F-002 修复）
Task 3 须新增一个测试 `test_full_chain_with_raw_json`：
- mock `feature_extractor.send_message_gpt`（不是 `difficulty_pipeline.extract_big_question_features`）
- 返回原始 JSON 字符串
- 验证完整链路：build_prompt → send_message_gpt → parse → aggregate → compute_difficulty
- 断言 final_difficulty >= 9.0 且 `_big_question` 存在

### A-003: points 总和校验（F-003 修复）
Task 3 的 Pipeline 分流逻辑中，在 `aggregate_big_question` 调用前增加：
```python
sq_points_sum = sum(sq["points"] for sq in structured["subquestions"])
if abs(sq_points_sum - total_score) / total_score > 0.2:
    logger.warning(f"[v3.1] 小问分值和({sq_points_sum})与总分({total_score})偏差>20%，fallback")
    structured = None
    big_question_fallback = True
```
补充测试：points 总和与 total_score 偏差 >20% 时触发 fallback。

### A-004: fallback 标记位置统一（F-004 修复）
设计文档 §9 原文"在 features 中标记 `big_question_fallback: true`"改为"在 flags 列表中追加 `big_question_fallback`"。（plan 中已是 flags 实现）

### A-005: Task 4 测试契约补齐（F-005 修复）
Task 4 `test_parallel_big_question_not_overscored` 的完整测试契约：
- 入口: `pipeline.evaluate_with_refinement(parallel_question)`
- 反例: 错误实现可能对并列大题也应用关键路径加成——本测试验证无 strong 依赖时不过度提升
- 边界: 全并列 / 混合 strong+weak / 单小问大题
- 回归: 防止 v3.1 引入并列大题系统性高估
- 命令: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestQ21EndToEnd::test_parallel_big_question_not_overscored -v`

### A-006: confidence 差异（F-006 accepted）
记入 v3.2 backlog。本次不修。
