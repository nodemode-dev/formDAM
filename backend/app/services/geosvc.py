import gzip
import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..db import ex, q, q1

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
NEAR_KM = 60.0
CITY_KM = 8.0
EARTH_KM = 6371.0
TRIP_AWAY_KM = 100.0
TRIP_GAP_DAYS = 2

_lock = threading.Lock()
_places: Optional[Dict[str, Any]] = None
_countries: Optional[List[Dict[str, Any]]] = None


def _load_places() -> Dict[str, Any]:
    global _places
    with _lock:
        if _places is None:
            with gzip.open(os.path.join(DATA, "places.json.gz"), "rt", encoding="utf-8") as fh:
                raw = json.load(fh)
            rows = raw["places"]
            lat = np.array([r[0] for r in rows], dtype=np.float64) / 1e4
            lon = np.array([r[1] for r in rows], dtype=np.float64) / 1e4
            _places = {"lat": lat, "lon": lon, "rows": rows, "countries": raw["countries"], "admin1": raw["admin1"],
                       "order": np.argsort(lat)}
        return _places


def countries_geo() -> List[Dict[str, Any]]:
    global _countries
    with _lock:
        if _countries is None:
            with gzip.open(os.path.join(DATA, "countries.json.gz"), "rt", encoding="utf-8") as fh:
                _countries = json.load(fh)["countries"]
            for c in _countries:
                xs = [p[0] for r in c["rings"] for p in r] or [0]
                ys = [p[1] for r in c["rings"] for p in r] or [0]
                c["bbox"] = (min(xs), min(ys), max(xs), max(ys))
        return _countries


def _inside(ring: List[List[float]], x: float, y: float) -> bool:
    hit = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            hit = not hit
        j = i
    return hit


def country_at(lat: float, lon: float) -> Optional[Dict[str, str]]:
    for c in countries_geo():
        x0, y0, x1, y1 = c["bbox"]
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            continue
        if any(_inside(r, lon, lat) for r in c["rings"]):
            return {"iso": c["iso"], "name": c["name"]}
    return None


def distance_km(lat1: float, lon1: float, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.minimum(1.0, a)))


def reverse(lat: float, lon: float) -> Dict[str, Optional[str]]:
    data = _load_places()
    band = 1.0
    sel = np.nonzero(np.abs(data["lat"] - lat) <= band)[0]
    out: Dict[str, Optional[str]] = {"place": None, "admin": None, "country": None, "iso": None}
    if sel.size:
        d = distance_km(lat, lon, data["lat"][sel], data["lon"][sel])
        best = int(np.argmin(d))
        close = np.nonzero(d <= CITY_KM)[0]
        if close.size > 1:
            best = int(close[int(np.argmax([data["rows"][int(sel[i])][5] for i in close]))])
        if d[best] <= NEAR_KM:
            row = data["rows"][int(sel[best])]
            cc = row[3]
            out.update(place=row[2], iso=cc, country=data["countries"].get(cc, cc),
                       admin=data["admin1"].get(f"{cc}.{row[4]}"))
            return out
    hit = country_at(lat, lon)
    if hit:
        out.update(country=hit["name"], iso=hit["iso"])
    return out


def assign(media_id: int) -> None:
    row = q1("SELECT lat, lon FROM media WHERE id=?", (media_id,))
    if row is None:
        return
    if row["lat"] is None or row["lon"] is None:
        ex("UPDATE media SET place=NULL, admin=NULL, country=NULL WHERE id=?", (media_id,))
        return
    found = reverse(row["lat"], row["lon"])
    ex("UPDATE media SET place=?, admin=?, country=? WHERE id=?", (found["place"], found["admin"], found["country"], media_id))


def on_metadata(media_id: int, meta: Dict[str, Any]) -> None:
    if meta.get("lat") is not None:
        assign(media_id)


def pending() -> int:
    return q1("SELECT COUNT(*) AS n FROM media WHERE lat IS NOT NULL AND country IS NULL")["n"]


def backfill_job(state: Dict[str, Any]) -> None:
    rows = q("SELECT id FROM media WHERE lat IS NOT NULL AND country IS NULL")
    state["counts"] = {"located": 0}
    for row in rows:
        assign(row["id"])
        state["counts"]["located"] += 1


def search(text: str, limit: int = 12) -> List[Dict[str, Any]]:
    data = _load_places()
    needle = text.strip().lower()
    if not needle:
        return []
    hits = [r for r in data["rows"] if r[2].lower().startswith(needle)]
    hits.sort(key=lambda r: -r[5])
    out = []
    for r in hits[:limit]:
        out.append({"name": r[2], "admin": data["admin1"].get(f"{r[3]}.{r[4]}"), "country": data["countries"].get(r[3], r[3]),
                    "lat": r[0] / 1e4, "lon": r[1] / 1e4})
    return out


VISIBLE = "trashed_ts IS NULL AND private=0 AND hidden=0 AND live_of IS NULL AND location_hidden=0"


def points(limit: int = 50000) -> List[List[float]]:
    return [[r["id"], r["lat"], r["lon"]] for r in q(
        f"SELECT id, lat, lon FROM media WHERE {VISIBLE} AND lat IS NOT NULL ORDER BY created_ts DESC LIMIT ?", (limit,))]


