from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from flock_blocker import __version__
from flock_blocker.config import get_settings
from flock_blocker.graph import run_turn
from flock_blocker.store import all_cameras, load_store

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

    @app.get("/api/cameras")
    def cameras() -> dict[str, object]:
        return {"cameras": [c.model_dump() for c in all_cameras()]}

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
        result = run_turn(
            "Alert me if I am near a publicly mapped Flock or ALPR camera.",
            lat=payload.lat,
            lon=payload.lon,
            radius_meters=payload.radius_meters,
        )
        if not result["alerts"] and payload.lat is None:
            raise HTTPException(status_code=400, detail="lat/lon required")
        return result

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
