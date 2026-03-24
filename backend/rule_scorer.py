"""非线性评分引擎 — 分段映射 + 交互项。

B1a 重写：替代线性加权，解决中等区域区分度不足。
设计文档: docs/plans/2026-03-24-biology-exam-optimizer-design.md §3.3
"""


_BLOOM_MAP = {1: 0.0, 2: 0.15, 3: 0.30, 4: 0.55, 5: 0.80, 6: 1.0}
_STEPS_MAP = {1: 0.0, 2: 0.10, 3: 0.20, 4: 0.40, 5: 0.50, 6: 0.70, 7: 0.80, 8: 0.90, 9: 0.95, 10: 1.0}
_BREADTH_MAP = {1: 0.10, 2: 0.45, 3: 0.90}
_DENSITY_MAP = {1: 0.10, 2: 0.40, 3: 0.85}
_NOVELTY_MAP = {1: 0.05, 2: 0.40, 3: 0.90}
_QTYPE_MAP = {1: 0.05, 2: 0.30, 3: 0.60, 4: 0.90}

_WEIGHTS = {"bloom": 0.25, "steps": 0.25, "breadth": 0.15, "density": 0.12, "novelty": 0.10, "qtype": 0.13}


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


def _interaction_bonus(bloom, steps, breadth, novelty, qtype) -> float:
    bonus = 0.0
    if bloom >= 4 and steps >= 5:
        bonus += 0.08
    if breadth >= 2 and novelty >= 2:
        bonus += 0.05
    if bloom >= 5 and qtype >= 3:
        bonus += 0.06
    return bonus


def compute_difficulty(features: dict) -> float:
    """6 维特征 → 2-10 难度分（非线性版本）。

    下限 2.0（最简单的纯识记单选也有基础难度），上限 10.0。
    reasoning_steps 超过 8 封顶（超长推理链不额外加分）。
    """
    bloom = features["bloom"]
    steps = min(features["reasoning_steps"], 8)  # 封顶 8
    breadth = features["knowledge_breadth"]
    density = features["info_density"]
    novelty = features["novelty"]
    qtype = features["question_type_factor"]

    mapped = {
        "bloom": _interpolate(_BLOOM_MAP, bloom),
        "steps": _interpolate(_STEPS_MAP, steps),
        "breadth": _interpolate(_BREADTH_MAP, breadth),
        "density": _interpolate(_DENSITY_MAP, density),
        "novelty": _interpolate(_NOVELTY_MAP, novelty),
        "qtype": _interpolate(_QTYPE_MAP, qtype),
    }

    _FLOOR = 2.0
    _RANGE = 8.0
    raw = sum(mapped[k] * _WEIGHTS[k] for k in _WEIGHTS)
    raw += _interaction_bonus(bloom, steps, breadth, novelty, qtype)
    return min(10.0, round(_FLOOR + raw * _RANGE, 1))


def score_to_label(score: float) -> str:
    if score <= 3.0:
        return "简单"
    elif score <= 5.0:
        return "中等偏易"
    elif score <= 7.0:
        return "中等偏难"
    else:
        return "困难"
