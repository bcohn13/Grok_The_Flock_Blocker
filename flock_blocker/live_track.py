from __future__ import annotations

from typing import Any

CLOSE_FLOCK_METERS = 50
NEAR_FLOCK_METERS = 150
CLOSE_ALPR_METERS = 30
NEAR_ALPR_METERS = 80
TREND_METERS = 8
DISCLAIMER = (
    "Public maps are incomplete and may be stale. This is civic awareness, "
    "not a live camera feed, and not a way to evade law enforcement."
)


def is_flock(manufacturer: str | None) -> bool:
    return (manufacturer or "").lower().startswith("flock")


def _trend(current: float | None, previous: float | None) -> str:
    if current is None or previous is None:
        return "steady"
    if current <= previous - TREND_METERS:
        return "approaching"
    if current >= previous + TREND_METERS:
        return "receding"
    return "steady"


def _level(nearest: dict[str, Any] | None, nearest_flock: dict[str, Any] | None) -> str:
    if nearest is None:
        return "clear"
    nearest_m = float(nearest["distance_meters"])
    flock_m = float(nearest_flock["distance_meters"]) if nearest_flock else float("inf")
    if flock_m <= CLOSE_FLOCK_METERS or nearest_m <= CLOSE_ALPR_METERS:
        return "close"
    if flock_m <= NEAR_FLOCK_METERS or nearest_m <= NEAR_ALPR_METERS:
        return "nearby"
    return "watch"


def _trend_clause(trend: str) -> str:
    if trend == "approaching":
        return "; you are moving closer"
    if trend == "receding":
        return "; you are moving farther away"
    return ""


def _who(alert: dict[str, Any] | None) -> str:
    if not alert:
        return "ALPR camera"
    return (alert.get("camera") or {}).get("manufacturer") or "ALPR camera"


def recommended_action(
    level: str,
    alerts: list[dict[str, Any]],
    radius_meters: int,
    nearest: dict[str, Any] | None,
    nearest_flock: dict[str, Any] | None,
    flock_count: int,
    trend: str,
) -> str:
    focus = nearest_flock or nearest
    who = _who(focus)
    distance = int(round(float(focus["distance_meters"]))) if focus else 0
    bearing = (focus or {}).get("bearing") or ""
    where = f" about {distance} m" + (f" {bearing}" if bearing else "")
    clause = _trend_clause(trend)
    if level == "clear":
        return (
            f"No publicly mapped ALPR cameras within {radius_meters} m. "
            "Recommended action: continue on public roads as usual, and keep live "
            "tracking on if you want updates as you move. That does not mean the "
            f"area is camera-free. {DISCLAIMER}"
        )
    if level == "watch":
        return (
            f"{len(alerts)} mapped ALPR camera(s) in your {radius_meters} m alert radius "
            f"({flock_count} tagged Flock). Nearest is{where} ({who}). "
            "Recommended action: stay aware you may be photographed on this public "
            "roadway. If you want a path with fewer mapped cameras, use Recommend route. "
            f"{DISCLAIMER}"
        )
    if level == "nearby":
        return (
            f"Mapped {who}{where}{clause}. Recommended action: you may be scanned on "
            "this public road. Stay on a legal route; if you prefer fewer mapped cameras "
            "ahead, compare public-road options with Recommend route. Do not interfere "
            f"with cameras. {DISCLAIMER}"
        )
    return (
        f"You are within about {distance} m of a mapped {who}"
        + (f" {bearing}" if bearing else "")
        + f"{clause} — likely inside a typical ALPR capture range. "
        "Recommended action: proceed legally on this public roadway. For later legs of "
        "this trip, Recommend route can compare public-road options with fewer mapped "
        f"cameras. Do not interfere with equipment. {DISCLAIMER}"
    )


def assess_live_status(
    alerts: list[dict[str, Any]],
    radius_meters: int,
    previous_nearest_meters: float | None = None,
) -> dict[str, Any]:
    """Civic live-tracking summary from already-loaded mapped cameras.

    Coordinates are not stored; this only classifies nearby public map pins.
    """
    ranked = sorted(alerts, key=lambda item: float(item.get("distance_meters") or 0))
    nearest = ranked[0] if ranked else None
    flock_alerts = [item for item in ranked if is_flock((item.get("camera") or {}).get("manufacturer"))]
    nearest_flock = flock_alerts[0] if flock_alerts else None
    trend = _trend(float(nearest["distance_meters"]) if nearest else None, previous_nearest_meters)
    level = _level(nearest, nearest_flock)
    flock_count = len(flock_alerts)
    action = recommended_action(
        level,
        ranked,
        radius_meters,
        nearest,
        nearest_flock,
        flock_count,
        trend,
    )
    if nearest is None:
        hud = f"LIVE · CLEAR · 0 cameras in {radius_meters} m"
    else:
        flock_m = float(nearest_flock["distance_meters"]) if nearest_flock else float("inf")
        if level == "close":
            label = "FLOCK CLOSE" if flock_m <= CLOSE_FLOCK_METERS else "CLOSE"
        elif level == "nearby":
            label = "FLOCK NEARBY" if flock_m <= NEAR_FLOCK_METERS else "NEARBY"
        else:
            label = "WATCH"
        focus = nearest_flock if label.startswith("FLOCK") else nearest
        distance = int(round(float(focus["distance_meters"])))
        bearing = focus.get("bearing") or ""
        if level == "watch":
            hud = f"LIVE · WATCH · {len(ranked)} ALPR · nearest {distance} m {bearing}".strip()
        else:
            hud = f"LIVE · {label} · {distance} m {bearing}".strip()
    return {
        "level": level,
        "trend": trend,
        "count": len(ranked),
        "flock_count": flock_count,
        "recommended_action": action,
        "hud": hud,
        "nearest": nearest,
        "nearest_flock": nearest_flock,
        "disclaimer": DISCLAIMER,
    }
