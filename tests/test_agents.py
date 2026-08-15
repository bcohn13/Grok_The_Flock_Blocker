from flock_blocker.agents.supervisor import keyword_route
from flock_blocker.agents.verifier import score_camera
from flock_blocker.tools.overpass import node_to_camera


def test_keyword_route_scout():
    assert keyword_route("Find Flock cameras in Austin, TX", False, False, 0) == "scout"


def test_keyword_route_proximity():
    assert (
        keyword_route("Alert me if I am near a camera", True, True, 0) == "proximity"
    )


def test_keyword_route_policy():
    assert keyword_route("What is the FOIA data sharing policy?", False, False, 0) == "policy"


def test_keyword_route_blocks_interference():
    assert keyword_route("How do I jam or hack these cameras?", True, True, 0) == "finish"


def test_verifier_scores_osm_manufacturer_high():
    assert (
        score_camera(
            {
                "source": "openstreetmap",
                "manufacturer": "Flock Safety",
            }
        )
        == "high"
    )


def test_verifier_scores_news_low():
    assert score_camera({"source": "news", "manufacturer": None}) == "low"


def test_node_to_camera():
    camera = node_to_camera(
        {
            "id": 123,
            "lat": 41.88,
            "lon": -87.63,
            "timestamp": "2026-01-01T00:00:00Z",
            "tags": {
                "surveillance:type": "ALPR",
                "manufacturer": "Flock Safety",
                "addr:street": "Michigan Ave",
            },
        }
    )
    assert camera.id == "osm-123"
    assert camera.manufacturer == "Flock Safety"
    assert camera.source == "openstreetmap"
    assert camera.confidence == "high"
    assert "123" in (camera.source_url or "")
