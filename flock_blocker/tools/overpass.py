from __future__ import annotations

import hashlib
from typing import Any

import httpx

from flock_blocker.config import get_settings
from flock_blocker.models import Camera

OVERPASS_QUERY = """
[out:json][timeout:25];
(
  node["surveillance:type"="ALPR"](around:{radius},{lat},{lon});
  node["man_made"="surveillance"]["camera:type"="alpr"](around:{radius},{lat},{lon});
);
out body;
"""


def _camera_id(osm_id: int) -> str:
    return f"osm-{osm_id}"


def node_to_camera(node: dict[str, Any]) -> Camera:
    tags = {str(k): str(v) for k, v in (node.get("tags") or {}).items()}
    manufacturer = tags.get("manufacturer") or tags.get("brand")
    street = tags.get("addr:street") or tags.get("street")
    city = tags.get("addr:city") or tags.get("city")
    osm_id = int(node["id"])
    return Camera(
        id=_camera_id(osm_id),
        lat=float(node["lat"]),
        lon=float(node["lon"]),
        manufacturer=manufacturer,
        camera_type="ALPR",
        street=street,
        city=city,
        source="openstreetmap",
        source_url=f"https://www.openstreetmap.org/node/{osm_id}",
        mapped_at=node.get("timestamp"),
        confidence="high" if manufacturer else "medium",
        notes="Publicly mapped ALPR node on OpenStreetMap.",
        tags=tags,
    )


OVERPASS_FALLBACKS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def query_alpr_around(lat: float, lon: float, radius_meters: int | None = None) -> list[Camera]:
    """Query the public Overpass API for OSM nodes tagged as ALPR cameras."""
    settings = get_settings()
    radius = radius_meters or settings.search_radius_meters
    query = OVERPASS_QUERY.format(radius=int(radius), lat=lat, lon=lon)
    urls = [settings.overpass_url, *[url for url in OVERPASS_FALLBACKS if url != settings.overpass_url]]
    last_error: Exception | None = None
    payload: dict[str, Any] | None = None
    with httpx.Client(timeout=40.0, headers={"User-Agent": settings.user_agent}) as client:
        for url in urls:
            try:
                response = client.post(url, data={"data": query})
                response.raise_for_status()
                payload = response.json()
                break
            except Exception as exc:
                last_error = exc
                continue
    if payload is None:
        raise last_error or RuntimeError("Overpass lookup failed")
    cameras: list[Camera] = []
    for element in payload.get("elements", []):
        if element.get("type") != "node":
            continue
        cameras.append(node_to_camera(element))
    return cameras


def stable_news_id(url: str, lat: float, lon: float) -> str:
    digest = hashlib.sha256(f"{url}:{lat:.5f}:{lon:.5f}".encode()).hexdigest()[:12]
    return f"news-{digest}"
