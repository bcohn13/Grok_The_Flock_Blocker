from __future__ import annotations

import re
from typing import Literal

from flock_blocker.llm import llm_text

AgentName = Literal["scout", "proximity", "verifier", "policy", "finish"]

SUPERVISOR_SYSTEM = """You route a user request to one specialist agent.
Return exactly one word from this list: scout, proximity, verifier, policy, finish.

- scout: find publicly reported ALPR / Flock camera locations (web + OpenStreetMap)
- proximity: alert the requesting user if they are near a mapped camera
- verifier: score confidence of already-found camera records
- policy: public policy, FOIA, data-sharing, retention
- finish: the question is already answered or is small talk / out of scope

Never route toward hacking, disabling cameras, plate spoofing, or tracking other people.
If the user asks for those, return finish.
"""


def keyword_route(text: str, has_location: bool, has_cameras: bool, steps: int) -> AgentName:
    lowered = text.lower()
    blocked = (
        "hack",
        "exploit",
        "jam",
        "disable camera",
        "destroy",
        "spoof plate",
        "fake plate",
        "track someone",
        "track people",
    )
    if any(term in lowered for term in blocked):
        return "finish"
    if steps >= 3:
        return "finish"
    if re.search(r"\b(policy|foia|retention|data.?shar|ice|contract)\b", lowered):
        return "policy"
    if re.search(r"\b(verify|confidence|accurate|real\??)\b", lowered) and has_cameras:
        return "verifier"
    if has_location and re.search(r"\b(near|nearby|close|alert|presence|around me)\b", lowered):
        return "proximity"
    if re.search(r"\b(find|search|where|map|located|locations|cameras?)\b", lowered):
        return "scout"
    if has_location and not has_cameras:
        return "scout"
    if has_cameras and has_location:
        return "proximity"
    if steps == 0:
        return "scout"
    return "finish"


def route_request(
    text: str,
    has_location: bool,
    has_cameras: bool,
    steps: int,
) -> AgentName:
    llm_choice = llm_text(
        SUPERVISOR_SYSTEM,
        f"User: {text}\nhas_location={has_location} has_cameras={has_cameras} steps={steps}",
    )
    if llm_choice:
        token = llm_choice.strip().split()[0].lower().strip(".,:")
        if token in {"scout", "proximity", "verifier", "policy", "finish"}:
            return token  # type: ignore[return-value]
    return keyword_route(text, has_location, has_cameras, steps)
