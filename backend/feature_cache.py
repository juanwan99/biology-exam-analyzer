"""RC1 根因修复：同卷特征缓存。

按题目内容指纹缓存 extract_features 的结果。同一道题（指纹相同）重复分析时直接复用
首次特征，从而消除 DeepSeek 跨跑主观打分漂移，保证同卷重跑难度可复现。
缓存命中：零 LLM 调用、零额外 token。

失效：_FEATURE_CACHE_VERSION 变更（特征 prompt/口径改动时手动 bump）即作废全部旧缓存。
"""
import os
import json
import hashlib

from logger import get_logger

logger = get_logger()

# v4: 方案B 特征提取拆分（难度核心 / 质量 / 教学三组顺序调用 + 部分降级）。
# schema 变更（新增 _llm_calls 子组记录、_feature_status 判据改为难度核心组为主），
# bump 版本作废全部旧 v3 单任务缓存，避免读到旧 schema。
_FEATURE_CACHE_VERSION = "v4-20260615-split"
_CACHE_DIR = os.environ.get(
    "FEATURE_CACHE_DIR",
    os.path.join(os.path.dirname(__file__), ".feature_cache"),
)


def _key(question_text, options, correct_answer, question_type, subject):
    sep = chr(0)
    raw = sep.join([
        _FEATURE_CACHE_VERSION,
        subject or "",
        question_type or "",
        question_text or "",
        options or "",
        correct_answer or "",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get(question_text, options, correct_answer, question_type, subject):
    """命中返回带 _feature_cache_hit=True 的特征 dict；未命中或异常返回 None。"""
    try:
        path = os.path.join(
            _CACHE_DIR,
            _key(question_text, options, correct_answer, question_type, subject) + ".json",
        )
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data["_feature_cache_hit"] = True
                return data
    except Exception as e:
        logger.warning(f"[特征缓存] 读取失败，降级为重新提取: {e}")
    return None


def set(question_text, options, correct_answer, question_type, subject, result):
    """写入缓存。任何异常降级为不缓存，不影响主流程。"""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        path = os.path.join(
            _CACHE_DIR,
            _key(question_text, options, correct_answer, question_type, subject) + ".json",
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"[特征缓存] 写入失败（不影响主流程）: {e}")
