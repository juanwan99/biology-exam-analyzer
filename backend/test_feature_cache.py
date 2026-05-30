"""RC1 同卷特征缓存测试。"""


def test_key_stable_and_versioned():
    import feature_cache as fc
    k1 = fc._key("q", "", "", "short_answer", "biology")
    k2 = fc._key("q", "", "", "short_answer", "biology")
    assert k1 == k2
    assert fc._key("q2", "", "", "short_answer", "biology") != k1
    assert fc._key("q", "", "", "single_choice", "biology") != k1


def test_set_get_roundtrip(tmp_path, monkeypatch):
    import feature_cache as fc
    monkeypatch.setattr(fc, "_CACHE_DIR", str(tmp_path))
    assert fc.get("q", "", "", "short_answer", "biology") is None
    fc.set("q", "", "", "short_answer", "biology", {"working_memory": 3, "_feature_status": "ok"})
    got = fc.get("q", "", "", "short_answer", "biology")
    assert got is not None
    assert got["working_memory"] == 3
    assert got["_feature_cache_hit"] is True


async def test_extract_features_uses_cache_second_time(tmp_path, monkeypatch):
    import feature_cache as fc
    import feature_extractor as fe
    monkeypatch.setattr(fc, "_CACHE_DIR", str(tmp_path))
    calls = {"n": 0}

    async def fake_uncached(question_text, options="", correct_answer="",
                            question_type="", subject="biology", media_items=None):
        calls["n"] += 1
        return {"working_memory": 4, "reasoning_steps": 5, "_feature_status": "ok"}

    monkeypatch.setattr(fe, "_extract_features_uncached", fake_uncached)
    r1 = await fe.extract_features("Q-genetics", question_type="short_answer")
    r2 = await fe.extract_features("Q-genetics", question_type="short_answer")
    assert calls["n"] == 1
    assert r2.get("_feature_cache_hit") is True
    assert r1["working_memory"] == r2["working_memory"] == 4


async def test_failed_features_not_cached(tmp_path, monkeypatch):
    import feature_cache as fc
    import feature_extractor as fe
    monkeypatch.setattr(fc, "_CACHE_DIR", str(tmp_path))

    async def fake_failed(question_text, options="", correct_answer="",
                          question_type="", subject="biology", media_items=None):
        return {"_feature_status": "failed"}

    monkeypatch.setattr(fe, "_extract_features_uncached", fake_failed)
    await fe.extract_features("Q-bad", question_type="short_answer")
    assert fc.get("Q-bad", "", "", "short_answer", "biology") is None
