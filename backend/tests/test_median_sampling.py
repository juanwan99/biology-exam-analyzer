"""#11：难度多次采样取中位 + 未标分卷大题分值按分节小计缩放。"""
import pytest

import feature_extractor as fe
from score_rules import (
    SOURCE_MODEL, SOURCE_PAPER, SOURCE_SECTION_SCALED, apportion, mark_section_mismatch,
    scale_section_scores,
)
from services.analysis_service import AnalysisService

BIG = "三、非选择题：本题共5小题，共60分。"
CORE = ["working_memory", "reasoning_steps", "chain_coupling", "trap_density", "novelty", "knowledge_breadth"]


def _outcome(values, ok=True, reason="r"):
    fields = dict(zip(CORE, values))
    fields["bloom"] = values[0] if values else 3
    fields["working_memory_reason"] = reason
    return {"fields": fields if ok else {}, "core_present": 6 if ok else 0, "ok": ok,
            "retry_count": 0, "response_length": 10, "degraded": not ok, "error": None if ok else "x"}


# ── 小题：难度核心组逐维中位 ──

def test_merge_takes_per_dimension_median_and_closest_reasons():
    merged = fe._merge_difficulty_samples([
        _outcome([2, 3, 1, 2, 2, 2], reason="low"),
        _outcome([3, 4, 2, 2, 3, 2], reason="mid"),
        _outcome([4, 6, 2, 3, 3, 3], reason="high"),
    ])
    assert [merged["fields"][k] for k in CORE] == [3, 4, 2, 2, 3, 2]
    assert merged["fields"]["working_memory_reason"] == "mid"
    assert merged["ok"] and merged["samples"] == 3 and merged["samples_ok"] == 3


def test_merge_ignores_failed_samples():
    merged = fe._merge_difficulty_samples([
        _outcome([], ok=False), _outcome([3, 5, 2, 2, 2, 2]), _outcome([], ok=False)])
    assert merged["ok"] and merged["samples_ok"] == 1
    assert merged["fields"]["reasoning_steps"] == 5


def test_merge_all_failed_keeps_failure():
    merged = fe._merge_difficulty_samples([_outcome([], ok=False), _outcome([], ok=False)])
    assert merged["ok"] is False and merged["samples_ok"] == 0


async def test_sample_difficulty_group_calls_n_times(monkeypatch):
    monkeypatch.setenv("DIFFICULTY_SAMPLES", "3")
    seq = iter([[2, 3, 1, 2, 2, 2], [4, 6, 2, 3, 3, 3], [3, 4, 2, 2, 3, 2]])
    calls = []

    async def fake_group(group_key, **kwargs):
        calls.append(group_key)
        return _outcome(next(seq))

    monkeypatch.setattr(fe, "_extract_group", fake_group)
    merged = await fe._sample_difficulty_group("difficulty", loader=None)
    assert calls == ["difficulty"] * 3
    assert merged["fields"]["reasoning_steps"] == 4


# ── 大题：整份算分取居中 ──

def _bigq(steps):
    return {
        "subquestions": [
            {"id": 1, "points": 4, "working_memory": 2, "reasoning_steps": steps, "trap_density": 2,
             "novelty": 2, "knowledge_breadth": 2, "chain_coupling": 1},
            {"id": 2, "points": 6, "working_memory": 3, "reasoning_steps": steps, "trap_density": 2,
             "novelty": 2, "knowledge_breadth": 2, "chain_coupling": 1},
        ],
        "dependencies": [], "global_features": {"shared_context_load": 1, "global_method_novelty": 1},
        "report": {}, "steps": steps,
    }


async def test_big_question_picks_median_scored_sample(monkeypatch):
    monkeypatch.setenv("BIG_QUESTION_SAMPLES", "3")
    seq = iter([_bigq(8), _bigq(1), _bigq(4)])

    async def fake_uncached(*args, **kwargs):
        return next(seq)

    monkeypatch.setattr(fe, "_extract_big_question_features_uncached", fake_uncached)
    chosen = await fe._sample_big_question_features("Q", total_score=10)
    assert chosen["steps"] == 4
    meta = chosen["_big_question_samples"]
    assert meta["samples_ok"] == 3 and meta["scores"] == sorted(meta["scores"])


