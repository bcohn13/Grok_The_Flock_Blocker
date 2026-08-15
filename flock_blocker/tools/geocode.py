from __future__ import annotations

import httpx

from flock_blocker.config import get_settings


def geocode_place(place: str) -> dict[str, float | str] | None:
    """Resolve a city or address to coordinates via OSM Nominatim."""
    settings = get_settings()
    params = {"q": place, "format": "json", "limit": 1}
    headers = {"User-Agent": settings.user_agent}
    with httpx.Client(timeout=20.0, headers=headers) as client:
        response = client.get(settings.nominatim_url, params=params)
        response.raise_for_status()
        payload = response.json()
    if not payload:
        return None
    hit = payload[0]
    return {
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
        "label": hit.get("display_name") or place,
    }
