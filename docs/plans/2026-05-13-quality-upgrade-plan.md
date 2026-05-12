# 提质改造计划 — biology-exam-analyzer 全面升级

> 日期: 2026-05-13
> 级别: T3（跨模块重构 + 新功能）
> 目标: 分析更科学、报告更美观、成本更低、平台能力更强

---

## 现有资产盘点

| 层 | 已有 | 位置 | 证据 |
|----|------|------|------|
| LLM 调用 | 统一 fallback 客户端，DeepSeek→Gemini 双链路 | `llm_client.py:1-80`, `llm_config.py` | PROVIDERS 列表 2 个 provider |
| 分析链路 | 拆题→逐题分析→难度→素养→统计→报告，完整 pipeline | `services/analysis_service.py:1-316` | run_full_analysis 编排 |
| 难度评估 | v3.1 特征提取+规则评分+大题结构化拆分 | `difficulty_pipeline.py`, `feature_extractor.py:557L`, `rule_scorer.py:221L` | extract_features + compute_difficulty |
| 素养分析 | 4 大素养 LLM 独立分析，含素养库 JSON | `competency_analyzer.py`, `prompts/competency_analysis_prompt.txt` | analyze_competency 独立 LLM 调用 |
| 知识点映射 | 人教版教材章节结构树，模糊匹配 | `knowledge_mapper.py:1-80` | TEXTBOOK_STRUCTURE dict |
| 统计分析 | 难度分布/曲线/Bloom/知识点分值加权 | `analysis_statistics.py:215L` | generate_exam_statistics |
| 报告生成 | Plotly 图表 + WeasyPrint PDF | `report_generator.py:967L`, `report_data.py:173L`, `report_insights.py:152L` | 数据聚合→LLM 洞察→PDF 渲染 |
| 报告模板 | HTML 模板 + CSS | `reports/templates.py:348L`, `reports/styles.py:40L` | 8 个 _render_* 函数 |
| 前端展示 | ResultDisplay + ExamStatisticsEnhanced | `ResultDisplay.jsx:555L`, `ExamStatisticsEnhanced.jsx:829L` | 在线结果 + 统计图表 |
| 题库/向量 | ExerciseBank + pgvector + 384维 embedding | `models.py:ExerciseBank`, `vector_service.py` | content_embedding Vector(1536) |
| 历史数据 | ExamHistory + QuestionPerformance + DifficultyMapping | `models.py`, `prediction_service.py` | 完整 schema 已建 |
| 分数预估 | 难度→得分率映射 + 线性回归 | `prediction_service.py`, `difficulty_mapper.py` | DifficultyMapping 表 |

## 增量 vs 新建论证

**默认立场：全部增量。** 所有改造在已有模块上扩展，不新建平行系统。

| 改造项 | 方式 | 论证 |
|--------|------|------|
| 分析+素养合并 | 修改 `analysis_service.py` + `question_analyzer.py` | 已有分析链路，合并两次 LLM 调用为一次 |
| 语义缓存 | 扩展 `ExerciseBank` + 新增 `cache_service.py` | 已有 pgvector 和 ExerciseBank 表，加缓存查询层 |
| 报告升级 | 修改 `report_generator.py` + `reports/` | 已有 Plotly + WeasyPrint 基础 |
| 整卷诊断 | 扩展 `analysis_statistics.py` | 已有统计函数，增加诊断维度 |
| Word 导出 | 新增 `reports/word_export.py` | 新功能，但挂接到已有 generate_report 流程 |
| 难度校准 | 扩展 `difficulty_pipeline.py` + `prediction_service.py` | 已有 DifficultyMapping 表和回归参数 |
| Token 追踪 | 修改 `llm_client.py` | 已有统一调用入口，加计量 |
| 批量模式 | 扩展 `analysis_service.py` + 新增前端组件 | 已有 run_full_analysis，外层加队列 |
| 知识点标准化 | 扩展 `knowledge_mapper.py` | 已有教材结构树，加 LLM 输出后处理 |
| 教学建议 | 扩展 `report_insights.py` | 已有 LLM 洞察生成，增加教学建议维度 |

