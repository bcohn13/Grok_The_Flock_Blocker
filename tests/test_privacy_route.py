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


def test_plan_privacy_route_reverse_starts_at_destination(monkeypatch):
    def fake_candidates(lat, lon, dest_lat, dest_lon, via=None):
        return [
            {
                "points": [(lat, lon), (dest_lat, dest_lon)],
                "streets": ["The Embarcadero"],
                "distance_meters": 500,
                "source": "osrm",
            }
        ]

    monkeypatch.setattr("flock_blocker.privacy_route.fetch_osrm_candidates", fake_candidates)
    monkeypatch.setattr("flock_blocker.privacy_route.scan_area", lambda *args, **kwargs: {})
    monkeypatch.setattr("flock_blocker.privacy_route.all_cameras", lambda: [])
    result = plan_privacy_route(
        37.78,
        -122.40,
        dest_lat=37.795,
        dest_lon=-122.394,
        destination="Ferry Building",
        origin="4th & Harrison",
        origin_lat=37.78,
        origin_lon=-122.40,
        reverse=True,
        scan=False,
    )
    assert result["reverse"] is True
    assert result["origin"] == "4th & Harrison"
    assert result["destination"] == "Ferry Building"
    assert result["origin_lat"] == 37.78
    assert result["recommended"]["points"][0]["lat"] == 37.795
    assert result["recommended"]["points"][-1]["lat"] == 37.78
    assert "from Ferry Building to 4th & Harrison" in result["narrative"]


def test_plan_privacy_route_geocodes_named_origin(monkeypatch):
    def fake_candidates(lat, lon, dest_lat, dest_lon, via=None):
        return [
            {
                "points": [(lat, lon), (dest_lat, dest_lon)],
                "streets": ["Market Street"],
                "distance_meters": 800,
                "source": "osrm",
            }
        ]

    monkeypatch.setattr("flock_blocker.privacy_route.fetch_osrm_candidates", fake_candidates)
    monkeypatch.setattr("flock_blocker.privacy_route.scan_area", lambda *args, **kwargs: {})
    monkeypatch.setattr("flock_blocker.privacy_route.all_cameras", lambda: [])
    monkeypatch.setattr(
        "flock_blocker.privacy_route.geocode_place",
        lambda place: {"lat": 37.7793, "lon": -122.4193, "label": "Civic Center"}
        if "Civic" in place
        else None,
    )
    result = plan_privacy_route(
        37.78,
        -122.40,
        dest_lat=37.795,
        dest_lon=-122.394,
        destination="Ferry Building",
        origin="Civic Center",
        scan=False,
    )
    assert result["origin_lat"] == 37.7793
    assert result["origin"] == "Civic Center"
    assert result["recommended"]["points"][0]["lat"] == 37.7793


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
