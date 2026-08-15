import pytest

from flock_blocker.store import load_store, reset_store


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path, monkeypatch):
    monkeypatch.setattr("flock_blocker.store.RUNTIME_PATH", tmp_path / "runtime_cameras.json")
    reset_store()
    load_store()
    yield
    reset_store()
