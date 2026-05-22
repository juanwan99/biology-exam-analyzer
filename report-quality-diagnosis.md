# 报告质量诊断 — GPT 深度分析上下文

## 用户反馈

用户看完端到端生成的报告后说"目前的报告我不太满意，质量不太好"。

## 端到端测试数据（20260514_003422.pdf，一模定稿.docx，20题+1题失败）

### 1. 特征提取（Call 2）几乎全废

19/20 题特征提取失败（DeepSeek 返回空响应），全部 fallback 到默认值：
```
working_memory=3, reasoning_steps=4, chain_coupling=2, trap_density=2, novelty=2, knowledge_breadth=2
```

**影响**：
- 所有题的 6 维雷达图几乎一模一样
- 难度评分被严重拉平（rule_scorer 基于这些特征计算）
- 报告中"特征分析"全是无意义的默认值

**根因候选**：
- DeepSeek fallback 走 feature_extractor prompt，该 prompt 可能对 DeepSeek 不兼容
- 备用 provider (AI) 先超时，才走的 DeepSeek
- feature_extractor prompt 太长或格式不匹配 DeepSeek

### 2. 知识点映射：55% 失败

97 个知识点中 53 个映射失败（返回原始内容）。

失败的知识点举例：
- "血糖平衡的调节" — 这是教材核心概念，不应该映射失败
- "物种的形成"、"碱基互补配对原则"、"核酸的结构与组成" — 都是教材基础概念
- "T细胞的分化与功能"、"选择培养基的原理" — 教材有但名称不完全匹配

**影响**：
- 知识覆盖分析不准确
- 教材分布统计严重失真
- "知识覆盖" section 的可信度很低

**根因候选**：
- LLM 输出的知识点名称太自由，不是课标标准术语
- 映射表只有 127 条 + 75 条同义词，覆盖面不够
- v2 prompt 没有约束知识点命名必须匹配课标

### 3. SEU/DU 数量太模式化

| SEU 数 | 题数 |
|--------|------|
| 1 | 6 题（选择题） |
| 2 | 10 题（选择题） |
| 4 | 1 题（大题） |
| 5 | 1 题（大题） |
| 6 | 1 题（大题） |
| 7 | 1 题（大题） |

DU 数量：19/20 题是 3 个，只有 1 题是 2 个。

**问题**：
- 选择题的 SEU 应该更细——4 个选项可能考查 4 个不同知识点，但模型几乎总是给 1-2 个 SEU
- DU=3 明显是照搬 few-shot 示例的模式。真实选择题 4 个干扰项应该有 3 个 DU（正确选项不算），但非选择题也给 3 个 DU 不合理
- 大题的 SEU 数量还算合理（4-7 对应多个小问）

**根因候选**：
- few-shot 示例引导性太强，模型照搬格式而不是根据题目内容决定
- prompt 对选择题的 SEU 拆分指导不够具体
- prompt 没有强调"每个选项都应该分析"

### 4. 素养分布过于集中

素养分布: 生命观念 18.4%, 科学思维 61.0%, 科学探究 9.2%, 社会责任 11.3%

20 题中 18 题的 primary_competency 是 "科学思维"，这不合理——一份完整的模考卷应该有更均衡的素养分布。

**根因候选**：
- LLM 对"科学思维"的判定阈值太低，把分析、推理、判断全归为科学思维
- prompt 对四大素养的区分指导不够
- v2 prompt 的 competency 字段只有 primary，没有让模型分析各素养的权重分布

### 5. 难度分布偏高

简单 8 分, 中等 32 分, 困难 40 分 — 一半试卷被判为"困难"。

**根因**：特征提取全部失败 → 默认值 → rule_scorer 基于默认值计算 → 难度不准

### 6. 质量评分缺失

日志中没有找到质量评分（quality_score）相关输出。

**根因候选**：
- 质量评分可能依赖 feature_extractor 的输出
- 如果 feature_extractor 返回空，质量评分可能被跳过

## 需要 GPT 分析的问题

1. **特征提取全废是 DeepSeek 兼容性问题还是 prompt 问题？** 读 feature_extractor.py 和它的 prompt，分析为什么 DeepSeek 返回空
2. **知识点映射 55% 失败的根因是什么？** 读 knowledge_mapper.py，看映射逻辑和词表覆盖范围
3. **SEU/DU 模式化的根因是 prompt 还是 few-shot？** 读 analysis_prompt_v2.txt，分析 few-shot 的引导效应
4. **素养分布集中到"科学思维"是 prompt 问题还是模型偏见？** 读 competency_analyzer.py 和 v2 prompt 的素养部分
5. **报告渲染层面还有什么问题？** 结合以上数据质量问题，报告的呈现方式是否合理

## 文件列表

GPT 应该读取以下文件做根因分析：
- backend/feature_extractor.py — 特征提取逻辑
- backend/prompts/ — 所有 prompt 文件
- backend/knowledge_mapper.py — 知识点映射
- backend/prompts/analysis_prompt_v2.txt — v2 主分析 prompt
- backend/competency_analyzer.py — 素养分析
- backend/rule_scorer.py — 难度规则评分
- backend/report_generator.py — 报告渲染（重点看数据流入口）
