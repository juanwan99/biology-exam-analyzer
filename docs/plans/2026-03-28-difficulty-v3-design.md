# 难度评分模型 v3 设计文档

> snapshot: 2026-03-28
> 状态: 设计确认
> 前序: v2 设计 → docs/plans/2026-03-24-difficulty-scoring-v2-design.md

## §0 覆盖声明

v3 替代 v2 的评分逻辑。v2 的 7 维特征提取 + 非线性规则评分全部重写。

## §1 设计动机

v2 本质是教育学分类器（Bloom + 题型 → 加权求和），不是难度预测器。核心问题：
- bloom=6（创造）自动高分，但模板化实验设计可能很简单
- qtype_factor 和 bloom 双重计分，实验设计题被系统性高估
- 不区分推理链的耦合度（7 步独立 vs 7 步链式）
- 缺少"陷阱密度"维度（选择题区分度的核心）

**v3 核心转变：难度 = 学生做错的概率，不是认知层级的高低。**

## §2 维度模型（v3: 6 维）

### 评分维度（参与难度计算）

| # | 维度 | 字段名 | 范围 | 含义 |
|---|------|--------|------|------|
| 1 | 工作记忆负荷 | `working_memory` | 1-5 | 解题关键步骤需同时处理的信息元素数 |
| 2 | 推理链长度 | `reasoning_steps` | 1-10 | 从题目信息到答案的最少认知操作数（沿用 v2） |
| 3 | 推理耦合度 | `chain_coupling` | 1-3 | 1=各步独立 2=部分依赖 3=全链依赖（前错后崩） |
| 4 | 陷阱密度 | `trap_density` | 1-3 | 看似正确但实际错误的推理路径/选项数量 |
| 5 | 熟悉度缺口 | `novelty` | 1-3 | 沿用 v2（1=教材原题 2=变式 3=全新情境） |
| 6 | 知识整合跨度 | `knowledge_breadth` | 1-3 | 沿用 v2（1=单知识点 2=跨考点 3=跨模块） |

### 报告维度（不参与评分，仅用于教学报告）

| 字段名 | 范围 | 用途 |
|--------|------|------|
| `bloom` | 1-6 | 认知层级标签（报告用） |
| `bloom_distribution` | dict | 逐选项/逐小问 bloom 分布（报告用） |
| `info_density` | 1-3 | 信息密度（报告用，v2 沿用） |
| `representation_complexity` | 1-3 | 表征复杂度（报告用，v2 沿用） |
| `quality_*` 系列 | - | 命题质量审查（沿用） |
| `teacher_comment` | - | 教师点评（沿用） |

### 删除的维度

| 字段名 | 原因 |
|--------|------|
| `question_type_factor` | 题型不直接影响难度，其效果已被 working_memory 和 chain_coupling 覆盖 |

## §3 评分公式（rule_scorer v3）

### 有效推理链

```
effective_steps = reasoning_steps × coupling_multiplier
coupling_multiplier = {1: 1.0, 2: 1.3, 3: 1.6}
```

### 维度映射（0-1 归一化）

| 维度 | 映射曲线 |
|------|---------|
| working_memory | {1: 0.05, 2: 0.15, 3: 0.35, 4: 0.65, 5: 1.00} |
| effective_steps | 线性 clamp: `min(1.0, effective_steps / 12.0)` |
| trap_density | {1: 0.10, 2: 0.45, 3: 0.90} |
| novelty | {1: 0.05, 2: 0.35, 3: 0.85} |
| knowledge_breadth | {1: 0.10, 2: 0.40, 3: 0.85} |

### 权重

| 维度 | 权重 | 理由 |
|------|------|------|
| working_memory | **0.28** | 工作记忆负荷是最强预测因子 |
| effective_steps | **0.28** | 推理链（含耦合度）决定出错概率 |
| trap_density | **0.18** | 陷阱决定"看起来会但做错" |
| novelty | **0.14** | 不熟悉度决定能否调用已有经验 |
| knowledge_breadth | **0.12** | 跨模块整合增加认知负担 |

