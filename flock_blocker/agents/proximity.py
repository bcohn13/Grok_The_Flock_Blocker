from __future__ import annotations

from typing import Any

from flock_blocker.config import get_settings
from flock_blocker.geo import compass_bearing
from flock_blocker.llm import llm_text
from flock_blocker.models import NearbyAlert
from flock_blocker.store import cameras_near, upsert_cameras
from flock_blocker.tools.overpass import query_alpr_around

PROXIMITY_SYSTEM = """You write short, calm awareness notices for a person who opted in
to check whether they are near a publicly mapped ALPR camera.
Rules:
- Address only the requesting user. Never report their location to anyone else.
- Do not suggest evading police, covering plates, damaging cameras, or jamming signals.
- Be clear that mapped cameras may be outdated, incomplete, or imprecise.
- Keep the tone practical and civic, not alarmist.
"""


def build_alert_message(distance_meters: float, manufacturer: str | None, bearing: str | None) -> str:
    who = manufacturer or "an ALPR camera"
    direction = f" to the {bearing}" if bearing else ""
    return (
        f"A publicly mapped {who} is about {int(round(distance_meters))} meters{direction} "
        "from your current location. This is an opt-in awareness notice from public maps, "
        "not a live feed and not a report to any agency."
    )


def run_proximity(
    lat: float,
    lon: float,
    radius_meters: int | None = None,
    refresh_osm: bool = True,
) -> dict[str, Any]:
    settings = get_settings()
    radius = radius_meters or settings.alert_radius_meters
    osm_error = None
    if refresh_osm:
        try:
            upsert_cameras(query_alpr_around(lat, lon, max(radius, 1500)))
        except Exception as exc:
            osm_error = str(exc)

    hits = cameras_near(lat, lon, radius)
    alerts: list[NearbyAlert] = []
    for camera, distance in hits:
        bearing = compass_bearing(lat, lon, camera.lat, camera.lon)
        alerts.append(
            NearbyAlert(
                camera=camera,
                distance_meters=round(distance, 1),
                bearing=bearing,
                message=build_alert_message(distance, camera.manufacturer, bearing),
            )
        )

    payload = {
        "lat": lat,
        "lon": lon,
        "radius_meters": radius,
        "count": len(alerts),
        "osm_error": osm_error,
        "alerts": [a.model_dump() for a in alerts],
    }
    llm_summary = llm_text(PROXIMITY_SYSTEM, str(payload)[:6000])
    if llm_summary:
        narrative = llm_summary
    elif alerts:
        narrative = (
            f"{len(alerts)} publicly mapped ALPR camera(s) are within {radius} meters. "
            "Only you received this notice; your coordinates are not stored."
        )
    else:
        narrative = (
            f"No publicly mapped ALPR cameras were found within {radius} meters. "
            "That does not mean the area is camera-free — public maps are incomplete."
        )
    payload["narrative"] = narrative
    return payload
