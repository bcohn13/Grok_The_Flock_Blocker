from __future__ import annotations

from typing import Any

from flock_blocker.geo import bearing_degrees, destination_point, haversine_meters
from flock_blocker.models import Camera
from flock_blocker.scan import scan_area
from flock_blocker.store import all_cameras
from flock_blocker.tools.geocode import geocode_place
from flock_blocker.walk_route import fetch_osrm_candidates

CAMERA_BUFFER_METERS = 70
MAX_DETOUR_RATIO = 2.2
DISCLAIMER = (
    "Among legal public-road options only. Public ALPR maps are incomplete, "
    "so a quieter route is not camera-free and is not a way to evade law enforcement."
)


def cameras_along_path(
    points: list[tuple[float, float]],
    cameras: list[Camera],
    radius_meters: float = CAMERA_BUFFER_METERS,
) -> list[dict[str, Any]]:
    """Unique mapped cameras that sit within radius of the roadway polyline."""
    hits: dict[str, dict[str, Any]] = {}
    sample = points[:: max(1, len(points) // 250)] or points
    for camera in cameras:
        closest = None
        for lat, lon in sample:
            distance = haversine_meters(camera.lat, camera.lon, lat, lon)
            if distance <= radius_meters and (closest is None or distance < closest):
                closest = distance
        if closest is not None:
            hits[camera.id] = {
                "id": camera.id,
                "lat": camera.lat,
                "lon": camera.lon,
                "manufacturer": camera.manufacturer,
                "distance_meters": round(closest, 1),
            }
    return sorted(hits.values(), key=lambda item: item["distance_meters"])


def _waypoints(lat: float, lon: float, dest_lat: float, dest_lon: float) -> list[tuple[float, float]]:
    heading = bearing_degrees(lat, lon, dest_lat, dest_lon)
    left = (heading - 90) % 360
    right = (heading + 90) % 360
    mid_lat = (lat + dest_lat) / 2
    mid_lon = (lon + dest_lon) / 2
    third_lat = lat + (dest_lat - lat) / 3
    third_lon = lon + (dest_lon - lon) / 3
    points: list[tuple[float, float]] = []
    for origin_lat, origin_lon in ((mid_lat, mid_lon), (third_lat, third_lon)):
        for bearing in (left, right):
            for meters in (700, 1400):
                points.append(destination_point(origin_lat, origin_lon, meters, bearing))
    return points


def _score_candidate(route: dict[str, Any], cameras: list[Camera]) -> dict[str, Any]:
    along = cameras_along_path(route["points"], cameras)
    flock = sum(1 for item in along if (item.get("manufacturer") or "").lower().startswith("flock"))
    return {
        **route,
        "camera_count": len(along),
        "flock_count": flock,
        "cameras": along,
    }


def _resolve_end(
    lat: float | None,
    lon: float | None,
    name: str | None,
    fallback_lat: float | None = None,
    fallback_lon: float | None = None,
    default_label: str = "Dropped pin",
    missing: str = "Provide a place name or map coordinates.",
) -> tuple[float, float, str]:
    label = (name or "").strip() or default_label
    if lat is not None and lon is not None:
        return float(lat), float(lon), label
    if name and name.strip():
        geo = geocode_place(name)
        if geo is None:
            raise ValueError(f"Could not geocode {name!r}")
        return float(geo["lat"]), float(geo["lon"]), str(geo.get("label") or name)
    if fallback_lat is not None and fallback_lon is not None:
        return float(fallback_lat), float(fallback_lon), label
    raise ValueError(missing)


def plan_privacy_route(
    lat: float,
    lon: float,
    dest_lat: float | None = None,
    dest_lon: float | None = None,
    destination: str | None = None,
    origin: str | None = None,
    origin_lat: float | None = None,
    origin_lon: float | None = None,
    reverse: bool = False,
    scan: bool = True,
) -> dict[str, Any]:
    dest_lat, dest_lon, dest_label = _resolve_end(
        dest_lat,
        dest_lon,
        destination,
        default_label="Route to",
        missing="Provide a destination name or dest_lat/dest_lon.",
    )
    lat, lon, origin_label = _resolve_end(
        origin_lat,
        origin_lon,
        origin,
        fallback_lat=lat,
        fallback_lon=lon,
        default_label="Route from",
        missing="Provide an origin name or origin_lat/origin_lon.",
    )
    user_origin = (lat, lon, origin_label)
    user_dest = (dest_lat, dest_lon, dest_label)
    if reverse:
        lat, lon, dest_lat, dest_lon = dest_lat, dest_lon, lat, lon
        origin_label, dest_label = dest_label, origin_label
    if haversine_meters(lat, lon, dest_lat, dest_lon) < 80:
        raise ValueError("Origin and destination are too close to plan a route.")

    if scan:
        mid_lat = (lat + dest_lat) / 2
        mid_lon = (lon + dest_lon) / 2
        radius = min(12_000, max(2_000, int(haversine_meters(lat, lon, dest_lat, dest_lon) + 1500)))
        try:
            scan_area(mid_lat, mid_lon, radius, place=dest_label)
        except Exception:
            pass

    cameras = [cam for cam in all_cameras() if cam.source != "seed"]
    raw: list[dict[str, Any]] = []
    try:
        raw.extend(fetch_osrm_candidates(lat, lon, dest_lat, dest_lon))
    except Exception:
        raw = []
    for via in _waypoints(lat, lon, dest_lat, dest_lon)[:6]:
        try:
            raw.extend(fetch_osrm_candidates(lat, lon, dest_lat, dest_lon, via=via))
        except Exception:
            continue
    if not raw:
        raise RuntimeError("Could not fetch a public-road route.")

    scored = [_score_candidate(route, cameras) for route in raw]
    shortest = min(item["distance_meters"] for item in scored) or 1
    viable = [
        item
        for item in scored
        if item["distance_meters"] <= shortest * MAX_DETOUR_RATIO
    ] or scored
    viable.sort(key=lambda item: (item["camera_count"], item["flock_count"], item["distance_meters"]))
    # Drop near-duplicate geometries (same camera count and ~same length).
    unique: list[dict[str, Any]] = []
    for item in viable:
        if any(
            abs(item["distance_meters"] - other["distance_meters"]) < 80
            and item["camera_count"] == other["camera_count"]
            for other in unique
        ):
            continue
        unique.append(item)
    recommended = unique[0]
    baseline = min(unique, key=lambda item: item["distance_meters"])
    saved = max(0, baseline["camera_count"] - recommended["camera_count"])
    narrative = (
        f"Recommended public-road route from {origin_label} to {dest_label} has "
        f"{recommended['camera_count']} mapped ALPR camera(s) within {CAMERA_BUFFER_METERS} m "
        f"of the roadway"
        + (f", {saved} fewer than the shortest option" if saved else "")
        + f" ({round(recommended['distance_meters'] / 1000, 2)} km). {DISCLAIMER}"
    )
    return {
        "origin": user_origin[2],
        "origin_lat": user_origin[0],
        "origin_lon": user_origin[1],
        "destination": user_dest[2],
        "dest_lat": user_dest[0],
        "dest_lon": user_dest[1],
        "reverse": reverse,
        "recommended": _dump_route(recommended),
        "alternatives": [_dump_route(item) for item in unique[:4]],
        "narrative": narrative,
        "disclaimer": DISCLAIMER,
        "camera_buffer_meters": CAMERA_BUFFER_METERS,
    }


def _dump_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "points": [{"lat": lat, "lon": lon} for lat, lon in route["points"]],
        "streets": route.get("streets") or [],
        "steps": route.get("steps") or [],
        "distance_meters": route["distance_meters"],
        "duration_seconds": route.get("duration_seconds") or 0,
        "source": route.get("source"),
        "camera_count": route["camera_count"],
        "flock_count": route["flock_count"],
        "cameras": route.get("cameras") or [],
    }
