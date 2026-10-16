"""HTTP API + static single-page app."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import advisor, calendar_events, dates, db, feeding, foods, nitrogen, rotation, services as svc
from . import products as products_mod
from .garden import cycle_index
from .plant_data import FAMILY_COMMON, FAMILY_RETURN_YEARS, FROST_THRESHOLD_F, PROFILES
from .scheduler import resolve_method
from .sources import geo
from .sources.http import SourceError
from .sources.soil import PRESETS

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
STATIC = os.path.join(os.path.dirname(__file__), "static")

@asynccontextmanager
async def _lifespan(_: FastAPI):
    feeding.upgrade()
    yield


app = FastAPI(title="Local Plant Calendar", version="1.0", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.exception_handler(svc.NotConfigured)
async def _not_configured(_: Request, exc: svc.NotConfigured):
    return JSONResponse(status_code=409, content={"detail": str(exc), "code": "no_location"})


@app.exception_handler(SourceError)
async def _source_error(_: Request, exc: SourceError):
    return JSONResponse(status_code=502, content={
        "detail": f"A data source could not be reached and nothing is cached yet: {exc}",
        "code": "source"})


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


# ------------------------------------------------------------------ settings
class AutoBedIn(BaseModel):
    kind: str = Field("raised", pattern="^(raised|in_ground|container)$")
    length_ft: float = Field(8, gt=0, le=1000)
    width_ft: float = Field(4, gt=0, le=1000)


class SettingsIn(BaseModel):
    location: dict | None = None
    frost_risk: float | None = Field(None, ge=0.05, le=0.5)
    cycle_years: int | None = Field(None, ge=1, le=8)
    start_year: int | None = Field(None, ge=1990, le=2200)
    lsf_override: str | None = None
    fff_override: str | None = None
    auto_size: bool | None = None
    auto_bed: AutoBedIn | None = None
    auto_feed: bool | None = None
    feed_product: str | None = None


_MD = re.compile(r"^\d{2}-\d{2}$")


@app.get("/api/version")
def version():
    """Which build is running (commit and build time are stamped into the image by CI)."""
    sha = os.environ.get("APP_VERSION") or "dev"
    return {"version": sha[:7], "commit": sha if sha != "dev" else None,
            "built": os.environ.get("APP_BUILT") or None}


@app.get("/api/settings")
def get_settings():
    s = svc.settings()
    s["current_cycle_year"] = cycle_index(dt.date.today().year, s)
    s["today"] = dt.date.today().isoformat()
    return s


@app.put("/api/settings")
def put_settings(body: SettingsIn):
    vals = body.model_dump(exclude_unset=True)
    for k in ("lsf_override", "fff_override"):
        if vals.get(k) and not _MD.match(vals[k]):
            raise HTTPException(400, f"{k} must look like MM-DD")
    if "location" in vals and vals["location"]:
        loc = vals["location"]
        if not (-90 <= float(loc.get("lat", 999)) <= 90 and
                -180 <= float(loc.get("lon", 999)) <= 180):
            raise HTTPException(400, "location needs valid lat/lon")
    if "feed_product" in vals and vals["feed_product"] not in feeding.FEED_PRODUCTS:
        raise HTTPException(400, "unknown fertilizer")
    db.put_settings(vals)
    if vals.get("auto_size") is False:
        db.execute("UPDATE beds SET auto = 0")   # turning sizing off keeps the beds it made
    svc.invalidate()
    if vals.keys() & {"location", "frost_risk", "cycle_years", "start_year", "lsf_override",
                      "fff_override", "auto_feed", "feed_product"}:
        feeding.refresh()
    return get_settings()


@app.get("/api/geocode")
def geocode(q: str = Query(..., min_length=2)):
    return geo.geocode(q)


@app.post("/api/refresh")
def refresh(what: str = "forecast"):
    if what == "all":
        db.cache_clear()
    else:
        db.cache_clear("GET https://api.open-meteo.com")
    svc.invalidate()
    return {"ok": True}


# ---------------------------------------------------------------------- site
@app.get("/api/site")
def site():
    loc = svc.location()
    clim = svc.climate()
    summary = clim.summary()
    soil = svc.site_soil()
    raised = svc.bed_soil({"soil": {"preset": "raised_mix"}})
    n = nitrogen.outlook(soil, raised, clim, svc.settings().get("auto_feed") is not False)
    return {"location": loc, "climate": summary, "zone": svc.zone(),
            "soil": soil, "nitrogen": n, "frost_thresholds": FROST_THRESHOLD_F,
            "sources": SOURCES}


SOURCES = [
    {"name": "Open-Meteo Forecast API", "url": "https://open-meteo.com/",
     "use": "16-day forecast, reference evapotranspiration (ET₀), soil temperature, humidity"},
    {"name": "Open-Meteo Historical Weather (ERA5)",
     "url": "https://open-meteo.com/en/docs/historical-weather-api",
     "use": "30 years of daily weather → frost probabilities, normals, degree days"},
    {"name": "USDA NRCS Soil Data Access (SSURGO)",
     "url": "https://sdmdataaccess.sc.egov.usda.gov/",
     "use": "Soil texture, organic matter, pH, water-holding capacity, drainage"},
    {"name": "ISRIC SoilGrids", "url": "https://soilgrids.org/",
     "use": "Global soil estimates (fallback when SSURGO has no data)"},
    {"name": "USDA Plant Hardiness Zone Map via phzmapi.org", "url": "https://phzmapi.org/",
     "use": "Hardiness zone for your ZIP code"},
    {"name": "Zippopotam.us", "url": "https://zippopotam.us/", "use": "ZIP → coordinates"},
    {"name": "FAO-56 Crop Evapotranspiration",
     "url": "https://www.fao.org/3/x0490e/x0490e00.htm",
     "use": "Crop coefficients, rooting depth, allowable depletion (built in)"},
]


# -------------------------------------------------------------------- plants
def _plant_summary(p: dict, w: dict | None) -> dict:
    return {
        "id": p["id"], "name": p["name"], "latin": p.get("latin", ""), "family": p["family"],
        "category": p["category"], "season": p["season"], "frost": p["frost"],
        "lifecycle": p["lifecycle"], "method": p["method"], "feeder": p["feeder"],
        "dtm": p["dtm"], "custom": bool(p.get("custom")),
        "windows": [{"start": x["start"], "end": x["end"], "season": x["season"],
                     "label": f"{x['start_label']} – {x['end_label']}",
                     "rec": x["establish"]} for x in (w or {}).get("windows", [])],
        "reasons": (w or {}).get("reasons", []),
        "window_method": (w or {}).get("method"),
    }


@app.get("/api/plants")
def list_plants():
    plants = svc.plants()
    try:
        eng = svc.engine()
    except svc.NotConfigured:
        eng = None
    out = []
    for p in sorted(plants.values(), key=lambda x: x["name"]):
        w = None
        if eng:
            try:
                w = eng.windows(p)
            except Exception:  # noqa: BLE001
                w = None
        out.append(_plant_summary(p, w))
    return {"plants": out, "families": FAMILY_COMMON, "located": eng is not None}


@app.get("/api/plants/{pid}")
def plant_detail(pid: str, dtm: int | None = None):
    plants = svc.plants()
    p = plants.get(pid)
    if not p:
        raise HTTPException(404, "unknown plant")
    out = {"plant": p, "family_common": FAMILY_COMMON.get(p["family"], p["family"]),
           "family_return_years": FAMILY_RETURN_YEARS.get(p["family"]),
           "frost_threshold_f": FROST_THRESHOLD_F[p["frost"]],
           "companions": [{"id": c, "name": plants[c]["name"]} for c in p["companions"]
                          if c in plants],
           "avoid": [{"id": c, "name": plants[c]["name"]} for c in p["avoid"] if c in plants],
           "per_sqft": round((12 / max(p["spacing"], 1)) ** 2, 2),
           "food_id": next((f["id"] for f in foods.catalog(plants) if f["plant_id"] == pid),
                           None),
           "methods": {}}
    try:
        eng = svc.engine()
        methods = ["direct", "transplant"] if p["method"] == "either" and not p.get("special") \
            else [resolve_method(p, None)]
        for m in methods:
            out["methods"][m] = eng.windows(p, m, dtm)
        out["located"] = True
    except svc.NotConfigured:
        out["located"] = False
    return out


class CustomPlantIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    base_id: str | None = None
    profile: str | None = None
    latin: str | None = None
    family: str | None = None
    overrides: dict = {}


ALLOWED_OVERRIDES = {"dtm", "indoor_weeks", "spacing", "row", "germ_min", "germ_max",
                     "heat_max", "frost", "method", "prefer", "dtm_from", "n_demand",
                     "feeder", "tips", "category", "season", "succession", "harvest_days",
                     "grow_min", "root_in", "kc"}


@app.post("/api/plants/custom")
def create_custom(body: CustomPlantIn):
    if not body.base_id and body.profile not in PROFILES:
        raise HTTPException(400, "pick a plant to copy or a profile")
    bad = set(body.overrides) - ALLOWED_OVERRIDES
    if bad:
        raise HTTPException(400, f"unsupported fields: {', '.join(sorted(bad))}")
    slug = re.sub(r"[^a-z0-9]+", "_", body.name.lower()).strip("_") or "plant"
    pid = f"custom_{slug}"
    existing = svc.plants()
    n = 2
    while pid in existing and not existing[pid].get("custom"):
        pid = f"custom_{slug}_{n}"
        n += 1
    spec = {"id": pid, **body.model_dump()}
    try:
        built = svc.build_custom(spec)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"invalid plant: {exc}") from exc
    db.execute("INSERT INTO custom_plants(id, data) VALUES(?, ?) "
               "ON CONFLICT(id) DO UPDATE SET data = excluded.data", (pid, json.dumps(spec)))
    return built


@app.delete("/api/plants/custom/{pid}")
def delete_custom(pid: str):
    if db.query("SELECT 1 FROM plantings WHERE plant_id = ?", (pid,)):
        raise HTTPException(409, "this plant is used in your rotation — remove it there first")
    db.execute("DELETE FROM custom_plants WHERE id = ?", (pid,))
    return {"ok": True}


@app.get("/api/profiles")
def profiles():
    return {"profiles": {k: {"category": v["category"], "season": v["season"]}
                         for k, v in PROFILES.items()},
            "families": sorted(FAMILY_COMMON)}


# ---------------------------------------------------------------------- beds
class BedIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    length_ft: float = Field(8, gt=0, le=1000)
    width_ft: float = Field(4, gt=0, le=1000)
    kind: str = Field("raised", pattern="^(raised|in_ground|container)$")
    soil: dict = {}
    mulched: bool = False
    initial_no3_ppm: float = Field(10, ge=0, le=200)
    notes: str = ""
    sort: int = 0


def _bed_out(b: dict) -> dict:
    return {**b, "area_sqft": b["length_ft"] * b["width_ft"], "soil_profile": svc.bed_soil(b)}


@app.get("/api/beds")
def list_beds():
    return {"beds": [_bed_out(b) for b in svc.beds()], "presets": {
        k: (v["name"] if v else "Native soil at your location") for k, v in PRESETS.items()}}


@app.post("/api/beds")
def create_bed(body: BedIn):
    bid = svc.add_bed(**body.model_dump())
    return _bed_out(next(b for b in svc.beds() if b["id"] == bid))


@app.put("/api/beds/{bid}")
def update_bed(bid: int, body: BedIn):
    if not db.query("SELECT 1 FROM beds WHERE id = ?", (bid,)):
        raise HTTPException(404, "unknown bed")
    # editing a bed the planner added makes it yours: it's no longer removed when empty
    db.execute("UPDATE beds SET name=?, length_ft=?, width_ft=?, kind=?, soil=?, mulched=?, "
               "initial_no3_ppm=?, notes=?, sort=?, auto=0 WHERE id=?",
               (body.name, body.length_ft, body.width_ft, body.kind, json.dumps(body.soil),
                int(body.mulched), body.initial_no3_ppm, body.notes, body.sort, bid))
    feeding.refresh([bid])
    return _bed_out(next(b for b in svc.beds() if b["id"] == bid))


@app.delete("/api/beds/{bid}")
def delete_bed(bid: int):
    db.execute("DELETE FROM beds WHERE id = ?", (bid,))
    return {"ok": True}


@app.delete("/api/beds")
def delete_all_beds():
    n = len(svc.beds())
    db.execute("DELETE FROM beds")   # plantings, amendments and waterings cascade
    return {"ok": True, "beds_removed": n}


# ----------------------------------------------------------------- plantings
class PlantingIn(BaseModel):
    bed_id: int
    plant_id: str
    cycle_year: int = Field(1, ge=1, le=8)
    doy: int | None = Field(None, ge=0, le=729)
    date: str | None = None          # alternative to doy: "YYYY-MM-DD" or "MM-DD"
    method: str | None = None
    area_sqft: float = Field(0, ge=0)
    successions: int = Field(1, ge=1, le=12)
    dtm_override: int | None = Field(None, ge=10, le=400)
    residue: str | None = Field(None, pattern="^(remove|incorporate)$")
    notes: str = ""


def _normalize_planting(body: PlantingIn) -> dict:
    plants = svc.plants()
    p = plants.get(body.plant_id)
    if not p:
        raise HTTPException(400, "unknown plant")
    if not db.query("SELECT 1 FROM beds WHERE id = ?", (body.bed_id,)):
        raise HTTPException(400, "unknown bed")
    s = svc.settings()
    if body.cycle_year > int(s["cycle_years"]):
        raise HTTPException(400, f"your rotation cycle has {s['cycle_years']} years")
    method = resolve_method(p, body.method)
    doy = body.doy
    if doy is None and body.date:
        doy = dates.month_day_to_idx(body.date)
    if doy is None:
        w = svc.engine().windows(p, method, body.dtm_override)
        if not w["windows"]:
            raise HTTPException(400, f"{p['name']} has no planting window at your location "
                                     f"({'; '.join(w['reasons'])}). Pick a date manually.")
        doy = w["windows"][0]["establish"]
    residue = body.residue or ("incorporate" if p["category"] == "cover" else "remove")
    return {"bed_id": body.bed_id, "plant_id": body.plant_id, "cycle_year": body.cycle_year,
            "doy": int(doy), "method": method, "area_sqft": body.area_sqft,
            "successions": body.successions, "dtm_override": body.dtm_override,
            "residue": residue, "notes": body.notes}


@app.get("/api/plantings")
def list_plantings():
    return {"plantings": svc.plantings()}


@app.post("/api/plantings")
def create_planting(body: PlantingIn):
    v = _normalize_planting(body)
    pid = db.execute(
        "INSERT INTO plantings(bed_id, plant_id, cycle_year, doy, method, area_sqft, "
        "successions, dtm_override, residue, notes) VALUES(?,?,?,?,?,?,?,?,?,?)",
        tuple(v.values()))
    feeding.refresh([v["bed_id"]])
    return db.query("SELECT * FROM plantings WHERE id = ?", (pid,))[0]


@app.put("/api/plantings/{pid}")
def update_planting(pid: int, body: PlantingIn):
    old = db.query("SELECT bed_id FROM plantings WHERE id = ?", (pid,))
    if not old:
        raise HTTPException(404, "unknown planting")
    v = _normalize_planting(body)
    db.execute("UPDATE plantings SET bed_id=?, plant_id=?, cycle_year=?, doy=?, method=?, "
               "area_sqft=?, successions=?, dtm_override=?, residue=?, notes=? WHERE id=?",
               (*v.values(), pid))
    feeding.refresh({old[0]["bed_id"], v["bed_id"]})
    return db.query("SELECT * FROM plantings WHERE id = ?", (pid,))[0]


@app.delete("/api/plantings/{pid}")
def delete_planting(pid: int):
    old = db.query("SELECT bed_id FROM plantings WHERE id = ?", (pid,))
    db.execute("DELETE FROM plantings WHERE id = ?", (pid,))
    if old:
        feeding.refresh([old[0]["bed_id"]])
    return {"ok": True}


class ActualIn(BaseModel):
    year: int
    established: str | None = None
    finished: str | None = None


@app.put("/api/plantings/{pid}/actual")
def set_actual(pid: int, body: ActualIn):
    for v in (body.established, body.finished):
        if v:
            dates.parse(v)
    db.execute("INSERT INTO actuals(planting_id, year, established, finished) VALUES(?,?,?,?) "
               "ON CONFLICT(planting_id, year) DO UPDATE SET "
               "established=COALESCE(excluded.established, actuals.established), "
               "finished=COALESCE(excluded.finished, actuals.finished)", (pid, body.year, body.established, body.finished))
    feeding.refresh(r["bed_id"] for r in db.query("SELECT bed_id FROM plantings WHERE id = ?", (pid,)))
    return {"ok": True}


# ---------------------------------------------------------- amendments/water
class AmendmentIn(BaseModel):
    bed_id: int
    cycle_year: int = Field(1, ge=1, le=8)
    date: str                       # "MM-DD" (repeats every cycle)
    product: str
    amount_lb: float = Field(..., gt=0)
    n_pct: float | None = Field(None, ge=0, le=60)
    notes: str = ""


@app.get("/api/products")
def products():
    return {k: {"name": v[0], "n_pct": v[1], "available": v[2], "half_life_days": v[3],
                "npk": products_mod.npk_text(k),
                "feed": k in feeding.FEED_PRODUCTS}   # offered for planned feedings
            for k, v in nitrogen.PRODUCTS.items()}


@app.get("/api/amendments")
def list_amendments():
    return {"amendments": svc.amendments()}


@app.post("/api/amendments")
def create_amendment(body: AmendmentIn):
    if body.product not in nitrogen.PRODUCTS and body.n_pct is None:
        raise HTTPException(400, "custom products need an N %")
    aid = db.execute("INSERT INTO amendments(bed_id, cycle_year, doy, product, amount_lb, "
                     "n_pct, notes) VALUES(?,?,?,?,?,?,?)",
                     (body.bed_id, body.cycle_year, dates.month_day_to_idx(body.date),
                      body.product, body.amount_lb, body.n_pct, body.notes))
    feeding.refresh([body.bed_id])   # planned feedings shrink to what's still missing
    return db.query("SELECT * FROM amendments WHERE id = ?", (aid,))[0]


@app.delete("/api/amendments/{aid}")
def delete_amendment(aid: int):
    row = db.query("SELECT bed_id, auto FROM amendments WHERE id = ?", (aid,))
    db.execute("DELETE FROM amendments WHERE id = ?", (aid,))
    if row and not row[0]["auto"]:
        feeding.refresh([row[0]["bed_id"]])
    return {"ok": True}


class WateringIn(BaseModel):
    bed_id: int
    date: str
    inches: float = Field(..., gt=0, le=10)


@app.post("/api/waterings")
def log_watering(body: WateringIn):
    dates.parse(body.date)
    db.execute("INSERT INTO waterings(bed_id, date, inches) VALUES(?,?,?)",
               (body.bed_id, body.date[:10], body.inches))
    return {"ok": True}


# ------------------------------------------------------------------ rotation
@app.get("/api/rotation")
def get_rotation():
    s = svc.settings()
    beds = svc.beds()
    plants = svc.plants()
    pls = svc.plantings()
    insts = svc.cycle_instances()
    clim = svc.climate()
    winter = clim.frost_dates(32)["frost_free_years"] < len(clim.years) / 2
    chk = rotation.check(beds, pls, plants, s, insts, winter)
    by_pl: dict[int, list] = {}
    for i in insts:
        by_pl.setdefault(i.planting["id"], []).append(i.to_dict())
    rows = []
    for b in beds:
        cells = []
        for c in range(1, int(s["cycle_years"]) + 1):
            items = []
            for pl in pls:
                p = plants.get(pl["plant_id"])
                if pl["bed_id"] != b["id"] or not p:
                    continue
                if pl["cycle_year"] != c and p["lifecycle"] != "perennial":
                    continue
                items.append({**pl, "name": p["name"], "family": p["family"],
                              "category": p["category"], "feeder": p["feeder"],
                              "lifecycle": p["lifecycle"],
                              "instances": by_pl.get(pl["id"], [])})
            cells.append({"cycle_year": c, "calendar_year": int(s["start_year"]) + c - 1,
                          "plantings": items, **chk["grid"][b["id"]][c]})
        rows.append({"bed": _bed_out(b), "cells": cells})
    return {"rows": rows, "issues": chk["issues"], "groups": chk["groups"],
            "cycle_years": s["cycle_years"], "start_year": s["start_year"],
            "current_cycle_year": cycle_index(dt.date.today().year, s),
            "family_common": FAMILY_COMMON}


# ------------------------------------------------------------------ calendar
@app.get("/api/calendar")
def calendar(year: int | None = None):
    year = year or dt.date.today().year
    s = svc.settings()
    beds = {b["id"]: b for b in svc.beds()}
    insts = svc.touching_instances(year)
    events, rows = [], []
    for i in insts:
        d = i.to_dict()
        d["bed"] = beds.get(i.planting["bed_id"], {}).get("name")
        rows.append(d)
        name = i.plant["name"]
        verb = {"transplant": "Transplant", "direct": "Sow"}.get(i.method, "Plant")
        if i.kind in ("overwinter", "perennial", "winterkill"):
            verb = "Plant"
        if i.indoor_start:
            events.append({"date": i.indoor_start[0].isoformat(), "type": "indoor",
                           "title": f"Start {name} indoors", "bed": d["bed"],
                           "detail": f"between {i.indoor_start[0]:%b %d} and "
                                     f"{i.indoor_start[1]:%b %d}"})
        if i.harden_off:
            events.append({"date": i.harden_off.isoformat(), "type": "harden",
                           "title": f"Harden off {name}", "bed": d["bed"]})
        if i.establish:
            events.append({"date": i.establish.isoformat(), "type": "plant",
                           "title": f"{verb} {name}"
                                    + (f" (succession {i.succession + 1})" if i.succession else ""),
                           "bed": d["bed"],
                           "detail": f"{i.area:.0f} sq ft"})
        if i.plant["category"] == "cover":
            events.append({"date": i.harvest_end.isoformat(), "type": "terminate",
                           "title": f"Terminate {name}" if i.kind != "winterkill"
                           else f"{name} winter-kills", "bed": d["bed"]})
        elif i.harvest_this_year:
            events.append({"date": i.maturity.isoformat(), "type": "harvest",
                           "title": f"Harvest {name}", "bed": d["bed"],
                           "detail": f"through {i.harvest_end:%b %d}"})
    cyc = cycle_index(year, s)
    for a in svc.amendments():
        if a["cycle_year"] == cyc:
            events.append({"date": dates.to_date(year, a["doy"]).isoformat(),
                           "type": "amend", "title": feeding.title(a),
                           "bed": beds.get(a["bed_id"], {}).get("name")})
    events = [e for e in events if e["date"].startswith(str(year))]
    events.sort(key=lambda e: e["date"])
    rows.sort(key=lambda r: (r["bed"] or "", r["start"]))
    clim = svc.climate()
    fd = clim.frost_dates(32)
    return {"year": year, "cycle_year": cyc, "events": events, "rows": rows,
            "frost": {"last_spring": dates.to_date(year, fd["spring"]["0.5"]).isoformat()
                      if fd["spring"]["0.5"] is not None else None,
                      "first_fall": dates.to_date(year, fd["fall"]["0.5"]).isoformat()
                      if fd["fall"]["0.5"] is not None else None}}


# ------------------------------------------------------------------ forecast
@app.get("/api/forecast")
def get_forecast():
    ctx = svc.forecast_context()
    today, fc, advice, watering = ctx["today"], ctx["forecast"], ctx["advice"], ctx["watering"]
    clim = svc.climate()
    t = dates.doy(today)
    normals = {"high": round(float(clim.tmax[t]), 1), "low": round(float(clim.tmin[t]), 1),
               "soil": round(float(clim.soil[t]), 1)}
    advice = {**advice, "tasks": sorted(advice["tasks"] + _feeding_tasks(today),
                                        key=lambda t: t["date"])}
    return {"days": [d for d in fc["days"] if d["date"] >= (today - dt.timedelta(7)).isoformat()],
            "today": today.isoformat(), "normals": normals, **advice,
            "watering": watering,
            "plant_now": advisor.plant_now(svc.engine(), list(svc.plants().values()), today)}


def _feeding_tasks(today: dt.date) -> list[dict]:
    """Feedings due in the next two weeks, for the Today page."""
    lo, hi = (today - dt.timedelta(3)).isoformat(), (today + dt.timedelta(14)).isoformat()
    out = []
    for year in sorted({today.year, (today + dt.timedelta(14)).year}):
        for st in feeding.plan(year)["steps"]:
            if lo <= st["date"] <= hi:
                what = (f"{st['amount']} {st['product_name'].lower()}"
                        + (f" ({st['measure']})" if st["measure"] else ""))
                out.append({"date": st["date"], "kind": "feed", "bed": st["bed"],
                            "title": (f"Feed {st['crop']}" if st["crop"] else
                                      f"Add {st['product_name'].lower()}"),
                            "text": f"{what}. {st['how']}"})
    return out


# ------------------------------------------------------------------ feeding
@app.get("/api/nutrients/{bid}")
def nutrients(bid: int, year: int | None = Query(None, ge=1990, le=2200)):
    bed = next((b for b in svc.beds() if b["id"] == bid), None)
    if not bed:
        raise HTTPException(404, "unknown bed")
    return feeding.bed_nutrients(bed, year or dt.date.today().year)


@app.get("/api/feeding-plan")
def feeding_plan(year: int | None = Query(None, ge=1990, le=2200)):
    return feeding.plan(year or dt.date.today().year)


# ------------------------------------------------------------------ nitrogen
@app.get("/api/nitrogen/{bid}")
def get_nitrogen(bid: int, cycles: int = Query(2, ge=1, le=4)):
    try:
        return svc.nitrogen_for_bed(bid, cycles)
    except KeyError:
        raise HTTPException(404, "unknown bed") from None


@app.get("/api/nitrogen")
def nitrogen_overview():
    out = []
    for b in svc.beds():
        r = get_nitrogen(b["id"], 1)
        out.append({"bed_id": b["id"], "bed": b["name"], "recommendations":
                    r["recommendations"], "start_om_pct": r["start_om_pct"],
                    "end_om_pct": r["end_om_pct"],
                    "years": r["years"]})
    return {"beds": out}


# --------------------------------------------------------------- food-first
class FoodIn(BaseModel):
    food_id: str
    amount_lb: float | None = Field(None, gt=0, le=10000)


def _food_row(r: dict) -> dict:
    ids = json.loads(r["planting_ids"])
    alive = {x["id"] for x in db.query(
        f"SELECT id FROM plantings WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))} \
        if ids else set()
    return {"id": r["id"], "food_id": r["food_id"], "amount_lb": r["amount_lb"],
            "verdict": r["verdict"], "created": r["created"],
            "planting_ids": [i for i in ids if i in alive],
            "removed_plantings": len(ids) - len(alive),
            "assessment": json.loads(r["assessment"])}


@app.get("/api/foods/search")
def food_search(q: str = Query(..., min_length=1)):
    return foods.search(q, svc.plants())


@app.get("/api/foods/bundles")
def food_bundles():
    return foods.bundle_list()


@app.post("/api/foods/assess")
def food_assess(body: FoodIn):
    try:
        return foods.assess(body.food_id, body.amount_lb)
    except KeyError:
        raise HTTPException(404, "unknown food") from None


@app.get("/api/foods/mine")
def my_foods():
    return {"foods": [_food_row(r) for r in db.query("SELECT * FROM foods ORDER BY id DESC")]}


def _grow(food_id: str, amount_lb: float | None) -> dict:
    """Assess a food and, if it can grow here, put it into the rotation."""
    # re-planning replaces the earlier plan for the same food
    for old in db.query("SELECT * FROM foods WHERE food_id = ?", (food_id,)):
        for pid in json.loads(old["planting_ids"]):
            db.execute("DELETE FROM plantings WHERE id = ?", (pid,))
        db.execute("DELETE FROM foods WHERE id = ?", (old["id"],))
    before = {b["id"] for b in svc.beds()}
    try:
        res, ctx, _ = foods.assess_sized(food_id, amount_lb)
    except KeyError:
        foods.prune_auto_beds()
        raise HTTPException(404, "unknown food") from None
    ids: list[int] = []
    if res["verdict"] in ("good", "fixable", "marginal", "partial") and res["placements"]:
        food = foods.resolve(food_id, ctx.plants)
        ids = foods.apply(res, food, ctx)
    foods.prune_auto_beds()
    feeding.refresh()
    if ids:
        feed = foods.feeding_advice(ids)
        if feed:
            res["steps"].insert(-1, {"title": "Feed", "text": " ".join(feed)})
    fid = db.execute("INSERT INTO foods(food_id, amount_lb, verdict, assessment, planting_ids, "
                     "created) VALUES(?,?,?,?,?,?)",
                     (food_id, amount_lb, res["verdict"], json.dumps(res), json.dumps(ids),
                      dt.date.today().isoformat()))
    out = _food_row(db.query("SELECT * FROM foods WHERE id = ?", (fid,))[0])
    out["beds_added"] = len({b["id"] for b in svc.beds()} - before)
    return out


@app.post("/api/foods/mine")
def grow_food(body: FoodIn):
    return _grow(body.food_id, body.amount_lb)


@app.post("/api/foods/mine/{fid}/replan")
def replan_food(fid: int, body: FoodIn | None = None):
    row = db.query("SELECT * FROM foods WHERE id = ?", (fid,))
    if not row:
        raise HTTPException(404, "unknown food")
    amount = body.amount_lb if body else row[0]["amount_lb"]
    return _grow(row[0]["food_id"], amount)


@app.delete("/api/foods/mine/{fid}")
def delete_food(fid: int, keep_plantings: bool = False):
    row = db.query("SELECT * FROM foods WHERE id = ?", (fid,))
    if row and not keep_plantings:
        for pid in json.loads(row[0]["planting_ids"]):
            db.execute("DELETE FROM plantings WHERE id = ?", (pid,))
    db.execute("DELETE FROM foods WHERE id = ?", (fid,))
    removed = foods.prune_auto_beds()
    feeding.refresh()
    return {"ok": True, "beds_removed": removed}


@app.post("/api/foods/bundle/{bid}")
def grow_bundle(bid: str):
    bundle = next((b for b in foods.bundle_list() if b["id"] == bid), None)
    if not bundle:
        raise HTTPException(404, "unknown bundle")
    existing = {r["food_id"] for r in db.query("SELECT food_id FROM foods")}
    return {"foods": [_grow(f, None) for f in bundle["foods"] if f not in existing]}


@app.post("/api/rotation/cover-crops")
def add_cover_crops():
    added = foods.fill_cover_crops()
    feeding.refresh()   # legume covers cut how much feeding the next crop needs
    return {"added": added}


# ------------------------------------------------------------- calendar views
@app.get("/api/calendar/events")
def calendar_range(start: str, end: str, forecast: bool = True):
    try:
        d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "start/end must be YYYY-MM-DD") from None
    if d1 < d0 or (d1 - d0).days > 400:
        raise HTTPException(400, "range must be 0–400 days")
    return calendar_events.build(d0, d1, include_forecast=forecast)


@app.get("/api/calendar.ics")
def calendar_ics(kinds: str | None = None, bed: int | None = None):
    wanted = {k for k in (kinds or "").split(",") if k in calendar_events.KINDS} or None
    return Response(calendar_events.ics(wanted, bed), media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'inline; filename="garden.ics"'})
