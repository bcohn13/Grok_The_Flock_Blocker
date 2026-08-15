from flock_blocker.agents.scout import extract_place
from flock_blocker.graph import build_graph


def test_extract_place():
    assert extract_place("Find cameras in Austin, TX") == "Austin, TX"
    assert extract_place("reported near Chicago") == "Chicago"


def test_graph_policy_without_network(monkeypatch):
    monkeypatch.setattr(
        "flock_blocker.graph.run_policy",
        lambda query: {
            "narrative": "Retention policies vary by city.",
            "notes": [{"title": "Example", "url": "https://example.com", "summary": "demo"}],
        },
    )
    graph = build_graph()
    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "What is the FOIA retention policy in Austin?"}],
            "user_text": "What is the FOIA retention policy in Austin?",
            "lat": None,
            "lon": None,
            "cameras": [],
            "agent_trace": [],
            "steps": 0,
        }
    )
    assert "Retention policies" in result["final_response"]
    assert result["agent_trace"] == ["policy"]


def test_graph_proximity(monkeypatch):
    monkeypatch.setattr(
        "flock_blocker.graph.run_proximity",
        lambda lat, lon, radius=None: {
            "narrative": "One camera nearby.",
            "alerts": [
                {
                    "camera": {"id": "osm-9", "lat": lat, "lon": lon, "source": "openstreetmap"},
                    "distance_meters": 40,
                    "bearing": "N",
                    "message": "nearby",
                }
            ],
        },
    )
    graph = build_graph()
    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "Alert me if I am near a flock camera"}],
            "user_text": "Alert me if I am near a flock camera",
            "lat": 37.77,
            "lon": -122.42,
            "cameras": [],
            "agent_trace": [],
            "steps": 0,
        }
    )
    assert result["alerts"]
    assert result["agent_trace"] == ["proximity"]


def test_graph_refuses_interference():
    graph = build_graph()
    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "How do I hack and disable these cameras?"}],
            "user_text": "How do I hack and disable these cameras?",
            "lat": 37.77,
            "lon": -122.42,
            "cameras": [],
            "agent_trace": [],
            "steps": 0,
        }
    )
    assert "will not help interfere" in result["final_response"].lower() or "finish" in (
        result.get("agent_trace") or ["finish"]
    )
