# 难度评分 v3.1 大题结构化拆分评估 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 大题（≥8分）的难度评分从扁平特征改为结构化拆分（小问特征 + 依赖图），通过关键路径模型聚合后走现有评分公式，修正 Q21 低估（8.2→9.5）和 Q19 偏高（9.9→~8.5）。

**Architecture:** 选择题路径完全不变。大题在 feature_extractor 中使用专用 prompt 输出结构化 JSON（subquestions + dependencies + global_features），rule_scorer 新增 `aggregate_big_question()` 将结构化特征聚合为标准 v3 特征向量，最后走现有 `compute_difficulty()` 评分。difficulty_pipeline 负责按 total_score 分流。

**Tech Stack:** Python 3.x, pytest, 无新依赖

**设计文档:** `docs/plans/2026-03-28-difficulty-v3.1-design.md`

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `backend/rule_scorer.py` | 关键路径算法 + 特征聚合规则 | 修改（新增 ~80 行） |
| `backend/feature_extractor.py` | 大题专用 prompt + 结构化 JSON 解析 | 修改（新增 ~150 行） |
| `backend/difficulty_pipeline.py` | 题型分流（total_score >= 8 → 大题路径） | 修改（新增 ~30 行） |
| `backend/test_core_modules.py` | 关键路径 + 聚合规则单元测试 | 修改（新增 ~80 行） |
| `backend/test_feature_difficulty.py` | 大题 prompt/parse + pipeline 集成测试 | 修改（新增 ~100 行） |

---

### Task 1: 关键路径算法 + 特征聚合规则（rule_scorer.py）

纯逻辑，无 LLM 依赖。这是 v3.1 的核心计算单元。

**Files:**
- Modify: `backend/rule_scorer.py:85-93`（在 `score_to_label` 之后追加）
- Test: `backend/test_core_modules.py`（在文件末尾追加新 class）

**测试契约:**
1. 线性依赖链 → 关键路径正确
   - 入口: `find_critical_path([sq1,sq2,sq3], [dep(1→2,strong), dep(2→3,strong)])`
   - 反例: 错误实现可能忽略 strong 过滤，把 weak 依赖也计入路径——本测试验证只有 strong 边参与
   - 边界: 无依赖（单节点）/ 全 weak 依赖 / 菱形 DAG
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_core_modules.py::TestCriticalPath -v`

2. Q21 聚合验算（设计文档 §5）
   - 入口: `aggregate_big_question(subquestions, dependencies, global_features)`
   - 反例: 错误实现可能用 total_steps 代替 critical_path_steps——Q21 的 effective_steps 会从 8.05 变成 10，导致评分偏高
   - 边界: 单小问 / 全并列（无 strong 依赖）/ 全链式
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_core_modules.py::TestAggregation -v`

**边界条件:**
- 单小问（no dependencies）→ 退化为该小问的原始特征
- 全 weak 依赖 → critical_path 只有单个最大 steps 节点，无跨问保持加成
- 菱形 DAG（1→2, 1→3, 2→4, 3→4）→ 选最长路径

- [ ] **Step 1: 写关键路径算法的失败测试**

在 `backend/test_core_modules.py` 文件末尾追加：

