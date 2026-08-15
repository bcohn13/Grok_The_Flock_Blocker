from __future__ import annotations

import httpx

from flock_blocker.config import get_settings


def _photon_label(props: dict, query: str) -> str:
    name = str(props.get("name") or props.get("street") or query).strip()
    parts = [name]
    for key in ("housenumber", "street", "district", "city", "state", "country"):
        value = props.get(key)
        if not value:
            continue
        text = str(value).strip()
        if text and text.lower() not in name.lower() and text not in parts:
            parts.append(text)
    return ", ".join(parts)


def _search_photon(
    query: str,
    lat: float | None,
    lon: float | None,
    limit: int,
) -> list[dict[str, float | str]]:
    settings = get_settings()
    params: dict[str, str | int | float] = {"q": query, "limit": limit}
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon
    with httpx.Client(timeout=12.0, headers={"User-Agent": settings.user_agent}) as client:
        response = client.get("https://photon.komoot.io/api/", params=params)
        response.raise_for_status()
        payload = response.json()
    hits: list[dict[str, float | str]] = []
    for feature in payload.get("features") or []:
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        props = feature.get("properties") or {}
        hits.append(
            {
                "lat": float(coords[1]),
                "lon": float(coords[0]),
                "label": _photon_label(props, query),
            }
        )
    return hits


def _search_nominatim(
    query: str,
    lat: float | None,
    lon: float | None,
    limit: int,
) -> list[dict[str, float | str]]:
    settings = get_settings()
    params: dict[str, str | int | float] = {
        "q": query,
        "format": "json",
        "limit": limit,
        "addressdetails": 0,
    }
    if lat is not None and lon is not None:
        delta = 0.35
        params["viewbox"] = f"{lon - delta},{lat + delta},{lon + delta},{lat - delta}"
    with httpx.Client(timeout=20.0, headers={"User-Agent": settings.user_agent}) as client:
        response = client.get(settings.nominatim_url, params=params)
        response.raise_for_status()
        payload = response.json()
    hits: list[dict[str, float | str]] = []
    for hit in payload or []:
        hits.append(
            {
                "lat": float(hit["lat"]),
                "lon": float(hit["lon"]),
                "label": str(hit.get("display_name") or query),
            }
        )
    return hits


def search_places(
    query: str,
    lat: float | None = None,
    lon: float | None = None,
    limit: int = 5,
) -> list[dict[str, float | str]]:
    """Maps-style place search: Photon first, Nominatim fallback."""
    query = (query or "").strip()
    if len(query) < 2:
        return []
    try:
        hits = _search_photon(query, lat, lon, limit)
        if hits:
            return hits[:limit]
    except Exception:
        hits = []
    try:
        hits = _search_nominatim(query, lat, lon, limit)
    except Exception:
        hits = []
    return hits[:limit]


def geocode_place(place: str) -> dict[str, float | str] | None:
    """Resolve a city, address, or landmark to coordinates."""
    hits = search_places(place, limit=1)
    return hits[0] if hits else None
