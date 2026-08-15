from flock_blocker.geo import haversine_meters
from flock_blocker.walk_route import SF_FOURTH_STREET, fallback_route, walking_route


def test_fourth_street_steps_stay_on_one_block_face():
    for start, end in zip(SF_FOURTH_STREET, SF_FOURTH_STREET[1:]):
        assert haversine_meters(start[0], start[1], end[0], end[1]) < 120


def test_fallback_route_is_densified(monkeypatch):
    result = fallback_route(37.780882, -122.399749)
    assert result["source"] == "osm-centerline"
    assert result["streets"] == ["4th Street"]
    assert len(result["points"]) > len(SF_FOURTH_STREET) - 2
    for start, end in zip(result["points"], result["points"][1:]):
        assert haversine_meters(start[0], start[1], end[0], end[1]) <= 22


def test_walking_route_uses_osrm_geometry(monkeypatch):
    monkeypatch.setattr(
        "flock_blocker.walk_route.fetch_osrm_route",
        lambda lat, lon, dest_lat, dest_lon: {
            "points": [(lat, lon), (dest_lat, dest_lon)],
            "streets": ["Congress Avenue"],
            "distance_meters": 100,
            "source": "osrm-foot",
        },
    )
    result = walking_route(30.2672, -97.7431, 30.2742, -97.7404)
    assert result["source"] == "osrm-foot"
    assert result["streets"] == ["Congress Avenue"]


def test_walking_route_uses_fourth_street_in_soma():
    result = walking_route(37.7809, -122.3998)
    assert result["source"] == "osm-centerline"
    assert result["streets"] == ["4th Street"]


def test_walking_route_reverse_starts_at_destination(monkeypatch):
    seen: dict[str, tuple[float, float, float, float]] = {}

    def fake(lat, lon, dest_lat, dest_lon):
        seen["coords"] = (lat, lon, dest_lat, dest_lon)
        return {
            "points": [(lat, lon), (dest_lat, dest_lon)],
            "streets": ["4th Street"],
            "distance_meters": 100,
            "source": "osrm",
        }

    monkeypatch.setattr("flock_blocker.walk_route.fetch_osrm_route", fake)
    result = walking_route(37.78, -122.40, 37.79, -122.39, reverse=True)
    assert seen["coords"] == (37.79, -122.39, 37.78, -122.40)
    assert result["points"][0] == (37.79, -122.39)
    assert result["points"][-1] == (37.78, -122.40)


def test_walking_route_reverse_fourth_street_without_dest():
    forward = walking_route(37.7809, -122.3998)
    backward = walking_route(37.7809, -122.3998, reverse=True)
    assert backward["points"] == list(reversed(forward["points"]))
    assert backward["source"] == "osm-centerline-reverse"
