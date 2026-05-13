"""难度校准服务 — 用历史考试数据反向校准难度预测。

依赖方向：difficulty_pipeline -> calibration_service（单向）。
本模块不 import difficulty_pipeline，只提供校准系数。
"""
import statistics as stats_mod
from typing import List, Tuple, Dict, Optional
from logger import get_logger

logger = get_logger()

_calibration_data: Optional[Dict] = None


async def collect_data_from_db(db_session) -> List[Tuple[float, float]]:
    """从数据库收集 (预测难度, 实际得分率) 数据对。"""
    from models import QuestionPerformance
    from sqlalchemy import select

    try:
        result = await db_session.execute(
            select(QuestionPerformance.absolute_difficulty, QuestionPerformance.score_rate)
            .where(QuestionPerformance.absolute_difficulty.isnot(None))
            .where(QuestionPerformance.score_rate.isnot(None))
        )
        pairs = [(float(row[0]), float(row[1])) for row in result.fetchall()]
        logger.info(f"[校准] 收集到 {len(pairs)} 条历史数据")
        return pairs
    except Exception as e:
        logger.warning(f"[校准] 数据收集失败: {e}")
        return []


def analyze(data_pairs: List[Tuple[float, float]]) -> Dict:
    """分析校准数据，计算偏差。"""
    if len(data_pairs) < 10:
        return {
            "status": "insufficient",
            "sample_count": len(data_pairs),
            "min_required": 10,
        }

    # 按难度区间分组
    ranges = {"简单(0-3.5)": [], "中等(3.5-6.5)": [], "困难(6.5-10)": []}
    for d, s in data_pairs:
        if d <= 3.5:
            ranges["简单(0-3.5)"].append((d, s))
        elif d <= 6.5:
            ranges["中等(3.5-6.5)"].append((d, s))
        else:
            ranges["困难(6.5-10)"].append((d, s))

    bias_by_range = {}
    for label, pairs in ranges.items():
        if pairs:
            pred_avg = stats_mod.mean([d for d, _ in pairs])
            actual_avg = stats_mod.mean([s for _, s in pairs])
            expected_rate = max(0, 1 - pred_avg / 10)
            bias = actual_avg - expected_rate
            bias_by_range[label] = {
                "count": len(pairs),
                "predicted_difficulty_avg": round(pred_avg, 2),
                "actual_score_rate_avg": round(actual_avg, 3),
                "expected_score_rate": round(expected_rate, 3),
                "bias": round(bias, 3),
            }

    # 总体 RMSE
    errors = []
    for d, s in data_pairs:
        expected = max(0, 1 - d / 10)
        errors.append((s - expected) ** 2)
    rmse = (sum(errors) / len(errors)) ** 0.5

    result = {
        "status": "calibrated",
        "sample_count": len(data_pairs),
        "overall_rmse": round(rmse, 4),
        "bias_by_range": bias_by_range,
    }

    global _calibration_data
    _calibration_data = result
    logger.info(f"[校准] 完成，RMSE={rmse:.4f}，样本={len(data_pairs)}")
    return result


def get_correction(difficulty: float) -> float:
    """获取校准修正值。difficulty_pipeline 调用此函数。

    Returns:
        修正值（加到 final_difficulty 上），默认 0（不校准）。
    """
    if _calibration_data is None or _calibration_data.get("status") != "calibrated":
        return 0.0

    bias_by_range = _calibration_data.get("bias_by_range", {})

    if difficulty <= 3.5:
        bias_info = bias_by_range.get("简单(0-3.5)", {})
    elif difficulty <= 6.5:
        bias_info = bias_by_range.get("中等(3.5-6.5)", {})
    else:
        bias_info = bias_by_range.get("困难(6.5-10)", {})

    bias = bias_info.get("bias", 0)
    # bias > 0 表示实际得分率高于预期 -> 难度预测偏高 -> 修正为降低难度
    # 修正幅度限制在 [-1.5, 1.5]
    correction = max(-1.5, min(1.5, -bias * 5))
    return round(correction, 2)


def get_calibration_status() -> Dict:
    """返回当前校准状态。"""
    if _calibration_data is None:
        return {"status": "not_calibrated", "sample_count": 0}
    return _calibration_data