```python
# ============ rule_scorer.py — 大题聚合 v3.1 ============

class TestCriticalPath:
    """find_critical_path 关键路径算法测试。"""

    def setup_method(self):
        from rule_scorer import find_critical_path
        self.find = find_critical_path

    def _sq(self, id, steps, points=4, wm=3, trap=2, novelty=2, breadth=2):
        return {"id": id, "points": points, "working_memory": wm,
                "reasoning_steps": steps, "trap_density": trap,
                "novelty": novelty, "knowledge_breadth": breadth}

    def _dep(self, fr, to, strength="strong"):
        return {"from": fr, "to": to, "strength": strength}

    def test_linear_chain(self):
        """1→2→3 线性链，关键路径 = [1,2,3]。"""
        sqs = [self._sq(1, 3), self._sq(2, 3), self._sq(3, 4)]
        deps = [self._dep(1, 2), self._dep(2, 3)]
        path_nodes, path_steps = self.find(sqs, deps)
        path_ids = [n["id"] for n in path_nodes]
        assert path_ids == [1, 2, 3]
        assert path_steps == 10  # 3+3+4

    def test_no_dependencies(self):
        """无依赖 → 关键路径 = 最大 steps 的单节点。"""
        sqs = [self._sq(1, 2), self._sq(2, 5), self._sq(3, 3)]
        path_nodes, path_steps = self.find(sqs, [])
        assert len(path_nodes) == 1
        assert path_nodes[0]["id"] == 2
        assert path_steps == 5

    def test_weak_deps_ignored(self):
        """weak 依赖不构成路径。"""
        sqs = [self._sq(1, 3), self._sq(2, 4), self._sq(3, 5)]
        deps = [self._dep(1, 2, "weak"), self._dep(2, 3, "weak")]
        path_nodes, path_steps = self.find(sqs, deps)
        assert len(path_nodes) == 1  # 退化为单节点
        assert path_nodes[0]["id"] == 3  # 最大 steps

    def test_partial_strong(self):
        """1→2(strong), 2→3(weak) → 关键路径 = [1,2]。"""
        sqs = [self._sq(1, 3), self._sq(2, 4), self._sq(3, 5)]
        deps = [self._dep(1, 2, "strong"), self._dep(2, 3, "weak")]
        path_nodes, path_steps = self.find(sqs, deps)
        path_ids = [n["id"] for n in path_nodes]
        assert path_ids == [1, 2]
        assert path_steps == 7

    def test_diamond_dag(self):
        """菱形: 1→2, 1→3, 2→4, 3→4 → 选最长路径。"""
        sqs = [self._sq(1, 2), self._sq(2, 5), self._sq(3, 3), self._sq(4, 2)]
        deps = [self._dep(1, 2), self._dep(1, 3), self._dep(2, 4), self._dep(3, 4)]
        path_nodes, path_steps = self.find(sqs, deps)
        path_ids = [n["id"] for n in path_nodes]
        assert path_ids == [1, 2, 4]  # 2+5+2=9 > 2+3+2=7
        assert path_steps == 9

    def test_single_subquestion(self):
        """单小问 → 路径就是它自己。"""
        sqs = [self._sq(1, 4)]
        path_nodes, path_steps = self.find(sqs, [])
        assert len(path_nodes) == 1
        assert path_steps == 4


class TestAggregation:
    """aggregate_big_question 特征聚合测试。"""

    def setup_method(self):
        from rule_scorer import aggregate_big_question
        self.aggregate = aggregate_big_question

    def _sq(self, id, steps, points=4, wm=3, trap=2, novelty=2, breadth=2):
        return {"id": id, "points": points, "working_memory": wm,
                "reasoning_steps": steps, "trap_density": trap,
                "novelty": novelty, "knowledge_breadth": breadth}

    def _dep(self, fr, to, strength="strong"):
        return {"from": fr, "to": to, "strength": strength}

    def test_q21_aggregation(self):
        """Q21 验算：设计文档 §5 端到端。"""
        sqs = [
            self._sq(1, 3, points=4, wm=3, trap=1, novelty=2, breadth=2),
            self._sq(2, 3, points=4, wm=4, trap=2, novelty=2, breadth=2),
            self._sq(3, 4, points=6, wm=4, trap=3, novelty=3, breadth=2),
        ]
        deps = [
            self._dep(1, 2, "weak"),
            self._dep(2, 3, "strong"),
        ]
        global_features = {"shared_context_load": 2, "global_method_novelty": 3}
        result = self.aggregate(sqs, deps, global_features)

        # effective_steps: critical_path=[2,3], steps=3+4=7, total=10, eff=7+0.35*3=8.05
        assert abs(result["effective_steps"] - 8.05) < 0.01
        # wm: max(4,4)=4, path_len=2, ctx=2 → 4+0.4+0.6=5.0
        assert result["working_memory"] == 5
        # trap: max on path = max(2,3) = 3
        assert result["trap_density"] == 3
        # novelty: max(3, weighted_avg) = 3
        assert result["novelty"] == 3
        # breadth: max(2,2,2) = 2
        assert result["knowledge_breadth"] == 2
        # chain_coupling: path_points=10, total=14, share=0.71 → 3
        assert result["chain_coupling"] == 3

    def test_parallel_subquestions(self):
        """全并列小问（无 strong 依赖）→ effective_steps 低于总和。"""
        sqs = [self._sq(1, 3), self._sq(2, 3), self._sq(3, 3)]
        global_features = {"shared_context_load": 1, "global_method_novelty": 1}
        result = self.aggregate(sqs, [], global_features)
        # critical_path = 单节点(3), total=9, eff = 3 + 0.35*6 = 5.1
        assert abs(result["effective_steps"] - 5.1) < 0.01

    def test_single_subquestion_passthrough(self):
        """单小问 → 特征原样传递（无聚合变换效果）。"""
        sqs = [self._sq(1, 5, wm=4, trap=2, novelty=2, breadth=3)]
        global_features = {"shared_context_load": 1, "global_method_novelty": 1}
        result = self.aggregate(sqs, [], global_features)
        assert result["working_memory"] == 4
        assert abs(result["effective_steps"] - 5.0) < 0.01
        assert result["trap_density"] == 2
        assert result["novelty"] == 2
        assert result["knowledge_breadth"] == 3

    def test_wm_clamped_to_5(self):
        """wm 聚合结果不超过 5。"""
        sqs = [
            self._sq(1, 3, wm=5, trap=1, novelty=1, breadth=1),
            self._sq(2, 3, wm=5, trap=1, novelty=1, breadth=1),
            self._sq(3, 3, wm=5, trap=1, novelty=1, breadth=1),
        ]
        deps = [self._dep(1, 2), self._dep(2, 3)]
        global_features = {"shared_context_load": 3, "global_method_novelty": 1}
        result = self.aggregate(sqs, deps, global_features)
        assert result["working_memory"] == 5  # clamped
```

- [ ] **Step 2: 运行测试确认失败**

Run: `docker-compose exec -T backend python -m pytest test_core_modules.py::TestCriticalPath test_core_modules.py::TestAggregation -v`
Expected: FAIL with "cannot import name 'find_critical_path'" / "cannot import name 'aggregate_big_question'"

- [ ] **Step 3: 实现 find_critical_path 和 aggregate_big_question**

在 `backend/rule_scorer.py` 文件末尾（`score_to_label` 之后）追加：

