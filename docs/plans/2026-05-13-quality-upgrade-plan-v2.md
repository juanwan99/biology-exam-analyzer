# 提质改造计划 v2 — biology-exam-analyzer

> 日期: 2026-05-13 | R1 Review: FAIL (13 findings) | v2 处置 8 个 finding
> 级别: T3 | 目标: 分析更科学、报告更美观、成本可观测、教师可校正

## R1 Review 处置记录

| Finding | 处置 | 说明 |
|---------|------|------|
| D-01 HIGH | 接受 | 成本优化不该排第一，重排优先级 |
| D-02 HIGH | 接受 | 14 Batch 过重，收敛为 7 Batch |
| D-03 HIGH | 接受 | 可编辑结果提前到 Phase 2 |
| D-04 MED | 接受 | 教学建议改为错因归类+讲评提纲+补救练习 |
| D-05 MED | 接受 | 砍掉竞品红海功能，聚焦试卷诊断+教师校正闭环 |
| S-01 HIGH | WONTFIX | 审查包缺文件是同步范围问题，不影响计划 |
| S-02 HIGH | WONTFIX | CLAUDE.md 过时，执行时以 llm_config.py 代码为准 |
| S-03 HIGH | 接受 | 合并素养在 service 层做，不改 analyzer 返回结构 |
| S-04 MED | 接受 | 加黄金样例和权重一致性测试 |
| S-05 HIGH | WONTFIX | 1.3 模型路由整个 Batch 已砍 |
| S-06 MED | 接受 | llm_call 内部记录 usage 不改返回类型 |
| S-07 HIGH | 接受 | standardize 用增量字段扩展现有结构 |
| S-08 MED | 接受 | 定义 bloom_level 与 features.bloom 优先级契约 |
| S-09 HIGH | 接受 | 覆盖度增加考试范围输入，未知时输出 unknown |
| S-10 MED | 接受 | 定义 calibration 与 prediction/difficulty 依赖方向 |
| S-11 HIGH | WONTFIX | 测试路径两处都有，审查包不完整导致误判 |
| S-12 MED | 接受 | Contract Pack 按 Batch 扩展 |
| S-13 MED | 接受 | 分享 token 权限边界+过期策略明确 |

## 现有资产盘点（同 v1，略）

见 v1 plan 资产盘点段。全部增量，无新建平行系统。

## 交付路径

- 目标目录: `backend/` + `frontend/src/`
- 生产 serving: Docker Compose (backend:8000 + frontend:80)
- 部署方式: `docker compose up --build -d`

---

## 修订后执行计划（7 Batch，砍掉 7 个低 ROI Batch）

**砍掉的 Batch（D-02/D-05 处置）：**
- ~~1.3 模型路由~~ — 月均 63 次不值得维护路由复杂度
- ~~3.2 Word 导出~~ — 竞品红海，教师优先需要好看的 PDF
- ~~3.3 在线报告+分享~~ — 竞品红海，优先级低
- ~~4.1 语义缓存~~ — 月均 63 次缓存命中率极低
- ~~4.3 批量模式~~ — 月均 63 次不需要批量
- ~~4.4 纵向对比~~ — 依赖数据积累，当前数据不足
- ~~Prompt 精简(1.1 T3/T4)~~ — 降为执行时随手优化，不单独 Batch

**重排后优先级（D-01 处置 — 教师感知价值优先）：**

```
Phase 1（科学性+可校正 = 核心价值）
  Batch 1: 分析合并 + Token 可观测 + Bloom 精细化
  Batch 2: 知识点标准化 + 可编辑结果（D-03 提前）
  Batch 3: 整卷质量诊断（含考试范围输入 S-09）

Phase 2（报告+教学 = 用户感知）
  Batch 4: 报告视觉升级
  Batch 5: 教学建议（错因归类+讲评提纲+补救练习 D-04）+ 置信度

Phase 3（数据闭环 = 长期价值）
  Batch 6: 难度校准闭环
  Batch 7: Token 统计面板 + 管理增强
```

