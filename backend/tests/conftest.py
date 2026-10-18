"""Per-test isolation for the combined pytest run."""
import pytest


@pytest.fixture(autouse=True)
def _isolate_feature_cache(tmp_path, monkeypatch):
    try:
        import feature_cache
        monkeypatch.setattr(feature_cache, "_CACHE_DIR", str(tmp_path / "_feature_cache"))
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def _isolate_runtime_store(tmp_path, monkeypatch):
    try:
        import runtime_store
        if runtime_store._conn is not None:
            try:
                runtime_store._conn.close()
            except Exception:
                pass
        monkeypatch.setattr(runtime_store, "_conn", None)
        monkeypatch.setattr(runtime_store, "_using_memory", False)
        runtime_store.init(tmp_path / "runtime.sqlite")
        yield
        if runtime_store._conn is not None:
            try:
                runtime_store._conn.close()
            except Exception:
                pass
            runtime_store._conn = None
    except Exception:
        yield


@pytest.fixture(autouse=True)
def _reset_deps_singletons():
    try:
        import deps
    except ImportError:
        yield
        return
    names = [
        "_analyzer_instance",
        "_difficulty_engine",
        "_competency_analyzer",
        "_knowledge_mapper",
        "_doc_processor",
        "_rule_splitter",
        "_word_splitter",
        "_pdf_splitter",
        "_report_generator",
        "_analysis_service",
    ]
    for name in names:
        if hasattr(deps, name):
            setattr(deps, name, None)
    yield
    for name in names:
        if hasattr(deps, name):
            setattr(deps, name, None)


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    """Sync tests still call asyncio.get_event_loop(); auto-mode async tests close it."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    yield
