from fastapi.testclient import TestClient

from flock_blocker.api import create_app
from flock_blocker.models import Camera


def test_health_presets_and_cameras():
    client = TestClient(create_app())
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    presets = client.get("/api/presets")
    assert presets.status_code == 200
    names = {item["name"] for item in presets.json()["presets"]}
    assert "San Francisco" in names
    cameras = client.get("/api/cameras")
    assert cameras.status_code == 200
    assert "cameras" in cameras.json()


def test_scan_requires_location():
    client = TestClient(create_app())
    response = client.post("/api/scan", json={})
    assert response.status_code == 400


def test_scan_and_nearby(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setattr(
        "flock_blocker.scan.query_alpr_around",
        lambda lat, lon, radius_meters=None: [
            Camera(
                id="osm-99",
                lat=lat,
                lon=lon,
                manufacturer="Flock Safety",
                source="openstreetmap",
                city="Testville",
            )
        ],
    )
    monkeypatch.setattr(
        "flock_blocker.agents.proximity.query_alpr_around",
        lambda lat, lon, radius_meters=None: [
            Camera(
                id="osm-99",
                lat=lat,
                lon=lon,
                manufacturer="Flock Safety",
                source="openstreetmap",
                city="Testville",
            )
        ],
    )
    scanned = client.post("/api/scan", json={"lat": 30.26, "lon": -97.74, "place": "Austin"})
    assert scanned.status_code == 200
    body = scanned.json()
    assert body["count"] == 1
    assert body["flock_count"] == 1
    nearby = client.post("/api/nearby", json={"lat": 30.26, "lon": -97.74, "radius_meters": 200})
    assert nearby.status_code == 200
    assert nearby.json()["count"] >= 1
    assert nearby.json()["alerts"]
    assert nearby.json()["recommended_action"]
    assert nearby.json()["level"] in {"clear", "watch", "nearby", "close"}

    live_calls = {"n": 0}

    def boom(*_args, **_kwargs):
        live_calls["n"] += 1
        raise AssertionError("live nearby should not refresh OSM")

    monkeypatch.setattr("flock_blocker.agents.proximity.query_alpr_around", boom)
    live = client.post(
        "/api/nearby",
        json={"lat": 30.26, "lon": -97.74, "radius_meters": 200, "live": True},
    )
    assert live.status_code == 200
    assert live.json()["count"] >= 1
    assert live.json()["recommended_action"]
    assert live.json()["level"] == "close"
    assert live_calls["n"] == 0


def test_privacy_route_endpoint(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setattr(
        "flock_blocker.api.plan_privacy_route",
        lambda *args, **kwargs: {
            "destination": "Ferry Building",
            "dest_lat": 37.7955,
            "dest_lon": -122.3937,
            "recommended": {
                "points": [{"lat": 37.78, "lon": -122.4}],
                "camera_count": 2,
                "flock_count": 2,
                "distance_meters": 1800,
                "streets": ["The Embarcadero"],
                "cameras": [],
            },
            "alternatives": [],
            "narrative": "demo",
            "disclaimer": "not evade",
        },
    )
    response = client.post(
        "/api/privacy-route",
        json={"lat": 37.7809, "lon": -122.3998, "destination": "Ferry Building", "scan": False},
    )
    assert response.status_code == 200
    assert response.json()["recommended"]["camera_count"] == 2


def test_walk_route_endpoint(monkeypatch):
    client = TestClient(create_app())
    monkeypatch.setattr(
        "flock_blocker.api.walking_route",
        lambda lat, lon, dest_lat=None, dest_lon=None, reverse=False: {
            "points": [(37.780882, -122.399749), (37.78119, -122.400131)],
            "streets": ["4th Street"],
            "distance_meters": 48,
            "source": "osm-centerline",
        },
    )
    response = client.post(
        "/api/walk-route",
        json={"lat": 37.7809, "lon": -122.3997, "dest_lat": 37.7857, "dest_lon": -122.4059},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["streets"] == ["4th Street"]
    assert body["points"][0]["lat"] == 37.780882

    reversed_walk = client.post(
        "/api/walk-route",
        json={
            "lat": 37.7809,
            "lon": -122.3997,
            "dest_lat": 37.7857,
            "dest_lon": -122.4059,
            "reverse": True,
        },
    )
    assert reversed_walk.status_code == 200


def test_index_served():
    client = TestClient(create_app())
    page = client.get("/")
    assert page.status_code == 200
    assert b"Grok the Flock Blocker" in page.content
    assert b"Live tracking" in page.content
    assert b"Recommend route to" in page.content
    assert b"Recommend route from" in page.content
    assert b"Demo walk from" in page.content
    assert b"Route from" in page.content