---

### Phase 1: 科学性 + 可校正（核心价值层）

#### Batch 1: 分析合并 + Token 可观测 + Bloom

**目标**: 每题 2 次 LLM 降为 1 次 + 知道成本 + Bloom 六层级

| Task | 文件 | 动作 |
|------|------|------|
| T1 Token 计量（内部） | `llm_client.py` | `_call_single_provider` 从 response JSON 提取 usage 字段，写入模块级计数器和日志；不改 `llm_call()->str` 签名（ORC-001，S-06 处置） |
| T2 Token 统计 API | `admin_router.py` | `/api/admin/token-stats` 返回按 provider 分组的 token 用量 |
| T3 合并 Prompt | `prompts/analysis_prompt.txt` | 在分析 prompt 末尾增加素养输出要求（4 素养权重 + primary + level） |
| T4 Service 层合并（S-03 处置） | `services/analysis_service.py` | `analyze_question()` 中：如果 `analysis` 结果已含 `competency` 且权重和 >= 0.9，直接使用；否则 fallback 到 `competency_analyzer.analyze_competency()` |
| T5 Bloom 字段 | `prompts/analysis_prompt.txt` | 新增 `bloom_level`(1-6) 字段 + 六层级简表 |
| T6 Bloom 优先级契约（S-08 处置） | `difficulty_pipeline.py` | 如果 `analysis.bloom_level` 存在且在 1-6 范围内，设为 `features.bloom = bloom_level`；否则保持特征提取推断值 |

**测试契约**:
- 入口: `analyze_question()` 返回 dict 含 `analysis.bloom_level` + `competency`（直接或 fallback）
- 反例: 合并 prompt 返回空 competency JSON -> fallback 到独立调用，不崩溃
- 反例(S-04): 黄金样例 — 选择题"分离定律"应返回科学思维为主素养，权重和 = 1.0
- 边界: bloom_level=7 -> clamp 为 6；bloom_level 缺失 -> 保持特征提取值
- 回归: `pytest backend/tests/ -x && pytest backend/test_*.py -x`
- 命令: 同上

**Contract Pack 扩展（S-12 处置）**:
- invariant: `llm_call()` 返回 str，usage 记录不影响调用延迟（<5ms 开销）
- invariant: 合并后 `question["competency"]` 结构 === 独立调用结构
- counter_example: usage 字段缺失（某些 provider 不返回）-> 记录 `{input: -1, output: -1}`，不崩溃
- risk_module: `llm_client.py` — usage 提取逻辑

#### Batch 2: 知识点标准化 + 可编辑结果

**目标**: 知识点映射到课标 + 教师可修正 AI 分析结果（D-03 提前）

| Task | 文件 | 动作 |
|------|------|------|
| T1 增量标准化（S-07 处置） | `knowledge_mapper.py` | 在现有 `map_knowledge_points()` 返回结构上增加 `{standard_name, confidence}` 字段，不替换现有 `mapped/textbook/chapter` 字段 |
| T2 模糊匹配增强 | `knowledge_mapper.py` | 用关键词交集 + 教材树最短路径匹配提升映射准确度 |
| T3 接入分析链路 | `services/analysis_service.py` | `analyze_question()` 后调用 `knowledge_mapper.map_knowledge_points()` 标准化 |
| T4 结果编辑 API | `analysis_router.py` | `PATCH /api/questions/{id}/analysis` — 教师修正知识点/难度/素养/答案 |
| T5 修正数据存储 | `models.py` | ExerciseBank 新增 `manual_override: JSON` + `override_at: DateTime` 字段 |
| T6 修正记录日志 | `admin_router.py` | `/api/admin/corrections` 查看修正历史 |
| T7 前端编辑入口 | `components/ResultDisplay.jsx` | 每题分析结果旁"修正"按钮，弹出编辑表单 |

