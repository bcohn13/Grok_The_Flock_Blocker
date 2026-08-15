from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from flock_blocker.models import Camera

ROOT = Path(__file__).resolve().parent.parent
SEED_PATH = ROOT / "data" / "seed_cameras.json"
RUNTIME_PATH = ROOT / "data" / "runtime_cameras.json"

_lock = Lock()
_cameras: dict[str, Camera] = {}


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def reset_store() -> None:
    with _lock:
        _cameras.clear()


def load_store() -> None:
    with _lock:
        _cameras.clear()
        for raw in _load_json(SEED_PATH) + _load_json(RUNTIME_PATH):
            camera = Camera.model_validate(raw)
            _cameras[camera.id] = camera


def all_cameras() -> list[Camera]:
    if not _cameras:
        load_store()
    with _lock:
        return list(_cameras.values())


def upsert_cameras(cameras: list[Camera]) -> int:
    if not _cameras:
        load_store()
    added = 0
    with _lock:
        for camera in cameras:
            if camera.id not in _cameras:
                added += 1
            _cameras[camera.id] = camera
        RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            cam.model_dump()
            for cam in _cameras.values()
            if cam.source != "seed"
        ]
        RUNTIME_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return added


def cameras_near(lat: float, lon: float, radius_meters: float) -> list[tuple[Camera, float]]:
    from flock_blocker.geo import haversine_meters

    hits: list[tuple[Camera, float]] = []
    for camera in all_cameras():
        distance = haversine_meters(lat, lon, camera.lat, camera.lon)
        if distance <= radius_meters:
            hits.append((camera, distance))
    hits.sort(key=lambda item: item[1])
    return hits