async def test_big_question_all_failed_returns_first_failure(monkeypatch):
    monkeypatch.setenv("BIG_QUESTION_SAMPLES", "3")

    async def fake_uncached(*args, **kwargs):
        return {"_big_question_failed": True, "failure_type": "x"}

    monkeypatch.setattr(fe, "_extract_big_question_features_uncached", fake_uncached)
    chosen = await fe._sample_big_question_features("Q", total_score=10)
    assert chosen["_big_question_failed"] is True


async def test_big_question_cache_hit_rescales_points_to_new_total(monkeypatch):
    async def fake_uncached(*args, **kwargs):
        return _bigq(3)

    monkeypatch.setattr(fe, "_extract_big_question_features_uncached", fake_uncached)
    await fe.extract_big_question_features("BigQ", question_type="short_answer", total_score=10)
    hit = await fe.extract_big_question_features("BigQ", question_type="short_answer", total_score=12)
    assert hit["_feature_cache_hit"] is True
    assert [sq["points"] for sq in hit["subquestions"]] == [5, 7]


# ── 分值：按分节小计缩放 ──

def test_apportion_sums_exactly():
    assert apportion([10, 12, 12, 12, 12], 60) == [10, 13, 13, 12, 12]
    assert sum(apportion([3, 3, 3], 10)) == 10
    assert apportion([4, 4], 9.5) == [5.0, 4.5]
    assert apportion([0, 0], 10) is None


def _section(scores, sources=None):
    sources = sources or [SOURCE_MODEL] * len(scores)
    return [{"id": 17 + i, "_section_header": BIG, "total_score": s, "score_status": "valid",
             "score_source": src} for i, (s, src) in enumerate(zip(scores, sources))]


def test_scale_model_scores_to_section_total():
    qs = _section([10, 12, 12, 12, 12])
    changes = scale_section_scores(qs)
    assert sum(q["total_score"] for q in qs) == 60
    assert {c["id"] for c in changes} == {18, 19}
    assert all(q["score_source"] == SOURCE_SECTION_SCALED for q in qs if q["id"] in (18, 19))
    assert mark_section_mismatch(qs) == []
    assert all(q["score_status"] == "valid" for q in qs)


def test_scale_keeps_paper_scores_fixed():
    qs = _section([14, 12, 12, 10, 10], [SOURCE_PAPER, SOURCE_MODEL, SOURCE_MODEL, SOURCE_MODEL, SOURCE_MODEL])
    scale_section_scores(qs)
    assert qs[0]["total_score"] == 14
    assert sum(q["total_score"] for q in qs) == 60


def test_scale_skips_when_ratio_out_of_range_or_count_mismatch():
    far = _section([30, 30, 30, 30, 30])
    assert scale_section_scores(far) == []
    assert [q["total_score"] for q in far] == [30] * 5
    short = _section([10, 12, 12, 12])
    assert scale_section_scores(short) == []


# ── 编排：改了分的题按新分值重算难度 ──

class _FakeEngine:
    def __init__(self):
        self.seen = []

    async def evaluate_with_refinement(self, question, **kwargs):
        self.seen.append((question["id"], question["total_score"]))
        return {"final_difficulty": 6.0, "difficulty_label": "中等", "confidence": 0.8, "features": {}}


async def test_rescale_reevaluates_only_changed_questions():
    engine = _FakeEngine()
    service = AnalysisService(analyzer=None, difficulty_engine=engine, competency_analyzer=None,
                              knowledge_mapper=None, doc_processor=None, word_splitter=None,
                              pdf_splitter=None)
    qs = _section([10, 12, 12, 12, 12])
    for q in qs:
        q.update({"content": f"题{q['id']}", "subject": "biology", "analysis": {"answer": "略"},
                  "difficulty": {"final_difficulty": 5.0}})
    changes = await service.rescale_section_scores(qs, [], "deep")
    assert sorted(engine.seen) == [(18, 13), (19, 13)]
    assert [c["id"] for c in changes] == [18, 19]
    assert qs[1]["difficulty"]["difficulty_label"] == "中等"
    assert qs[0]["difficulty"] == {"final_difficulty": 5.0}
    assert qs[1]["_metadata_envelope"]["question"]["total_score"] == 13