### 交互项

```
bonus = 0
if working_memory >= 4 and effective_steps >= 8:  # 高负荷 + 长链
    bonus += 0.08
if trap_density >= 2 and novelty >= 2:  # 有陷阱 + 不熟悉
    bonus += 0.06
if knowledge_breadth >= 3 and working_memory >= 3:  # 跨模块 + 高负荷
    bonus += 0.04
```

### 最终分数

```
raw = Σ(mapped[dim] × weight[dim]) + bonus
score = 2.0 + raw × 8.0  # 映射到 2-10
score = clamp(score, 2.0, 10.0)
```

### 标签

| 分数 | 标签 |
|------|------|
| ≤ 3.5 | 简单 |
| ≤ 5.5 | 中等偏易 |
| ≤ 7.5 | 中等偏难 |
| > 7.5 | 困难 |

## §4 LLM Prompt 改造

feature_extractor.py 的 prompt 需要：
1. 新增 `working_memory`、`chain_coupling`、`trap_density` 的提取指令和判例
2. 删除 `question_type_factor` 的提取
3. bloom 保留提取但标注"仅用于报告，不影响难度评分"
4. info_density、representation_complexity 保留提取但标注"报告用"

### Prompt 新增段落

```
"working_memory": 1-5（解题关键步骤中，需要同时在脑中保持的信息元素数量。
  1=直接匹配（读题→回忆→作答），
  2=单一比较（两个概念对比），
  3=多条件筛选（3-4个条件同时考虑），
  4=多要素联立（4-5个信息元素交叉推理），
  5=复杂系统推理（5+个要素同时操控，如多基因+环境+表型+系谱联合分析）），

"chain_coupling": 1-3（推理链中各步骤的依赖关系。
  1=独立：各步骤可单独完成，错一步不影响其他（如选择题四个选项独立判断），
  2=部分依赖：部分步骤依赖前步结论，但有独立分支（如先判断遗传方式再推基因型，但表现型判断独立），
  3=全链依赖：前一步错则后续全错（如连续遗传推理、多步代谢通路分析、基因工程构建→转化→筛选→验证全链条）），

"trap_density": 1-3（看起来合理但实际错误的推理路径或选项数量。
  1=低（0-1个干扰项有效，答案一眼可见），
  2=中（2-3个选项/路径有迷惑性，需要仔细排除），
  3=高（4+个看似合理的错误路径，或存在经典易混淆概念陷阱）），
```

## §5 改动清单

| 文件 | 改动 |
|------|------|
| `backend/feature_extractor.py` | prompt 重写（新增 3 维，删 qtype_factor，bloom 标注仅报告用） |
| `backend/rule_scorer.py` | 评分公式全部重写（新权重、新维度、新交互项） |
| `backend/difficulty_pipeline.py` | 适配新特征字段名 |
| `backend/test_feature_difficulty.py` | 更新测试用例 |
| `backend/test_core_modules.py` | 更新 scorer 相关测试 |

## §6 向后兼容

- `bloom` / `bloom_distribution` / `info_density` / `representation_complexity` 继续提取，前端和报告不受影响
- `difficulty_pipeline.py` 的对外接口（`evaluate_with_refinement`）不变
- `final_difficulty` / `difficulty_label` / `score_distribution_by_difficulty` 字段名不变
- 旧的 `question_type_factor` 字段：提取时不再要求，parse_features 中移出 FEATURE_RANGES（遇到旧数据忽略）

## §7 预期效果（Q19 vs Q20）

| 维度 | Q19 槟榔碱·实验设计 | Q20 水稻·基因工程 |
|------|-------------------|------------------|
| working_memory | 3 | 5 |
| reasoning_steps | 7 | 7 |
| chain_coupling | 1（各步独立） | 3（全链依赖） |
| effective_steps | 7.0 | 11.2 |
| trap_density | 2 | 3 |
| novelty | 3 | 3 |
| knowledge_breadth | 3 | 3 |
| **预估分数** | **~7.0（中等偏难）** | **~9.0（困难）** |
