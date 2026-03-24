"""锚点校准 — isotonic regression。

B1a: 用可信锚点拟合单调校准曲线。
无校准模型时原样返回（不阻塞 pipeline）。
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CALIBRATION_PATH = Path(__file__).parent / "calibration_model.json"
_calibration_fn = None


def calibrate(raw_score: float) -> float:
    """校准原始分数。无校准模型时原样返回。"""
    fn = _get_calibration_fn()
    if fn is None:
        return raw_score
    return _apply_piecewise(fn, raw_score)


def fit_calibration(raw_scores: list, anchor_scores: list):
    """用 isotonic regression 拟合校准函数并保存。"""
    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        logger.error("sklearn 未安装，无法拟合校准模型")
        return

    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(raw_scores, anchor_scores)

    model = {
        "x": [float(v) for v in ir.X_thresholds_],
        "y": [float(v) for v in ir.y_thresholds_],
    }
    _CALIBRATION_PATH.write_text(json.dumps(model, indent=2))
    logger.info(f"校准模型已保存: {_CALIBRATION_PATH}")

    global _calibration_fn
    _calibration_fn = model


def _get_calibration_fn():
    global _calibration_fn
    if _calibration_fn is not None:
        return _calibration_fn
    if _CALIBRATION_PATH.exists():
        _calibration_fn = json.loads(_CALIBRATION_PATH.read_text())
        return _calibration_fn
    return None


def _apply_piecewise(model: dict, value: float) -> float:
    xs, ys = model["x"], model["y"]
    if value <= xs[0]:
        return ys[0]
    if value >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= value <= xs[i + 1]:
            ratio = (value - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + ratio * (ys[i + 1] - ys[i])
    return ys[-1]
