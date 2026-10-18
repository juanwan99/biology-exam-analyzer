import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    import runtime_store as rs
    monkeypatch.setattr(rs, "_conn", None)
    monkeypatch.setattr(rs, "_using_memory", False)
    rs.init(tmp_path / "runtime.sqlite")
    yield rs
    if rs._conn is not None:
        rs._conn.close()
        rs._conn = None


def test_token_roundtrip_and_dict_facade(store):
    tokens = store.TokenMap()
    tokens["abc"] = {"id": 1, "username": "user003", "login_time": "2026-08-19T00:00:00"}
    assert "abc" in tokens
    assert tokens.get("abc")["username"] == "user003"
    del tokens["abc"]
    assert tokens.get("abc") is None


def test_session_roundtrip(store):
    store.save_session("s1", {"questions": [1]})
    assert store.get_session("s1") == {"questions": [1]}
    assert store.get_session("missing") is None


def test_task_roundtrip(store):
    store.put_task("t1", {"status": "processing", "progress": 0})
    row = store.get_task("t1")
    assert row["status"] == "processing"
    store.put_task("t1", {"status": "completed", "progress": 3, "result": {"ok": True}})
    assert store.get_task("t1")["result"]["ok"] is True
