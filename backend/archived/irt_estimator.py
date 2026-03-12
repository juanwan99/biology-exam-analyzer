"""2PL IRT 参数估计器 — 模拟学生作答 → 难度参数。

设计文档: docs/plans/2026-03-11-difficulty-pipeline-design.md §3
"""
import numpy as np
from scipy.optimize import minimize


# 预设学生能力值（4 档 × 3 人）
STUDENT_THETAS = np.array([
    -1.5, -1.5, -1.5,  # Level 1: 基础薄弱
    -0.5, -0.5, -0.5,  # Level 2: 中等偏下
     0.5,  0.5,  0.5,  # Level 3: 中等偏上
     1.5,  1.5,  1.5,  # Level 4: 优秀
])


def _neg_log_posterior(params, responses, thetas):
    """2PL 模型负对数后验（含 a 的 LogNormal 先验）。"""
    a, b = params
    ll = 0.0
    for theta, r in zip(thetas, responses):
        p = 1.0 / (1.0 + np.exp(-a * (theta - b)))
        p = np.clip(p, 1e-6, 1 - 1e-6)
        ll += r * np.log(p) + (1 - r) * np.log(1 - p)
    # LogNormal(0, 0.5) 先验正则化 a
    log_prior_a = -0.5 * (np.log(max(a, 1e-6))) ** 2 / (0.5 ** 2)
    return -(ll + log_prior_a)


def _b_to_score(b):
    """b 参数映射到 0-10 分制。b=-3→0, b=0→5, b=+3→10。"""
    score = (b + 3.0) / 6.0 * 10.0
    return round(max(0.0, min(10.0, score)), 1)


def _score_to_label(score):
    """分数 → 难度标签。"""
    if score <= 3.0:
        return "简单"
    elif score <= 5.0:
        return "中等偏易"
    elif score <= 7.0:
        return "中等偏难"
    else:
        return "困难"


def _compute_confidence(result, responses):
    """基于 Fisher 信息矩阵标准误倒数计算置信度。"""
    if not result.success:
        return 0.4
    a, b = result.x
    # Fisher 信息 for b
    fisher_b = 0.0
    for theta in STUDENT_THETAS:
        p = 1.0 / (1.0 + np.exp(-a * (theta - b)))
        p = np.clip(p, 1e-6, 1 - 1e-6)
        fisher_b += (a ** 2) * p * (1 - p)
    if fisher_b < 1e-10:
        return 0.4
    se_b = 1.0 / np.sqrt(fisher_b)
    # se_b 越小 → 置信度越高。se_b=0→1.0, se_b=2→~0.33
    confidence = 1.0 / (1.0 + se_b)
    return round(max(0.0, min(1.0, confidence)), 2)


def estimate_difficulty(responses):
    """从 12 个模拟学生作答结果估计题目难度。

    Args:
        responses: list[float]，长度 12，每项 0/0.5/1（错/半对/对）

    Returns:
        dict: {
            difficulty_score: float (0-10),
            difficulty_label: str,
            irt_params: {b, a, b_se},
            confidence: float (0-1),
            flags: list[str]
        }
    """
    responses = np.array(responses, dtype=float)
    thetas = STUDENT_THETAS
    flags = []

    # Step 1: 全对/全错检查
    correct_rate = np.mean(responses)
    if correct_rate >= 1.0:
        b = -2.5
        return {
            "difficulty_score": _b_to_score(b),
            "difficulty_label": _score_to_label(_b_to_score(b)),
            "irt_params": {"b": b, "a": 1.0, "b_se": None},
            "confidence": 0.3,
            "flags": ["floor_hit"],
        }
    if correct_rate <= 0.0:
        b = 2.5
        return {
            "difficulty_score": _b_to_score(b),
            "difficulty_label": _score_to_label(_b_to_score(b)),
            "irt_params": {"b": b, "a": 1.0, "b_se": None},
            "confidence": 0.3,
            "flags": ["ceiling_hit"],
        }

    # Step 2: MAP 拟合
    result = minimize(
        _neg_log_posterior,
        x0=[1.0, 0.0],
        args=(responses, thetas),
        method="L-BFGS-B",
        bounds=[(0.2, 4.0), (-4.0, 4.0)],
    )

    a_est, b_est = result.x

    # a hit bound → 退化 1PL
    if a_est <= 0.21 or a_est >= 3.99:
        flags.append("a_extreme")
        a_est = 1.0
        result_1pl = minimize(
            lambda params, r, t: _neg_log_posterior([1.0, params[0]], r, t),
            x0=[0.0],
            args=(responses, thetas),
            method="L-BFGS-B",
            bounds=[(-4.0, 4.0)],
        )
        b_est = result_1pl.x[0]
        result = result_1pl  # for confidence calc

    # Step 3: 收敛检查
    if not result.success and "a_extreme" not in flags:
        flags.append("fallback")
        p_clipped = np.clip(correct_rate, 0.05, 0.95)
        b_est = -np.log(p_clipped / (1 - p_clipped))
        a_est = 1.0
        confidence = 0.4
    else:
        confidence = _compute_confidence(result, responses)

    score = _b_to_score(b_est)

    # b_se 计算
    a_final = a_est
    fisher_b = 0.0
    for theta in thetas:
        p = 1.0 / (1.0 + np.exp(-a_final * (theta - b_est)))
        p = np.clip(p, 1e-6, 1 - 1e-6)
        fisher_b += (a_final ** 2) * p * (1 - p)
    b_se = round(1.0 / np.sqrt(max(fisher_b, 1e-10)), 2)

    return {
        "difficulty_score": score,
        "difficulty_label": _score_to_label(score),
        "irt_params": {"b": round(b_est, 2), "a": round(a_est, 2), "b_se": b_se},
        "confidence": confidence,
        "flags": flags,
    }
