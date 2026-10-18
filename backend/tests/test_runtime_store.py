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


def test_fail_unfinished_tasks_only_touches_processing(store):
    import task_manager
    running = task_manager.create(5)
    done = task_manager.create(3)
    task_manager.complete(done, {"questions": []})
    assert task_manager.fail_unfinished() == 1
    row = task_manager.get(running)
    assert row["status"] == "failed"
    assert row["error"] == task_manager.RESTART_MESSAGE
    assert task_manager.get(done)["status"] == "completed"
    assert task_manager.fail_unfinished() == 0


@pytest.mark.asyncio
async def test_cancelled_pipeline_marks_task_failed(store, monkeypatch):
    import asyncio
    import analysis_router
    import task_manager

    started = asyncio.Event()

    async def slow_analyze(q, image_bytes, mode):
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(analysis_router, "analyze_question_full", slow_analyze)
    task_id = task_manager.create(1)
    job = asyncio.create_task(analysis_router._run_analysis_pipeline(
        task_id, [{"id": 1, "content": "1. 题"}], [], "deep", None, False, "full", "x.docx", None))
    await started.wait()
    job.cancel()
    with pytest.raises(asyncio.CancelledError):
        await job
    row = task_manager.get(task_id)
    assert row["status"] == "failed" and row["error"] == task_manager.RESTART_MESSAGE
