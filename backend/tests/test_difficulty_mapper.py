"""分数预估的难度 → 得分率映射：库里只有占位映射时走真实考试校准曲线（#7）。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from difficulty_mapper import CURVE, DifficultyMapper


def _mapper(global_mapping):
    m = DifficultyMapper.__new__(DifficultyMapper)
    m.db = None

    async def get_mapping(mapping_type, key, grade, difficulty):
        return global_mapping if mapping_type == "global" else None

    m._get_mapping = AsyncMock(side_effect=get_mapping)
    return m


def _global_row(sample_count, confidence):
    # 数据库初始化脚本 02_prediction_schema.sql 写的占位行就是 sample_count=0 / confidence=0.5
    return SimpleNamespace(mapping_type="global", sample_count=sample_count, confidence=confidence,
                           slope=-0.075, intercept=1.025, avg_score_rate=0.7, score_rate_stddev=0.1)


def test_curve_is_monotone_and_bounded():
    assert len(CURVE["x"]) == len(CURVE["y"]) >= 2
    assert CURVE["x"] == sorted(CURVE["x"])
    assert all(a >= b for a, b in zip(CURVE["y"], CURVE["y"][1:]))
    assert all(0.0 <= y <= 1.0 for y in CURVE["y"])
    assert 0 < CURVE["residual_std"] < 0.5


@pytest.mark.asyncio
async def test_placeholder_global_mapping_falls_to_curve():
    m = _mapper(_global_row(sample_count=0, confidence=0.5))
    for d in (1.0, 4.5, 6.0, 9.5):
        rate, low, high = await m.predict_rate(difficulty=d, grade="高三")
        assert rate == pytest.approx(float(np.interp(d, CURVE["x"], CURVE["y"])))
        assert low <= rate <= high


@pytest.mark.asyncio
async def test_reliable_global_mapping_still_wins():
    # 置信度不到 0.6 也用：全局映射只看样本数是不是占位
    m = _mapper(_global_row(sample_count=25, confidence=0.5))
    rate, _, _ = await m.predict_rate(difficulty=6.0, grade="高三")
    assert rate == pytest.approx(1.025 - 0.075 * 6.0)