```python
# ── 大题结构化聚合 v3.1 ────────────────────────────────────────

def find_critical_path(subquestions: list, dependencies: list) -> tuple:
    """找到 strong 依赖构成的加权最长路径。

    Args:
        subquestions: [{"id": int, "reasoning_steps": int, ...}, ...]
        dependencies: [{"from": int, "to": int, "strength": "strong"|"weak"}, ...]

    Returns:
        (path_nodes: list[dict], path_steps: int)
        path_nodes 按路径顺序排列。无 strong 依赖时返回 steps 最大的单节点。
    """
    sq_map = {sq["id"]: sq for sq in subquestions}
    ids = [sq["id"] for sq in subquestions]

    # 只保留 strong 依赖
    strong_edges = [(d["from"], d["to"]) for d in dependencies if d.get("strength") == "strong"]
    if not strong_edges:
        best = max(subquestions, key=lambda s: s["reasoning_steps"])
        return [best], best["reasoning_steps"]

    # 构建邻接表 + 入度
    adj = {i: [] for i in ids}
    in_degree = {i: 0 for i in ids}
    for fr, to in strong_edges:
        if fr in adj and to in adj:
            adj[fr].append(to)
            in_degree[to] += 1

    # 拓扑排序
    from collections import deque
    queue = deque(i for i in ids if in_degree[i] == 0)
    topo_order = []
    while queue:
        node = queue.popleft()
        topo_order.append(node)
        for nxt in adj[node]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    # DP 最长路径（权重 = reasoning_steps）
    dist = {i: sq_map[i]["reasoning_steps"] for i in ids}
    prev = {i: None for i in ids}
    for node in topo_order:
        for nxt in adj[node]:
            new_dist = dist[node] + sq_map[nxt]["reasoning_steps"]
            if new_dist > dist[nxt]:
                dist[nxt] = new_dist
                prev[nxt] = node

    # 回溯最长路径
    end_node = max(ids, key=lambda i: dist[i])
    path_ids = []
    cur = end_node
    while cur is not None:
        path_ids.append(cur)
        cur = prev[cur]
    path_ids.reverse()

    path_nodes = [sq_map[i] for i in path_ids]
    path_steps = sum(sq_map[i]["reasoning_steps"] for i in path_ids)
    return path_nodes, path_steps


def aggregate_big_question(subquestions: list, dependencies: list,
                           global_features: dict) -> dict:
    """将结构化大题特征聚合为标准 v3 特征向量。

    设计文档: docs/plans/2026-03-28-difficulty-v3.1-design.md §4

    Returns:
        dict: 包含 effective_steps, working_memory, trap_density, novelty,
              knowledge_breadth, chain_coupling（向后兼容）
    """
    path_nodes, critical_path_steps = find_critical_path(subquestions, dependencies)
    total_steps = sum(sq["reasoning_steps"] for sq in subquestions)
    off_path = total_steps - critical_path_steps

    # §4.2 effective_steps
    effective_steps = critical_path_steps + 0.35 * off_path

    # §4.3 working_memory（峰值 + 跨问保持）
    path_wm = [sq["working_memory"] for sq in path_nodes]
    path_length = len(path_nodes)
    shared_ctx = global_features.get("shared_context_load", 1)
    wm_raw = max(path_wm) + 0.4 * (path_length - 1) + 0.3 * shared_ctx
    wm = min(5, max(1, round(wm_raw)))

    # §4.4 novelty（方法新颖度增强）
    total_points = sum(sq["points"] for sq in subquestions)
    weighted_novelty = sum(sq["novelty"] * sq["points"] for sq in subquestions) / total_points if total_points > 0 else 2
    method_novelty = global_features.get("global_method_novelty", 1)
    novelty = max(method_novelty, round(weighted_novelty))

    # §4.5 trap_density（关键路径最大值）
    trap = max(sq["trap_density"] for sq in path_nodes)

    # §4.6 knowledge_breadth（全局最大值）
    breadth = max(sq["knowledge_breadth"] for sq in subquestions)

    # §4.7 chain_coupling 回写（向后兼容）
    path_points = sum(sq["points"] for sq in path_nodes)
    score_share = path_points / total_points if total_points > 0 else 0
    if score_share < 0.35:
        chain_coupling = 1
    elif score_share <= 0.70:
        chain_coupling = 2
    else:
        chain_coupling = 3

    return {
        "effective_steps": round(effective_steps, 2),
        "working_memory": wm,
        "trap_density": trap,
        "novelty": novelty,
        "knowledge_breadth": breadth,
        "chain_coupling": chain_coupling,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `docker-compose exec -T backend python -m pytest test_core_modules.py::TestCriticalPath test_core_modules.py::TestAggregation -v`
Expected: 11 tests PASS

- [ ] **Step 5: 提交**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add backend/rule_scorer.py backend/test_core_modules.py
git commit -m "feat: v3.1 关键路径算法 + 特征聚合规则

find_critical_path: DAG 最长路径（仅 strong 依赖）
aggregate_big_question: 特征层聚合（effective_steps/wm/trap/novelty/breadth）
11 个新测试覆盖线性链/菱形/并列/单节点/Q21 验算

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

**审查清单:**
- ✓ `find_critical_path` 仅用 strong 依赖构建图
- ✓ 无 strong 依赖时退化为单节点（最大 steps）
- ✓ `aggregate_big_question` 返回的 wm 被 clamp 到 [1,5]
- ✗ 如果 subquestions 为空列表 → 应抛异常而非崩溃
- ✓ Q21 端到端验算结果与设计文档 §5 一致
- ✗ 如果 effective_steps 计算错误，Q19 偏高问题不会被修正

---

### Task 2: 大题专用 Prompt + 结构化 JSON 解析（feature_extractor.py）

**Files:**
- Modify: `backend/feature_extractor.py:236-268`（在 `extract_features` 之后追加）
- Test: `backend/test_feature_difficulty.py`（在文件末尾追加新 class）

**测试契约:**
1. 结构化 JSON 正确解析
   - 入口: `parse_big_question_features(valid_json_string)`
   - 反例: 错误实现可能不校验 subquestions 中的字段范围——越界值会传入聚合层导致异常
   - 边界: 空 subquestions / 缺失 dependencies / 缺失 global_features / 截断 JSON
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestParseBigQuestion -v`