**新增文件（均为叶子模块，不是平行系统）：**
- `cache_service.py` — 语义缓存查询
- `reports/word_export.py` — Word 导出
- `reports/charts.py` — 图表生成集中管理
- `exam_diagnostics.py` — 整卷质量诊断
- `token_tracker.py` — Token 用量追踪

## 交付路径

- 目标目录：`backend/` + `frontend/src/`
- 生产 serving：Docker Compose（backend:8000 + frontend:80）
- 用户访问 URL：已有（京东云）
- 部署方式：`docker compose up --build -d`

---

## 执行计划

### Phase 1: 成本优化（基础设施层，其他 Phase 依赖）

#### Batch 1.1: Token 追踪 + Prompt 精简

**目标**: 知道钱花在哪，减少浪费

| Task | 文件 | 动作 |
|------|------|------|
| T1 Token 计量 | `llm_client.py` | 每次 llm_call 记录 input/output token 数（从 API response usage 字段提取），累计到内存计数器，写入日志 |
| T2 Token 统计 API | `admin_router.py` | 新增 `/api/admin/token-stats` 端点，返回本次启动以来的 token 用量（按 provider 分组） |
| T3 Prompt 精简 | `prompts/analysis_prompt.txt` | 精简 analysis_prompt：移除冗余示例，保留核心指令，目标从 ~120 行降到 ~60 行 |
| T4 素养 Prompt 精简 | `prompts/competency_analysis_prompt.txt` | 精简素养 prompt：四大素养定义改为简表，目标从 ~60 行降到 ~30 行 |

**测试契约**:
- 入口: `/api/admin/token-stats` 返回 `{providers: [{name, input_tokens, output_tokens, call_count}]}`
- 反例: 如果 llm_call 不记录 token，统计 API 返回全零
- 边界: provider 返回无 usage 字段时不崩溃（记录 unknown）
- 回归: 现有 207 个测试全绿
- 命令: `pytest backend/tests/ -x`

#### Batch 1.2: 分析+素养合并（核心成本优化）

**目标**: 每题从 2 次 LLM 调用降到 1 次（~33% 调用量）

| Task | 文件 | 动作 |
|------|------|------|
| T1 合并 Prompt | `prompts/analysis_prompt.txt` | 在现有分析 prompt 末尾增加素养分析输出字段要求（4 素养 + primary + level） |
| T2 解析合并响应 | `question_analyzer.py` | analyze_question 返回中包含 competency 字段，从同一 LLM 响应解析 |
| T3 跳过独立素养调用 | `services/analysis_service.py` | analyze_question 中：如果分析结果已含 competency，跳过 competency_analyzer.analyze_competency |
| T4 保留回退 | `services/analysis_service.py` | 如果合并响应中 competency 为空/缺失，仍 fallback 到独立素养分析 |
| T5 更新测试 | `tests/` | 更新 parity 测试，验证合并后输出与独立调用等价 |

**测试契约**:
- 入口: `analyze_question()` 返回包含 `competency` 字段
- 反例: 如果合并 prompt 缺少素养部分，competency 字段为空则自动 fallback
- 边界: LLM 返回 JSON 中缺少 competency 键则 fallback 不报错
- 回归: 现有 parity 测试仍通过
- 命令: `pytest backend/tests/test_parity_and_concurrency.py -v`

#### Batch 1.3: 模型分级路由

**目标**: 简单题用便宜模型，复杂题用强模型

| Task | 文件 | 动作 |
|------|------|------|
| T1 路由策略 | `llm_config.py` | 新增 `get_provider_for_task(task_type)` — 选择题分析用 DeepSeek，大题/实验题用 Gemini |
| T2 接入路由 | `llm_client.py` | llm_call 增加可选参数 `task_type`，传入时按路由策略选择 provider |
| T3 分析层传递 | `question_analyzer.py` | analyze_question 传 task_type 给 llm_call（基于 question_type 判断） |
| T4 拆题不路由 | `question_analyzer.py` | split_questions 始终用视觉能力最强的模型 |

