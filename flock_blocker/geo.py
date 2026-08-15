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
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    degrees = (math.degrees(math.atan2(x, y)) + 360) % 360
    labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return labels[int((degrees + 22.5) / 45) % 8]


def bbox_from_point(lat: float, lon: float, radius_meters: float) -> tuple[float, float, float, float]:
    """Return (south, west, north, east) bounding box around a point."""
    d_lat = radius_meters / 111_320
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    d_lon = radius_meters / (111_320 * cos_lat)
    return (lat - d_lat, lon - d_lon, lat + d_lat, lon + d_lon)