def places_summary() -> Dict[str, Any]:
    countries = []
    for row in q(f"""SELECT country, COUNT(*) AS n, AVG(lat) AS lat, AVG(lon) AS lon FROM media
                     WHERE {VISIBLE} AND country IS NOT NULL GROUP BY country ORDER BY n DESC"""):
        cover = q1(f"SELECT id FROM media WHERE {VISIBLE} AND country=? ORDER BY favorite DESC, rating DESC, created_ts DESC LIMIT 1", (row["country"],))
        countries.append({"country": row["country"], "count": row["n"], "lat": row["lat"], "lon": row["lon"], "cover": cover["id"] if cover else None})
    cities = []
    for row in q(f"""SELECT place, admin, country, COUNT(*) AS n, AVG(lat) AS lat, AVG(lon) AS lon FROM media
                     WHERE {VISIBLE} AND place IS NOT NULL GROUP BY place, country ORDER BY n DESC LIMIT 500"""):
        cover = q1(f"SELECT id FROM media WHERE {VISIBLE} AND place=? AND country=? ORDER BY favorite DESC, rating DESC, created_ts DESC LIMIT 1",
                   (row["place"], row["country"]))
        cities.append({"place": row["place"], "admin": row["admin"], "country": row["country"], "count": row["n"],
                       "lat": row["lat"], "lon": row["lon"], "cover": cover["id"] if cover else None})
    return {"countries": countries, "cities": cities}


def home_place() -> Optional[Tuple[float, float, str]]:
    row = q1(f"""SELECT place, country, AVG(lat) AS lat, AVG(lon) AS lon, COUNT(*) AS n FROM media
                 WHERE {VISIBLE} AND place IS NOT NULL GROUP BY place, country ORDER BY n DESC LIMIT 1""")
    if row is None:
        return None
    return row["lat"], row["lon"], row["place"]


def trips(min_items: int = 4) -> List[Dict[str, Any]]:
    home = home_place()
    if home is None:
        return []
    rows = q(f"SELECT id, lat, lon, created_ts, place, country FROM media WHERE {VISIBLE} AND lat IS NOT NULL ORDER BY created_ts")
    out: List[Dict[str, Any]] = []
    current: List[Any] = []

    def flush() -> None:
        if len(current) >= min_items:
            days = {datetime.fromtimestamp(r["created_ts"]).date() for r in current}
            places: Dict[str, int] = {}
            countries: Dict[str, int] = {}
            for r in current:
                if r["place"]:
                    places[r["place"]] = places.get(r["place"], 0) + 1
                if r["country"]:
                    countries[r["country"]] = countries.get(r["country"], 0) + 1
            top_places = sorted(places, key=lambda k: -places[k])[:2]
            top_country = max(countries, key=lambda k: countries[k]) if countries else ""
            start = current[0]["created_ts"]
            title = " & ".join(top_places) if top_places else top_country
            if len(countries) > 1:
                title = top_country if len(countries) <= 2 else f"{len(countries)} countries"
            out.append({"key": f"trip-{int(start)}", "title": title or "Trip", "country": top_country,
                        "start_ts": start, "end_ts": current[-1]["created_ts"], "days": len(days), "count": len(current),
                        "ids": [r["id"] for r in current]})

    for r in rows:
        away = float(distance_km(home[0], home[1], np.array([r["lat"]]), np.array([r["lon"]]))[0]) >= TRIP_AWAY_KM
        if not away:
            flush()
            current = []
            continue
        if current and r["created_ts"] - current[-1]["created_ts"] > TRIP_GAP_DAYS * 86400:
            flush()
            current = []
        current.append(r)
    flush()
    out.reverse()
    return out


def set_location(ids: List[int], lat: Optional[float], lon: Optional[float]) -> None:
    for media_id in ids:
        ex("UPDATE media SET lat=?, lon=?, alt=NULL, xmp_ts=NULL WHERE id=?", (lat, lon, media_id))
        assign(media_id)


def set_location_hidden(ids: List[int], hidden: bool) -> None:
    for media_id in ids:
        ex("UPDATE media SET location_hidden=?, xmp_ts=NULL WHERE id=?", (1 if hidden else 0, media_id))


def adjust_dates(ids: List[int], mode: str, ts: Optional[float], delta_s: float) -> List[Dict[str, Any]]:
    out = []
    first = q1(f"SELECT MIN(created_ts) AS t FROM media WHERE id IN ({','.join('?' * len(ids))})", ids)["t"] if ids else None
    for media_id in ids:
        row = q1("SELECT created_ts, created_src, orig_created_ts FROM media WHERE id=?", (media_id,))
        if row is None:
            continue
        original = row["orig_created_ts"] if row["orig_created_ts"] is not None else row["created_ts"]
        if mode == "revert":
            if row["orig_created_ts"] is None:
                continue
            ex("UPDATE media SET created_ts=?, created_src='exif', orig_created_ts=NULL, xmp_ts=NULL WHERE id=?", (row["orig_created_ts"], media_id))
            out.append({"id": media_id, "created_ts": row["orig_created_ts"]})
            continue
        if mode == "set" and ts is not None:
            new_ts = ts + (row["created_ts"] - first if first is not None else 0)
        else:
            new_ts = row["created_ts"] + delta_s
        ex("UPDATE media SET created_ts=?, created_src='adjusted', orig_created_ts=?, xmp_ts=NULL WHERE id=?", (new_ts, original, media_id))
        out.append({"id": media_id, "created_ts": new_ts})
    return out


def now() -> float:
    return time.time()
