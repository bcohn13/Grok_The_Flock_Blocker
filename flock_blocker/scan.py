from __future__ import annotations

from typing import Any

from flock_blocker.store import upsert_cameras
from flock_blocker.tools.geocode import geocode_place
from flock_blocker.tools.overpass import query_alpr_around


def scan_area(
    lat: float,
    lon: float,
    radius_meters: int = 4000,
    place: str | None = None,
) -> dict[str, Any]:
    """Load publicly mapped ALPR nodes around a point. No web search, no LLM."""
    cameras = query_alpr_around(lat, lon, radius_meters)
    added = upsert_cameras(cameras)
    flock = sum(
        1
        for camera in cameras
        if (camera.manufacturer or "").lower().startswith("flock")
    )
    return {
        "place": place,
        "lat": lat,
        "lon": lon,
        "radius_meters": radius_meters,
        "count": len(cameras),
        "added": added,
        "flock_count": flock,
        "cameras": [camera.model_dump() for camera in cameras],
    }


def scan_place(place: str, radius_meters: int = 4000) -> dict[str, Any]:
    geo = geocode_place(place)
    if geo is None:
        return {
            "place": place,
            "lat": None,
            "lon": None,
            "radius_meters": radius_meters,
            "count": 0,
            "added": 0,
            "flock_count": 0,
            "cameras": [],
            "error": f"Could not geocode {place!r}",
        }
    return scan_area(
        float(geo["lat"]),
        float(geo["lon"]),
        radius_meters,
        place=str(geo["label"]),
    )
