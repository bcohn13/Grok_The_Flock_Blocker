from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CameraSource = Literal["openstreetmap", "news", "seed", "user_report"]
Confidence = Literal["high", "medium", "low"]


class Camera(BaseModel):
    id: str
    lat: float
    lon: float
    manufacturer: str | None = None
    camera_type: str = "ALPR"
    street: str | None = None
    city: str | None = None
    source: CameraSource = "openstreetmap"
    source_url: str | None = None
    mapped_at: str | None = None
    confidence: Confidence = "medium"
    notes: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class NearbyAlert(BaseModel):
    camera: Camera
    distance_meters: float
    bearing: str | None = None
    message: str


class ScoutFinding(BaseModel):
    title: str
    url: str
    snippet: str
    city_hint: str | None = None


class PolicyNote(BaseModel):
    title: str
    url: str
    summary: str
