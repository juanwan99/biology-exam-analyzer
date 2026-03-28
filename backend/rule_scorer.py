"""难度评分引擎 v3 — 难度预测模型（工作记忆 + 推理耦合 + 陷阱密度）。

设计文档: docs/plans/2026-03-28-difficulty-v3-design.md §3
v3 核心变化：bloom 不参与评分，新增 working_memory/chain_coupling/trap_density。
"""

# ── 维度映射（0-1 归一化）────────────────────────────────────────

_WM_MAP = {1: 0.05, 2: 0.15, 3: 0.35, 4: 0.65, 5: 1.00}
_TRAP_MAP = {1: 0.10, 2: 0.45, 3: 0.90}
_NOVELTY_MAP = {1: 0.05, 2: 0.35, 3: 0.85}
_BREADTH_MAP = {1: 0.10, 2: 0.40, 3: 0.85}
_COUPLING_MAP = {1: 1.0, 2: 1.3, 3: 1.6}

# ── 权重 ────────────────────────────────────────────────────────

_WEIGHTS = {
    "working_memory": 0.28,
    "effective_steps": 0.28,
    "trap_density": 0.18,
    "novelty": 0.14,
    "knowledge_breadth": 0.12,
}


def _interpolate(mapping: dict, value: float) -> float:
    keys = sorted(mapping.keys())
    if value <= keys[0]:
        return mapping[keys[0]]
    if value >= keys[-1]:
        return mapping[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= value <= hi:
            ratio = (value - lo) / (hi - lo)
            return mapping[lo] + ratio * (mapping[hi] - mapping[lo])
    return mapping[keys[-1]]


def _interaction_bonus(wm, eff_steps, trap, novelty, breadth) -> float:
    """交互项加分。"""
    bonus = 0.0
    if wm >= 4 and eff_steps >= 8:      # 高负荷 + 长链
        bonus += 0.08
    if trap >= 2 and novelty >= 2:       # 有陷阱 + 不熟悉
        bonus += 0.06
    if breadth >= 3 and wm >= 3:         # 跨模块 + 高负荷
        bonus += 0.04
    return bonus


def compute_difficulty(features: dict) -> float:
    """v3: 特征 → 2-10 难度分。

    评分维度：working_memory, reasoning_steps × chain_coupling, trap_density, novelty, knowledge_breadth
    bloom 不参与评分。
    """
    wm = features.get("working_memory", 3)
    steps = min(features.get("reasoning_steps", 4), 10)
    coupling = features.get("chain_coupling", 2)
    trap = features.get("trap_density", 2)
    novelty = features.get("novelty", 2)
    breadth = features.get("knowledge_breadth", 2)

    # 有效推理链 = 步数 × 耦合系数
    coupling_mult = _COUPLING_MAP.get(coupling, 1.0)
    effective_steps = steps * coupling_mult

    # 各维度归一化
    mapped = {
        "working_memory": _interpolate(_WM_MAP, wm),
        "effective_steps": min(1.0, effective_steps / 12.0),  # 线性 clamp
        "trap_density": _interpolate(_TRAP_MAP, trap),
        "novelty": _interpolate(_NOVELTY_MAP, novelty),
        "knowledge_breadth": _interpolate(_BREADTH_MAP, breadth),
    }

    raw = sum(mapped[k] * _WEIGHTS[k] for k in _WEIGHTS)
    raw += _interaction_bonus(wm, effective_steps, trap, novelty, breadth)

    score = 2.0 + raw * 8.0
    return min(10.0, round(score, 1))


def score_to_label(score: float) -> str:
    if score <= 3.5:
        return "简单"
    elif score <= 5.5:
        return "中等偏易"
    elif score <= 7.5:
        return "中等偏难"
    else:
        return "困难"


# ── 大题结构化聚合 v3.1 ────────────────────────────────────────

def find_critical_path(subquestions: list, dependencies: list) -> tuple:
    """找到 strong 依赖构成的加权最长路径。

    Args:
        subquestions: [{"id": int, "reasoning_steps": int, ...}, ...]
        dependencies: [{"from": int, "to": int, "strength": "strong"|"weak"}, ...]

    Returns:
        (path_nodes: list[dict], path_steps: int)
        path_nodes 按路径顺序排列。无 strong 依赖时��回 steps 最大的单节点。
    """
    sq_map = {sq["id"]: sq for sq in subquestions}
    ids = [sq["id"] for sq in subquestions]

    # 只保留 strong 依赖，过滤自环 (A-001)
    strong_edges = [(d["from"], d["to"]) for d in dependencies
                    if d.get("strength") == "strong" and d["from"] != d["to"]]
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

    # 环检测 (A-001): topo_order 不完整 → 退化单节点
    if len(topo_order) < len(ids):
        best = max(subquestions, key=lambda s: s["reasoning_steps"])
        return [best], best["reasoning_steps"]

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