**测试契约**:
- 入口: `get_provider_for_task("single_choice")` 返回 DeepSeek；`get_provider_for_task("experiment")` 返回 Gemini
- 反例: 如果路由函数不存在，llm_call 行为不变（向后兼容）
- 边界: 未知 task_type 使用默认 fallback 链
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

---

### Phase 2: 分析科学性（核心价值层）

#### Batch 2.1: 知识点标准化

**目标**: LLM 自由输出的知识点映射到课标体系

| Task | 文件 | 动作 |
|------|------|------|
| T1 后处理映射 | `knowledge_mapper.py` | 新增 `standardize_points(raw_points) -> List[Dict]`，返回 `{raw, standard, chapter, confidence}` |
| T2 模糊匹配增强 | `knowledge_mapper.py` | 用 jieba 分词 + 关键词匹配，对每个 raw point 找最近的教材章节节点 |
| T3 接入分析链路 | `services/analysis_service.py` | analyze_question 后对 knowledge_points 执行标准化 |
| T4 统计使用标准名 | `analysis_statistics.py` | 知识点统计优先使用 standard 名称 |

**测试契约**:
- 入口: `standardize_points(["基因分离定律"])` 返回 `[{raw: "基因分离定律", standard: "分离定律", chapter: "必修2-1.1", confidence: 0.9}]`
- 反例: 如果映射表为空，返回原始名称 + confidence=0
- 边界: 完全无关的输入（如"量子力学"）confidence < 0.3，保留原始
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

#### Batch 2.2: Bloom 认知层次精细化

**目标**: 从简单/中等/困难三档升级为布鲁姆六层级精确判定

| Task | 文件 | 动作 |
|------|------|------|
| T1 Prompt 加入 Bloom | `prompts/analysis_prompt.txt` | 新增 `bloom_level` 字段（1-6），附六层级定义简表 |
| T2 解析 Bloom | `question_analyzer.py` | 从 LLM 响应提取 bloom_level |
| T3 难度引用 | `difficulty_pipeline.py` | 如果 LLM 分析已返回 bloom_level，优先使用（而非特征提取推断） |
| T4 统计升级 | `analysis_statistics.py` | Bloom 分布统计使用精确 bloom_level（已有 BLOOM_LABELS） |

**测试契约**:
- 入口: analyze_question 返回包含 `bloom_level: int`（1-6）
- 反例: bloom_level 缺失则回退到 feature_extractor 推断
- 边界: bloom_level 值超出 1-6 则 clamp 到范围内
- 回归: difficulty_pipeline 现有测试绿
- 命令: `pytest backend/tests/test_feature_difficulty.py -v`

#### Batch 2.3: 整卷质量诊断

**目标**: 从统计描述升级为命题质量评价

| Task | 文件 | 动作 |
|------|------|------|
| T1 诊断引擎 | 新建 `exam_diagnostics.py` | `diagnose_exam(questions, statistics) -> DiagnosticReport`，含 5 个诊断维度 |
| T2 难度梯度合理性 | `exam_diagnostics.py` | 检查难度分布是否符合正态/合理梯度（30% 简单 + 50% 中等 + 20% 困难为理想） |
| T3 知识点覆盖度 | `exam_diagnostics.py` | 对标课标知识体系，计算覆盖率（已考查 / 应考查章节） |
| T4 素养均衡度 | `exam_diagnostics.py` | 4 素养权重是否均衡，是否有素养维度完全缺失 |
| T5 区分度估算 | `exam_diagnostics.py` | 基于难度分布和题型分布估算试卷区分能力 |
| T6 接入报告 | `report_data.py`, `report_insights.py` | 诊断结果加入报告数据和 LLM 洞察 |

**测试契约**:
- 入口: `diagnose_exam(questions, statistics)` 返回 `{gradient, coverage, competency_balance, discrimination, overall_rating}`
- 反例: 全部难题则 gradient.rating = "偏难"，overall 不是"优秀"
- 边界: 0 题返回空诊断不崩溃；1 题跳过梯度分析
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

#### Batch 2.4: 难度校准闭环

**目标**: 用历史考试数据反向校准难度预测