2. 大题 prompt 包含结构化输出指令
   - 入口: `build_big_question_prompt(question_text, ...)`
   - 反例: 错误实现可能遗漏 dependencies 或 global_features 的输出指令——LLM 不会输出未要求的字段
   - 边界: 无选项 / 无答案
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestBuildBigQuestionPrompt -v`

**边界条件:**
- subquestions 为空数组 → 返回 None（fallback 信号）
- dependencies 缺失 → 视为无依赖（全并列）
- global_features 缺失 → 用默认值 {shared_context_load: 1, global_method_novelty: 1}
- 截断 JSON → 尝试修复，失败返回 None

- [ ] **Step 1: 写解析器的失败测试**

在 `backend/test_feature_difficulty.py` 文件末尾追加：

```python
class TestParseBigQuestion:
    """大题结构化 JSON 解析测试。"""

    def setup_method(self):
        from feature_extractor import parse_big_question_features
        self.parse = parse_big_question_features

    def _valid_input(self):
        return json.dumps({
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2, "brief": "基础"},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "分析"},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "strong", "reason": "依赖前问结论"}
            ],
            "global_features": {
                "shared_context_load": 2, "global_method_novelty": 3,
            },
            "bloom": 4, "bloom_reason": "分析",
            "info_density": 2, "representation_complexity": 2,
            "quality_score": 4,
            "quality_scientific": "准确",
            "quality_normative": "规范",
            "quality_language": "清晰",
            "quality_context": "合理",
            "quality_sensitivity": "无风险",
            "teacher_comment": "考查能力综合。",
        })

    def test_valid_parse(self):
        result = self.parse(self._valid_input())
        assert result is not None
        assert len(result["subquestions"]) == 2
        assert result["subquestions"][0]["working_memory"] == 3
        assert len(result["dependencies"]) == 1
        assert result["global_features"]["global_method_novelty"] == 3
        assert result["report"]["bloom"] == 4

    def test_subquestion_range_clipped(self):
        """小问特征越界被裁剪。"""
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 10, "reasoning_steps": 0,
                 "trap_density": 5, "novelty": -1, "knowledge_breadth": 99, "brief": "x"},
            ],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        result = self.parse(raw)
        sq = result["subquestions"][0]
        assert sq["working_memory"] == 5
        assert sq["reasoning_steps"] == 1
        assert sq["trap_density"] == 3
        assert sq["novelty"] == 1
        assert sq["knowledge_breadth"] == 3

    def test_empty_subquestions_returns_none(self):
        """空 subquestions → 返回 None（触发 fallback）。"""
        raw = json.dumps({
            "subquestions": [],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        assert self.parse(raw) is None

    def test_missing_dependencies_defaults_empty(self):
        """缺失 dependencies → 视为空。"""
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 6, "working_memory": 3, "reasoning_steps": 4,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
            ],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "bloom": 3,
        })
        result = self.parse(raw)
        assert result["dependencies"] == []

    def test_missing_global_features_defaults(self):
        """缺失 global_features → 用默认值。"""
        raw = json.dumps({
            "subquestions": [
                {"id": 1, "points": 6, "working_memory": 3, "reasoning_steps": 4,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2, "brief": "x"},
            ],
            "dependencies": [],
            "bloom": 3,
        })
        result = self.parse(raw)
        assert result["global_features"]["shared_context_load"] == 1
        assert result["global_features"]["global_method_novelty"] == 1

    def test_unparseable_returns_none(self):
        """不可解析文本 → 返回 None。"""
        assert self.parse("这是一道很难的题") is None

    def test_report_fields_preserved(self):
        """报告字段（bloom/quality/teacher_comment）正确保留。"""
        result = self.parse(self._valid_input())
        assert "bloom" in result["report"]
        assert "quality_scientific" in result["report"]
        assert "teacher_comment" in result["report"]


class TestBuildBigQuestionPrompt:
    """大题专用 prompt 构建测试。"""

    def setup_method(self):
        from feature_extractor import build_big_question_prompt
        self.build = build_big_question_prompt

    def test_contains_subquestions_instruction(self):
        prompt = self.build("某大题内容", question_type="实验题")
        assert "subquestions" in prompt
        assert "dependencies" in prompt
        assert "global_features" in prompt
        assert "shared_context_load" in prompt
        assert "global_method_novelty" in prompt

    def test_contains_strength_values(self):
        prompt = self.build("某大题内容")
        assert "weak" in prompt
        assert "strong" in prompt

    def test_contains_question_text(self):
        prompt = self.build("番茄红素PSY融合蛋白实验", correct_answer="见解析")
        assert "番茄红素PSY融合蛋白实验" in prompt
        assert "见解析" in prompt
```

- [ ] **Step 2: 运行测试确认失败**

Run: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestParseBigQuestion test_feature_difficulty.py::TestBuildBigQuestionPrompt -v`
Expected: FAIL with "cannot import name"

- [ ] **Step 3: 实现 build_big_question_prompt 和 parse_big_question_features**

在 `backend/feature_extractor.py` 文件末尾（`extract_features` 函数之后）追加。完整代码见设计文档附录。核心要点：

`build_big_question_prompt`: 与 `build_feature_prompt` 结构类似，但要求 LLM 输出 `subquestions[]` + `dependencies[]` + `global_features{}`。包含 strength 判定规则（strong=前错后错，weak=辅助理解）和 global_method_novelty 判例。

`parse_big_question_features`: 三层 JSON 解析策略（直接/code block/嵌套提取）。subquestions 中每个字段裁剪到 `_SQ_RANGES` 范围。空 subquestions 返回 None。dependencies 过滤无效 id 和非法 strength。global_features 缺失用默认值。报告字段复用 v3 的 `REPORT_RANGES`/`_REASON_KEYS`/`_QUALITY_KEYS`。

`extract_big_question_features`: 异步 LLM 调用封装，max_tokens=2000，失败返回 None。

