from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from flock_blocker import __version__
from flock_blocker.agents.proximity import run_proximity
from flock_blocker.config import get_settings
from flock_blocker.graph import run_turn
from flock_blocker.privacy_route import plan_privacy_route
from flock_blocker.presets import PRESETS
from flock_blocker.scan import scan_area, scan_place
from flock_blocker.store import all_cameras, load_store
from flock_blocker.walk_route import walking_route

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    lat: float | None = None
    lon: float | None = None
    radius_meters: int | None = Field(default=None, ge=50, le=50_000)


class NearbyRequest(BaseModel):
    lat: float
    lon: float
    radius_meters: int | None = Field(default=None, ge=50, le=50_000)
    refresh_osm: bool = True
    live: bool = False


class WalkRouteRequest(BaseModel):
    lat: float
    lon: float
    dest_lat: float | None = None
    dest_lon: float | None = None


class PrivacyRouteRequest(BaseModel):
    lat: float
    lon: float
    dest_lat: float | None = None
    dest_lon: float | None = None
    destination: str | None = Field(default=None, max_length=200)
    scan: bool = True


class ScanRequest(BaseModel):
    lat: float | None = None
    lon: float | None = None
    place: str | None = Field(default=None, max_length=200)
    radius_meters: int = Field(default=4000, ge=200, le=25_000)


def create_app() -> FastAPI:
    load_store()
    app = FastAPI(
        title="Grok the Flock Blocker",
        description="Multi-agent awareness tool for publicly reported ALPR camera locations.",
        version=__version__,
    )

    @app.get("/api/health")
    def health() -> dict[str, object]:
        settings = get_settings()
        return {
            "ok": True,
            "version": __version__,
            "llm_enabled": settings.has_llm,
            "provider": settings.llm_provider if settings.has_llm else None,
        }

    @app.get("/api/presets")
    def presets() -> dict[str, object]:
        return {"presets": PRESETS}

    @app.get("/api/cameras")
    def cameras() -> dict[str, object]:
        return {"cameras": [c.model_dump() for c in all_cameras()]}

    @app.post("/api/scan")
    def scan(payload: ScanRequest) -> dict[str, object]:
        try:
            if payload.lat is not None and payload.lon is not None:
                return scan_area(
                    payload.lat,
                    payload.lon,
                    payload.radius_meters,
                    place=payload.place,
                )
            if payload.place:
                result = scan_place(payload.place, payload.radius_meters)
                if result.get("error"):
                    raise HTTPException(status_code=404, detail=result["error"])
                return result
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"OSM lookup failed: {exc}") from exc
        raise HTTPException(status_code=400, detail="Provide lat/lon or a place name.")

    @app.post("/api/chat")
    def chat(payload: ChatRequest) -> dict[str, object]:
        return run_turn(
            payload.message,
            lat=payload.lat,
            lon=payload.lon,
            radius_meters=payload.radius_meters,
        )

    @app.post("/api/nearby")
    def nearby(payload: NearbyRequest) -> dict[str, object]:
        try:
            result = run_proximity(
                payload.lat,
                payload.lon,
                payload.radius_meters,
                refresh_osm=payload.refresh_osm and not payload.live,
                use_llm=not payload.live,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Proximity lookup failed: {exc}") from exc
        return result

    @app.post("/api/walk-route")
    def walk_route(payload: WalkRouteRequest) -> dict[str, object]:
        try:
            result = walking_route(
                payload.lat,
                payload.lon,
                payload.dest_lat,
                payload.dest_lon,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Street routing failed: {exc}") from exc
        return {
            "points": [{"lat": lat, "lon": lon} for lat, lon in result["points"]],
            "streets": result["streets"],
            "distance_meters": result["distance_meters"],
            "source": result["source"],
        }

    @app.post("/api/privacy-route")
    def privacy_route(payload: PrivacyRouteRequest) -> dict[str, object]:
        try:
            return plan_privacy_route(
                payload.lat,
                payload.lon,
                dest_lat=payload.dest_lat,
                dest_lon=payload.dest_lon,
                destination=payload.destination,
                scan=payload.scan,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Privacy routing failed: {exc}") from exc

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
