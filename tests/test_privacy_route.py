from flock_blocker.geo import haversine_meters
from flock_blocker.models import Camera
from flock_blocker.privacy_route import cameras_along_path, plan_privacy_route


def _cam(cam_id: str, lat: float, lon: float) -> Camera:
    return Camera(
        id=cam_id,
        lat=lat,
        lon=lon,
        manufacturer="Flock Safety",
        source="openstreetmap",
    )


def test_cameras_along_path_counts_nearby_only():
    path = [(37.78, -122.40), (37.781, -122.401), (37.782, -122.402)]
    near = _cam("osm-near", 37.781, -122.401)
    far = _cam("osm-far", 37.80, -122.42)
    hits = cameras_along_path(path, [near, far], radius_meters=70)
    assert [item["id"] for item in hits] == ["osm-near"]


def test_plan_privacy_route_prefers_fewer_cameras(monkeypatch):
    busy = {
        "points": [(37.78, -122.40), (37.781, -122.401)],
        "streets": ["4th Street"],
        "distance_meters": 400,
        "source": "osrm",
    }
    quiet = {
        "points": [(37.78, -122.40), (37.7802, -122.403)],
        "streets": ["3rd Street"],
        "distance_meters": 520,
        "source": "osrm-via",
    }
    monkeypatch.setattr(
        "flock_blocker.privacy_route.fetch_osrm_candidates",
        lambda *args, **kwargs: [busy] if kwargs.get("via") is None else [quiet],
    )
    monkeypatch.setattr("flock_blocker.privacy_route.scan_area", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        "flock_blocker.privacy_route.all_cameras",
        lambda: [_cam("osm-near", 37.781, -122.401)],
    )
    result = plan_privacy_route(
        37.78,
        -122.40,
        dest_lat=37.785,
        dest_lon=-122.405,
        destination="Ferry Building",
        scan=False,
    )
    assert result["recommended"]["camera_count"] <= result["alternatives"][-1]["camera_count"]
    assert "evade" in result["disclaimer"]
    assert result["recommended"]["points"][0]["lat"] == 37.78
