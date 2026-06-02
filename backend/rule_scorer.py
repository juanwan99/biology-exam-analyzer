"""难度评分引擎 v3 - 难度预测模型（工作记忆 + 推理耦合 + 陷阱密度）。

设计文档: docs/plans/2026-03-28-difficulty-v3-design.md §3
v3 核心变化：bloom 不参与评分，新增 working_memory/chain_coupling/trap_density。
"""

# ── 维度映射（0-1 归一化）────────────────────────────────────────

_WM_MAP = {1: 0.05, 2: 0.15, 3: 0.35, 4: 0.65, 5: 1.00}
_TRAP_MAP = {1: 0.10, 2: 0.45, 3: 0.90}
_NOVELTY_MAP = {1: 0.05, 2: 0.35, 3: 0.85}
_BREADTH_MAP = {1: 0.10, 2: 0.40, 3: 0.85}
_COUPLING_MAP = {1: 1.0, 2: 1.3, 3: 1.6}
_REPRESENTATION_MAP = {1: 0.05, 2: 0.45, 3: 0.85}
_INFO_DENSITY_MAP = {1: 0.05, 2: 0.35, 3: 0.75}

# ── 权重 ────────────────────────────────────────────────────────

_WEIGHTS = {
    "working_memory": 0.25,
    "effective_steps": 0.24,
    "trap_density": 0.16,
    "novelty": 0.08,
    "knowledge_breadth": 0.09,
    "representation_complexity": 0.10,
    "info_density": 0.08,
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
    if wm >= 4 and eff_steps >= 8:
        bonus += 0.06
    if trap >= 2 and novelty >= 2:
        bonus += 0.04
    if breadth >= 3 and wm >= 3:
        bonus += 0.03
    return bonus


def compute_difficulty(features: dict) -> float:
    """v3: 特征 → 2-10 难度分。

    评分维度：working_memory, reasoning_steps × chain_coupling, trap_density,
    novelty, knowledge_breadth。bloom 不参与评分。
    """
    wm = features.get("working_memory", 3)
    steps = min(features.get("reasoning_steps", 4), 10)
    coupling = features.get("chain_coupling", 2)
    trap = features.get("trap_density", 2)
    novelty = features.get("novelty", 2)
    breadth = features.get("knowledge_breadth", 2)
    representation = features.get("representation_complexity", 1)
    info_density = features.get("info_density", features.get("information_density", 2))

    coupling_mult = _COUPLING_MAP.get(coupling, 1.0)
    effective_steps = steps * coupling_mult

    mapped = {
        "working_memory": _interpolate(_WM_MAP, wm),
        "effective_steps": min(1.0, effective_steps / 12.0),
        "trap_density": _interpolate(_TRAP_MAP, trap),
        "novelty": _interpolate(_NOVELTY_MAP, novelty),
        "knowledge_breadth": _interpolate(_BREADTH_MAP, breadth),
        "representation_complexity": _interpolate(_REPRESENTATION_MAP, representation),
        "info_density": _interpolate(_INFO_DENSITY_MAP, info_density),
    }

    raw = sum(mapped[k] * _WEIGHTS[k] for k in _WEIGHTS)
    raw += _interaction_bonus(wm, effective_steps, trap, novelty, breadth)
    if representation >= 2 and info_density >= 3 and wm >= 3:
        raw += 0.04
    if novelty >= 3 and representation >= 3 and info_density >= 3 and wm >= 4:
        raw += 0.03

    score = 2.0 + raw * 8.0
    return min(10.0, round(score, 1))


def score_to_label(score: float) -> str:
    if score <= 3.5:
        return "简单"
    if score <= 5.5:
        return "中等偏易"
    if score <= 7.5:
        return "中等偏难"
    return "困难"


# ── 大题结构化聚合 v3.1 ────────────────────────────────────────

def _valid_dependency_edges(subquestions: list, dependencies: list) -> list:
    sq_ids = {
        sq.get("id")
        for sq in subquestions
        if isinstance(sq, dict) and "id" in sq
    }
    edges = []
    for dep in dependencies:
        if not isinstance(dep, dict):
            continue
        fr = dep.get("from")
        to = dep.get("to")
        strength = dep.get("strength")
        if (
            fr in sq_ids
            and to in sq_ids
            and fr != to
            and strength in ("weak", "strong")
        ):
            edges.append((fr, to, strength))
    return edges


def _bounded_int(value, low: int, high: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _topological_order(ids: list, edges: list) -> tuple[list, dict]:
    adj = {i: [] for i in ids}
    in_degree = {i: 0 for i in ids}
    for fr, to, strength in edges:
        if fr in adj and to in adj:
            adj[fr].append((to, strength))
            in_degree[to] += 1

    from collections import deque

    queue = deque(i for i in ids if in_degree[i] == 0)
    topo_order = []
    while queue:
        node = queue.popleft()
        topo_order.append(node)
        for nxt, _strength in adj[node]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                queue.append(nxt)

    if len(topo_order) < len(ids):
        raise ValueError("dependency graph contains a cycle")
    return topo_order, adj


def find_critical_path(subquestions: list, dependencies: list) -> tuple:
    """找到依赖构成的加权最长路径。

    节点权重 = reasoning_steps * (0.45 + 0.55 * points / total_points)，
    让分值影响关键路径，但不让小分值高瓶颈小问被完全忽略。
    weak 依赖也代表共同情境/方法的认知延续，不能退化为独立小问。

    Args:
        subquestions: [{"id": int, "reasoning_steps": int, "points": int, ...}, ...]
        dependencies: [{"from": int, "to": int, "strength": "strong"|"weak"}, ...]

    Returns:
        (path_nodes: list[dict], path_steps: int)
    """
    if not subquestions:
        raise ValueError("subquestions is required")

    sq_map = {sq["id"]: sq for sq in subquestions}
    ids = [sq["id"] for sq in subquestions]
    total_points = sum(sq["points"] for sq in subquestions) or 1

    edges = _valid_dependency_edges(subquestions, dependencies)
    def node_weight(sq_id):
        sq = sq_map[sq_id]
        point_share = sq["points"] / total_points
        point_factor = 0.45 + 0.55 * point_share
        return sq["reasoning_steps"] * point_factor

    if not edges:
        best = max(subquestions, key=lambda s: s["reasoning_steps"] * (0.45 + 0.55 * (s["points"] / total_points)))
        return [best], best["reasoning_steps"]

    topo_order, adj = _topological_order(ids, edges)

    dist = {i: node_weight(i) for i in ids}
    prev = {i: None for i in ids}
    for node in topo_order:
        for nxt, strength in adj[node]:
            edge_factor = 1.0 if strength == "strong" else 0.55
            new_dist = dist[node] + edge_factor * node_weight(nxt)
            if new_dist > dist[nxt]:
                dist[nxt] = new_dist
                prev[nxt] = node

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


# 链长归一（2026-05-30 链长累加重设）：依赖链上重复同强度强边的几何衰减系数，
# 第 k 重强边边际贡献 ×decay**k，使难度由最难环/认知深度主导而非强边数量，
# 长强链几何收敛封顶（治 strong_increment 无界，weak 早已被 min(2.2) 封顶）。
_STRONG_CHAIN_DECAY = 0.6


def _dependent_path_load(path_nodes: list, dependencies: list) -> float:
    """将依赖路径换算为认知负荷。

    首个小问承担完整负荷；后续小问复用前文情境和已有结论，只计增量。
    strong 增量高于 weak，但 weak 不能被丢弃。
    """
    if not path_nodes:
        return 0.0
    if len(path_nodes) == 1:
        return float(path_nodes[0]["reasoning_steps"])

    total_points = sum(node["points"] for node in path_nodes) or 1
    avg_points = total_points / len(path_nodes)
    first = path_nodes[0]
    first_factor = 0.75 + 0.25 * min(1.0, first["points"] / avg_points)
    load = first["reasoning_steps"] * first_factor
    edge_strength = {
        (dep.get("from"), dep.get("to")): dep.get("strength")
        for dep in dependencies
        if isinstance(dep, dict) and dep.get("strength") in ("weak", "strong")
    }
    strong_contribs = []
    weak_increment = 0.0
    for left, right in zip(path_nodes, path_nodes[1:]):
        strength = edge_strength.get((left["id"], right["id"]), "weak")
        if strength == "strong":
            strong_contribs.append(0.58 * right["reasoning_steps"])
        else:
            weak_increment += 0.40 * right["reasoning_steps"]
    # 链长累加重设：强边按贡献降序后几何衰减，惩罚重复的同强度边（链长冗余）
    # 而非单条深边（真难度）。最难环排首位拿满权 decay**0=1，深度信号无损；
    # 等强简单边几何收敛封顶，长易链不再线性无界压过短难链。
    strong_contribs.sort(reverse=True)
    strong_increment = sum(
        contrib * (_STRONG_CHAIN_DECAY ** k)
        for k, contrib in enumerate(strong_contribs)
    )
    return load + strong_increment + min(2.2, weak_increment)


def aggregate_big_question(subquestions: list, dependencies: list,
                           global_features: dict) -> dict:
    """将结构化大题特征聚合为标准 v3 特征向量。"""
    if not subquestions:
        raise ValueError("subquestions is required")

    path_nodes, critical_path_steps = find_critical_path(subquestions, dependencies)
    total_steps = sum(sq["reasoning_steps"] for sq in subquestions)
    off_path = total_steps - critical_path_steps

    valid_edges = _valid_dependency_edges(subquestions, dependencies)
    has_strong_dependency = any(strength == "strong" for _, _, strength in valid_edges)
    has_weak_dependency = any(strength == "weak" for _, _, strength in valid_edges)
    has_dependency = bool(valid_edges)
    shared_ctx = _bounded_int(global_features.get("shared_context_load", 1), 1, 3, 1)
    method_novelty = _bounded_int(global_features.get("global_method_novelty", 1), 1, 3, 1)
    total_points = sum(sq["points"] for sq in subquestions)
    substantial_nodes = [
        sq for sq in subquestions
        if total_points > 0 and sq["points"] / total_points >= 0.15
    ] or list(path_nodes)
    independent_multi_part = (
        not has_dependency
        and total_points >= 10
        and len(substantial_nodes) >= 3
        and (shared_ctx >= 2 or method_novelty >= 2)
    )
    branch_cap = 2.2 if has_dependency or independent_multi_part else 1.4
    branch_factor = 0.50 if independent_multi_part else 0.42
    branch_load = min(branch_cap, branch_factor * (max(0, off_path) ** 0.5))

    path_length = len(path_nodes)
    context_load = 0.25 * max(0, shared_ctx - 1) + 0.35 * max(0, method_novelty - 1)
    if independent_multi_part:
        context_load += min(0.35, 0.15 * (len(substantial_nodes) - 2))
    effective_steps = _dependent_path_load(path_nodes, dependencies) + branch_load + context_load

    structural_nodes = list(path_nodes)
    for sq in substantial_nodes:
        if sq not in structural_nodes:
            structural_nodes.append(sq)

    wm_raw = (
        max(sq["working_memory"] for sq in structural_nodes)
        + 0.25 * (path_length - 1)
        + 0.25 * shared_ctx
    )
    if independent_multi_part:
        wm_raw += min(0.45, 0.15 * (len(substantial_nodes) - 1))
    wm = min(5, max(1, round(wm_raw)))

    novelty = max(
        method_novelty,
        max(sq["novelty"] for sq in path_nodes),
        max(sq["novelty"] for sq in substantial_nodes),
    )

    trap = max(sq["trap_density"] for sq in structural_nodes)
    breadth = max(
        max(sq["knowledge_breadth"] for sq in path_nodes),
        max(sq["knowledge_breadth"] for sq in substantial_nodes),
    )
    if (
        total_points >= 12
        and len(substantial_nodes) >= 3
        and (method_novelty >= 3 or trap >= 3 or has_dependency)
    ):
        # 大题的知识广度是整题层面的负荷，不能只取单个小问的最大值。
        breadth = max(breadth, 3)

    dependency_strengths = {
        (dep.get("from"), dep.get("to")): dep.get("strength")
        for dep in dependencies
        if isinstance(dep, dict)
    }
    path_edge_strengths = [
        dependency_strengths.get((left["id"], right["id"]))
        for left, right in zip(path_nodes, path_nodes[1:])
    ]
    if path_length >= 3 and path_edge_strengths and all(strength == "strong" for strength in path_edge_strengths):
        chain_coupling = 3
    elif (
        has_strong_dependency
        or has_weak_dependency
        or path_length >= 2
        or (
            independent_multi_part
            and shared_ctx >= 2
            and method_novelty >= 2
        )
        or (shared_ctx >= 2 and method_novelty >= 3 and total_points >= 10 and len(subquestions) >= 3)
    ):
        chain_coupling = 2
    else:
        chain_coupling = 1

    return {
        "effective_steps": round(effective_steps, 2),
        "working_memory": wm,
        "trap_density": trap,
        "novelty": novelty,
        "knowledge_breadth": breadth,
        "chain_coupling": chain_coupling,
    }