```python
def build_big_question_prompt(question_text: str, options: str = "",
                              correct_answer: str = "",
                              question_type: str = "") -> str:
    """构建大题结构化特征提取 prompt（v3.1）。"""
    parts = [question_text]
    if options:
        parts.append(f"选项：{options}")
    if correct_answer:
        parts.append(f"正确答案/参考答案：{correct_answer}")
    question_block = "\n".join(parts)
    qtype_hint = f"\n题型：{question_type}" if question_type else ""

    return f"""你是一名资深高中生物命题审查专家。这是一道非选择题（大题），请按小问拆分分析。

题目：
{question_block}{qtype_hint}

请输出严格 JSON（不要多余解释），格式如下：
{{
  "subquestions": [
    {{
      "id": 1,
      "points": 该小问分值(整数),
      "working_memory": 1-5（该小问解题时需同时在脑中保持的信息元素数），
      "reasoning_steps": 正整数（该小问最少认知操作数），
      "trap_density": 1-3（看似正确但实际错误的推理路径数），
      "novelty": 1-3（知识/方法新颖度），
      "knowledge_breadth": 1-3（跨知识模块程度），
      "brief": "核心任务(<=20字)"
    }}
  ],
  "dependencies": [
    {{
      "from": 源小问id,
      "to": 目标小问id,
      "strength": "weak"或"strong",
      "reason": "依赖内容(<=30字)"
    }}
  ],
  "global_features": {{
    "shared_context_load": 1-3（跨问保持负担。1=各问独立 2=共享背景 3=围绕复杂系统），
    "shared_context_reason": "<=20字",
    "global_method_novelty": 1-3（教材外方法。1=全教材内 2=部分外 3=核心方法外），
    "method_novelty_reason": "<=20字"
  }},
  "bloom": 1-6, "bloom_distribution": {{}}, "bloom_reason": "<=30字",
  "info_density": 1-3, "density_reason": "<=20字",
  "representation_complexity": 1-3, "representation_reason": "<=20字",
  "quality_score": 1-5,
  "quality_scientific": "<=60字", "quality_normative": "<=60字",
  "quality_language": "<=60字", "quality_context": "<=60字",
  "quality_sensitivity": "<=60字", "teacher_comment": "<=150字"
}}

**dependencies 判定规则（关键！）：**
- "strong"：前一问的结论/产物是后一问的前提。不知道前问答案就无法做后问。
- "weak"：前一问的背景知识有助于后问理解，但不知道前问答案也能部分作答
- 无关的小问之间不加 dependency

**global_method_novelty 判例：**
- 1：所有方法在高中教材中有明确介绍
- 2：部分方法需要迁移应用
- 3：核心方法在教材中完全没有（如 In-Fusion 克隆、CRISPR）
"""


_SQ_RANGES = {
    "working_memory": (1, 5),
    "reasoning_steps": (1, 10),
    "trap_density": (1, 3),
    "novelty": (1, 3),
    "knowledge_breadth": (1, 3),
}


def parse_big_question_features(raw: str) -> dict | None:
    """解析大题结构化 JSON。返回 None 表示解析失败（触发 fallback）。"""
    if not isinstance(raw, str):
        return None

    data = None
    try:
        data = json.loads(raw.strip())
    except (json.JSONDecodeError, TypeError):
        pass
    if data is None:
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    if data is None:
        depth = 0
        start = raw.find('{')
        if start >= 0:
            for i in range(start, len(raw)):
                if raw[i] == '{': depth += 1
                elif raw[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try: data = json.loads(raw[start:i+1])
                        except json.JSONDecodeError: pass
                        break
    if not isinstance(data, dict):
        logger.warning(f"[大题解析] JSON 解析失败，原始长度={len(raw)}")
        return None

    sqs_raw = data.get("subquestions", [])
    if not isinstance(sqs_raw, list) or len(sqs_raw) == 0:
        logger.warning("[大题解析] subquestions 缺失或为空")
        return None

    subquestions = []
    for sq in sqs_raw:
        if not isinstance(sq, dict): continue
        cleaned = {"id": sq.get("id", len(subquestions) + 1),
                    "points": max(1, int(sq.get("points", 2))),
                    "brief": str(sq.get("brief", ""))[:20]}
        for key, (lo, hi) in _SQ_RANGES.items():
            val = sq.get(key, 2)
            try: val = int(val)
            except (ValueError, TypeError): val = 2
            cleaned[key] = max(lo, min(hi, val))
        subquestions.append(cleaned)
    if not subquestions: return None

    deps_raw = data.get("dependencies", [])
    dependencies = []
    valid_ids = {sq["id"] for sq in subquestions}
    if isinstance(deps_raw, list):
        for dep in deps_raw:
            if not isinstance(dep, dict): continue
            fr, to = dep.get("from"), dep.get("to")
            strength = dep.get("strength", "weak")
            if fr in valid_ids and to in valid_ids and strength in ("weak", "strong"):
                dependencies.append({"from": fr, "to": to, "strength": strength,
                                     "reason": str(dep.get("reason", ""))[:30]})

    gf_raw = data.get("global_features", {})
    if isinstance(gf_raw, dict):
        try: scl = max(1, min(3, int(gf_raw.get("shared_context_load", 1))))
        except (ValueError, TypeError): scl = 1
        try: gmn = max(1, min(3, int(gf_raw.get("global_method_novelty", 1))))
        except (ValueError, TypeError): gmn = 1
    else: scl, gmn = 1, 1
    global_features = {"shared_context_load": scl, "global_method_novelty": gmn}

    report = {}
    for key in ["bloom", "info_density", "representation_complexity"]:
        val = data.get(key)
        if val is not None:
            lo, hi = REPORT_RANGES.get(key, (1, 6))
            try: report[key] = max(lo, min(hi, int(val)))
            except (ValueError, TypeError): pass
    for reason_key in _REASON_KEYS:
        if reason_key in data: report[reason_key] = str(data[reason_key])[:50]
    bloom_dist = data.get("bloom_distribution")
    if isinstance(bloom_dist, dict):
        cleaned_bd = {}
        for label, count in bloom_dist.items():
            if label in _BLOOM_LABELS:
                try: cleaned_bd[label] = max(0, int(count))
                except (ValueError, TypeError): pass
        if sum(cleaned_bd.values()) > 0: report["bloom_distribution"] = cleaned_bd
    qs = data.get("quality_score")
    if qs is not None:
        try: report["quality_score"] = max(1, min(5, int(qs)))
        except (ValueError, TypeError): pass
    for qkey in _QUALITY_KEYS:
        if qkey in data:
            limit = 200 if qkey == "teacher_comment" else 80
            report[qkey] = str(data[qkey])[:limit]

    return {"subquestions": subquestions, "dependencies": dependencies,
            "global_features": global_features, "report": report}


async def extract_big_question_features(question_text: str, options: str = "",
                                        correct_answer: str = "",
                                        question_type: str = "") -> dict | None:
    """调用 LLM 提取大题结构化特征。返回 None 表示失败。"""
    prompt = build_big_question_prompt(question_text, options, correct_answer, question_type)
    try:
        raw = await send_message_gpt(prompt, max_tokens=2000, temperature=0)
        result = parse_big_question_features(raw)
        if result is None:
            logger.warning(f"[大题提取] 结构化解析失败，原始长度={len(raw)}")
        else:
            logger.info(f"[大题提取] 成功: {len(result['subquestions'])}小问, "
                        f"{len(result['dependencies'])}依赖")
        return result
    except Exception as e:
        logger.error(f"[大题提取] API 调用失败: {e}")
        return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestParseBigQuestion test_feature_difficulty.py::TestBuildBigQuestionPrompt -v`
