"""Turns rotation plantings (bed + cycle year + planned date) into concrete
dated instances for any calendar year."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import dates
from .scheduler import Engine


def cycle_index(year: int, settings: dict) -> int:
    n = max(1, int(settings.get("cycle_years") or 1))
    return (year - int(settings["start_year"])) % n + 1


def first_year_for_cycle(cycle_year: int, settings: dict) -> int:
    return int(settings["start_year"]) + cycle_year - 1


@dataclass
class Instance:
    planting: dict
    plant: dict
    year: int                      # calendar year of the establishment slot
    succession: int
    method: str
    area: float                    # sq ft used by this instance
    establish: dt.date | None      # None for perennials already in the ground
    maturity: dt.date
    harvest_end: dt.date
    kind: str
    indoor_start: tuple[dt.date, dt.date] | None = None
    harden_off: dt.date | None = None
    notes: list[str] = field(default_factory=list)
    frost_risk: float | None = None
    ok: bool = True
    harvest_this_year: bool = True
    actual: bool = False
    grow_start: dt.date | None = None   # perennials: active growing season
    grow_end: dt.date | None = None

    @property
    def start(self) -> dt.date:
        if self.grow_start:
            return max(self.grow_start, self.establish) if self.establish else self.grow_start
        return self.establish or dt.date(self.maturity.year, 1, 1)

    @property
    def end(self) -> dt.date:
        return max(self.harvest_end, self.grow_end) if self.grow_end else self.harvest_end

    def active_on(self, day: dt.date) -> bool:
        return self.start <= day <= self.end

    def to_dict(self) -> dict:
        p, pl = self.plant, self.planting
        return {
            "planting_id": pl["id"], "bed_id": pl["bed_id"], "plant_id": p["id"],
            "name": p["name"], "family": p["family"], "category": p["category"],
            "year": self.year, "succession": self.succession, "method": self.method,
            "area_sqft": round(self.area, 1), "kind": self.kind,
            "establish": dates.iso(self.establish), "maturity": dates.iso(self.maturity),
            "harvest_end": dates.iso(self.harvest_end),
            "indoor_start": [dates.iso(x) for x in self.indoor_start]
            if self.indoor_start else None,
            "harden_off": dates.iso(self.harden_off), "notes": self.notes,
            "frost_risk": self.frost_risk, "ok": self.ok,
            "harvest_this_year": self.harvest_this_year, "actual": self.actual,
            "start": dates.iso(self.start), "end": dates.iso(self.end),
        }


def _succession_step(plant: dict) -> int:
    return int(plant.get("succession") or 14)


def instances_for_year(year: int, plantings: list[dict], plants: dict[str, dict],
                       engine: Engine, settings: dict, beds: dict[int, dict],
                       actuals: dict[tuple[int, int], dict] | None = None) -> list[Instance]:
    """Instances whose establishment slot belongs to calendar ``year``."""
    actuals = actuals or {}
    cyc = cycle_index(year, settings)
    out: list[Instance] = []
    for pl in plantings:
        p = plants.get(pl["plant_id"])
        bed = beds.get(pl["bed_id"])
        if not p or not bed:
            continue
        bed_area = bed["length_ft"] * bed["width_ft"]
        area_total = pl["area_sqft"] or bed_area
        if p["lifecycle"] == "perennial":
            out.extend(_perennial(year, pl, p, engine, settings, area_total))
            continue
        if pl["cycle_year"] != cyc:
            continue
        n = max(1, int(pl["successions"] or 1))
        step = _succession_step(p)
        for i in range(n):
            d = int(pl["doy"]) + i * step
            act = actuals.get((pl["id"], year)) if i == 0 else None
            if act and act.get("established"):
                ad = dates.parse(act["established"])
                d = dates.doy(ad) + (ad.year - year) * 365
            plan = engine.plan(p, d, pl["method"], pl.get("dtm_override"))
            inst = Instance(
                planting=pl, plant=p, year=year, succession=i, method=plan["method"],
                area=area_total / n, establish=dates.to_date(year, plan["establish"]),
                maturity=dates.to_date(year, plan["maturity"]),
                harvest_end=dates.to_date(year, plan["harvest_end"]),
                kind=plan["kind"], notes=list(plan["notes"]),
                frost_risk=plan.get("frost_risk"), ok=plan.get("ok", True),
                actual=bool(act and act.get("established")),
            )
            if act and act.get("finished") and i == 0:
                inst.harvest_end = dates.parse(act["finished"])
            if "indoor_start" in plan:
                a, b = plan["indoor_start"]
                inst.indoor_start = (dates.to_date(year, a), dates.to_date(year, b))
                inst.harden_off = dates.to_date(year, plan["harden_off"])
            out.append(inst)
    return out


def _perennial(year: int, pl: dict, p: dict, engine: Engine, settings: dict,
               area: float) -> list[Instance]:
    planted_year = first_year_for_cycle(pl["cycle_year"], settings)
    if year < planted_year:
        return []
    plan = engine.plan(p, int(pl["doy"]), pl["method"])
    fy = plan.get("first_harvest_year", 1)
    harvest_ok = year >= planted_year + fy - 1
    notes = list(plan["notes"]) if year == planted_year else []
    if not harvest_ok:
        notes.append(f"Establishment year — no harvest until {planted_year + fy - 1}.")
    # harvest anchors are relative to the planting slot; shift into this year
    mat = dates.to_date(year, plan["maturity"] if year == planted_year
                        else plan["maturity"] % 365)
    end = dates.to_date(year, plan["harvest_end"] if year == planted_year
                        else plan["maturity"] % 365 + plan["harvest_end"] - plan["maturity"])
    inst = Instance(
        planting=pl, plant=p, year=year, succession=0, method=plan["method"], area=area,
        establish=dates.to_date(year, int(pl["doy"])) if year == planted_year else None,
        maturity=mat, harvest_end=end, kind="perennial", notes=notes,
        harvest_this_year=harvest_ok,
    )
    inst.grow_start, inst.grow_end = growing_season_bounds(year, engine)
    return [inst]


def instances_touching(year: int, *args, **kw) -> list[Instance]:
    """Instances that occupy any part of calendar ``year`` (includes crops
    planted the previous fall, such as garlic and winter cover crops)."""
    cur = instances_for_year(year, *args, **kw)
    prev = [i for i in instances_for_year(year - 1, *args, **kw)
            if i.end.year >= year and i.kind != "perennial"]
    return prev + cur


def growing_season_bounds(year: int, engine: Engine) -> tuple[dt.date, dt.date]:
    """Rough active season for perennials (water/N demand)."""
    return (dates.to_date(year, engine.lsf - 21), dates.to_date(year, engine.fff + 14))