**测试契约**:
- 入口: `map_knowledge_points(["基因分离定律"])` 返回结果含 `standard_name` + `confidence` 字段
- 反例: 无法映射的知识点 -> confidence < 0.3，保留原始名称
- 边界: 空列表 -> 返回空列表不崩溃
- 入口: `PATCH /api/questions/1/analysis {knowledge_points: [...]}` -> 200 + 覆盖原分析
- 反例: 不存在的 id -> 404
- 回归: `pytest backend/tests/ -x && pytest backend/test_*.py -x`

**Contract Pack**:
- invariant: map_knowledge_points 返回结构向后兼容（旧字段不删）
- invariant: manual_override 写入不影响原始分析结果（分开存储）
- counter_example: PATCH 请求 body 为空 -> 400 不写入
- risk_module: `knowledge_mapper.py` — 增量字段不能破坏现有统计

#### Batch 3: 整卷质量诊断

**目标**: 从统计描述升级为命题质量评价

| Task | 文件 | 动作 |
|------|------|------|
| T1 诊断引擎 | 新建 `exam_diagnostics.py` | `diagnose_exam(questions, statistics, exam_scope=None) -> DiagnosticReport` |
| T2 考试范围输入（S-09 处置） | `exam_diagnostics.py` | `exam_scope` 参数：`{grade: "高三", volumes: ["必修1","必修2","选择性必修1"]}` 或 None |
| T3 难度梯度合理性 | `exam_diagnostics.py` | 检测难度分布偏离度（30%简单+50%中等+20%困难为基准） |
| T4 知识点覆盖度 | `exam_diagnostics.py` | 有 exam_scope 时：覆盖率 = 已考查章节 / 范围内章节数；无 scope 时：输出 `{coverage: "unknown", reason: "未指定考试范围"}` |
| T5 素养均衡度 | `exam_diagnostics.py` | 4 素养权重方差，是否有素养完全缺失 |
| T6 区分度估算 | `exam_diagnostics.py` | 基于难度分布+题型分布估算区分能力 |
| T7 接入报告 | `report_data.py`, `report_insights.py` | 诊断结果进入报告数据和 LLM 洞察 |
| T8 前端范围输入 | `pages/AnalyzerPage.jsx` | 分析前可选填考试范围（年级 + 册别 checkbox） |

**测试契约**:
- 入口: `diagnose_exam(questions, statistics)` 返回 `{gradient, coverage, competency_balance, discrimination, overall_rating}`
- 反例: 全部难题 -> gradient.rating = "偏难"
- 反例: exam_scope=None -> coverage = "unknown"（S-09 处置）
- 边界: 0 题 -> 空诊断不崩溃；1 题 -> 跳过梯度分析
- 回归: `pytest backend/tests/ -x && pytest backend/test_*.py -x`

**Contract Pack**:
- invariant: exam_scope=None 时诊断不抛异常，覆盖度输出 unknown
- invariant: 诊断失败不影响分析结果返回（try/except 包裹）
- counter_example: knowledge_mapper 无对应册别章节 -> coverage 回退 unknown
- risk_module: `exam_diagnostics.py` — 新模块

---

### Phase 2: 报告 + 教学（用户感知层）

#### Batch 4: 报告视觉升级

**目标**: 专业教育出版物级 PDF 报告

| Task | 文件 | 动作 |
|------|------|------|
| T1 素养雷达图 | `report_generator.py` | Plotly polar chart，4 维度 |
| T2 知识点热力图 | `report_generator.py` | 知识点 x 难度 Plotly heatmap |
| T3 题型分值饼图 | `report_generator.py` | 题型分布 Plotly pie |
| T4 整卷诊断可视化 | `report_generator.py` | 诊断结果仪表盘（Batch 3 数据） |
| T5 CSS 重写 | `reports/styles.py` | 专业配色、字体层级、页眉页脚、分页控制 |
| T6 模板重构 | `reports/templates.py` | 封面→概览→难度→知识点→素养→诊断→逐题→教学建议 |