Expected: 11 tests PASS

- [ ] **Step 5: 提交**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add backend/feature_extractor.py backend/test_feature_difficulty.py
git commit -m "feat: v3.1 大题专用 prompt + 结构化 JSON 解析

build_big_question_prompt: 按小问拆分+依赖图+全局特征
parse_big_question_features: 容错解析+范围裁剪+fallback None
extract_big_question_features: 异步 LLM 调用封装
11 个新测试

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

**审查清单:**
- ✓ prompt 包含 subquestions/dependencies/global_features 三段输出指令
- ✓ strength 只接受 "weak" 和 "strong" 两个值
- ✓ 空 subquestions 返回 None（fallback 信号）
- ✗ 如果 parse 错误地接受了非法 strength 值，依赖图会包含无效边
- ✓ 报告字段（bloom/quality/teacher_comment）与 v3 parse_features 一致

---

### Task 3: Pipeline 题型分流 + Fallback（difficulty_pipeline.py）

**Files:**
- Modify: `backend/difficulty_pipeline.py:1-90`（import 区 + `_evaluate_single` 方法）
- Test: `backend/test_feature_difficulty.py`（追加集成测试）

**测试契约:**
1. 大题路由到结构化路径
   - 入口: `pipeline.evaluate_with_refinement({"content": "...", "total_score": 12, ...})`
   - 反例: 错误实现可能忽略 total_score 判断——大题仍走 v3 原路径
   - 边界: total_score=8（边界值）/ total_score=7（不触发）
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestBigQuestionPipeline -v`

2. 结构化解析失败时 fallback 到 v3
   - 入口: `pipeline.evaluate_with_refinement(...)` 且 LLM 返回无法解析的文本
   - 反例: 错误实现可能在解析失败时崩溃而非 fallback
   - 边界: None 返回
   - 回归: N/A
   - 命令: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestBigQuestionPipeline::test_fallback_on_parse_failure -v`

**边界条件:**
- total_score=8 → 触发大题路径（≥8）
- total_score=7 → 走 v3 原路径（<8）
- 结构化解析返回 None → fallback 到 v3 原路径，标记 big_question_fallback

- [ ] **Step 1: 写 Pipeline 分流的失败测试**

在 `backend/test_feature_difficulty.py` 文件末尾追加：

```python
class TestBigQuestionPipeline:
    """大题 pipeline 分流 + fallback 测试。"""

    def _q21_structured_features(self):
        return {
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
                {"id": 3, "points": 6, "working_memory": 4, "reasoning_steps": 4,
                 "trap_density": 3, "novelty": 3, "knowledge_breadth": 2},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "weak", "reason": "背景知识"},
                {"from": 2, "to": 3, "strength": "strong", "reason": "改造方案"},
            ],
            "global_features": {"shared_context_load": 2, "global_method_novelty": 3},
            "report": {"bloom": 5, "info_density": 3, "representation_complexity": 2,
                       "quality_score": 4, "teacher_comment": "综合实验题"},
        }

    def test_big_question_routes_to_structured(self):
        """total_score >= 8 → 走大题结构化路径。"""
        structured = self._q21_structured_features()
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "番茄红素PSY融合蛋白...",
                    "question_type": "实验题",
                    "correct_answer": "见解析",
                    "total_score": 14,
                })
            )
        assert result["final_difficulty"] >= 9.0, f"Q21 应 >=9.0，实际 {result['final_difficulty']}"
        assert "big_question_fallback" not in (result.get("flags") or [])

    def test_small_question_uses_v3(self):
        """total_score < 8 → 走 v3 原路径。"""
        mock_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 1,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
        }
        with patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "下列关于DNA...", "question_type": "选择题",
                    "correct_answer": "A", "total_score": 2,
                })
            )
        assert result["features"] is not None
        assert "big_question_fallback" not in (result.get("flags") or [])

    def test_boundary_score_8_triggers_big(self):
        """total_score = 8 → 触发大题路径。"""
        structured = self._q21_structured_features()
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题...", "question_type": "简答题",
                    "correct_answer": "", "total_score": 8,
                })
            )
        assert result["features"] is not None

    def test_boundary_score_7_stays_v3(self):
        """total_score = 7 → 不触发大题路径。"""
        mock_features = {
            "working_memory": 3, "reasoning_steps": 4, "chain_coupling": 2,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 3, "info_density": 2, "representation_complexity": 1,
        }
        with patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_features):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某题...", "question_type": "简答题",
                    "correct_answer": "", "total_score": 7,
                })
            )
        assert result["features"] is not None

    def test_fallback_on_parse_failure(self):
        """结构化解析失败 → fallback 到 v3 原路径。"""
        mock_flat = {
            "working_memory": 4, "reasoning_steps": 6, "chain_coupling": 2,
            "trap_density": 2, "novelty": 2, "knowledge_breadth": 2,
            "bloom": 4, "info_density": 2, "representation_complexity": 1,
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=None), \
             patch("difficulty_pipeline.extract_features",
                   new_callable=AsyncMock, return_value=mock_flat):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "某大题...", "question_type": "实验题",
                    "correct_answer": "", "total_score": 12,
                })
            )
        assert result["features"] is not None
        assert "big_question_fallback" in result.get("flags", [])
        assert result["confidence"] < 0.7
```

