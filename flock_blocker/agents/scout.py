from __future__ import annotations

import json
import re
from typing import Any

from flock_blocker.llm import llm_text
from flock_blocker.models import Camera, ScoutFinding
from flock_blocker.store import upsert_cameras
from flock_blocker.tools.geocode import geocode_place
from flock_blocker.tools.overpass import query_alpr_around, stable_news_id
from flock_blocker.tools.web_search import search_web

SCOUT_SYSTEM = """You summarize publicly reported ALPR / Flock camera information.
Only use the search snippets and OSM results provided. Do not invent coordinates.
If a result is about policy rather than a location, say so. Keep the summary concise.
Never suggest interfering with cameras, spoofing plates, or accessing private systems.
"""


def extract_place(text: str) -> str | None:
    """Best-effort place name from a user request."""
    patterns = [
        r"(?:in|near|around|at)\s+([A-Z][A-Za-z .'-]+(?:,\s*[A-Z]{2})?)",
        r"([A-Z][A-Za-z .'-]+,\s*[A-Z]{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip(" .")
    return None


def run_scout(
    query: str,
    lat: float | None = None,
    lon: float | None = None,
    radius_meters: int | None = None,
) -> dict[str, Any]:
    place = extract_place(query)
    resolved_label = None
    if lat is None or lon is None:
        if place:
            geo = geocode_place(place)
            if geo:
                lat, lon = float(geo["lat"]), float(geo["lon"])
                resolved_label = str(geo["label"])
        if lat is None or lon is None:
            # Default demo city if the user did not give a place or coordinates.
            geo = geocode_place(place or "San Francisco, CA")
            if geo:
                lat, lon = float(geo["lat"]), float(geo["lon"])
                resolved_label = str(geo["label"])

    osm_cameras: list[Camera] = []
    osm_error = None
    if lat is not None and lon is not None:
        try:
            osm_cameras = query_alpr_around(lat, lon, radius_meters)
        except Exception as exc:  # network flake should not kill the agent
            osm_error = str(exc)

    search_query = (
        f"Flock Safety ALPR cameras reported locations {place or query} "
        "news OR FOIA OR city council"
    )
    web_error = None
    raw_hits: list[dict[str, str]] = []
    try:
        raw_hits = search_web(search_query, max_results=6)
    except Exception as exc:
        web_error = str(exc)

    findings = [
        ScoutFinding(
            title=hit["title"],
            url=hit["url"],
            snippet=hit["snippet"],
            city_hint=place,
        )
        for hit in raw_hits
        if hit.get("url")
    ]

    news_cameras: list[Camera] = []
    if lat is not None and lon is not None:
        for finding in findings[:3]:
            news_cameras.append(
                Camera(
                    id=stable_news_id(finding.url, lat, lon),
                    lat=lat,
                    lon=lon,
                    manufacturer=None,
                    city=place,
                    source="news",
                    source_url=finding.url,
                    confidence="low",
                    notes=(
                        "City-level pin from a public news/web report, not a precise "
                        f"camera coordinate. {finding.title}"
                    ),
                )
            )

    added = upsert_cameras(osm_cameras)
    summary_source = {
        "place": resolved_label or place,
        "lat": lat,
        "lon": lon,
        "osm_count": len(osm_cameras),
        "osm_added": added,
        "osm_error": osm_error,
        "web_error": web_error,
        "findings": [f.model_dump() for f in findings],
        "osm_sample": [c.model_dump() for c in osm_cameras[:12]],
        "news_pins": [c.model_dump() for c in news_cameras],
    }
    llm_summary = llm_text(SCOUT_SYSTEM, json.dumps(summary_source, indent=2)[:8000])
    if llm_summary:
        narrative = llm_summary
    else:
        narrative = _fallback_summary(summary_source)

    return {
        "narrative": narrative,
        "cameras": [c.model_dump() for c in osm_cameras],
        "findings": [f.model_dump() for f in findings],
        "place": resolved_label or place,
        "lat": lat,
        "lon": lon,
    }


def _fallback_summary(payload: dict[str, Any]) -> str:
    place = payload.get("place") or "the requested area"
    lines = [
        f"Scout results for {place}.",
        f"OpenStreetMap ALPR-tagged nodes nearby: {payload['osm_count']}.",
    ]
    if payload.get("osm_error"):
        lines.append(f"OSM lookup issue: {payload['osm_error']}")
    if payload.get("findings"):
        lines.append("Public web reports:")
        for finding in payload["findings"][:5]:
            lines.append(f"- {finding['title']} ({finding['url']})")
    else:
        lines.append("No web reports were returned for this query.")
    lines.append(
        "Coordinates come from public OSM tags or city-level news pins. "
        "Treat them as reported, not live confirmation."
    )
    return "\n".join(lines)