**测试契约**:
- 入口: `generate_pdf_report(data, insights)` 生成含 4 种图表的 PDF
- 反例: 空数据 -> 生成"数据不足"提示页，不崩溃
- 边界: 1 题 -> 雷达图仍渲染
- 回归: `pytest backend/test_report_render.py -v`

#### Batch 5: 教学建议（D-04 处置）+ 置信度

**目标**: 报告从描述升级为可行动的教学决策支持

| Task | 文件 | 动作 |
|------|------|------|
| T1 错因归类 | `report_insights.py` | 新增 prompt：按 common_mistakes 聚类，输出 Top 3-5 错因类型 + 涉及题号 |
| T2 讲评提纲 | `report_insights.py` | 基于错因类型生成讲评课提纲（重点讲解顺序 + 时间分配建议） |
| T3 补救练习推荐 | `report_insights.py` | 基于薄弱知识点从 ExerciseBank 推荐 3-5 道练习题 |
| T4 置信度计算 | `services/analysis_service.py` | 基于 LLM 响应完整度计算 `analysis_confidence`（0-1）：JSON 解析成功 +0.3, 知识点非空 +0.2, 答案非空 +0.2, 素养非空 +0.15, bloom_level 存在 +0.15 |
| T5 置信度标注 | `components/ResultDisplay.jsx` | 低置信度(<0.6)标注"建议人工核验" |
| T6 报告渲染 | `reports/templates.py` | 报告末尾新增"错因分析→讲评提纲→补救练习→教学建议"章节 |

**测试契约**:
- 入口: 报告含"错因分析"章节 + 至少 3 个错因类型
- 反例: 全部题目高置信度 -> 不出现"建议人工核验"
- 边界: ExerciseBank 为空 -> 补救练习部分输出"暂无题库数据"
- 回归: `pytest backend/tests/ -x && pytest backend/test_*.py -x`

**Contract Pack**:
- invariant: 置信度 0.0-1.0，从不返回 None
- invariant: 补救练习推荐失败不影响其他报告内容
- counter_example: LLM 返回完全无效 JSON -> confidence=0.0, 标注"分析失败"

---

### Phase 3: 数据闭环（长期价值层）

#### Batch 6: 难度校准闭环

**目标**: 用历史考试数据反向校准难度预测

| Task | 文件 | 动作 |
|------|------|------|
| T1 校准服务（S-10 处置） | 新建 `calibration_service.py` | 依赖方向：calibration_service -> prediction_service（读历史数据）-> difficulty_pipeline（提供修正系数）；difficulty_pipeline 不直接访问 DB |
| T2 校准数据收集 | `calibration_service.py` | `collect_data() -> List[Tuple[predicted_difficulty, actual_score_rate]]` |
| T3 偏差分析 | `calibration_service.py` | `analyze(data) -> {bias_by_range, overall_rmse, sample_count}` |
| T4 修正系数 | `calibration_service.py` | `get_correction(difficulty) -> float` — difficulty_pipeline 调用获取修正 |
| T5 校准 API | `admin_router.py` | `/api/admin/calibration` — 校准状态 + 手动触发校准 |
| T6 最小样本门槛 | `calibration_service.py` | < 10 场考试 -> 不校准，返回 correction=0 |

**测试契约**:
- 入口: `analyze([(5.0, 0.6), (7.0, 0.3)])` 返回 `{bias_by_range, overall_rmse}`
- 反例: 空数据 -> `{status: "insufficient", sample_count: 0}`
- 边界: 极端偏差 -> warning 日志，不崩溃
- 回归: `pytest backend/tests/ -x && pytest backend/test_*.py -x`

#### Batch 7: Token 面板 + 管理增强

**目标**: 管理后台可视化 token 成本和修正数据

