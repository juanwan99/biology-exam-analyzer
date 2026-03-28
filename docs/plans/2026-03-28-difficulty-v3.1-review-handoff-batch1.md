[biology-exam-analyzer] Executor→Reviewer | 2026-03-28 12:03:56
## 审查交接单: Task 1-4
计划: /home/ubuntu/biology-exam-analyzer/docs/plans/2026-03-28-difficulty-v3.1-plan.md

### 逐 Task 自审
| Task | 计划要求 | 实际执行 | 状态 | 说明 |
|------|---------|---------|------|------|
| T1 | find_critical_path + aggregate_big_question（含 A-001 环检测） | commit 2cec9b3, 实现两函数 + 12 测试 | ✅ | |
| T2 | build_big_question_prompt + parse_big_question_features + extract_big_question_features | commit 96ff480, 实现三函数 + 10 测试 | ✅ | |
| T3 | Pipeline 分流 + fallback + A-002 入口级集成 + A-003 points 校验 | commit 6176ec1, 重写 _evaluate_single + 8 测试（含 A-002 全链路 + A-003 偏差>20%） | ✅ | |
| T4 | Q21 端到端 >=9.0 + 并列大题不过度提升(A-005) + CLAUDE.md 更新 | commit 55388ca, 2 测试 + CLAUDE.md 3 行更新 | ✅ | |

> 状态: ✅一致 / ❌不一致 / 🔀改进

### Plan Amendments 处置
| Amendment | 来源 | 处置 | 验证 |
|-----------|------|------|------|
| A-001 环检测 | F-001 | Task 1: 自环过滤(from!=to) + 环检测(topo_order<ids→单节点) | test_cycle_returns_single_node + test_self_loop_ignored PASS |
| A-002 入口级集成测试 | F-002 | Task 3: test_full_chain_with_raw_json mock send_message_gpt 级别 | PASS, score>=9.0 |
| A-003 points 总和校验 | F-003 | Task 3: 聚合前 sum(points) vs total_score 偏差>20% → fallback | test_points_sum_mismatch_triggers_fallback PASS |
| A-004 fallback 标记统一 | F-004 | 设计文档 §9 已是 flags，plan 中已是 flags，代码实现为 flags | 一致，无需修改 |
| A-005 测试契约补齐 | F-005 | Task 4: test_parallel_big_question_not_overscored 含完整 5 字段契约 | PASS, score<7.0 |
| A-006 confidence 差异 | F-006 | accepted, 不修，记入 v3.2 backlog | N/A |

### 预审自检（送审前必填）
| 测试契约 slice | 对应测试文件:函数 | 验证命令 | 实际输出（pass/fail + 关键行） |
|---------------|------------------|---------|------------------------------|
| 线性依赖链→关键路径 | test_core_modules.py::TestCriticalPath::test_linear_chain | `docker-compose exec -T backend python -m pytest test_core_modules.py::TestCriticalPath -v` | 8 passed in 0.06s |
| Q21 聚合验算 §5 | test_core_modules.py::TestAggregation::test_q21_aggregation | `docker-compose exec -T backend python -m pytest test_core_modules.py::TestAggregation -v` | 4 passed in 0.06s |
| 结构化 JSON 解析 | test_feature_difficulty.py::TestParseBigQuestion | `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestParseBigQuestion -v` | 7 passed in 0.13s |
| 大题路由→结构化路径 | test_feature_difficulty.py::TestBigQuestionPipeline | `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestBigQuestionPipeline -v` | 7 passed in 12.44s |
| Q21 端到端 >=9.0 | test_feature_difficulty.py::TestQ21EndToEnd::test_q21_score_at_least_9 | `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestQ21EndToEnd -v` | 2 passed |
| 全链路 raw JSON (A-002) | test_feature_difficulty.py::TestBigQuestionPipeline::test_full_chain_with_raw_json | 同上 BigQuestionPipeline | PASS, score>=9.0 |
| points 偏差 fallback (A-003) | test_feature_difficulty.py::TestBigQuestionPipeline::test_points_sum_mismatch_triggers_fallback | 同上 BigQuestionPipeline | PASS, big_question_fallback in flags |

### 验证清单自检
- ✅ `find_critical_path` 仅用 strong 依赖构建图
- ✅ 无 strong 依赖时退化为单节点（最大 steps）
- ✅ `aggregate_big_question` 返回的 wm 被 clamp 到 [1,5]
- ✅ Q21 端到端验算结果与设计文档 §5 一致 (effective_steps=8.05, wm=5, trap=3, novelty=3)
- ✅ prompt 包含 subquestions/dependencies/global_features 三段输出指令
- ✅ strength 只接受 "weak" 和 "strong" 两个值
- ✅ 空 subquestions 返回 None（fallback 信号）
- ✅ total_score >= 8 触发大题路径
- ✅ 大题评分用 effective_steps 且 chain_coupling=1（避免双重计算）
- ✅ fallback 时标记 big_question_fallback 且降低 confidence
- ✅ 原有选择题测试全部不受影响（97 全量 PASS + 14 LLM 客户端 PASS）
- ✅ Q21 评分 >= 9.0（修正 v3 的 8.2）
- ✅ 并列简单大题 < 7.0（不过度提升）
- ✅ CLAUDE.md 文件描述与代码一致
- ✅ 环检测（A-001）: cycle→单节点, self-loop→过滤
- ✅ 入口级集成（A-002）: mock send_message_gpt 级全链路
- ✅ points 校验（A-003）: 偏差>20% fallback

### 自查（四要素格式）

- 新增文件的边界 case：
  构造输入: 环依赖 deps=[1→2, 2→3, 3→1]
  运行命令: `docker-compose exec -T backend python -m pytest test_core_modules.py::TestCriticalPath::test_cycle_returns_single_node -v`
  实际输出:
  ```
  PASSED
  ```
  结论: 环依赖正确退化为单节点，不崩溃

- 状态变量/锁的异常路径：
  构造输入: extract_big_question_features 返回 None（LLM 失败）
  运行命令: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestBigQuestionPipeline::test_fallback_on_parse_failure -v`
  实际输出:
  ```
  PASSED - big_question_fallback in flags, confidence < 0.7
  ```
  结论: 解析失败正确 fallback 到 v3 原路径，confidence 扣减

- 字符串匹配/条件判断的假阴性：
  构造输入: total_score=7（边界值 <8 不触发）和 total_score=8（边界值 >=8 触发）
  运行命令: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestBigQuestionPipeline::test_boundary_score_7_stays_v3 test_feature_difficulty.py::TestBigQuestionPipeline::test_boundary_score_8_triggers_big -v`
  实际输出:
  ```
  2 passed
  ```
  结论: 边界值 7/8 分流正确

使用 codex-review skill 进行 GPT 代码审查。