| Task | 文件 | 动作 |
|------|------|------|
| T1 校准数据收集 | `prediction_service.py` | 新增 `collect_calibration_data()` — 提取所有 (预测难度, 实际得分率) 数据对 |
| T2 校准分析 | `difficulty_pipeline.py` | 新增 `calibrate(data_pairs)` — 计算预测偏差、按难度区间的系统偏差 |
| T3 校准修正 | `difficulty_pipeline.py` | evaluate 时如果有校准数据，对 final_difficulty 做修正 |
| T4 校准 API | `admin_router.py` | `/api/admin/calibration-status` — 显示校准数据量、偏差统计、上次校准时间 |
| T5 数据积累提示 | `exam_diagnostics.py` | 诊断报告中提示"已积累 N 场考试数据，校准可信度: X" |

**测试契约**:
- 入口: `calibrate([(5.0, 0.6), (7.0, 0.3), ...])` 返回 `{bias_by_range, overall_rmse, correction_func}`
- 反例: 数据不足（<10 对）则不校准，返回 `{status: "insufficient", min_required: 10}`
- 边界: 极端偏差（预测全错）则输出 warning，不崩溃
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

---

### Phase 3: 报告与输出（用户感知层）

#### Batch 3.1: 报告视觉升级

**目标**: 专业教育出版物级别的 PDF 报告

| Task | 文件 | 动作 |
|------|------|------|
| T1 雷达图 | `report_generator.py` | 新增素养雷达图（4 维度，Plotly polar chart） |
| T2 热力图 | `report_generator.py` | 新增知识点x难度热力图（Plotly heatmap） |
| T3 题型分值饼图 | `report_generator.py` | 新增题型分布饼图 |
| T4 CSS 大改版 | `reports/styles.py` | 重写 CSS：专业配色方案、字体层级、页眉页脚、分页控制 |
| T5 模板重构 | `reports/templates.py` | 报告结构：封面→概览→难度分析→知识点分析→素养分析→逐题详析→整卷诊断→教学建议 |

**测试契约**:
- 入口: `generate_pdf_report(data, insights)` 生成包含 4 种图表的 PDF
- 反例: 空数据则生成带"数据不足"提示的 PDF，不崩溃
- 边界: 1 题则雷达图仍渲染，饼图单分类
- 回归: test_report_render 绿
- 命令: `pytest backend/test_report_render.py -v`

#### Batch 3.2: Word 导出

**目标**: 教师可直接编辑的 Word 报告

| Task | 文件 | 动作 |
|------|------|------|
| T1 Word 导出模块 | 新建 `reports/word_export.py` | `generate_word_report(data, insights, output_path)` — 用 python-docx 生成 |
| T2 表格 + 嵌入图表 | `reports/word_export.py` | 支持表格（知识点统计）+ Plotly 图表转 PNG 嵌入 |
| T3 API 端点 | `analysis_router.py` | `/api/reports/{id}.docx` 下载 Word 报告 |
| T4 前端按钮 | `components/ResultDisplay.jsx` | "下载 Word 报告" 按钮 |
| T5 依赖 | `requirements.txt` | 新增 `python-docx` |

**测试契约**:
- 入口: `/api/reports/{id}.docx` 返回合法 .docx 文件
- 反例: id 不存在则 404
- 边界: 空分析结果则生成只有封面的 Word
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

#### Batch 3.3: 报告定制 + 在线报告

**目标**: 可选报告详细度 + Web 在线报告

| Task | 文件 | 动作 |
|------|------|------|
| T1 详细度参数 | `services/analysis_service.py` | generate_report 增加 `detail_level: brief/standard/full` + `sections: List[str]` 可选段落 |
| T2 brief 模式 | `report_generator.py` | brief 模式只含概览 + 难度曲线 + 整卷诊断（1-2 页） |
| T3 前端选项 | `pages/AnalyzerPage.jsx` | 报告选项区：详细度 radio + 段落勾选 checkbox |
| T4 在线报告页 | 新建 `frontend/src/pages/ReportPage.jsx` | 根据分析结果 ID 渲染交互式 Web 报告 |
| T5 分享链接 | `analysis_router.py` | `/api/report-link/{id}` 返回 token 化链接，无需登录可查看 |