| Task | 文件 | 动作 |
|------|------|------|
| T1 Token 面板页 | `frontend/src/pages/admin/TokenStatsPage.jsx` | 按日/按 provider 的 token 用量图表 |
| T2 修正数据面板 | `frontend/src/pages/admin/CorrectionsPage.jsx` | 教师修正记录列表 + 统计 |
| T3 校准状态面板 | `frontend/src/pages/admin/CalibrationPage.jsx` | 校准数据量 + 偏差图 |

**测试契约**:
- 入口: 管理后台页面加载不报错
- 回归: 全量测试绿

---

## 执行顺序与依赖

```
Phase 1（科学性+可校正）
  Batch 1: 分析合并+Token+Bloom
     |
  Batch 2: 知识点标准化+可编辑 (依赖 Batch 1 的合并输出)
     |
  Batch 3: 整卷诊断 (依赖 Batch 2 的标准化知识点)

Phase 2（报告+教学）
  Batch 4: 报告视觉 (依赖 Batch 3 的诊断数据)
     |
  Batch 5: 教学建议+置信度 (依赖 Batch 4 的报告模板)

Phase 3（数据闭环）
  Batch 6: 难度校准 (独立，依赖历史数据积累)
  Batch 7: 管理面板 (依赖 Batch 1/2/6 的 API)
```

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 合并 Prompt 质量下降 | 分析+素养同时变差 | 保留独立素养调用 fallback + 黄金样例测试 |
| 可编辑结果并发冲突 | 多教师同时修正 | 单用户系统，暂不处理并发 |
| 报告 CSS 跨平台差异 | WeasyPrint 渲染不一致 | 用安全 CSS 子集 |
| 校准数据不足 | 校准无效 | 最小 10 场门槛 |
| 诊断无考试范围 | 覆盖度伪指标 | scope=None 时输出 unknown |

## semantic_regression (ORC)

- ORC-001: `llm_call()` 始终返回 str（usage 内部记录，不改签名）
- ORC-002: `analyze_question()` 返回 dict 含 `analysis` + `difficulty` 键
- ORC-003: `run_full_analysis()` 返回 dict 含 `questions`, `competency_summary`, `exam_statistics`
- ORC-004: `map_knowledge_points()` 返回结构向后兼容（旧字段不删，新增 standard_name/confidence）
- ORC-005: 报告/诊断/校准失败不影响分析结果返回
- ORC-006: 所有新增写入 API（PATCH/POST）走现有 auth 中间件
- ORC-007: manual_override 不覆盖原始分析数据（分开存储）

## Contract Pack（全局级，Batch 级见各 Batch 段）

### invariants
1. 合并后 `question["competency"]` 结构 === 独立调用结构 | verification: golden_example_test
2. `map_knowledge_points` 返回结构含旧字段 + 新字段 | verification: backward_compat_test
3. Token 计量 >= 0 | verification: token_tracker_test
4. `exam_scope=None` 时诊断不抛异常 | verification: diagnostics_no_scope_test
5. manual_override 与 analysis 分开存储 | verification: override_isolation_test

### counter_examples
1. 合并 prompt 返回空 competency -> fallback 独立调用 | mitigation: service 层 fallback 逻辑
2. usage 字段缺失 -> 记录 {input:-1, output:-1} | mitigation: 默认值填充
3. knowledge_mapper 无对应章节 -> coverage=unknown | mitigation: S-09 unknown 输出
4. PATCH body 为空 -> 400 不写入 | mitigation: request validation

### risk_modules
- `llm_client.py` — usage 提取不能影响调用性能
- `knowledge_mapper.py` — 增量字段不能破坏统计
- `services/analysis_service.py` — 合并逻辑 fallback 正确性
- `exam_diagnostics.py` — 新模块错误隔离
- `calibration_service.py` — DB 访问边界

### test_debt
- 报告 CSS 视觉测试 — 需 screenshot 对比 | deadline: Batch 4 末尾评估
- 真实 LLM 端到端测试 — 需 API key | deadline: 手动验证
