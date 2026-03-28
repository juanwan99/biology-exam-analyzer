# 难度评分模型 v3.1 设计文档 — 大题结构化拆分评估

> snapshot: 2026-03-28
> 状态: 设计确认
> 前序: v3 设计 → docs/plans/2026-03-28-difficulty-v3-design.md
> GPT 5.4 设计咨询 → docs/plans/.codex-difficulty-v3-consult-raw.log

## §0 覆盖声明

> [2026-03-28 12:26:03 实现完成] Commits: 2cec9b3..5bde271

v3.1 扩展 v3 评分逻辑，不替代。选择题（total_score ≤ 4）走 v3 原路径不变。大题（total_score ≥ 8）新增结构化拆分 → 特征聚合路径。

## §1 设计动机

v3 对选择题评分合理（4.2-8.8），但大题存在系统性低估：

| 题号 | 题目 | v3 评分 | 教师预期 | 偏差 |
|------|------|---------|---------|------|
| Q21 | 番茄红素 PSY 融合蛋白 | 8.2 | ≥9.5 | **-1.3（严重低估）** |
| Q19 | 槟榔碱口腔纤维化 | 9.9 | 8-9 | +0.9（偏高） |

**根因（GPT 咨询确认）**：LLM 把大题的多小问依赖关系压成一组扁平标量时，产生两种系统性偏差：
- **平均化**：把"一个很强的关键链"平均成"几个部分独立的小问"
- **保守化**：把"前一问错后续全错"描述成"部分相关"（coupling=2 实际应为 3）

**设计原则**：不改 prompt 措辞（钝器），改输出结构 → 特征层聚合。

## §2 触发条件

```python
is_big_question = total_score >= 8
```

| 路径 | 条件 | 流程 |
|------|------|------|
| 选择题 | total_score < 8 | v3 原路径：整题特征 → compute_difficulty |
| 大题 | total_score ≥ 8 | v3.1：结构化提取 → 特征聚合 → compute_difficulty |

## §3 大题 LLM 输出结构

仍然整题一次 LLM 调用（成本不变），但输出从扁平 JSON 变为结构化 JSON。

### 输出 Schema

```json
{
  "subquestions": [
    {
      "id": 1,
      "points": 4,
      "working_memory": 3,
      "reasoning_steps": 3,
      "trap_density": 1,
      "novelty": 2,
      "knowledge_breadth": 2,
      "brief": "回答番茄红素合成基础知识"
    },
    {
      "id": 2,
      "points": 4,
      "working_memory": 4,
      "reasoning_steps": 3,
      "trap_density": 2,
      "novelty": 2,
      "knowledge_breadth": 2,
      "brief": "分析 GFP-PSY 定位失败原因 + 提出改造方案"
    },
    {
      "id": 3,
      "points": 6,
      "working_memory": 4,
      "reasoning_steps": 4,
      "trap_density": 3,
      "novelty": 3,
      "knowledge_breadth": 2,
      "brief": "设计引物 + 判断正反插入 PCR 条带大小"
    }
  ],
  "dependencies": [
    {"from": 1, "to": 2, "strength": "weak", "reason": "第2问需要合成通路背景知识"},
    {"from": 2, "to": 3, "strength": "strong", "reason": "第3问引物设计依赖第2问的改造方案(PSY-GFP)"}
  ],
  "global_features": {
    "shared_context_load": 2,
    "global_method_novelty": 3,
    "shared_context_reason": "GFP融合蛋白构建策略贯穿全题",
    "method_novelty_reason": "In-Fusion克隆技术在高中教材中完全没有"
  },
  "bloom": 5,
  "bloom_distribution": {"识记": 1, "理解": 1, "应用": 1, "分析": 2, "评价": 1, "创造": 1},
  "bloom_reason": "需要评价改造方案可行性并设计引物",
  "info_density": 3,
  "density_reason": "融合蛋白图+载体图+凝胶图",
  "representation_complexity": 2,
  "representation_reason": "载体构建示意图",
  "quality_score": 4,
  "quality_scientific": "无明显问题",
  "quality_normative": "各小问分值分配合理",
  "quality_language": "表述清晰",
  "quality_context": "融合蛋白定位问题情境真实",
  "quality_sensitivity": "无舆情风险",
  "teacher_comment": "本题以番茄红素合成为背景..."
}
```

