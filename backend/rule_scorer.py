"""规则评分引擎 — 6 维特征加权公式。

设计文档: docs/plans/2026-03-12-feature-difficulty-design.md §4
"""


def compute_difficulty(features: dict) -> float:
    """6 维特征 → 0-10 难度分。

    Args:
        features: dict with keys bloom, reasoning_steps, knowledge_breadth,
                  info_density, novelty, question_type_factor

    Returns:
        float: 0.0-10.0 难度分数，保留 1 位小数
    """
    bloom = features["bloom"]
    steps = features["reasoning_steps"]
    breadth = features["knowledge_breadth"]
    density = features["info_density"]
    novelty = features["novelty"]
    qtype = features["question_type_factor"]

    raw = (
        (bloom / 6) * 0.25
        + min(steps / 8, 1.0) * 0.25
        + (breadth / 3) * 0.15
        + (density / 3) * 0.15
        + (novelty / 3) * 0.10
        + (qtype / 4) * 0.10
    )
    return round(raw * 10, 1)


def score_to_label(score: float) -> str:
    """分数 → 难度标签（与 irt_estimator 一致）。"""
    if score <= 3.0:
        return "简单"
    elif score <= 5.0:
        return "中等偏易"
    elif score <= 7.0:
        return "中等偏难"
    else:
        return "困难"
