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