### 字段说明

**subquestions[]**（每小问特征）：
- `id`: 小问序号（从 1 开始）
- `points`: 该小问分值（所有小问分值之和应等于整题分值）
- `working_memory`, `reasoning_steps`, `trap_density`, `novelty`, `knowledge_breadth`: 与 v3 定义一致，但仅针对该小问
- `brief`: 该小问核心任务一句话（≤20 字）

**dependencies[]**（依赖关系）：
- `from` → `to`: 哪个小问依赖哪个（有向边）
- `strength`: `"weak"` | `"strong"`
  - `weak`: 背景知识辅助，不知道也能部分作答
  - `strong`: 前问结论是后问前提，前错则后错
- `reason`: 依赖具体内容（≤30 字）

**global_features**（整题级特征）：
- `shared_context_load` (1-3): 共享材料带来的跨问保持负担（1=各问独立素材，2=共享一个实验背景，3=全题围绕一个复杂系统）
- `global_method_novelty` (1-3): 整题是否含教材外方法/技术（1=全部教材内，2=部分教材外，3=核心方法教材外）

## §4 特征聚合规则

从 subquestions + dependencies + global_features 聚合出一组标准 v3 特征，然后走现有 `compute_difficulty()` 评分。

### 4.1 关键路径计算

```python
def find_critical_path(subquestions, dependencies):
    """找到加权最长路径（权重 = reasoning_steps）。
    
    仅 strong 依赖构成有效路径边。weak 依赖不纳入关键路径。
    """
    # 构建有向图（只用 strong 依赖）
    # DAG 最长路径算法（拓扑排序 + DP）
    # 返回: critical_path_nodes, critical_path_steps
```

### 4.2 effective_steps（替代 steps × coupling）

```python
critical_path_steps = sum(sq["reasoning_steps"] for sq in path_nodes)
total_steps = sum(sq["reasoning_steps"] for sq in all_subquestions)
off_path_steps = total_steps - critical_path_steps
effective_steps = critical_path_steps + 0.35 * off_path_steps
```

**Q21 验算**：
- 小问 1(3步) → 小问 2(3步) → 小问 3(4步)，关键路径 = [2,3]（strong 链）
- critical_path_steps = 3+4 = 7，total_steps = 3+3+4 = 10
- effective_steps = 7 + 0.35 × 3 = 8.05

**Q19 验算**（假设并列结构）：
- 关键路径较短（如 4 步），total = 8
- effective_steps = 4 + 0.35 × 4 = 5.4（v3 原来用 8×1.3=10.4，大幅降低）

### 4.3 working_memory（峰值 + 跨问保持）

```python
path_wm_values = [sq["working_memory"] for sq in path_nodes]
path_length = len(path_nodes)
shared_ctx = global_features["shared_context_load"]
wm = clip(max(path_wm_values) + 0.4 * (path_length - 1) + 0.3 * shared_ctx, 1, 5)
```

**Q21 验算**：
- path_nodes = [sq2(wm=4), sq3(wm=4)]，max=4
- path_length=2, shared_context=2
- wm = clip(4 + 0.4×1 + 0.3×2, 1, 5) = clip(5.0, 1, 5) = 5

### 4.4 novelty（方法新颖度增强）

```python
# 按分值加权平均各小问 novelty
weighted_novelty = sum(sq["novelty"] * sq["points"] for sq in sqs) / sum(sq["points"] for sq in sqs)
# 取方法新颖度和内容新颖度的较高者
novelty = max(global_features["global_method_novelty"], weighted_novelty)
```

**Q21 验算**：
- weighted_novelty = (2×4 + 2×4 + 3×6) / 14 = 34/14 ≈ 2.4
- global_method_novelty = 3（In-Fusion 教材外）
- novelty = max(3, 2.4) = 3

### 4.5 trap_density（关键路径最大值）

```python
trap = max(sq["trap_density"] for sq in path_nodes)
```

关键路径上的陷阱决定整题丢分风险。**Q21**: max(2, 3) = 3

### 4.6 knowledge_breadth（全局最大值）

```python
breadth = max(sq["knowledge_breadth"] for sq in all_subquestions)
```

