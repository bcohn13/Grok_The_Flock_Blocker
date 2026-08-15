from __future__ import annotations

from typing import Any

from flock_blocker.llm import llm_text
from flock_blocker.models import Camera

VERIFIER_SYSTEM = """You score how trustworthy a reported ALPR camera record is.
Prefer OpenStreetMap nodes with a manufacturer tag. Treat city-level news pins as low
confidence. Never claim a camera is confirmed unless the source is a public map node
or a primary public document. Return a short paragraph."""


def score_camera(camera: Camera | dict[str, Any]) -> str:
    data = camera if isinstance(camera, dict) else camera.model_dump()
    source = data.get("source")
    manufacturer = data.get("manufacturer")
    if source == "openstreetmap" and manufacturer:
        return "high"
    if source == "openstreetmap":
        return "medium"
    if source == "seed":
        return "low"
    return "low"


def run_verifier(cameras: list[dict[str, Any]] | None = None, notes: str = "") -> dict[str, Any]:
    cameras = cameras or []
    scored = []
    for camera in cameras:
        confidence = score_camera(camera)
        item = dict(camera)
        item["confidence"] = confidence
        scored.append(item)

    counts = {"high": 0, "medium": 0, "low": 0}
    for item in scored:
        counts[item["confidence"]] += 1

    llm_summary = llm_text(
        VERIFIER_SYSTEM,
        f"Notes: {notes}\nCameras: {scored[:20]}",
    )
    if llm_summary:
        narrative = llm_summary
    else:
        narrative = (
            f"Verified {len(scored)} records: {counts['high']} high, "
            f"{counts['medium']} medium, {counts['low']} low confidence. "
            "OSM ALPR tags with a manufacturer are strongest; news pins are city-level only."
        )
    return {"narrative": narrative, "cameras": scored, "counts": counts}
