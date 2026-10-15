"""Food-first planning: "I want to eat X" -> can it grow here, and if so,
exactly how, where and when.

The heavy lifting:

1. **Resolve** a food name ("refried beans") to a crop and variety.
2. **Climate**: hardiness zone for perennials; for annuals, try the preferred
   method, then the alternative, then a faster variety, then season
   extension — and explain the outcome.
3. **Soil**: score every bed (pH, texture, drainage, organic matter) and
   work out lime/sulfur/compost amounts where it's fixable.
4. **Placement**: put the crop into the rotation every year of the cycle,
   moving it between beds so its plant family is kept apart, in beds with
   free space during its season, after a good preceding crop.
5. **Plan**: a written, dated growing guide for this location.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import unicodedata

from . import dates, db, services as svc
from .food_data import BUNDLES, FOODS
from .garden import cycle_index, instances_for_year
from .plant_data import FAMILY_COMMON, FAMILY_RETURN_YEARS
from .rotation import _counts_for_rotation, main_group
from .scheduler import Engine, resolve_method

EDIBLE_CATEGORIES = {"vegetable", "herb", "fruit"}


# ------------------------------------------------------------------ search
def _singular(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("oes"):
        return w[:-2]
    if len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(_singular(w) for w in s.split())


def catalog(plants: dict[str, dict]) -> list[dict]:
    """Explicit foods plus every edible plant (incl. custom ones) as a food."""
    out, used = [], set()
    for f in FOODS:
        if f["plant_id"] and f["plant_id"] not in plants:
            continue
        out.append(dict(f))
        if f["plant_id"]:
            used.add(f["plant_id"])
    for p in plants.values():
        if p["id"] in used or p["category"] not in EDIBLE_CATEGORIES:
            continue
        out.append({"id": f"plant:{p['id']}", "name": p["name"], "plant_id": p["id"],
                    "aliases": [p.get("latin", "")], "yield_lb_sqft": None,
                    "use": "fresh", "variety": None, "dtm": None, "how": None,
                    "unit": "lb", "default_area": None, "note": None})
    return out


def search(q: str, plants: dict[str, dict], limit: int = 12) -> list[dict]:
    nq = norm(q)
    if not nq:
        return []
    words = nq.split()
    scored = []
    for f in catalog(plants):
        names = [norm(f["name"])] + [norm(a) for a in f["aliases"] if a]
        if f["plant_id"]:
            names.append(norm(plants[f["plant_id"]]["name"]))
        best = 0
        for n in names:
            if n == nq:
                best = max(best, 100)
            elif n.startswith(nq):
                best = max(best, 80)
            elif all(w in n.split() for w in words):
                best = max(best, 65)
            elif nq in n:
                best = max(best, 45)
            elif all(any(t.startswith(w) for t in n.split()) for w in words):
                best = max(best, 35)
        if best:
            # prefer explicit foods over generic plant entries
            scored.append((best + (5 if not f["id"].startswith("plant:") else 0), f))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    out = []
    for score, f in scored[:limit]:
        p = plants.get(f["plant_id"]) if f["plant_id"] else None
        out.append({"id": f["id"], "name": f["name"], "plant_id": f["plant_id"],
                    "plant_name": p["name"] if p else None, "note": f["note"],
                    "use": f["use"], "has_yield": f["yield_lb_sqft"] is not None})
    return out


def resolve(food_id: str, plants: dict[str, dict]) -> dict | None:
    for f in catalog(plants):
        if f["id"] == food_id:
            return f
    return None


# ---------------------------------------------------------------- context
def zone_number(z: str | None) -> float | None:
    if not z:
        return None
    m = re.match(r"(\d+)([ab]?)", str(z))
    if not m:
        return None
    return int(m.group(1)) + (0.5 if m.group(2) == "b" else 0.0)


def zone_label(z: float) -> str:
    return f"{int(z)}{'b' if z % 1 >= 0.5 else 'a'}"


class Ctx:
    """Everything the planner needs, loaded once per request."""

    def __init__(self):
        self.settings = svc.settings()
        svc.location(self.settings)
        self.plants = svc.plants()
        self.engine = svc.engine()
        self.clim = svc.climate()
        self.beds = svc.beds()
        self.bed_map = {b["id"]: b for b in self.beds}
        self.soils = {b["id"]: svc.bed_soil(b) for b in self.beds}
        self.plantings = svc.plantings()
        self.actuals = svc.actuals()
        self.n = int(self.settings["cycle_years"])
        self.start = int(self.settings["start_year"])
        self.current_cycle = cycle_index(dt.date.today().year, self.settings)
        z = svc.zone()
        self.zone = zone_number(z["zone"]) if z else None
        # garden sizing: add beds when a food doesn't fit (on unless turned off)
        self.auto = self.settings.get("auto_size") is not False
        self.template = self.settings.get("auto_bed") or db.DEFAULT_SETTINGS["auto_bed"]
        self._years: dict[int, list] = {}

    def instances(self, year: int):
        if year not in self._years:
            self._years[year] = instances_for_year(
                year, self.plantings, self.plants, self.engine, self.settings, self.bed_map,
                actuals=self.actuals)
        return self._years[year]


# ---------------------------------------------------------------- climate
def climate_fit(food: dict, p: dict, ctx: Ctx) -> dict:
    dtm = round(sum(food["dtm"]) / 2) if food.get("dtm") else None
    notes: list[str] = []
    status = "good"
    zone = p.get("zone")
    if p["lifecycle"] == "perennial" and zone and ctx.zone is not None:
        zmin, zmax = zone
        if ctx.zone < zmin:
            work = None
            if p.get("container_ok"):
                work = (f"Grow it in a large container (15+ gallons) and move it into a garage "
                        f"or sunroom when nights drop below ~{28 if p['frost'] != 'tender' else 35}°F.")
            return {"status": "unsuitable", "windows": [], "method": None, "dtm": None,
                    "reasons": [f"{p['name']} survives winters only to zone {zone_label(zmin)}; "
                                f"your garden is zone {zone_label(ctx.zone)}, so a normal "
                                "winter would kill it."],
                    "workaround": work, "notes": []}
        if ctx.zone > zmax + 0.5:
            return {"status": "unsuitable", "windows": [], "method": None, "dtm": None,
                    "reasons": [f"{p['name']} needs colder winters (chill) than zone "
                                f"{zone_label(ctx.zone)} provides — it grows to zone "
                                f"{zone_label(zmax)}."],
                    "workaround": "Look for low-chill varieties bred for the South.",
                    "notes": []}
        if ctx.zone > zmax:
            status = "marginal"
            notes.append("You're at the warm edge of its range — choose a low-chill variety.")
    if p.get("special"):
        w = ctx.engine.windows(p, None, None)
        return {"status": status if w["windows"] else "unsuitable", "windows": w["windows"],
                "method": w["method"], "dtm": None, "reasons": w["reasons"],
                "workaround": None, "notes": notes, "risk_engine": ctx.engine}

    methods = [resolve_method(p, None)]
    if p["method"] == "either":
        methods.append("transplant" if methods[0] == "direct" else "direct")
    base = food["dtm"][0] if food.get("dtm") else p["dtm"][0]
    fast = max(int(round(base * 0.85)), 20)
    options = [(m, dtm, ctx.engine, None) for m in methods]
    options += [(m, fast, ctx.engine,
                 f"Choose the fastest variety you can find (about {fast} days to harvest).")
                for m in methods]
    if ctx.engine.risk < 0.5:
        risky = Engine(ctx.clim, min(ctx.engine.risk + 0.2, 0.5))
        options += [(m, fast, risky,
                     f"Choose a fast variety (~{fast} days) and protect young plants with row "
                     "cover or a low tunnel; cover again if an early fall frost threatens.")
                    for m in methods]
    first_reasons = None
    for m, d, eng, work in options:
        w = eng.windows(p, m, d)
        if first_reasons is None:
            first_reasons = w["reasons"]
        if w["windows"]:
            if work:
                status = "marginal"
            if m != methods[0] and not work:
                notes.append(f"{'Starting indoors' if m == 'transplant' else 'Direct sowing'} "
                             "works better than the usual method here.")
            for n in w["windows"][0]["notes"]:
                if not n.startswith("Warning") and n not in notes:
                    notes.append(n)
            return {"status": status, "windows": w["windows"], "method": m, "dtm": d,
                    "reasons": [], "workaround": work, "notes": notes, "risk_engine": eng}
    return {"status": "unsuitable", "windows": [], "method": None, "dtm": None,
            "reasons": first_reasons or ["no planting window"], "notes": notes,
            "workaround": ("A greenhouse or hoop house is the realistic option."
                           if "season too short / too cold to mature" in (first_reasons or [])
                           or "frost risk too high" in (first_reasons or []) else None)}


# ------------------------------------------------------------------- soil
_LIME = {"coarse": 3.0, "medium": 6.0, "fine": 8.0}     # lb/100 sq ft per pH unit
_SULFUR = {"coarse": 1.0, "medium": 1.5, "fine": 2.0}


def _soil_group(soil: dict) -> str:
    clay, sand = soil.get("clay") or 20, soil.get("sand") or 40
    if sand >= 70:
        return "coarse"
    if clay >= 35:
        return "fine"
    return "medium"


def soil_fit(p: dict, soil: dict, bed: dict) -> dict:
    issues, fixes, score = [], [], 0
    area = bed["length_ft"] * bed["width_ft"]
    lo, hi = p["ph"]
    ph = float(soil["ph"])
    grp = _soil_group(soil)
    if ph < lo - 0.2:
        target = min((lo + hi) / 2, lo + 0.5)
        rate = _LIME[grp] * (target - ph)
        issues.append(f"pH {ph:.1f} is too acidic (wants {lo}–{hi})")
        fixes.append(f"Work in ~{rate * area / 100:.1f} lb of garden lime "
                     f"({rate:.1f} lb per 100 sq ft) a few months before planting to raise pH "
                     f"toward {target:.1f}.")
        score = max(score, 2 if lo - ph > 1.5 else 1)
    elif ph > hi + 0.2:
        target = max((lo + hi) / 2, hi - 0.5)
        rate = _SULFUR[grp] * (ph - target)
        issues.append(f"pH {ph:.1f} is too alkaline (wants {lo}–{hi})")
        if ph - hi > 1.0:
            fixes.append("Alkaline soil rebounds after sulfur — grow it in a raised bed or "
                         "container filled with an acidic mix (peat/pine bark).")
            score = 2
        else:
            fixes.append(f"Work in ~{rate * area / 100:.1f} lb of elemental sulfur "
                         f"({rate:.1f} lb per 100 sq ft) a season ahead; recheck pH next year.")
            score = max(score, 1)
    clay = soil.get("clay") or 0
    if p.get("soil_pref") == "loose" and clay >= 35:
        issues.append(f"heavy clay ({clay:.0f}%) deforms roots and tubers")
        fixes.append(f"Loosen it with 2–3 inches of compost (~{area * 2.5 / 12:.0f} cu ft) or "
                     "grow it in a raised bed, and pick short or round varieties.")
        score = max(score, 2 if bed.get("kind") == "in_ground" and clay >= 45 else 1)
    drain = (soil.get("drainage") or "").lower()
    if "poorly" in drain:
        issues.append(f"{soil['drainage'].lower()} soil stays waterlogged")
        fixes.append("Grow it in a raised bed (8+ inches) so roots don't sit in water.")
        score = max(score, 2 if p.get("soil_pref") == "loose" or p["category"] == "fruit"
                    else 1)
    if p["feeder"] == "heavy" and float(soil["om_pct"]) < 2.0:
        cu_ft = area * 2 / 12
        issues.append(f"low organic matter ({soil['om_pct']:.1f}%) for a heavy feeder")
        fixes.append(f"Spread 2 inches of compost (~{cu_ft:.0f} cu ft) before planting.")
        score = max(score, 1)
    fit = ["good", "fixable", "poor"][score]
    return {"fit": fit, "issues": issues, "fixes": fixes}


# --------------------------------------------------------------- quantity
def plant_area(p: dict) -> float:
    """Sq ft per plant in an intensively planted bed (rows ~12" or plant spacing)."""
    return p["spacing"] * max(p["spacing"], min(p["row"], 12)) / 144


def area_for(food: dict, p: dict, amount: float | None) -> tuple[float, str]:
    pa = plant_area(p)
    if amount and food.get("yield_lb_sqft"):
        return max(amount / food["yield_lb_sqft"], pa), "amount"
    if food.get("default_area"):
        return max(float(food["default_area"]), pa), "default"
    return max(min(16.0, 4 * pa), pa), "default"


# -------------------------------------------------------------- placement
def _dates_for(eng: Engine, p: dict, doy: int, method: str, dtm, year: int):
    plan = eng.plan(p, doy, method, dtm)
    return plan, dates.to_date(year, plan["establish"]), dates.to_date(year, plan["harvest_end"])


def _free_area(ctx: Ctx, bed: dict, s: dt.date, e: dt.date, year: int, tentative) -> float:
    area = bed["length_ft"] * bed["width_ft"]
    spans = []
    for y in (year - 1, year, year + 1):
        for i in ctx.instances(y):
            if i.planting["bed_id"] == bed["id"] and i.start <= e and i.end >= s:
                spans.append((i.start, i.end, i.area))
    spans += [(t["start"], t["end"], t["area"]) for t in tentative
              if t["bed_id"] == bed["id"] and t["start"] <= e and t["end"] >= s]
    peak, d = 0.0, s
    while d <= e:
        peak = max(peak, sum(a for a0, a1, a in spans if a0 <= d <= a1))
        d += dt.timedelta(days=3)
    return max(area - peak, 0.0)


def _family_conflict(ctx: Ctx, p: dict, bed_id: int, cyc: int, tentative) -> int | None:
    need = FAMILY_RETURN_YEARS.get(p["family"])
    if not need or not _counts_for_rotation(p):
        return None
    years = {pl["cycle_year"] for pl in ctx.plantings if pl["bed_id"] == bed_id
             and (q := ctx.plants.get(pl["plant_id"])) and q["family"] == p["family"]
             and _counts_for_rotation(q)}
    years |= {t["cycle_year"] for t in tentative if t["bed_id"] == bed_id}
    years.discard(cyc)
    if not years:
        return None if ctx.n >= need or ctx.n == 1 else ctx.n
    gap = min(min((cyc - y) % ctx.n, (y - cyc) % ctx.n) for y in years)
    return gap if gap < need else None


def _sequence_bonus(ctx: Ctx, p: dict, bed_id: int, cyc: int, tentative) -> float:
    if ctx.n == 1:
        return 0.0
    prev = (cyc - 2) % ctx.n + 1
    rows = [pl for pl in ctx.plantings if pl["bed_id"] == bed_id and pl["cycle_year"] == prev]
    g = main_group(rows, ctx.plants)
    if g is None:
        tg = [t for t in tentative if t["bed_id"] == bed_id and t["cycle_year"] == prev]
        g = p["feeder"] if tg else None
    me = p["feeder"]
    table = {("heavy", "fixer"): 2, ("heavy", "heavy"): -2, ("fixer", "heavy"): 1,
             ("light", "heavy"): 1, ("light", "medium"): 0.5, ("medium", "fixer"): 1,
             ("fixer", "fixer"): -1}
    return table.get((me, g), 0.0)


def _companion_score(ctx: Ctx, p: dict, bed_id: int, s: dt.date, e: dt.date, year: int):
    score = 0.0
    for i in ctx.instances(year):
        if i.planting["bed_id"] != bed_id or i.start > e or i.end < s:
            continue
        q = i.plant
        if q["id"] in p["avoid"] or p["id"] in q["avoid"]:
            score -= 3
        elif q["id"] in p["companions"] or p["id"] in q["companions"]:
            score += 0.5
    return min(score, 1.5)


def place(food: dict, p: dict, fit: dict, soils: dict, area_needed: float, ctx: Ctx):
    method, dtm, eng = fit["method"], fit["dtm"], fit.get("risk_engine") or ctx.engine
    wins = fit["windows"]
    perennial = p["lifecycle"] == "perennial"
    years = [ctx.current_cycle] if perennial else list(range(1, ctx.n + 1))
    use = [wins[0]]
    if food["use"] == "fresh" and p.get("succession") and len(wins) > 1:
        use = wins[:2]
    per_window = area_needed / len(use)
    # don't scatter a crop into slivers: chunks of at least ~a quarter of the need
    largest = max((b["length_ft"] * b["width_ft"] for b in ctx.beds), default=0.0)
    min_area = min(max(plant_area(p), 4.0, 0.25 * per_window), per_window, largest)
    any_ok_soil = any(s["fit"] != "poor" for s in soils.values())
    max_beds = 3
    if ctx.auto:  # beds are added to fit, so a big planting may span more of them
        t_area = ctx.template["length_ft"] * ctx.template["width_ft"]
        max_beds = max(3, math.ceil(per_window / t_area) + 1)
    tentative, placements, problems, short = [], [], [], []
    missing = 0.0
    for cyc in years:
        year = ctx.start + cyc - 1
        for w in use:
            plan, s, e = _dates_for(eng, p, w["establish"], method, dtm, year)
            remaining = per_window
            cands = []
            for bed in ctx.beds:
                sf = soils[bed["id"]]["fit"]
                if sf == "poor" and any_ok_soil:
                    continue
                free = _free_area(ctx, bed, s, e, year, tentative)
                if perennial:  # it stays put, so it needs the room every year of the cycle
                    for y in range(ctx.start, ctx.start + ctx.n):
                        if y != year:
                            ys = dates.to_date(y, plan["establish"])
                            ye = dates.to_date(y, plan["harvest_end"])
                            free = min(free, _free_area(ctx, bed, ys, ye, y, tentative))
                if free + 1e-6 < min_area:
                    continue
                score = {"good": 3, "fixable": 1, "poor": -4}[sf]
                gap = _family_conflict(ctx, p, bed["id"], cyc, tentative)
                if gap is not None:
                    # a hard rule unless the cycle is too short to ever satisfy it
                    if gap != ctx.n:
                        continue
                    score -= 6
                score += _sequence_bonus(ctx, p, bed["id"], cyc, tentative)
                score += _companion_score(ctx, p, bed["id"], s, e, year)
                score += 4 * min(free / remaining, 1.0)  # fewer, fuller beds
                cands.append((score, -bed["id"], bed, free, gap))
            cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
            used = 0
            for score, _, bed, free, gap in cands:
                if remaining <= 0.5 or used >= max_beds:
                    break
                a = round(min(remaining, free), 1)
                if a < min_area and a < remaining - 0.5:
                    continue
                succ = 1
                if food["use"] == "fresh" and p.get("succession"):
                    succ = max(1, min(len(w.get("successions") or [1]), 4))
                item = {"bed_id": bed["id"], "bed": bed["name"], "cycle_year": cyc,
                        "calendar_year": year, "doy": w["establish"], "method": method,
                        "dtm_override": dtm, "area_sqft": a, "successions": succ,
                        "start": s, "end": e, "season": w["season"],
                        "family_gap": gap, "soil_fit": soils[bed["id"]]["fit"],
                        "plan": plan}
                placements.append(item)
                tentative.append(item)
                remaining -= a
                used += 1
            if remaining > max(0.5, 0.1 * per_window):
                missing = max(missing, remaining)
                short.append((year, remaining, w["season"].lower()))
    total_short = sum(r for _, r, _ in short)
    if short:
        yrs = [str(y) for y, _, _ in short]
        when = yrs[0] if len(yrs) == 1 else ", ".join(yrs[:-1]) + " and " + yrs[-1]
        partial = all(r < per_window - 0.5 for _, r, _ in short)
        problems.append(
            f"{'Not enough' if partial else 'No'} room in {when} for the "
            f"{' & '.join(sorted({s for _, _, s in short}))} planting without breaking the "
            f"{FAMILY_COMMON.get(p['family'], p['family']).lower()} rotation or crowding other "
            "crops.")
    return placements, problems, missing, total_short


# ---------------------------------------------------------------- assess
def assess(food_id: str, amount_lb: float | None = None, ctx: Ctx | None = None) -> dict:
    ctx = ctx or Ctx()
    food = resolve(food_id, ctx.plants)
    if not food:
        raise KeyError(food_id)
    base = {"food": _food_out(food, ctx), "amount_lb": amount_lb}
    if not food["plant_id"]:
        return {**base, "verdict": "unsuitable", "headline": f"{food['name']}: not a garden crop here",
                "reasons": [food["note"]], "placements": [], "steps": [], "workaround": None}
    p = ctx.plants[food["plant_id"]]
    base["plant"] = {"id": p["id"], "name": p["name"], "family": p["family"],
                     "family_common": FAMILY_COMMON.get(p["family"], p["family"])}
    fit = climate_fit(food, p, ctx)
    soils = {b["id"]: soil_fit(p, ctx.soils[b["id"]], b) for b in ctx.beds}
    base["soil"] = [{"bed_id": b["id"], "bed": b["name"], **soils[b["id"]]} for b in ctx.beds]
    base["climate"] = {k: v for k, v in fit.items() if k not in ("risk_engine", "windows")}
    base["climate"]["windows"] = [{"season": w["season"], "start": w["start_label"],
                                   "end": w["end_label"], "labels": w["labels"]}
                                  for w in fit["windows"]]
    if fit["status"] == "unsuitable":
        return {**base, "verdict": "unsuitable",
                "headline": f"{food['name']}: not suited to your climate",
                "reasons": fit["reasons"], "workaround": fit.get("workaround"),
                "placements": [], "steps": []}
    if not ctx.beds:
        return {**base, "verdict": "needs_beds", "headline": "Add a bed first",
                "reasons": ["Your rotation is organized by bed — add at least one."],
                "workaround": None, "placements": [], "steps": []}
    if all(s["fit"] == "poor" for s in soils.values()):
        fixes = sorted({f for s in soils.values() for f in s["fixes"]})
        return {**base, "verdict": "unsuitable",
                "headline": f"{food['name']}: your soil doesn't suit it",
                "reasons": sorted({i for s in soils.values() for i in s["issues"]}),
                "workaround": " ".join(fixes), "placements": [], "steps": []}
    area, how = area_for(food, p, amount_lb)
    placements, problems, missing, total_short = place(food, p, fit, soils, area, ctx)
    verdict = fit["status"]
    if any(pl["soil_fit"] != "good" for pl in placements) and verdict == "good":
        verdict = "fixable"
    if problems and placements:
        verdict = "partial"
        problems.append(f"About {missing:.0f} more sq ft of bed space (for example "
                        f"{_bed_suggestion(missing)}) would let it grow every year.")
    if not placements:
        verdict = "no_space"
    yearly = _yearly_area(placements, p)
    expected = round(yearly * food["yield_lb_sqft"], 1) if food["yield_lb_sqft"] else None
    headline = {
        "good": f"{food['name']}: a great fit for your garden",
        "fixable": f"{food['name']}: a good fit with a little soil prep",
        "marginal": f"{food['name']}: possible here, with some help",
        "no_space": f"{food['name']}: right climate, but your beds are full then",
        "partial": f"{food['name']}: right climate, but only room in some years",
    }[verdict]
    out = {**base, "verdict": verdict, "headline": headline, "reasons": problems,
           "workaround": fit.get("workaround"), "area_needed": round(area, 1),
           "area_missing": round(total_short, 1),   # across every year that's short
           "area_basis": how, "area_per_year": round(yearly, 1),
           "expected_yield": expected, "unit": food["unit"],
           "placements": [_placement_out(pl, p) for pl in placements]}
    out["steps"] = build_steps(food, p, fit, soils, placements, ctx, expected, yearly)
    return out


def _bed_suggestion(sqft: float) -> str:
    for w, length in ((3, 6), (4, 6), (4, 8), (4, 12), (4, 16)):
        if w * length >= sqft:
            return f"one {w}×{length} ft bed"
    n = -(-int(round(sqft)) // 32)
    words = {2: "two", 3: "three", 4: "four", 5: "five"}
    return f"{words[n]} 4×8 ft beds" if n in words else f"{n} beds of 4×8 ft"


def _yearly_area(placements, p) -> float:
    if not placements:
        return 0.0
    by_year: dict[int, float] = {}
    for pl in placements:
        by_year[pl["cycle_year"]] = by_year.get(pl["cycle_year"], 0) + pl["area_sqft"]
    return sum(by_year.values()) / len(by_year)


def _food_out(food: dict, ctx: Ctx) -> dict:
    return {k: food[k] for k in ("id", "name", "plant_id", "use", "variety", "unit", "note")}


def _placement_out(pl: dict, p: dict) -> dict:
    plan = pl["plan"]
    verb = "Plant" if p.get("special") else \
        {"transplant": "Transplant", "direct": "Sow"}.get(pl["method"], "Plant")
    return {"verb": verb, "bed_id": pl["bed_id"], "bed": pl["bed"], "cycle_year": pl["cycle_year"],
            "calendar_year": pl["calendar_year"], "doy": pl["doy"], "method": pl["method"],
            "area_sqft": pl["area_sqft"], "successions": pl["successions"],
            "dtm_override": pl["dtm_override"], "season": pl["season"],
            "establish": pl["start"].isoformat(), "harvest_end": pl["end"].isoformat(),
            "maturity": dates.to_date(pl["calendar_year"], plan["maturity"]).isoformat(),
            "soil_fit": pl["soil_fit"]}


# ----------------------------------------------------------- garden sizing
SHORT_OF_SPACE = {"partial", "no_space", "needs_beds"}


def assess_sized(food_id: str, amount_lb: float | None = None) -> tuple[dict, Ctx, int]:
    """Assess a food; with garden sizing on, add beds (from the bed template)
    until it fits. Returns the assessment, its context and how many beds were
    added. Beds that end up unused are removed by ``prune_auto_beds``."""
    ctx = Ctx()
    res = assess(food_id, amount_lb, ctx)
    added = 0
    if not ctx.auto:
        return res, ctx, added
    t = ctx.template
    bed_area = t["length_ft"] * t["width_ft"]
    for _ in range(6):
        if res["verdict"] not in SHORT_OF_SPACE:
            break
        missing = res.get("area_missing") or bed_area
        n = max(1, math.ceil(missing / bed_area - 0.05))
        names = _next_bed_names(n)
        for name in names:
            svc.add_bed(name, t["length_ft"], t["width_ft"], t["kind"], auto=True)
        added += n
        ctx = Ctx()
        new = assess(food_id, amount_lb, ctx)
        stuck = (new["verdict"] in SHORT_OF_SPACE and res["verdict"] != "needs_beds"
                 and new.get("area_missing", 0) >= missing - 0.5)
        res = new
        if stuck:   # more beds don't help (e.g. the template's soil doesn't suit it)
            break
    return res, ctx, added


def _next_bed_names(n: int) -> list[str]:
    nums = [int(m.group(1)) for b in svc.beds() if (m := re.fullmatch(r"Bed (\d+)", b["name"]))]
    start = max(nums, default=len(svc.beds())) + 1
    return [f"Bed {start + i}" for i in range(n)]


def prune_auto_beds() -> int:
    """Remove beds the planner added that no longer hold anything (no
    plantings, and nothing logged against them)."""
    rows = db.query("SELECT id FROM beds WHERE auto = 1 AND id NOT IN "
                    "(SELECT bed_id FROM plantings) AND id NOT IN (SELECT bed_id FROM waterings) "
                    "AND id NOT IN (SELECT bed_id FROM amendments)")
    for r in rows:
        db.execute("DELETE FROM beds WHERE id = ?", (r["id"],))
    return len(rows)


# ------------------------------------------------------------------ guide
def build_steps(food, p, fit, soils, placements, ctx: Ctx, expected, yearly) -> list[dict]:
    steps = []
    w = fit["windows"][0]
    lab = w["labels"]
    if food.get("variety"):
        steps.append({"title": "Pick the variety", "text": food["variety"] + "."})
    elif fit.get("workaround") and "variety" in fit["workaround"]:
        steps.append({"title": "Pick the variety", "text": fit["workaround"]})

    prep = []
    beds_used = sorted({pl["bed_id"] for pl in placements})
    for bid in beds_used:
        s = soils[bid]
        if s["fixes"]:
            prep.append(f"{ctx.bed_map[bid]['name']}: " + " ".join(s["fixes"]))
    if p["feeder"] == "fixer":
        prep.append("Legumes make their own nitrogen — skip nitrogen fertilizer. Dust seed with "
                    "a legume inoculant the first time they grow in a bed.")
    elif p["feeder"] == "heavy":
        prep.append("Mix an inch of compost into the bed before planting.")
    steps.append({"title": "Prepare the soil",
                  "text": " ".join(prep) if prep else "Your soil suits it — just loosen the bed "
                                                      "and rake it smooth."})

    if fit["method"] == "transplant" and lab.get("indoor_start"):
        steps.append({"title": "Start seeds indoors",
                      "text": f"Sow indoors {lab['indoor_start']} under lights, at "
                              f"{p['germ_min']}°F or warmer. Harden off from "
                              f"{lab.get('harden_off', '')} for a week."})
    pa = plant_area(p)
    n_plants = max(1, int(round(yearly / pa))) if yearly else None
    verb = {"transplant": "Transplant", "direct": "Sow"}.get(fit["method"], "Plant")
    if p.get("special"):
        verb = "Plant"
    succ = ""
    if placements and placements[0]["successions"] > 1:
        succ = (f" Sow a new batch every {p['succession']} days "
                f"({placements[0]['successions']} sowings) for a steady supply.")
    seasons = " and ".join(sorted({x["season"].lower() for x in placements})) if placements else ""
    steps.append({"title": f"{verb} outside",
                  "text": f"{verb} around {lab['establish']} (window {w['start_label']} – "
                          f"{w['end_label']}){f', with a {seasons} planting' if ' and ' in seasons else ''}. "
                          f"Space {p['spacing']}\" apart"
                          + (f", {p['depth']}\" deep" if p.get("depth") and verb == "Sow" else "")
                          + (f" — about {n_plants} plants" if n_plants else "") + "." + succ})

    mat = w["maturity"]
    et0 = float(ctx.clim.et0[[(mat - k) % 365 for k in range(21)]].mean())
    weekly = et0 * p["kc"][1] * 7
    steps.append({"title": "Water",
                  "text": f"At peak growth it uses about {weekly:.1f}\" of water a week "
                          f"(~{weekly * 0.623:.1f} gal per sq ft). Keep the soil evenly moist; "
                          "the Today page tells you when each bed needs it."})

    for note in fit.get("notes", []):
        steps.append({"title": "Heads-up", "text": note})

    harvest = (f"Harvest from about {lab.get('maturity')}"
               + (f" until {dates.label(w['harvest_end'])}" if w.get("harvest_end") else "") + ".")
    if p.get("special") and p["special"].get("first_harvest_year", 1) > 1:
        harvest += f" First real harvest in year {p['special']['first_harvest_year']}."
    if food.get("how"):
        harvest += " " + food["how"]
    if expected:
        harvest += f" Expect roughly {expected:g} {food['unit']} a year from {yearly:.0f} sq ft."
    steps.append({"title": "Harvest", "text": harvest})

    by_year: dict[int, list[str]] = {}
    for x in placements:
        names = by_year.setdefault(x["calendar_year"], [])
        if x["bed"] not in names:
            names.append(x["bed"])
    if len(by_year) > 1:
        fam = FAMILY_COMMON.get(p["family"], p["family"]).lower()
        moves = "; ".join(f"{y}: {', '.join(b)}" for y, b in sorted(by_year.items()))
        steps.append({"title": "Every year",
                      "text": f"It rotates through your beds ({moves}) so {fam} don't build up "
                              "soil diseases, then the cycle repeats."})
    return steps


# ------------------------------------------------------------------ apply
def apply(assessment: dict, food: dict, ctx: Ctx | None = None) -> list[int]:
    ctx = ctx or Ctx()
    p = ctx.plants[food["plant_id"]]
    ids = []
    for pl in assessment["placements"]:
        residue = "incorporate" if p["category"] == "cover" else "remove"
        ids.append(db.execute(
            "INSERT INTO plantings(bed_id, plant_id, cycle_year, doy, method, area_sqft, "
            "successions, dtm_override, residue, notes) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (pl["bed_id"], p["id"], pl["cycle_year"], pl["doy"], pl["method"], pl["area_sqft"],
             pl["successions"], pl["dtm_override"], residue, f"For {food['name']}")))
    return ids


def feeding_advice(planting_ids: list[int]) -> list[str]:
    """The feedings planned for the new plantings or, with automatic feeding
    off, any shortfall the nitrogen model projects for them."""
    if not planting_ids:
        return []
    from . import feeding
    planned = feeding.describe(planting_ids)
    if planned:
        return ["Your soil can't supply all the nitrogen this crop needs for a full "
                "harvest, so these feedings are on your calendar:"] + planned
    rows = db.query(f"SELECT DISTINCT bed_id FROM plantings WHERE id IN "
                    f"({','.join('?' * len(planting_ids))})", tuple(planting_ids))
    out = []
    for r in rows:
        res = svc.nitrogen_for_bed(r["bed_id"], cycles=1)
        for rec in res["recommendations"]:
            if rec["kind"] == "deficit" and rec.get("planting_id") in planting_ids:
                out.append(f"{res['bed']}: {rec['text']}")
    return out


def bundle_list() -> list[dict]:
    return [{"id": k, "name": v["name"], "foods": v["foods"]} for k, v in BUNDLES.items()]



# ------------------------------------------------------------- cover crops
COVER_CHOICES = {
    # next year's main crop group -> preferred covers (first that fits wins)
    "heavy": ["hairy_vetch", "crimson_clover", "winter_pea", "cereal_rye", "oats"],
    "fixer": ["cereal_rye", "oats", "winter_wheat"],
    None: ["crimson_clover", "cereal_rye", "oats"],
}


def fill_cover_crops(ctx: Ctx | None = None) -> list[dict]:
    """Put a winter cover crop into every bed that would sit bare over winter,
    choosing a legume ahead of heavy feeders and a nitrogen catch crop
    otherwise — only where it fits between harvest and next spring's planting."""
    ctx = ctx or Ctx()
    added = []
    for bed in ctx.beds:
        area = bed["length_ft"] * bed["width_ft"]
        if any(pl["bed_id"] == bed["id"] and ctx.plants.get(pl["plant_id"], {})
               .get("lifecycle") == "perennial" for pl in ctx.plantings):
            continue
        for cyc in range(1, ctx.n + 1):
            year = ctx.start + cyc - 1
            insts = [i for i in ctx.instances(year) if i.planting["bed_id"] == bed["id"]]
            if not insts:
                continue
            dec = dt.date(year, 12, 15)
            nxt = [i for i in ctx.instances(year + 1) if i.planting["bed_id"] == bed["id"]]
            if any(i.active_on(dec) for i in insts + nxt):
                continue
            next_cyc = cyc % ctx.n + 1
            group = main_group([pl for pl in ctx.plantings if pl["bed_id"] == bed["id"]
                                and pl["cycle_year"] == next_cyc], ctx.plants)
            for pid in COVER_CHOICES.get(group, COVER_CHOICES[None]):
                p = ctx.plants.get(pid)
                if not p:
                    continue
                if p["family"] == "Fabaceae" and _family_conflict(ctx, p, bed["id"], cyc, []):
                    continue
                w = ctx.engine.windows(p)
                if not w["windows"]:
                    continue
                win = w["windows"][0]
                # latest sowing that still fits after this year's last harvest
                last = max(i.end for i in insts)
                sow = max(win["establish"], dates.doy(last) + 3)
                if sow > win["end"]:
                    continue
                plan, s, e = _dates_for(ctx.engine, p, sow, w["method"], None, year)
                free = _free_area(ctx, bed, s, e, year, [])
                if free < 0.6 * area:
                    continue
                pid_new = db.execute(
                    "INSERT INTO plantings(bed_id, plant_id, cycle_year, doy, method, "
                    "area_sqft, successions, residue, notes) VALUES(?,?,?,?,?,?,?,?,?)",
                    (bed["id"], pid, cyc, sow, w["method"], round(free, 1), 1, "incorporate",
                     "Winter cover crop (auto)"))
                added.append({"planting_id": pid_new, "bed": bed["name"], "cycle_year": cyc,
                              "plant": p["name"], "sow": s.isoformat(),
                              "terminate": e.isoformat()})
                ctx.plantings = svc.plantings()
                ctx._years.clear()
                break
    return added
