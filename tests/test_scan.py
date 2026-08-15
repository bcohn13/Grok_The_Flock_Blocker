from flock_blocker.models import Camera
from flock_blocker.scan import scan_area


def test_scan_area_counts_flock(monkeypatch):
    monkeypatch.setattr(
        "flock_blocker.scan.query_alpr_around",
        lambda lat, lon, radius_meters=None: [
            Camera(
                id="osm-1",
                lat=lat,
                lon=lon,
                manufacturer="Flock Safety",
                source="openstreetmap",
            ),
            Camera(
                id="osm-2",
                lat=lat + 0.001,
                lon=lon,
                manufacturer="Motorola",
                source="openstreetmap",
            ),
        ],
    )
    result = scan_area(37.77, -122.42, 1000, place="SF")
    assert result["count"] == 2
    assert result["flock_count"] == 1
    assert result["place"] == "SF"
