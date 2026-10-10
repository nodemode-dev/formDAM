from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import jobs
from ..db import q
from ..services import geosvc

router = APIRouter()

MAX_IDS = 20000


class LocationIn(BaseModel):
    ids: List[int] = Field(..., max_length=MAX_IDS)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    copy_from: Optional[int] = None


class HiddenIn(BaseModel):
    ids: List[int] = Field(..., max_length=MAX_IDS)
    hidden: bool


class DatesIn(BaseModel):
    ids: List[int] = Field(..., max_length=MAX_IDS)
    mode: str = Field("shift", pattern="^(set|shift|revert)$")
    ts: Optional[float] = None
    delta_s: float = 0.0


def ensure_geo_backfill() -> None:
    if geosvc.pending() and not jobs.running("places"):
        jobs.start("places", geosvc.backfill_job)


@router.get("/places")
def places():
    return geosvc.places_summary()


@router.get("/places/points")
def points(limit: int = Query(50000, ge=1, le=200000)):
    return {"points": geosvc.points(limit)}


@router.get("/places/countries")
def countries():
    return {"countries": [{"iso": c["iso"], "name": c["name"], "rings": c["rings"]} for c in geosvc.countries_geo()]}


@router.get("/places/search")
def search(text: str = Query("", max_length=120)):
    return {"results": geosvc.search(text)}


@router.get("/places/reverse")
def reverse(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    return geosvc.reverse(lat, lon)


@router.get("/trips")
def trips():
    return {"trips": geosvc.trips()}


@router.post("/media/location")
def set_location(payload: LocationIn):
    lat, lon = payload.lat, payload.lon
    if payload.copy_from is not None:
        src = q("SELECT lat, lon FROM media WHERE id=?", (payload.copy_from,))
        if not src or src[0]["lat"] is None:
            raise HTTPException(400, detail="The source item has no location")
        lat, lon = src[0]["lat"], src[0]["lon"]
    if (lat is None) != (lon is None):
        raise HTTPException(400, detail="Give both latitude and longitude, or neither")
    geosvc.set_location(payload.ids, lat, lon)
    rows = q(f"SELECT id, lat, lon, place, admin, country FROM media WHERE id IN ({','.join('?' * len(payload.ids))})",
             payload.ids) if payload.ids else []
    return {"items": [dict(r) for r in rows]}


@router.post("/media/location-hidden")
def location_hidden(payload: HiddenIn):
    geosvc.set_location_hidden(payload.ids, payload.hidden)
    return {"ok": True, "count": len(payload.ids)}


@router.post("/media/dates")
def adjust_dates(payload: DatesIn):
    if payload.mode == "set" and payload.ts is None:
        raise HTTPException(400, detail="A date is required")
    return {"items": geosvc.adjust_dates(payload.ids, payload.mode, payload.ts, payload.delta_s)}