**测试契约**:
- 入口: `generate_report(..., detail_level="brief")` 生成精简报告
- 反例: sections=[] 则生成空报告框架
- 边界: 非法 detail_level 则 ValueError
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

---

### Phase 4: 平台能力（增长层）

#### Batch 4.1: 语义缓存

**目标**: 重复/相似题目秒出结果

| Task | 文件 | 动作 |
|------|------|------|
| T1 缓存服务 | 新建 `cache_service.py` | `find_similar(content, threshold=0.92) -> Optional[CachedAnalysis]` — 用 pgvector 余弦相似度 |
| T2 embedding 生成 | `cache_service.py` | 用已有 sentence-transformers 模型生成题目 embedding |
| T3 缓存写入 | `services/analysis_service.py` | 分析完成后写入缓存（content + embedding + analysis_result） |
| T4 缓存查询 | `services/analysis_service.py` | 分析前先查缓存，命中则跳过 LLM 调用 |
| T5 缓存统计 | `admin_router.py` | `/api/admin/cache-stats` — 命中率、缓存大小、最近命中 |
| T6 存储表 | `models.py` | 新增 `AnalysisCache` 表（或扩展 ExerciseBank） |

**测试契约**:
- 入口: 相同题目第二次分析则从缓存返回，不调用 LLM
- 反例: 缓存为空则正常 LLM 分析
- 边界: 相似但不同的题（相似度 0.85-0.92）则不命中，全量分析
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

#### Batch 4.2: 教学建议 + 置信度

**目标**: 报告从描述升级为决策支持

| Task | 文件 | 动作 |
|------|------|------|
| T1 教学建议 Prompt | `report_insights.py` | 新增教学建议生成 prompt：基于薄弱知识点 + 素养短板，输出 3-5 条具体建议 |
| T2 建议渲染 | `reports/templates.py` | 报告末尾新增"教学改进建议"章节 |
| T3 置信度计算 | `question_analyzer.py` | 从 LLM 响应提取 `analysis_confidence`（0-1），基于响应完整度/JSON 质量 |
| T4 置信度标注 | `components/ResultDisplay.jsx` | 低置信度（<0.6）的分析项标注"建议人工核验" |
| T5 置信度聚合 | `analysis_statistics.py` | 整卷平均置信度 + 低置信度题目数 |

**测试契约**:
- 入口: 报告包含"教学建议"章节，至少 3 条
- 反例: 全部题目高置信度则不出现"建议人工核验"
- 边界: 全部低置信度则报告首页 warning
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

#### Batch 4.3: 批量模式

**目标**: 一次上传多份试卷，排队处理

| Task | 文件 | 动作 |
|------|------|------|
| T1 批量上传 API | `analysis_router.py` | `/api/analyze/batch` — 接收多文件，返回 job_id 列表 |
| T2 任务队列 | 新建 `job_queue.py` | 内存队列 + asyncio.Queue，后台消费者逐个处理 |
| T3 进度查询 | `analysis_router.py` | `/api/analyze/batch/{job_id}/status` — 返回进度百分比 |
| T4 前端批量页 | `pages/AnalyzerPage.jsx` | 多文件拖拽 + 进度条列表 + 全部完成后汇总 |

**测试契约**:
- 入口: POST `/api/analyze/batch` 3 个文件则返回 3 个 job_id
- 反例: 0 个文件则 400
- 边界: 超出限制（>10 文件）则 413
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

#### Batch 4.4: 纵向对比 + 可编辑结果

**目标**: 多试卷对比 + 教师可修正分析结果

| Task | 文件 | 动作 |
|------|------|------|
| T1 对比 API | `analysis_router.py` | `/api/analyze/compare` — 接收多份分析结果 ID，返回对比数据（难度趋势、知识点偏移） |
| T2 对比数据计算 | `analysis_statistics.py` | `compare_exams(exam_ids) -> ComparisonReport` |
| T3 对比前端 | 新建 `pages/ComparisonPage.jsx` | 对比图表（折线叠加、差异高亮） |
| T4 结果编辑 API | `analysis_router.py` | `PATCH /api/questions/{id}/analysis` — 教师修正知识点/难度/素养 |
| T5 修正数据存储 | `models.py` | ExerciseBank 新增 `manual_override: JSON` 字段 |
| T6 修正反馈日志 | `admin_router.py` | 管理后台显示修正记录（人工标注数据，未来可用于微调） |

