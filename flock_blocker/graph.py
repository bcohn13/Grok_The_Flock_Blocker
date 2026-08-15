from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from flock_blocker.agents.policy import run_policy
from flock_blocker.agents.proximity import run_proximity
from flock_blocker.agents.scout import run_scout
from flock_blocker.agents.supervisor import route_request
from flock_blocker.agents.verifier import run_verifier


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_text: str
    lat: float | None
    lon: float | None
    radius_meters: int | None
    next_agent: str
    steps: int
    cameras: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    policy_notes: list[dict[str, Any]]
    agent_trace: list[str]
    final_response: str


def _user_text(state: AgentState) -> str:
    if state.get("user_text"):
        return state["user_text"]
    messages = state.get("messages") or []
    for message in reversed(messages):
        content = getattr(message, "content", None) or (
            message.get("content") if isinstance(message, dict) else None
        )
        if content:
            return str(content)
    return ""


def supervisor_node(state: AgentState) -> dict[str, Any]:
    text = _user_text(state)
    called = set(state.get("agent_trace") or [])
    has_location = state.get("lat") is not None and state.get("lon") is not None
    has_cameras = bool(state.get("cameras"))
    steps = int(state.get("steps") or 0)
    nxt = route_request(text, has_location, has_cameras, steps)
    if nxt in called:
        lowered = text.lower()
        wants_nearby = any(word in lowered for word in ("near", "nearby", "alert", "around me"))
        if "scout" in called and wants_nearby and has_location and "proximity" not in called:
            nxt = "proximity"
        elif "scout" in called and "verify" in lowered and "verifier" not in called:
            nxt = "verifier"
        else:
            nxt = "finish"
    return {"next_agent": nxt, "steps": steps}


def scout_node(state: AgentState) -> dict[str, Any]:
    result = run_scout(
        _user_text(state),
        lat=state.get("lat"),
        lon=state.get("lon"),
        radius_meters=state.get("radius_meters"),
    )
    trace = list(state.get("agent_trace") or [])
    trace.append("scout")
    return {
        "cameras": result["cameras"],
        "findings": result["findings"],
        "lat": result.get("lat", state.get("lat")),
        "lon": result.get("lon", state.get("lon")),
        "final_response": result["narrative"],
        "agent_trace": trace,
        "next_agent": "supervisor",
        "steps": int(state.get("steps") or 0) + 1,
        "messages": [{"role": "assistant", "content": result["narrative"]}],
    }


def proximity_node(state: AgentState) -> dict[str, Any]:
    lat, lon = state.get("lat"), state.get("lon")
    if lat is None or lon is None:
        message = (
            "Proximity alerts need your coordinates. Share them in the browser "
            "(opt-in) or pass lat/lon. Location is used for this check only."
        )
        return {
            "final_response": message,
            "next_agent": "finish",
            "steps": int(state.get("steps") or 0) + 1,
            "agent_trace": [*list(state.get("agent_trace") or []), "proximity"],
            "messages": [{"role": "assistant", "content": message}],
        }
    result = run_proximity(float(lat), float(lon), state.get("radius_meters"))
    trace = list(state.get("agent_trace") or [])
    trace.append("proximity")
    return {
        "alerts": result["alerts"],
        "cameras": [item["camera"] for item in result["alerts"]] or state.get("cameras") or [],
        "final_response": result["narrative"],
        "agent_trace": trace,
        "next_agent": "finish",
        "steps": int(state.get("steps") or 0) + 1,
        "messages": [{"role": "assistant", "content": result["narrative"]}],
    }


def verifier_node(state: AgentState) -> dict[str, Any]:
    result = run_verifier(state.get("cameras") or [], notes=_user_text(state))
    trace = list(state.get("agent_trace") or [])
    trace.append("verifier")
    return {
        "cameras": result["cameras"],
        "final_response": result["narrative"],
        "agent_trace": trace,
        "next_agent": "finish",
        "steps": int(state.get("steps") or 0) + 1,
        "messages": [{"role": "assistant", "content": result["narrative"]}],
    }


def policy_node(state: AgentState) -> dict[str, Any]:
    result = run_policy(_user_text(state))
    trace = list(state.get("agent_trace") or [])
    trace.append("policy")
    return {
        "policy_notes": result["notes"],
        "final_response": result["narrative"],
        "agent_trace": trace,
        "next_agent": "finish",
        "steps": int(state.get("steps") or 0) + 1,
        "messages": [{"role": "assistant", "content": result["narrative"]}],
    }


def finish_node(state: AgentState) -> dict[str, Any]:
    existing = state.get("final_response")
    if existing:
        return {}
    message = (
        "I can search public reports and OpenStreetMap for ALPR / Flock cameras, "
        "check whether you (opt-in) are near a mapped camera, verify source confidence, "
        "or summarize public policy. I will not help interfere with cameras or track other people."
    )
    return {
        "final_response": message,
        "messages": [{"role": "assistant", "content": message}],
        "agent_trace": [*list(state.get("agent_trace") or []), "finish"],
    }


def _route(state: AgentState) -> Literal["scout", "proximity", "verifier", "policy", "finish"]:
    nxt = state.get("next_agent") or "finish"
    if nxt in {"scout", "proximity", "verifier", "policy", "finish"}:
        return nxt  # type: ignore[return-value]
    return "finish"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("scout", scout_node)
    graph.add_node("proximity", proximity_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("policy", policy_node)
    graph.add_node("finish", finish_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route,
        {
            "scout": "scout",
            "proximity": "proximity",
            "verifier": "verifier",
            "policy": "policy",
            "finish": "finish",
        },
    )
    graph.add_edge("scout", "supervisor")
    graph.add_edge("proximity", "finish")
    graph.add_edge("verifier", "finish")
    graph.add_edge("policy", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


_APP = None


def get_graph():
    global _APP
    if _APP is None:
        _APP = build_graph()
    return _APP


def run_turn(
    text: str,
    lat: float | None = None,
    lon: float | None = None,
    radius_meters: int | None = None,
    cameras: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    graph = get_graph()
    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": text}],
            "user_text": text,
            "lat": lat,
            "lon": lon,
            "radius_meters": radius_meters,
            "cameras": cameras or [],
            "findings": [],
            "alerts": [],
            "policy_notes": [],
            "agent_trace": [],
            "steps": 0,
        }
    )
    return {
        "response": result.get("final_response") or "",
        "agent_trace": result.get("agent_trace") or [],
        "cameras": result.get("cameras") or [],
        "findings": result.get("findings") or [],
        "alerts": result.get("alerts") or [],
        "policy_notes": result.get("policy_notes") or [],
        "lat": result.get("lat"),
        "lon": result.get("lon"),
    }
