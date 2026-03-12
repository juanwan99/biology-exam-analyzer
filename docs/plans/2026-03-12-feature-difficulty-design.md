# 特征分析难度评估设计

> snapshot: 2026-03-12
> [2026-03-12 18:46:50 实现完成] Commits: 1843bc3..62fc726
> 覆盖: 旧 DifficultyPipeline（模拟学生 + IRT）

## §0 覆盖声明

本设计替代 `difficulty_pipeline.py` 中的 Stage 2（模拟学生作答）和 Stage 3（IRT 拟合）。
旧模块（`simulated_student.py`、`irt_estimator.py`）保留文件但不再作为主路径调用。

## §1 问题分析

### 现状
- 当前 Pipeline：12 个模拟学生（Claude Sonnet）做题 → 2PL IRT 拟合 → 难度分数
- 核心缺陷：**floor_hit**——LLM 知识是"全有"的，无法模拟真实学生的知识盲区
- 实测数据（9 道高考单选题）：44% 触发 floor_hit（全部学生答对），包括标注 0.80 的难题
- 替换 Haiku 做弱学生效果不稳定（5/8 仍 floor_hit）

### 根因
高考生物大量题目考知识记忆，不需要推理。无论 Sonnet 还是 Haiku，训练数据都包含完整高中教材。
prompt 说"你基础薄弱"只是让模型演弱，不是真弱。

## §2 方案选型

| 方案 | 优势 | 劣势 | 结论 |
|------|------|------|------|
| A. 模拟学生（当前） | 直觉、可解释 | floor_hit 44%，12 次 API/题 | ❌ 根因无法解决 |
| B. 换弱模型（Haiku/GPT-3.5） | 实现简单 | 实测不稳定，知识记忆题仍全对 | ❌ |
| C. LLM 直接预测难度 | 1 次 API/题 | 不可解释，缺乏校准 | ❌ |
| **D. 特征提取 + 规则评分** | 可解释、1 次 API/题、可校准 | 初始权重靠专家经验 | ✅ 采用 |

学术支撑：文献综述（Springer 2023）显示特征提取+ML 方法相关性达 r=0.87，优于 LLM 直接预测。

## §3 特征维度

6 维特征体系，精简自 MCU-03 题目分析框架（4492 道高考生物题验证）。

### F1: 认知层级 (bloom)
Bloom 认知分类法，6 级。
- 1=识记（直接回忆事实）
- 2=理解（解释概念）
- 3=应用（在熟悉情境使用知识）
- 4=分析（拆解信息、找关系）
- 5=评价（判断、批判）
- 6=创造（设计实验、提出方案）

### F2: 推理步数 (reasoning_steps)
从题目信息到正确答案的推理步骤数。
- 选择题逐项验证：每个选项算 1 步
- 遗传计算：每个推理环节算 1 步
- 取值 1-10+，超过 8 步按 8 计算（封顶）

### F3: 知识跨度 (knowledge_breadth)
- 1=单知识点（一个概念即可解答）
- 2=跨考点（同模块多知识点）
- 3=跨模块（如遗传+进化+生态综合）

### F4: 信息密度 (info_density)
- 1=低（≤2 条信息/条件）
- 2=中（3-5 条）
- 3=高（>5 条，或含图表/数据表）

### F5: 情境新颖度 (novelty)
- 1=教材原文（教材例题或经典题型）
- 2=变式（教材概念+新包装）
- 3=全新情境（科研前沿/生活实际/跨学科，需要知识迁移）

### F6: 题型因子 (question_type_factor)
- 1=单选题
- 2=多选题/填空题
- 3=简答题
- 4=实验设计题/论述题

## §4 评分公式

### v1 加权线性公式

```python
def compute_difficulty(features: dict) -> float:
    """6 维特征 → 0-10 难度分。"""
    bloom = features["bloom"]           # 1-6
    steps = features["reasoning_steps"] # 1-10+
    breadth = features["knowledge_breadth"]  # 1-3
    density = features["info_density"]       # 1-3
    novelty = features["novelty"]            # 1-3
    qtype = features["question_type_factor"] # 1-4

    raw = (
        (bloom / 6) * 0.25
        + min(steps / 8, 1.0) * 0.25
        + (breadth / 3) * 0.15
        + (density / 3) * 0.15
        + (novelty / 3) * 0.10
        + (qtype / 4) * 0.10
    )
    return round(raw * 10, 1)
```

