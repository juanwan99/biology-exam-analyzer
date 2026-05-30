"""按子问拆分细粒度分析的合并器（RC7 方案A）。

把 N 个子问各自产出的局部 FineGrainedResult dict 合并成整题一个。
纯函数，只编排已有结构，不调用 LLM、不引入新 schema。

核心不变量（见 plans/2026-05-30-rc7-plan-a-split-merge-design.md §3）：
- I1 整题 SEU score_share 和≈1.0：各子问局部和=1.0，按子问权重 w_i(extractor score_share，跨子问和=1.0)
  缩放后整题自动=1.0。merged_share = local_share * w_i。
- I2 seu_id/du_id 整题唯一：前缀 sq{i}_。
- I3 stimulus_units 题级共享去重：按 (type, description) 归并，is_core 取 OR。
- total_score = 各子问分值之和（=整题总分）。
合并产物交回调用方做 compute_summary_from_units + validate_score_conservation（不在本模块重复造校验）。
"""
from typing import List, Dict


def _dedup_stimulus(stimulus_units: List[Dict]) -> List[Dict]:
    """题级共享材料去重：相同 (stimulus_type, description前30字) 归并，is_core 取 OR，su_id 重排。"""
    merged = {}
    order = []
    for su in stimulus_units:
        st = su.get("stimulus_type", "") or ""
        desc = (su.get("description", "") or "").strip()[:30]
        key = (st, desc)
        if key in merged:
            if su.get("is_core"):
                merged[key]["is_core"] = True
        else:
            copy = dict(su)
            merged[key] = copy
            order.append(key)
    result = []
    for i, key in enumerate(order, start=1):
        su = merged[key]
        su["su_id"] = f"su_{i}"
        result.append(su)
    return result


def merge_subquestion_results(sub_results: List[Dict],
                              subquestions: List[Dict],
                              total_score: float) -> Dict:
    """合并 N 个子问局部 FineGrainedResult dict → 整题 _fine_grained payload。

    sub_results[i] 与 subquestions[i] 一一对应（同序）。
    sub_results[i] = {scoring_units:[...局部 score_share 和≈1.0...], diagnostic_units, stimulus_units, detailed_analysis?}
    subquestions[i] = extractor 子问 {id, points, score_share, ...}（score_share 跨子问和=1.0，用作权重）
    返回 {scoring_units, diagnostic_units, stimulus_units, total_score, detailed_analysis}。
    """
    if not sub_results:
        raise ValueError("sub_results is required")
    n = len(sub_results)

    # 权重：优先用 extractor 的 score_share（跨子问和=1.0）；缺失则按 points/total；再缺则均分。
    weights = []
    for i in range(n):
        sq = subquestions[i] if i < len(subquestions) else {}
        w = sq.get("score_share")
        if w is None:
            pts = sq.get("points")
            w = (pts / total_score) if (pts and total_score) else (1.0 / n)
        weights.append(float(w))
    wsum = sum(weights) or 1.0
    weights = [w / wsum for w in weights]  # 归一化权重，防 extractor 权重和漂移

    merged_seus: List[Dict] = []
    merged_dus: List[Dict] = []
    merged_sus: List[Dict] = []
    detailed_parts: List[str] = []

    for idx, sub in enumerate(sub_results, start=1):
        w = weights[idx - 1]
        for seu in sub.get("scoring_units", []) or []:
            copy = dict(seu)
            copy["score_share"] = round(float(seu.get("score_share", 0) or 0) * w, 6)
            copy["seu_id"] = f"sq{idx}_{seu.get('seu_id', 'seu')}"
            merged_seus.append(copy)
        for du in sub.get("diagnostic_units", []) or []:
            copy = dict(du)
            copy["du_id"] = f"sq{idx}_{du.get('du_id', 'du')}"
            merged_dus.append(copy)
        for su in sub.get("stimulus_units", []) or []:
            merged_sus.append(dict(su))
        da = sub.get("detailed_analysis")
        if da:
            detailed_parts.append(f"（{idx}）{da}")

    # I1 浮点兜底：整题 score_share 和强制拉回 1.0
    share_sum = sum(s["score_share"] for s in merged_seus)
    if merged_seus and share_sum > 0 and abs(share_sum - 1.0) > 1e-9:
        for s in merged_seus:
            s["score_share"] = round(s["score_share"] / share_sum, 6)

    return {
        "scoring_units": merged_seus,
        "diagnostic_units": merged_dus,
        "stimulus_units": _dedup_stimulus(merged_sus),
        "total_score": int(round(total_score)) if total_score else 0,
        "detailed_analysis": "\n".join(detailed_parts),
    }
