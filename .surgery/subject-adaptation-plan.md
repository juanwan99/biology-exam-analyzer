# 九学科适配实施方案（目标 2）——骨架 v1

> 基于 2026-06-13 实查。已有地基比 GOAL 文档预估的多，工作量从"从零设计"收窄为"补全贯通"。

## 已有地基（实查确认）

| 组件 | 状态 |
|---|---|
| `prompts/{subject}/` 19 科目录（高中 9 + 初中 cz-10） | ✅ 每科 6 文件：analysis/big_question_extractor/competency/feature_extractor/report_insights/split，内容真实（180-220 行/科） |
| `backend/prompt_loader.py` PromptLoader(subject) | ✅ 学科加载 + _base fallback（_base 目录暂不存在） |
| `feature_extractor.py` | ✅ 已接 PromptLoader(subject)（2 处） |
| `difficulty_pipeline.py` | ✅ 可传 subject（test_9subjects 直调验证） |
| `test_9subjects.py` | ✅ 九科 ×2 题集成测试脚本（需 DEEPSEEK_API_KEY 手动跑） |
| docker-compose `./prompts:/app/subject_prompts` 挂载 | ✅ |

## 缺口（按层）

### L1 API/入口层
- [ ] `analyze_auto` 加 `subject: str = Form("biology")` 参数，向下贯通
- [ ] 前端 AnalyzerPage 加学科选择器（9 科下拉/宫格）
- [ ] `_run_analysis_pipeline` / `analyze_question_full` / analysis_service 链路传 subject

### L2 分析层（最大块）
- [ ] question_analyzer 拆分/分析 prompt：从旧 PROMPT_DIR（backend/prompts/，含生产 v2 细粒度 prompt）切到 PromptLoader
  - 关键决策：v2 prompt（SEU/DU/SU 细粒度，生产在用）只有生物版。方案 A=为 9 科生成 analysis_prompt_v2（工作量大、质量要校）；方案 B=把 v2 结构做成学科无关模板+学科参数注入（推荐，单一事实源）
- [ ] competency_analyzer：素养框架从硬编码（生物四素养）改数据驱动
- [ ] knowledge_mapper：人教版生物章节 dict → rules/subjects/{subject}.json（9 科章节树）
- [ ] llm_schemas：素养字段（生物四条写死）按学科动态生成/校验

### L3 报告层
- [ ] report_insights / report_product_model / charts / html / exam_diagnostics / analysis_calibration：素养维度名称与条数参数化
- [ ] 前端 ResultDisplay / 素养图表组件：维度动态渲染（雷达图 4-6 维自适应）
- [ ] AnalyzerPage 静态文案（"生命观念、科学思维等核心素养"）

### L4 数据层
- [ ] DB：exam_history / question_performance 等表加 subject 列（DDL 兼容式，默认 'biology'）
- [ ] exercise_bank 相似题、真实校准数据：按学科留空起步，报告对应板块自动隐藏（降级共识）

## 学科素养框架（写入 rules/subjects/{subject}.json，执行时按课标校对）
语文4：语言建构与运用/思维发展与提升/审美鉴赏与创造/文化传承与理解
数学6：数学抽象/逻辑推理/数学建模/直观想象/数学运算/数据分析
英语4：语言能力/文化意识/思维品质/学习能力
物理4：物理观念/科学思维/科学探究/科学态度与责任
化学5：宏观辨识与微观探析/变化观念与平衡思想/证据推理与模型认知/科学探究与创新意识/科学态度与社会责任
生物4：生命观念/科学思维/科学探究/社会责任（现状）
政治4：政治认同/科学精神/法治意识/公共参与
历史5：唯物史观/时空观念/史料实证/历史解释/家国情怀
地理4：人地协调观/综合思维/区域认知/地理实践力

## 验收
- 9 科每科 ≥1 份真卷 E2E（拆题正确、分析完整、报告 PDF+HTML、素养维度符合课标）
- 生物回归：旧报告可打开 + 再跑一卷与升级前量级一致
- 测试卷来源：生物有现成（一模/高考卷）；其余 8 科需准备（用户提供或从公开真题构造 docx）

## 待办（摘谷歌部署后启动）
1. workflow 深调研：question_analyzer prompt 切换的精确方案 + 素养/报告层参数化的全部触点清单
2. 9 科 rules/subjects JSON 资源包生成（含章节树，并行 agent 每科一个）
3. 实施 → 九科 E2E
