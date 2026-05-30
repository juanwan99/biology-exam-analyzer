"""RC7 方案A 合并器 TDD（Slice1）。锁死合并不变量 I1-I3 + total_score。"""
import pytest
from fine_grained_merge import merge_subquestion_results, _dedup_stimulus
from llm_schemas import FineGrainedResult, validate_score_conservation


def _seu(seu_id, share, kp="光合作用"):
    return {"seu_id": seu_id, "label": f"采分点{seu_id}", "score_share": share,
            "knowledge_links": [{"knowledge_point": kp, "share": 1.0}],
            "bloom_level": 3, "allocation_confidence": 0.8}


def _su(desc, stype="table", is_core=False):
    return {"su_id": "su_1", "stimulus_type": stype, "description": desc,
            "is_core": is_core, "complexity": 2}


def _du(du_id, mis="误区"):
    return {"du_id": du_id, "option_or_trap": "trap_1", "misconception": mis}


def _two_subq_results():
    # 子问1(权重0.7): 2个SEU局部0.5/0.5 + 共享材料; 子问2(权重0.3): 1个SEU局部1.0 + 同一共享材料
    sub1 = {"scoring_units": [_seu("seu_1", 0.5), _seu("seu_2", 0.5)],
            "diagnostic_units": [_du("du_1")], "stimulus_units": [_su("某湖泊食物网表")],
            "detailed_analysis": "子问1分析"}
    sub2 = {"scoring_units": [_seu("seu_1", 1.0)],
            "diagnostic_units": [_du("du_1")], "stimulus_units": [_su("某湖泊食物网表")],
            "detailed_analysis": "子问2分析"}
    subqs = [{"id": 1, "score_share": 0.7, "points": 7},
             {"id": 2, "score_share": 0.3, "points": 3}]
    return [sub1, sub2], subqs, 10.0


def test_score_share_conserves_to_one():
    """I1: 各子问局部和=1.0，按权重缩放后整题和=1.0。"""
    sub_results, subqs, total = _two_subq_results()
    merged = merge_subquestion_results(sub_results, subqs, total)
    s = sum(u["score_share"] for u in merged["scoring_units"])
    assert abs(s - 1.0) < 0.001, f"整题 score_share 和={s}"


def test_weight_reflects_subquestion_share():
    """子问1(权重0.7)的SEU总占比应≈0.7，子问2≈0.3。"""
    sub_results, subqs, total = _two_subq_results()
    merged = merge_subquestion_results(sub_results, subqs, total)
    sq1 = sum(u["score_share"] for u in merged["scoring_units"] if u["seu_id"].startswith("sq1_"))
    sq2 = sum(u["score_share"] for u in merged["scoring_units"] if u["seu_id"].startswith("sq2_"))
    assert abs(sq1 - 0.7) < 0.001 and abs(sq2 - 0.3) < 0.001


def test_seu_ids_unique_and_prefixed():
    """I2: 各子问都产 seu_1，合并后必须前缀去撞唯一。"""
    sub_results, subqs, total = _two_subq_results()
    merged = merge_subquestion_results(sub_results, subqs, total)
    ids = [u["seu_id"] for u in merged["scoring_units"]]
    assert len(ids) == len(set(ids)), f"seu_id 重复: {ids}"
    assert all(i.startswith("sq") for i in ids)
    assert "sq1_seu_1" in ids and "sq2_seu_1" in ids


def test_du_ids_prefixed():
    sub_results, subqs, total = _two_subq_results()
    merged = merge_subquestion_results(sub_results, subqs, total)
    dids = [u["du_id"] for u in merged["diagnostic_units"]]
    assert len(dids) == len(set(dids)), f"du_id 重复: {dids}"


def test_stimulus_deduped():
    """I3: 题级共享材料(同description)合并后去重为1。"""
    sub_results, subqs, total = _two_subq_results()
    merged = merge_subquestion_results(sub_results, subqs, total)
    assert len(merged["stimulus_units"]) == 1, f"未去重: {merged['stimulus_units']}"


def test_stimulus_is_core_or():
    """去重时 is_core 取 OR：一个子问标 core 则保留 core。"""
    sus = [_su("同材料", is_core=False), _su("同材料", is_core=True)]
    deduped = _dedup_stimulus(sus)
    assert len(deduped) == 1 and deduped[0]["is_core"] is True


def test_total_score_summed():
    sub_results, subqs, total = _two_subq_results()
    merged = merge_subquestion_results(sub_results, subqs, total)
    assert merged["total_score"] == 10


def test_merged_constructs_fine_grained_result():
    """合并产物必须能构造 FineGrainedResult(过 check_score_conservation 构造门) + validate_score_conservation 通过。"""
    sub_results, subqs, total = _two_subq_results()
    merged = merge_subquestion_results(sub_results, subqs, total)
    fg = FineGrainedResult(**merged)  # 守恒门：sum≈1.0 否则 raise
    ok, errors = validate_score_conservation(fg, fg.total_score)
    assert ok, f"守恒校验失败: {errors}"


def test_weight_falls_back_to_points_when_no_share():
    """extractor 缺 score_share 时按 points/total。"""
    sub_results, _, total = _two_subq_results()
    subqs = [{"id": 1, "points": 7}, {"id": 2, "points": 3}]  # 无 score_share
    merged = merge_subquestion_results(sub_results, subqs, total)
    s = sum(u["score_share"] for u in merged["scoring_units"])
    assert abs(s - 1.0) < 0.001


def test_empty_raises():
    with pytest.raises(ValueError):
        merge_subquestion_results([], [], 10.0)


def test_detailed_analysis_concatenated():
    sub_results, subqs, total = _two_subq_results()
    merged = merge_subquestion_results(sub_results, subqs, total)
    assert "子问1分析" in merged["detailed_analysis"] and "子问2分析" in merged["detailed_analysis"]
