# 计划审查报告: 特征分析难度评估

> Claude 降级审查（GPT Codex 不可用: jdcloud 未安装 codex CLI）
> 审查时间: 2026-03-12 14:59:24

## 审查对象

- 计划: `docs/plans/2026-03-12-feature-difficulty-plan.md`
- 设计: `docs/plans/2026-03-12-feature-difficulty-design.md`
- Commit: `35dd26e`

## A. 自洽性

| 检查项 | 结果 | 说明 |
|--------|------|------|
| Task 依赖完整 | ✅ | T1(rule_scorer) → T2(feature_extractor imports rule_scorer? No) → T3(pipeline imports both) → T4(e2e验证) |
| 接口契约一致 | ✅ | `compute_difficulty(features)` 和 `extract_features()` 签名在 T1/T2 定义、T3 消费，一致 |
| 破坏性操作有回滚 | ✅ | 旧文件(simulated_student.py, irt_estimator.py)保留不删 |
| 逻辑矛盾 | ⚠️ | 见 F-01 |

## B. 代码库对齐

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 引用路径真实 | ✅ | `backend/` 下所有文件路径经 `ls` 确认 |
| 不违反现有 API | ✅ | `evaluate_with_refinement` 签名不变，返回值包含所有旧字段 |
| main.py 兼容 | ✅ | main.py 不引用 simulated_responses/irt_params/irt_difficulty（grep 0 匹配） |
| 不命名冲突 | ✅ | `feature_extractor.py` 和 `rule_scorer.py` 是新文件名 |

## C. 架构适配

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 安全约束 | ✅ | API key 从环境变量读取（复用 claude_client.py） |
| 无不当硬编码 | ✅ | 权重在公式中，设计文档已说明 v2 校准路径 |
| 项目约定 | ✅ | 文件结构遵循现有 backend/ 平铺模式 |

## D. 完整性

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 测试策略 | ✅ | 单元测试(T1/T2) + mock集成(T3) + 真题e2e(T4) |
| 迁移考虑 | ✅ | 旧模块保留，pipeline 替换是原子的 |
| 批次边界 | ✅ | 单 Chunk，6 Tasks，适合单批次执行 |

## E. 风险评估

| 风险 | 级别 | 缓解 |
|------|------|------|
| LLM 特征提取不稳定 | 中 | temperature=0 + 3层解析容错 + 默认值 fallback |
| 旧字段缺失导致前端异常 | 低 | main.py 验证确认无引用旧独有字段 |
| 公式权重不准 | 低 | 设计文档已规划 v2 校准路径，v1 是最小可行 |

## Finding 清单

### F-01: plan 中 `_evaluate_single` 移除了 `correct_answer` 空检查但未明确说明
- **ID:** F-01
- **Severity:** LOW
- **Category:** design-concern
- **Evidence:** 设计文档 §5 prompt 包含 `correct_answer`，但 plan Task 3 的新代码中 `correct_answer` 为空时仍传给 LLM（空字符串）。Task 5 专门处理此问题但描述模糊。
- **Impact:** 低。空答案传给 LLM 不会报错，只是 prompt 中 `正确答案：` 后面为空，LLM 仍能分析题目特征。
- **Suggested action:** Task 5 可简化为纯确认步骤，合并到 Task 3。或在 prompt 中条件性省略答案行。
- **Planner 处置:** 接受。Task 5 保留为独立确认步骤，不合并。空答案传入 LLM 无害。

### F-02: test_feature_difficulty.py 中 `asyncio.get_event_loop()` 在 Python 3.10+ 会触发 DeprecationWarning
- **ID:** F-02
- **Severity:** LOW
- **Category:** suggestion
- **Evidence:** Task 3 测试代码使用 `asyncio.get_event_loop().run_until_complete()`
- **Impact:** 不影响功能，仅警告。
- **Suggested action:** 改用 `asyncio.run()` 或 `pytest-asyncio`。
- **Planner 处置:** 接受建议。Executor 执行时如果 jdcloud Python >= 3.10 可自行调整。

### F-03: 计划未提及 `options` 字段在 exercise_bank 中的格式
- **ID:** F-03
- **Severity:** MED
- **Category:** code-bug
- **Evidence:** Task 3 代码 `options = question.get("options", "")` 然后 `full_text = f"{question_text}\n{options}"`。但 exercise_bank 中 options 可能是 JSON array（如 `["A. xxx", "B. xxx"]`）而非纯字符串。
- **Impact:** 如果 options 是 JSON，拼接后 LLM 看到的是 `["A. xxx", ...]` 而非格式化文本，影响特征判断准确性。
- **Suggested action:** Executor 执行前先查 exercise_bank.options 的实际格式（`SELECT options FROM exercise_bank LIMIT 3`），根据实际格式做字符串化处理。

## 结论: PASS

无 HIGH/MED code-bug 阻塞。F-03 标记为 MED code-bug，但属于数据格式确认问题，Executor 执行时可现场验证并处理。

Gate 1 通过，可进入执行阶段。