### 公式特性
- 纯识记单选题最低分：(1/6)*0.25 + (1/8)*0.25 + (1/3)*0.15 + (1/3)*0.15 + (1/3)*0.10 + (1/4)*0.10 = 0.042+0.031+0.05+0.05+0.033+0.025 = 0.231 → **2.3 分**
- 17 步跨模块遗传实验设计最高分：(5/6)*0.25 + 1.0*0.25 + 1.0*0.15 + 1.0*0.15 + 1.0*0.10 + 1.0*0.10 = 0.208+0.25+0.15+0.15+0.10+0.10 = 0.958 → **9.6 分**
- 区间合理，中等题约 4-6 分

### v2 校准路径（后续）
有真实数据后：
1. 收集题目的真实正确率/得分率
2. 线性回归拟合 6 维权重
3. 若线性不够 → XGBoost + SHAP 分析特征交互

## §5 LLM 特征提取

### Prompt 设计
一次 API 调用提取全部 6 维特征，输出 JSON。使用 Gemini（现有分析管道已用 Gemini）或 Claude Sonnet。

```
你是一名资深高中生物教师。请分析这道题目的难度特征。

题目：{question_text}
选项：{options}
正确答案：{correct_answer}

请输出以下 6 个维度的评分（严格 JSON）：
{
  "bloom": 1-6（1识记 2理解 3应用 4分析 5评价 6创造），
  "reasoning_steps": 正整数（从题目信息到答案的推理步数），
  "knowledge_breadth": 1-3（1单知识点 2跨考点 3跨模块），
  "info_density": 1-3（1低≤2条 2中3-5条 3高>5条或含图表），
  "novelty": 1-3（1教材原文 2变式 3全新情境），
  "question_type_factor": 1-4（1单选 2多选/填空 3简答 4实验设计）
}
只输出 JSON，不要解释。
```

### 解析容错
- JSON 解析失败 → 正则提取数字
- 数值越界 → clip 到合法范围
- API 失败 → 返回默认值（各维度中位数，难度 5.0）

## §6 系统集成

### 文件变更
| 文件 | 动作 | 说明 |
|------|------|------|
| `feature_extractor.py` | 新增 | LLM 特征提取 prompt + JSON 解析 |
| `rule_scorer.py` | 新增 | 加权公式 + 标签映射 |
| `difficulty_pipeline.py` | 修改 | Stage 2/3 替换为特征提取+规则评分 |
| `simulated_student.py` | 保留 | 不再作为主路径，可选备用 |
| `irt_estimator.py` | 保留 | 不再作为主路径，可选备用 |

### API 兼容
`DifficultyPipeline.evaluate_with_refinement()` 返回格式不变：
- `base_difficulty` / `final_difficulty` → 新公式分数
- `difficulty_label` → 从分数映射（简单/中等偏易/中等偏难/困难）
- `score_distribution_by_difficulty` → 保持不变
- 新增 `features` 字段 → 6 维特征原始值（可解释性）

### 成本对比
| | 模拟学生（旧） | 特征分析（新） |
|---|---|---|
| API 调用/题 | 12 次 Sonnet | 1 次 Sonnet/Gemini |
| 估算成本/题 | ~$0.12 | ~$0.01 |
| 延迟/题 | ~30s | ~3s |
| floor_hit | 44% | 不存在 |

## §7 验证计划

用 biology-exam-analyzer DB 中 697 道有 `difficulty_level` 标注的真题验证：
1. 对 697 道题跑特征提取 + 规则评分
2. 对比新分数与旧 `difficulty_level` 的分布
3. 检查极端 case（旧标注 0.80 的题是否得到较高分数）
4. 与之前模拟学生实测的 9 道题结果对比

验收标准：
- 新分数分布不再聚集（旧系统 77% 在 0.60）
- 难度排序与直觉一致（遗传计算 > 概念辨析）
- 无 floor_hit / ceiling_hit

## §8 决策记录

| 决策 | 理由 |
|------|------|
| 6 维而非 8 维 | YAGNI，MCU-03 的"干扰项质量"和"图表分析"可后续加入 |
| 线性公式而非 ML | 无校准数据，先跑通再优化 |
| 保留旧模块文件 | 可选备用，后续可能作为辅助信号 |
| 用 Sonnet 而非 Gemini 提取 | 现有 `claude_client.py` 已可用，减少集成工作 |