跨模块整合看整题而非单问。**Q21**: max(2, 2, 2) = 2

### 4.7 chain_coupling 回写（向后兼容）

大题不再使用 chain_coupling 参与评分（被 critical_path_steps 替代），但为兼容报告前端，从依赖图派生：

```python
total_points = sum(sq["points"] for sq in all_subquestions)
path_points = sum(sq["points"] for sq in path_nodes)
critical_path_score_share = path_points / total_points
if critical_path_score_share < 0.35:
    chain_coupling = 1
elif critical_path_score_share <= 0.70:
    chain_coupling = 2
else:
    chain_coupling = 3
```

## §5 Q21 端到端验算

| 维度 | v3 原值 | v3.1 聚合值 | 说明 |
|------|--------|------------|------|
| working_memory | 4 | **5** | 峰值 + 跨问保持 |
| effective_steps | 6×1.3=7.8 | **8.05** | 关键路径模型 |
| trap_density | 2 | **3** | 关键路径最大值 |
| novelty | 2 | **3** | 方法新颖度 |
| knowledge_breadth | 2 | 2 | 不变 |
| chain_coupling | 2 | 3(派生) | 不参与评分 |

v3.1 评分（代入 compute_difficulty）：
- wm_mapped = 1.00（wm=5）
- eff_steps_mapped = min(1.0, 8.05/12) = 0.67
- trap_mapped = 0.90（trap=3）
- novelty_mapped = 0.85（novelty=3）
- breadth_mapped = 0.40（breadth=2）
- raw = 1.00×0.28 + 0.67×0.28 + 0.90×0.18 + 0.85×0.14 + 0.40×0.12 = 0.28 + 0.188 + 0.162 + 0.119 + 0.048 = 0.797
- bonus = 0.08(wm≥4+eff≥8) + 0.06(trap≥2+novelty≥2) = 0.14
- score = 2.0 + (0.797+0.14)×8.0 = 2.0 + 7.50 = **9.5**

✅ 与教师预期（≥9.5）吻合。

## §6 Q19 验算（预期降低）

假设 LLM 输出：4 个小问（steps: 2,2,2,2），依赖关系 1→2(strong), 3 和 4 独立。
- critical_path = [1,2]，steps = 4，total = 8
- effective_steps = 4 + 0.35×4 = 5.4
- wm = clip(max(4,3) + 0.4×1 + 0.3×2, 1, 5) = clip(5.0, 1, 5) = 5（假设 wm 峰值 4）

这里 effective_steps 从 v3 的 8×1.3=10.4 降到 5.4，可显著修正 Q19 的偏高。

## §7 改动清单

| 文件 | 改动 | 改动量估计 |
|------|------|-----------|
| `feature_extractor.py` | 新增 `build_big_question_prompt()` + `parse_big_question_features()` | ~150 行 |
| `rule_scorer.py` | 新增 `aggregate_big_question()` + `find_critical_path()` | ~80 行 |
| `difficulty_pipeline.py` | `_evaluate_single()` 增加题型分流逻辑 | ~30 行 |
| `test_feature_difficulty.py` | 新增大题聚合测试 | ~100 行 |
| `test_core_modules.py` | 新增关键路径 + 聚合规则测试 | ~80 行 |

## §8 不改的部分

- 选择题路径完全不变
- `compute_difficulty()` 公式不变（聚合后的特征直接传入）
- 对外接口（`evaluate_with_refinement`）不变
- 前端 / 报告消费的字段名不变
- LLM 调用次数不增加（大题仍是 1 次调用）

## §9 降级策略

大题结构化提取失败时（JSON 解析失败 / subquestions 缺失 / 依赖图矛盾）：
1. fallback 到 v3 原路径（整题扁平特征 → compute_difficulty）
2. 在 flags 列表中追加 `"big_question_fallback"`
3. confidence 额外扣 0.15

## §10 未来扩展（v3.2 方向，本次不做）

- `response_construction` (1-3) 生成型作答负担维度（GPT 建议第 7 维）
- 分题型校准曲线（选择题/大题独立校准）
- `cognitive_difficulty` vs `score_risk` 双输出
- 评估集切片化验证（按链式/并列/实验设计/知识分析分类）