- [ ] **Step 2: 运行测试确认失败**

Run: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestBigQuestionPipeline -v`
Expected: FAIL

- [ ] **Step 3: 修改 difficulty_pipeline.py 实现分流**

修改 `backend/difficulty_pipeline.py` import 区，将：
```python
from feature_extractor import extract_features, DEFAULT_FEATURES
from rule_scorer import compute_difficulty, score_to_label
```
改为：
```python
from feature_extractor import extract_features, extract_big_question_features, DEFAULT_FEATURES
from rule_scorer import compute_difficulty, score_to_label, aggregate_big_question
```

替换 `_evaluate_single` 方法（第 21-90 行）：

```python
    async def _evaluate_single(self, question: dict, **kwargs) -> dict:
        question_text = question.get("content", "")
        correct_answer = question.get("correct_answer", "")
        total_score = float(question.get("total_score", 1))
        options = question.get("options", "")
        question_type = question.get("question_type", "")

        if not question_text:
            logger.warning("题目内容为空，跳过难度评估")
            return self._default_result()

        options_text = ""
        if isinstance(options, dict):
            options_text = " ".join(f"{k}.{v}" for k, v in sorted(options.items()))
        elif isinstance(options, list):
            options_text = " ".join(str(o) for o in options)
        elif isinstance(options, str) and options:
            options_text = options

        full_text = question_text
        if options_text:
            full_text = f"{question_text}\n{options_text}"

        # ── v3.1 大题分流 ──
        is_big_question = total_score >= 8
        big_question_fallback = False

        if is_big_question:
            logger.info(f"[v3.1] 大题模式 (total_score={total_score}): {question_text[:50]}...")
            structured = await extract_big_question_features(
                full_text, "", correct_answer, question_type)

            if structured is not None:
                aggregated = aggregate_big_question(
                    structured["subquestions"],
                    structured["dependencies"],
                    structured["global_features"],
                )
                features = {
                    "working_memory": aggregated["working_memory"],
                    "reasoning_steps": round(aggregated["effective_steps"]),
                    "chain_coupling": aggregated["chain_coupling"],
                    "trap_density": aggregated["trap_density"],
                    "novelty": aggregated["novelty"],
                    "knowledge_breadth": aggregated["knowledge_breadth"],
                }
                features.update(structured.get("report", {}))
                features["_big_question"] = {
                    "subquestions": structured["subquestions"],
                    "dependencies": structured["dependencies"],
                    "global_features": structured["global_features"],
                    "effective_steps": aggregated["effective_steps"],
                }
            else:
                big_question_fallback = True
                logger.warning("[v3.1] 结构化解析失败，fallback 到 v3 原路径")

        if not is_big_question or big_question_fallback:
            logger.info(f"开始特征提取: {question_text[:50]}...")
            features = await extract_features(full_text, "", correct_answer, question_type)
            logger.info(f"特征提取完成: {features}")

        # Stage 2.5: 合并 Gemini representation
        flags = []
        if big_question_fallback:
            flags.append("big_question_fallback")
        analysis_result = kwargs.get("analysis_result") or {}
        features, flags = self._merge_representation(features, analysis_result, flags)

        # Stage 3: 规则评分
        if is_big_question and not big_question_fallback:
            score_features = dict(features)
            score_features["reasoning_steps"] = features["_big_question"]["effective_steps"]
            score_features["chain_coupling"] = 1  # 不让 coupling 再乘一次
            raw_score = compute_difficulty(score_features)
        else:
            raw_score = compute_difficulty(features)

        from calibration import calibrate
        score = calibrate(raw_score)
        label = score_to_label(score)
        logger.info(f"规则评分: raw={raw_score} calibrated={score} ({label})"
                    + (" [v3.1 大题]" if is_big_question and not big_question_fallback else ""))

        confidence = self._compute_confidence(features, flags)
        if big_question_fallback:
            confidence = max(0.2, confidence - 0.15)

        bloom = features.get("bloom", 3)
        cognitive_level = round(bloom / 6.0 * 10.0, 1)

        return {
            "base_difficulty": score,
            "final_difficulty": score,
            "difficulty_label": label,
            "cognitive_level": cognitive_level,
            "score_distribution_by_difficulty": self._score_distribution(score, total_score),
            "features": features,
            "raw_score": raw_score,
            "confidence": confidence,
            "predicted_score_rate": None,
            "flags": flags,
        }
