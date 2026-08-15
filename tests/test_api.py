from fastapi.testclient import TestClient

from flock_blocker.api import create_app


def test_health_and_cameras():
    client = TestClient(create_app())
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    cameras = client.get("/api/cameras")
    assert cameras.status_code == 200
    assert "cameras" in cameras.json()
