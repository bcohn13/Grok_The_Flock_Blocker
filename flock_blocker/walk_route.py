from __future__ import annotations

from typing import Any

import httpx

from flock_blocker.config import get_settings
from flock_blocker.geo import densify_path, haversine_meters

# Pedestrian-legal OSM centerline of 4th Street, San Francisco, from Harrison
# toward Market. Consecutive points are on the same roadway, not block diagonals.
SF_FOURTH_STREET: list[tuple[float, float]] = [
    (37.780882, -122.399749),
    (37.78119, -122.400131),
    (37.781388, -122.40038),
    (37.781582, -122.400621),
    (37.781773, -122.400861),
    (37.781956, -122.40109),
    (37.782179, -122.401369),
    (37.782454, -122.401711),
    (37.782633, -122.401933),
    (37.783193, -122.402639),
    (37.783772, -122.403358),
    (37.784074, -122.403734),
    (37.784414, -122.404169),
    (37.784835, -122.404696),
    (37.785171, -122.405118),
    (37.785422, -122.40543),
    (37.78565, -122.405703),
    (37.785714, -122.405916),
]


def _osrm_urls() -> list[str]:
    settings = get_settings()
    primary = getattr(settings, "osrm_url", "https://router.project-osrm.org")
    return [
        primary.rstrip("/"),
        "https://router.project-osrm.org",
    ]


def _route_from_osrm(route: dict[str, Any], source: str) -> dict[str, Any]:
    geometry = (route.get("geometry") or {}).get("coordinates") or []
    points = [(float(latlon[1]), float(latlon[0])) for latlon in geometry]
    if len(points) < 2:
        raise ValueError("OSRM geometry was too short")
    streets: list[str] = []
    for leg in route.get("legs") or []:
        for step in leg.get("steps") or []:
            name = (step.get("name") or "").strip()
            if name and name not in streets:
                streets.append(name)
    return {
        "points": densify_path(points, 25.0),
        "streets": streets,
        "distance_meters": round(float(route.get("distance") or 0)),
        "source": source,
    }


def fetch_osrm_candidates(
    lat: float,
    lon: float,
    dest_lat: float,
    dest_lon: float,
    via: tuple[float, float] | None = None,
) -> list[dict[str, Any]]:
    """Return legal public-road driving routes, including OSRM alternatives."""
    settings = get_settings()
    if via:
        path = f"{lon},{lat};{via[1]},{via[0]};{dest_lon},{dest_lat}"
        params = {"overview": "full", "geometries": "geojson", "steps": "true"}
        label = "osrm-via"
    else:
        path = f"{lon},{lat};{dest_lon},{dest_lat}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "alternatives": "true",
        }
        label = "osrm"
    last_error: Exception | None = None
    with httpx.Client(timeout=20.0, headers={"User-Agent": settings.user_agent}) as client:
        for base in dict.fromkeys(_osrm_urls()):
            try:
                response = client.get(f"{base}/route/v1/driving/{path}", params=params)
                response.raise_for_status()
                routes: list[dict[str, Any]] = []
                for index, route in enumerate(response.json().get("routes") or []):
                    source = f"{label}-{index}" if index else label
                    routes.append(_route_from_osrm(route, source))
                if routes:
                    return routes
            except Exception as exc:
                last_error = exc
                continue
    if last_error:
        raise last_error
    return []


def fetch_osrm_route(lat: float, lon: float, dest_lat: float, dest_lon: float) -> dict[str, Any]:
    """Snap start/end to the public road network and return the on-road geometry."""
    candidates = fetch_osrm_candidates(lat, lon, dest_lat, dest_lon)
    if not candidates:
        raise RuntimeError("OSRM lookup failed")
    return candidates[0]


def fallback_route(lat: float, lon: float) -> dict[str, Any]:
    """Use the SF 4th Street centerline when routing is unavailable."""
    start = min(SF_FOURTH_STREET, key=lambda p: haversine_meters(lat, lon, p[0], p[1]))
    start_index = SF_FOURTH_STREET.index(start)
    points = densify_path(SF_FOURTH_STREET[start_index:], 18.0)
    distance = 0.0
    for a, b in zip(points, points[1:]):
        distance += haversine_meters(a[0], a[1], b[0], b[1])
    return {
        "points": points,
        "streets": ["4th Street"],
        "distance_meters": round(distance),
        "source": "osm-centerline",
    }


def walking_route(
    lat: float,
    lon: float,
    dest_lat: float | None = None,
    dest_lon: float | None = None,
    reverse: bool = False,
) -> dict[str, Any]:
    if reverse and dest_lat is not None and dest_lon is not None:
        lat, lon, dest_lat, dest_lon = dest_lat, dest_lon, lat, lon
        reverse = False
    if dest_lat is None or dest_lon is None:
        nearest = min(SF_FOURTH_STREET, key=lambda p: haversine_meters(lat, lon, p[0], p[1]))
        if haversine_meters(lat, lon, nearest[0], nearest[1]) < 500:
            result = fallback_route(lat, lon)
        else:
            result = fetch_osrm_route(lat, lon, lat + 0.005, lon)
    else:
        try:
            result = fetch_osrm_route(lat, lon, dest_lat, dest_lon)
        except Exception:
            nearest = min(SF_FOURTH_STREET, key=lambda p: haversine_meters(lat, lon, p[0], p[1]))
            if haversine_meters(lat, lon, nearest[0], nearest[1]) < 800:
                result = fallback_route(lat, lon)
            else:
                raise
    if reverse:
        result = {
            **result,
            "points": list(reversed(result["points"])),
            "streets": list(reversed(result.get("streets") or [])),
            "source": f"{result.get('source')}-reverse",
        }
    return result