```

- [ ] **Step 4: 运行全部测试确认通过**

Run: `docker-compose exec -T backend python -m pytest test_core_modules.py test_feature_difficulty.py -v`
Expected: 所有新旧测试 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add backend/difficulty_pipeline.py backend/test_feature_difficulty.py
git commit -m "feat: v3.1 Pipeline 大题分流 + fallback

total_score>=8 走结构化提取+聚合，否则 v3 原路径
解析失败自动 fallback + confidence 扣减
6 个新测试覆盖分流/边界/fallback

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

**审查清单:**
- ✓ total_score >= 8 触发大题路径
- ✓ 大题评分用 effective_steps 且 chain_coupling=1（避免双重计算）
- ✓ fallback 时标记 big_question_fallback 且降低 confidence
- ✗ 如果忘记设 chain_coupling=1，大题评分会被 coupling 再乘一次
- ✓ 原有选择题测试全部不受影响

---

### Task 4: 端到端验证 + CLAUDE.md 更新

**Files:**
- Modify: `backend/test_feature_difficulty.py`（追加端到端验证测试）
- Modify: `/home/ubuntu/biology-exam-analyzer/CLAUDE.md`（更新项目描述）

**测试契约:**
1. Q21 端到端评分 >= 9.0
   - 入口: `pipeline.evaluate_with_refinement(Q21_question)`
   - 反例: 聚合规则有 bug 会导致评分仍在 8.x——本测试捕获此情况
   - 边界: N/A（端到端验证）
   - 回归: 修复 Q21 低估（v3: 8.2 → v3.1: >=9.0）
   - 命令: `docker-compose exec -T backend python -m pytest test_feature_difficulty.py::TestQ21EndToEnd -v`

- [ ] **Step 1: 写 Q21 端到端验证测试**

在 `backend/test_feature_difficulty.py` 文件末尾追加：

```python
class TestQ21EndToEnd:
    """Q21 端到端验证：v3.1 修正低估。"""

    def test_q21_score_at_least_9(self):
        """Q21（14分番茄红素 PSY 融合蛋白）评分应 >= 9.0。"""
        structured = {
            "subquestions": [
                {"id": 1, "points": 4, "working_memory": 3, "reasoning_steps": 3,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 4, "working_memory": 4, "reasoning_steps": 3,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
                {"id": 3, "points": 6, "working_memory": 4, "reasoning_steps": 4,
                 "trap_density": 3, "novelty": 3, "knowledge_breadth": 2},
            ],
            "dependencies": [
                {"from": 1, "to": 2, "strength": "weak", "reason": "背景知识"},
                {"from": 2, "to": 3, "strength": "strong", "reason": "改造方案"},
            ],
            "global_features": {"shared_context_load": 2, "global_method_novelty": 3},
            "report": {"bloom": 5, "info_density": 3, "representation_complexity": 2},
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "番茄红素PSY融合蛋白实验...",
                    "question_type": "实验题",
                    "correct_answer": "见解析",
                    "total_score": 14,
                })
            )
        score = result["final_difficulty"]
        assert score >= 9.0, f"Q21 v3.1 应 >=9.0（修正 v3 的 8.2），实际 {score}"
        assert score <= 10.0
        assert "_big_question" in result["features"]
        assert len(result["features"]["_big_question"]["subquestions"]) == 3

    def test_parallel_big_question_not_overscored(self):
        """并列大题不应被过度提升。"""
        structured = {
            "subquestions": [
                {"id": 1, "points": 3, "working_memory": 3, "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 2, "points": 3, "working_memory": 3, "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 3, "points": 3, "working_memory": 3, "reasoning_steps": 2,
                 "trap_density": 1, "novelty": 2, "knowledge_breadth": 2},
                {"id": 4, "points": 3, "working_memory": 3, "reasoning_steps": 2,
                 "trap_density": 2, "novelty": 2, "knowledge_breadth": 2},
            ],
            "dependencies": [],
            "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
            "report": {"bloom": 3, "info_density": 2, "representation_complexity": 1},
        }
        with patch("difficulty_pipeline.extract_big_question_features",
                   new_callable=AsyncMock, return_value=structured):
            pipeline = DifficultyPipeline()
            result = asyncio.get_event_loop().run_until_complete(
                pipeline.evaluate_with_refinement({
                    "content": "并列简答题...",
                    "question_type": "简答题",
                    "correct_answer": "",
                    "total_score": 12,
                })
            )
        score = result["final_difficulty"]
        assert score < 7.0, f"全并列简单大题不应超 7.0，实际 {score}"
```

- [ ] **Step 2: 运行全量测试**

Run: `docker-compose exec -T backend python -m pytest test_core_modules.py test_feature_difficulty.py test_llm_client.py -v`
Expected: 所有测试 PASS

- [ ] **Step 3: 更新 CLAUDE.md**

更新 `/home/ubuntu/biology-exam-analyzer/CLAUDE.md` 中 feature_extractor/rule_scorer/difficulty_pipeline 的描述行：

```
│   ├── feature_extractor.py # 特征提取（v3 扁平 + v3.1 大题结构化）
│   ├── rule_scorer.py       # 规则评分 v3 + v3.1 大题聚合（关键路径模型）
│   ├── difficulty_pipeline.py # 难度评估编排（v3.1 大题分流）
```

- [ ] **Step 4: 提交**

```bash
cd /home/ubuntu/biology-exam-analyzer
git add backend/test_feature_difficulty.py CLAUDE.md
git commit -m "test: v3.1 Q21 端到端验证(>=9.0) + 并列大题不过度提升 + CLAUDE.md 更新

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

**审查清单:**
- ✓ Q21 评分 >= 9.0（修正 v3 的 8.2）
- ✓ 并列简单大题 < 7.0（不过度提升）
- ✓ CLAUDE.md 文件描述与代码一致
- ✗ 如果 Q21 测试通过但实际 LLM 输出结构与 mock 不一致，线上效果可能不同
