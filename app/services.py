"""Shared, cached access to location data, the plant library and the garden."""

from __future__ import annotations

import copy
import datetime as dt
import json
import threading

from . import climate as climate_mod
from . import db, nitrogen
from .garden import cycle_index, instances_for_year, instances_touching
from .plant_data import PROFILES, builtin_plants
from .scheduler import Engine
from .sources import geo, soil as soil_mod, weather


class NotConfigured(RuntimeError):
    pass


_lock = threading.RLock()
_mem: dict[str, object] = {}


def invalidate() -> None:
    with _lock:
        _mem.clear()


def _memo(key: str, fn):
    with _lock:
        if key not in _mem:
            _mem[key] = fn()
        return _mem[key]


# -------------------------------------------------------------- location
def settings() -> dict:
    return db.get_settings()


def location(s: dict | None = None) -> dict:
    s = s or settings()
    loc = s.get("location")
    if not loc or loc.get("lat") is None:
        raise NotConfigured("Set your garden location first (Settings).")
    return loc


def climate():
    s = settings()
    loc = location(s)
    key = f"clim {loc['lat']:.3f} {loc['lon']:.3f} {s.get('lsf_override')} " \
          f"{s.get('fff_override')}"
    return _memo(key, lambda: climate_mod.build(
        weather.fetch_archive(loc["lat"], loc["lon"]),
        s.get("lsf_override"), s.get("fff_override")))


def engine() -> Engine:
    s = settings()
    loc = location(s)
    key = f"engine {loc['lat']:.3f} {loc['lon']:.3f} {s.get('lsf_override')} " \
          f"{s.get('fff_override')} {s.get('frost_risk')}"
    return _memo(key, lambda: Engine(climate(), float(s.get("frost_risk") or 0.1)))


def site_soil() -> dict:
    loc = location()
    return _memo(f"soil {loc['lat']:.4f} {loc['lon']:.4f}",
                 lambda: soil_mod.soil_at(loc["lat"], loc["lon"]))


def zone() -> dict:
    loc = location()

    def get():
        z = geo.hardiness_zone(loc.get("zip"))
        if z:
            return z
        try:
            est = climate().summary()["zone_estimate"]
        except Exception:  # noqa: BLE001
            return None
        return {"zone": est, "temperature_range": None,
                "source": "Estimated from 30 years of winter lows"}
    return _memo(f"zone {loc.get('zip')} {loc['lat']}", get)


def forecast() -> dict:
    loc = location()
    return weather.fetch_forecast(loc["lat"], loc["lon"])


# ----------------------------------------------------------------- plants
def _custom_rows() -> list[dict]:
    return [json.loads(r["data"]) for r in db.query("SELECT data FROM custom_plants")]


def build_custom(spec: dict) -> dict:
    """Custom plants start from a built-in plant or a profile."""
    builtins = {p["id"]: p for p in builtin_plants()}
    if spec.get("base_id") in builtins:
        base = copy.deepcopy(builtins[spec["base_id"]])
    else:
        base = copy.deepcopy(PROFILES.get(spec.get("profile") or "leafy", PROFILES["leafy"]))
        base.update(companions=[], avoid=[], tips="", special=None,
                    profile=spec.get("profile") or "leafy")
    for k, v in (spec.get("overrides") or {}).items():
        if v not in (None, ""):
            base[k] = v
    base.update(id=spec["id"], name=spec["name"], custom=True,
                latin=spec.get("latin") or base.get("latin", ""),
                family=spec.get("family") or base.get("family", "Other"),
                base_id=spec.get("base_id"))
    return base


def plants() -> dict[str, dict]:
    out = {p["id"]: p for p in builtin_plants()}
    for spec in _custom_rows():
        try:
            out[spec["id"]] = build_custom(spec)
        except Exception:  # noqa: BLE001 — skip broken custom entries
            continue
    return out


# ------------------------------------------------------------------ garden
def beds() -> list[dict]:
    rows = db.query("SELECT * FROM beds ORDER BY sort, id")
    for r in rows:
        r["soil"] = json.loads(r["soil"] or "{}")
        r["mulched"] = bool(r["mulched"])
    return rows


def bed_soil(bed: dict) -> dict:
    try:
        site = site_soil()
    except NotConfigured:
        site = soil_mod.finish(dict(soil_mod.DEFAULT_SOIL))
    return soil_mod.bed_soil(site, bed.get("soil"))


def plantings() -> list[dict]:
    return db.query("SELECT * FROM plantings ORDER BY cycle_year, doy, id")


def actuals() -> dict[tuple[int, int], dict]:
    return {(r["planting_id"], r["year"]): r for r in db.query("SELECT * FROM actuals")}


def amendments() -> list[dict]:
    return db.query("SELECT * FROM amendments ORDER BY cycle_year, doy")


def _args():
    s = settings()
    bs = beds()
    return (plantings(), plants(), engine(), s, {b["id"]: b for b in bs}), {"actuals": actuals()}


def year_instances(year: int):
    a, kw = _args()
    return instances_for_year(year, *a, **kw)


def touching_instances(year: int):
    a, kw = _args()
    return instances_touching(year, *a, **kw)


def cycle_instances():
    """One full rotation cycle of instances (cycle years 1..N)."""
    s = settings()
    a, kw = _args()
    out = []
    for c in range(int(s["cycle_years"])):
        out.extend(instances_for_year(int(s["start_year"]) + c, *a, **kw))
    return out


def current_cycle_year() -> int:
    return cycle_index(dt.date.today().year, settings())


def nitrogen_for_bed(bed_id: int, cycles: int = 2) -> dict:
    s = settings()
    bed = next((b for b in beds() if b["id"] == bed_id), None)
    if not bed:
        raise KeyError(bed_id)
    years = min(max(int(s["cycle_years"]) * cycles, 2), 12)
    start = int(s["start_year"])
    insts = []
    for y in range(start - 1, start + years):
        insts.extend(i for i in year_instances(y) if i.planting["bed_id"] == bed_id)
    insts = [i for i in insts if i.end.year >= start]
    amend = [a for a in amendments() if a["bed_id"] == bed_id]
    return nitrogen.simulate(bed, bed_soil(bed), insts, amend, climate(), start, years, s,
                             lambda y: cycle_index(y, s))


def forecast_context(today: dt.date | None = None) -> dict:
    """Forecast + the advice and watering plans derived from it (shared by the
    Today page and the calendar)."""
    from . import advisor, water  # local import keeps module start-up light
    today = today or dt.date.today()
    fc = forecast()
    clim = climate()
    bs = beds()
    bed_map = {b["id"]: b for b in bs}
    insts = touching_instances(today.year)
    if today.month >= 10:
        insts += [i for i in year_instances(today.year + 1)
                  if i.start <= today + dt.timedelta(days=30)]
    advice = advisor.advise(insts, fc, clim, bed_map, today)
    logs: dict[int, dict[str, float]] = {}
    for r in db.query("SELECT bed_id, date, SUM(inches) AS inches FROM waterings "
                      "GROUP BY bed_id, date"):
        logs.setdefault(r["bed_id"], {})[r["date"]] = r["inches"]
    watering = [water.schedule(b, bed_soil(b), [i for i in insts if i.planting["bed_id"] == b["id"]],
                               fc["days"], logs.get(b["id"], {}), today) for b in bs]
    return {"today": today, "forecast": fc, "instances": insts, "advice": advice,
            "watering": watering}
