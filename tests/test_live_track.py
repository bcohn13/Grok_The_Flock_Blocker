from flock_blocker.live_track import assess_live_status


def _alert(distance: float, manufacturer: str = "Flock Safety", bearing: str = "NE") -> dict:
    return {
        "camera": {"id": "osm-1", "manufacturer": manufacturer, "lat": 37.78, "lon": -122.4},
        "distance_meters": distance,
        "bearing": bearing,
    }


def test_live_status_clear():
    status = assess_live_status([], 400)
    assert status["level"] == "clear"
    assert status["flock_count"] == 0
    assert "Recommended action" in status["recommended_action"]
    assert "not a way to evade" in status["recommended_action"]
    assert "LIVE · CLEAR" in status["hud"]


def test_live_status_watch_distant_alpr():
    status = assess_live_status([_alert(220, "Generic ALPR", "S")], 400)
    assert status["level"] == "watch"
    assert status["flock_count"] == 0
    assert "Recommend route" in status["recommended_action"]
    assert "WATCH" in status["hud"]


def test_live_status_nearby_flock():
    status = assess_live_status([_alert(90)], 400)
    assert status["level"] == "nearby"
    assert status["flock_count"] == 1
    assert "FLOCK NEARBY" in status["hud"]
    assert "may be scanned" in status["recommended_action"]


def test_live_status_close_flock():
    status = assess_live_status([_alert(20)], 400)
    assert status["level"] == "close"
    assert "FLOCK CLOSE" in status["hud"]
    assert "proceed legally" in status["recommended_action"]
    assert "jam" not in status["recommended_action"].lower()
    assert "cover" not in status["recommended_action"].lower()


def test_live_status_approaching_mentions_moving_closer():
    status = assess_live_status([_alert(80)], 400, previous_nearest_meters=120)
    assert status["trend"] == "approaching"
    assert "moving closer" in status["recommended_action"]


def test_live_status_receding():
    status = assess_live_status([_alert(120)], 400, previous_nearest_meters=80)
    assert status["trend"] == "receding"
    assert "farther away" in status["recommended_action"]
