from flock_blocker.models import Camera
from flock_blocker.store import cameras_near, load_store, upsert_cameras


def test_seed_cameras_load():
    load_store()
    nearby = cameras_near(37.7879, -122.4075, 50)
    assert nearby
    assert nearby[0][0].source == "seed"


def test_upsert_and_nearby(tmp_path, monkeypatch):
    monkeypatch.setattr("flock_blocker.store.RUNTIME_PATH", tmp_path / "runtime.json")
    load_store()
    added = upsert_cameras(
        [
            Camera(
                id="osm-1",
                lat=30.2672,
                lon=-97.7431,
                manufacturer="Flock Safety",
                source="openstreetmap",
                city="Austin",
            )
        ]
    )
    assert added == 1
    hits = cameras_near(30.2672, -97.7431, 100)
    assert any(camera.id == "osm-1" for camera, _distance in hits)
