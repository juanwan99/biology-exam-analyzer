"""pytest 全局 fixture。"""
import pytest


@pytest.fixture(autouse=True)
def _isolate_feature_cache(tmp_path, monkeypatch):
    """RC1: 每个测试使用独立的特征缓存目录，避免跨测试/跨运行的缓存串扰。
    生产环境不受影响（仅 pytest 下生效）。"""
    try:
        import feature_cache
        monkeypatch.setattr(
            feature_cache, "_CACHE_DIR", str(tmp_path / "_feature_cache")
        )
    except ImportError:
        pass
