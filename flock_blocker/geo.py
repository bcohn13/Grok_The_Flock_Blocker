from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compass_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Cardinal direction from point 1 toward point 2."""
    degrees = bearing_degrees(lat1, lon1, lat2, lon2)
    labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return labels[int((degrees + 22.5) / 45) % 8]


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing in degrees from point 1 toward point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def densify_path(points: list[tuple[float, float]], spacing_meters: float = 20.0) -> list[tuple[float, float]]:
    """Insert points so consecutive samples are at most spacing_meters apart.

    Intended for already-on-road polylines (OSM centerlines or OSRM geometry).
    """
    if len(points) < 2:
        return list(points)
    out: list[tuple[float, float]] = [points[0]]
    for start, end in zip(points, points[1:]):
        distance = haversine_meters(start[0], start[1], end[0], end[1])
        steps = max(1, math.ceil(distance / spacing_meters)) if distance else 1
        for i in range(1, steps + 1):
            t = i / steps
            out.append((start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t))
        if out[-1] != end:
            out.append(end)
    return out


def destination_point(lat: float, lon: float, distance_meters: float, bearing_degrees: float) -> tuple[float, float]:
    """Travel `distance_meters` from a point along a compass bearing."""
    angular = distance_meters / EARTH_RADIUS_M
    bearing = math.radians(bearing_degrees)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def bbox_from_point(lat: float, lon: float, radius_meters: float) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) bounding box around a point."""
    d_lat = radius_meters / 111_320
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    d_lon = radius_meters / (111_320 * cos_lat)
    return (lat - d_lat, lon - d_lon, lat + d_lat, lon + d_lon)