**测试契约**:
- 入口: `/api/analyze/compare?ids=1,2,3` 返回 `{trend, knowledge_shift, competency_change}`
- 反例: 只有 1 个 id 则返回单卷摘要（无对比）
- 边界: 不存在的 id 则 404
- 回归: 全量测试绿
- 命令: `pytest backend/tests/ -x`

---

## 执行顺序与依赖

```
Phase 1（成本） -----> Phase 2（科学性） -----> Phase 3（报告） -----> Phase 4（平台）
  1.1 Token追踪        2.1 知识点标准化        3.1 视觉升级            4.1 语义缓存
  1.2 分析合并 -------> 2.2 Bloom精细化 ------> 3.2 Word导出            4.2 教学建议+置信度
  1.3 模型路由          2.3 整卷诊断 ----------> 3.3 定制+在线报告       4.3 批量模式
                        2.4 难度校准                                    4.4 对比+可编辑
```

**关键依赖**:
- 1.2（分析合并）-> 2.2（Bloom 字段在合并 prompt 中加入）
- 2.3（整卷诊断）-> 3.1（诊断结果渲染到报告）
- 1.1（Token 追踪）-> 1.3（路由策略基于 token 成本数据）

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| 合并 Prompt 质量下降 | 分析 + 素养同时变差 | 保留独立素养调用作 fallback；A/B 对比验证 |
| 语义缓存误命中 | 相似但不同的题返回错误分析 | 高阈值（0.92）+ 缓存结果标注来源 |
| 报告 CSS 跨平台不一致 | WeasyPrint 渲染与浏览器不同 | 用 WeasyPrint 支持的安全 CSS 子集 |
| Bloom 层级 LLM 判断不一致 | 同题不同次分析给不同 Bloom 层级 | temperature=0 + 特征提取作兜底 |
| 历史数据不足（难度校准） | 校准无效 | 最小样本量门槛（10 场），不足时跳过校准 |

## semantic_regression（ORC 不变量）

- ORC-001: `llm_call()` 始终返回 str，从不返回 None（AllProvidersFailed 异常代替）
- ORC-002: `analyze_question()` 返回 dict 必须包含 `analysis` 和 `difficulty` 键
- ORC-003: `run_full_analysis()` 返回 dict 必须包含 `questions`, `competency_summary`, `exam_statistics` 键
- ORC-004: 缓存命中时，返回结构与 LLM 分析结构完全一致（透明缓存）
- ORC-005: 报告生成失败不影响分析结果返回（report_error 字段传递错误）
- ORC-006: 所有新增 API 端点走现有 auth 中间件

## Contract Pack

### invariants
1. 分析合并后的输出结构包含分别调用的全部输出字段 | verification: 新增 parity 测试
2. 语义缓存命中返回值与非缓存返回值结构一致 | verification: cache_parity_test
3. Token 计量大于等于 0 且单调递增 | verification: token_tracker_test

### counter_examples
1. 合并 prompt 返回空 JSON 导致系统崩溃 | tests_that_still_pass: fallback 路径测试 | mitigation: 独立素养调用 fallback
2. 缓存表为空加 DB 连接失败导致分析阻塞 | tests_that_still_pass: 缓存 miss 测试 | mitigation: 缓存查询 try/except，失败等同 miss

### risk_modules
- `llm_client.py` — token 计量不能影响调用性能
- `question_analyzer.py` — prompt 合并不能降低分析质量
- `cache_service.py` — 新模块，需要完整错误处理

### test_debt
- 报告 CSS 视觉测试 — 需要 screenshot 对比，当前无框架 | deadline: Phase 3 末尾评估
- 真实 LLM 响应端到端测试 — 需要 API key，CI 不可用 | deadline: 手动验证
