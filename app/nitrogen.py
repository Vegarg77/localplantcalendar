"""Daily soil-nitrogen budget for a bed across the whole rotation cycle.

Pools (lb N per acre-equivalent, converted to per-bed amounts for display):

* **Mineral N** (nitrate + ammonium) — what plants can use right now.
* **Organic N** in soil organic matter — mineralises ~1.7 %/yr at the site's
  average temperature (the extension rule of thumb "each 1 % organic matter
  releases ~20 lb N/acre/yr"), faster in warm soil, nearly zero below 41 °F.
* **Residue/amendment pools** — crop residues, cover crops, compost and
  fertilisers release N on their own schedules.  High carbon residues (mature
  rye, corn stalks) first *tie up* mineral N.

Flows: crop uptake follows an S-curve over each crop's development; legumes
draw little from the soil and leave fixed N in roots/residue; water draining
below the root zone (winter rain on a bare bed) leaches nitrate.

It is a planning model, not a lab test: use it to see trends ("this bed runs
short every third year", "you lose N over winter with no cover crop") and
calibrate the starting value with a soil nitrate test when you can.
"""

from __future__ import annotations

import datetime as dt
import math

from . import dates
from .climate import Climate
from .garden import Instance

SQFT_PER_ACRE = 43560.0
SOIL_LB_PER_ACRE_6IN = 2_000_000.0
N_FRACTION_OF_OM = 0.058
MINERALIZATION_PER_YEAR = 0.0172
PPM_TO_LB_ACRE_12IN = 4.0        # 1 ppm nitrate-N in the top 12" ~ 4 lb/acre
UNAVAILABLE_FLOOR = 5.0           # lb/acre plants can't strip out

# product: (default N %, fraction available in-season, release half-life days)
PRODUCTS = {
    "compost": ("Compost", 1.0, 0.10, 90),
    "aged_manure": ("Aged manure", 1.5, 0.25, 60),
    "worm_castings": ("Worm castings", 1.0, 0.20, 60),
    "blood_meal": ("Blood meal (12-0-0)", 12.0, 0.75, 14),
    "feather_meal": ("Feather meal (12-0-0)", 12.0, 0.60, 45),
    "fish_emulsion": ("Fish emulsion (5-1-1)", 5.0, 0.90, 5),
    "alfalfa_meal": ("Alfalfa meal (2.5-1-2)", 2.5, 0.50, 30),
    "soybean_meal": ("Soybean meal (7-1-2)", 7.0, 0.60, 30),
    "cottonseed_meal": ("Cottonseed meal (6-2-1)", 6.0, 0.55, 40),
    "organic_555": ("Balanced organic fertilizer (5-5-5)", 5.0, 0.50, 30),
    "urea": ("Urea (46-0-0)", 46.0, 1.00, 3),
    "ammonium_sulfate": ("Ammonium sulfate (21-0-0)", 21.0, 1.00, 2),
    "synthetic_101010": ("Synthetic 10-10-10", 10.0, 1.00, 3),
}

RESIDUE_RELEASE = {
    # fraction mineralised quickly, half-life days, immobilisation fraction
    "low": (0.60, 20, 0.0),
    "medium": (0.35, 40, 0.0),
    "high": (0.10, 60, 0.40),
}


def _temp_factor(t_f: float) -> float:
    if t_f < 41:
        return 0.0
    return 2.0 ** ((t_f - 68.0) / 18.0)  # Q10 = 2 per 10 °C


def _logistic(frac: float) -> float:
    lo, hi = 1 / (1 + math.exp(5)), 1 / (1 + math.exp(-5))
    v = 1 / (1 + math.exp(-10 * (frac - 0.5)))
    return min(max((v - lo) / (hi - lo), 0.0), 1.0)


def lb_acre_to_bed_oz(lb_acre: float, area_sqft: float) -> float:
    return lb_acre * area_sqft / SQFT_PER_ACRE * 16


class _Uptake:
    """Cumulative uptake curve for one instance, by GDD progress."""

    def __init__(self, inst: Instance, clim: Climate, bed_area: float):
        p = inst.plant
        self.inst = inst
        self.frac_area = min(inst.area / bed_area, 1.0) if bed_area else 1.0
        self.fixer = p["feeder"] == "fixer"
        self.demand = p["n_demand"] * self.frac_area
        self.start = inst.start
        grow_end = inst.maturity + (inst.harvest_end - inst.maturity) / 2
        if inst.kind == "perennial":
            grow_end = inst.end
        self.stop = max(grow_end, self.start + dt.timedelta(days=7))
        base, cap = p["base_f"], (86.0 if p["season"] == "warm" else 75.0)
        g = []
        d = self.start
        while d <= self.stop:
            t = float(clim.tmean[dates.doy(d)])
            g.append(max(0.0, min(t, cap) - base) + 0.05)
            d += dt.timedelta(days=1)
        tot = sum(g)
        acc, self.curve = 0.0, []
        for x in g:
            acc += x
            self.curve.append(_logistic(acc / tot))
        self.taken = 0.0
        self.deficit = 0.0
        self.peak_deficit_day: dt.date | None = None

    def want(self, day: dt.date) -> float:
        if day < self.start or day > self.stop:
            return 0.0
        i = (day - self.start).days
        prev = self.curve[i - 1] if i > 0 else 0.0
        return (self.curve[i] - prev) * self.demand


def simulate(bed: dict, soil: dict, insts: list[Instance], amendments: list[dict],
             clim: Climate, start_year: int, years: int, settings: dict,
             cycle_of_year) -> dict:
    area = bed["length_ft"] * bed["width_ft"]
    om0 = float(soil["om_pct"])
    organic = om0 / 100 * SOIL_LB_PER_ACRE_6IN * N_FRACTION_OF_OM
    mineral = float(bed.get("initial_no3_ppm") or 10) * PPM_TO_LB_ACRE_12IN
    fc12 = float(soil.get("fc", 0.28)) * 12
    taw12 = float(soil.get("awc", 0.17)) * 12
    storage = taw12 * 0.8

    tf_mean = sum(_temp_factor(float(t)) for t in clim.tmean) / 365 or 1.0
    k_day = MINERALIZATION_PER_YEAR / 365

    uptakes = [_Uptake(i, clim, area) for i in insts]
    ends: dict[dt.date, list[_Uptake]] = {}
    for u in uptakes:
        ends.setdefault(u.inst.end, []).append(u)

    pools: list[list[float]] = []   # [remaining, daily_k, kind: +1 residue / +2 amendment
    #                                  release, -1 immobilise]
    events, series = [], []
    yearly: dict[int, dict] = {}

    # amendments are planned per cycle year and repeat every cycle
    amend_by_day: dict[dt.date, list[dict]] = {}
    for y in range(start_year, start_year + years):
        cyc = cycle_of_year(y)
        for a in amendments:
            if a["cycle_year"] == cyc:
                amend_by_day.setdefault(dates.to_date(y, a["doy"]), []).append(a)

    day = dt.date(start_year, 1, 1)
    end_day = dt.date(start_year + years - 1, 12, 31)
    while day <= end_day:
        y = yearly.setdefault(day.year, {
            "year": day.year, "cycle_year": cycle_of_year(day.year),
            "start_mineral": mineral, "mineralized": 0.0, "residue": 0.0,
            "amendments": 0.0, "uptake": 0.0, "leached": 0.0, "fixed": 0.0,
            "deficit": 0.0, "immobilized": 0.0})
        doy = dates.doy(day)
        t = float(clim.tmean[doy])
        tf = _temp_factor(t) / tf_mean

        # 1. soil organic matter mineralisation
        m = organic * k_day * tf
        organic -= m
        mineral += m
        y["mineralized"] += m

        # 2. residue / amendment pools
        for pool in pools:
            if pool[0] <= 0:
                continue
            r = pool[0] * (1 - math.exp(-pool[1] * max(tf, 0.15)))
            pool[0] -= r
            if pool[2] > 0:
                mineral += r
                if pool[2] == 1:   # amendments are already counted when applied
                    y["residue"] += r
            else:
                take = min(r, max(mineral - UNAVAILABLE_FLOOR, 0.0))
                mineral -= take
                organic += take
                y["immobilized"] += take
        pools = [p for p in pools if p[0] > 0.01]

        # 3. amendments applied today
        for a in amend_by_day.get(day, []):
            name, n_pct_def, avail, half = PRODUCTS.get(
                a["product"], (a["product"], a.get("n_pct") or 5.0, 0.5, 30))
            n_pct = a.get("n_pct") or n_pct_def
            n_lb_acre = a["amount_lb"] * n_pct / 100 * SQFT_PER_ACRE / max(area, 1e-6)
            pools.append([n_lb_acre * avail, math.log(2) / half, 2])
            organic += n_lb_acre * (1 - avail)
            y["amendments"] += n_lb_acre
            events.append({"date": day.isoformat(), "type": "amendment",
                           "label": f"{a['amount_lb']:g} lb {name}",
                           "n_lb_acre": round(n_lb_acre, 1)})

        # 4. crop uptake
        wants = [(u, u.want(day)) for u in uptakes]
        total = sum(w for _, w in wants)
        if total > 0:
            avail = max(mineral - UNAVAILABLE_FLOOR, 0.0) * 0.5
            got = min(total, avail)
            ratio = got / total
            for u, w in wants:
                if w <= 0:
                    continue
                g = w * ratio
                u.taken += g
                short = w - g
                if short > 0:
                    if u.fixer:
                        y["fixed"] += short  # nodules make up the difference
                    else:
                        u.deficit += short
                        y["deficit"] += short
                        if u.peak_deficit_day is None:
                            u.peak_deficit_day = day
            mineral -= got
            y["uptake"] += got

        # 5. residues return when a crop finishes
        for u in ends.get(day, []):
            p = u.inst.plant
            incorporate = (u.inst.planting.get("residue") or "remove") == "incorporate"
            # removing residue still leaves roots (~10 %) behind
            res_n = u.taken * (p["residue_frac"] if incorporate else 0.1 * p["residue_frac"])
            if u.fixer:
                fix = p["n_fix"] * u.frac_area * (1.0 if incorporate else 0.4)
                res_n += fix
                y["fixed"] += fix
            if res_n > 0:
                quick, half, immob = RESIDUE_RELEASE[p["residue_cn"]]
                pools.append([res_n * quick, math.log(2) / half, 1])
                organic += res_n * (1 - quick)
                if immob:
                    pools.append([res_n * immob, math.log(2) / 20, -1])
                events.append({"date": day.isoformat(), "type": "residue",
                               "label": f"{p['name']} residue "
                                        f"{'incorporated' if incorporate else 'removed'}",
                               "n_lb_acre": round(res_n, 1)})

        # 6. water balance & leaching
        active = [u for u in uptakes if u.start <= day <= u.stop]
        kc = 1.0 if active else 0.3
        storage += float(clim.precip[doy])
        storage -= kc * float(clim.et0[doy])
        if active and storage < 0.5 * taw12:
            storage = 0.5 * taw12     # irrigated in season
        storage = max(storage, 0.0)
        drain = max(storage - taw12, 0.0)
        storage -= drain
        if drain > 0 and mineral > UNAVAILABLE_FLOOR:
            loss = (mineral - UNAVAILABLE_FLOOR) * 0.9 * drain / (fc12 + drain)
            mineral -= loss
            y["leached"] += loss

        y["end_mineral"] = mineral
        y["end_om_pct"] = organic / (SOIL_LB_PER_ACRE_6IN * N_FRACTION_OF_OM) * 100
        if day.weekday() == 0 or day == end_day:
            series.append({"date": day.isoformat(), "mineral": round(mineral, 1),
                           "ppm": round(mineral / PPM_TO_LB_ACRE_12IN, 1),
                           "om_pct": round(y["end_om_pct"], 2)})
        day += dt.timedelta(days=1)

    crops = []
    for u in uptakes:
        if u.inst.kind == "perennial" and u.demand <= 0:
            continue
        need_oz = lb_acre_to_bed_oz(u.deficit, area)
        crops.append({
            "name": u.inst.plant["name"], "plant_id": u.inst.plant["id"],
            "year": u.inst.year, "planting_id": u.inst.planting["id"],
            "start": u.start.isoformat(), "end": u.inst.end.isoformat(),
            "demand_lb_acre": round(u.demand, 1), "taken_lb_acre": round(u.taken, 1),
            "deficit_lb_acre": round(u.deficit, 1), "fixer": u.fixer,
            "deficit_n_oz_bed": round(need_oz, 2),
            "short_from": u.peak_deficit_day.isoformat() if u.peak_deficit_day else None,
        })

    recs = _recommendations(crops, yearly, uptakes, area, om0, settings, clim, amendments)
    return {
        "bed_id": bed["id"], "bed": bed["name"], "area_sqft": area,
        "series": series, "events": events, "crops": crops,
        "years": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in yr.items()}
                  for yr in yearly.values()],
        "recommendations": recs,
        "start_om_pct": om0,
        "end_om_pct": round(organic / (SOIL_LB_PER_ACRE_6IN * N_FRACTION_OF_OM) * 100, 2),
    }


def blood_meal_oz(n_oz: float) -> float:
    return n_oz / 0.12


def _md(d: dt.date) -> str:
    return f"{dates.MONTH_ABBR[d.month - 1]} {d.day}"


_LEGUMES: dict[str, dict] | None = None


def _legume_covers() -> dict[str, dict]:
    global _LEGUMES
    if _LEGUMES is None:
        from .plant_data import builtin_plants
        ids = ("hairy_vetch", "crimson_clover", "cowpea_cover", "sunn_hemp")
        _LEGUMES = {p["id"]: p for p in builtin_plants() if p["id"] in ids}
    return _LEGUMES


def _winter_legume(p: dict, lsf: int, fff: int) -> tuple[int, int]:
    """(last sowing day, first day it can be cut) for a fall-sown legume, as day
    indices relative to the year it's cut in (sowing is negative = last fall)."""
    sow = p["special"]["plant"]
    cut = p["special"]["harvest"]
    return fff + sow[3] - 365, lsf + cut[1]


def _grow_n_first(inst: Instance, insts: list[Instance], lsf: int, fff: int) -> str | None:
    """Suggest a legume that fits the gap before ``inst`` in the same bed."""
    if inst.kind == "perennial":
        return None
    before = [i for i in insts if i is not inst and i.end < inst.start]
    prev = max(before, key=lambda i: i.end, default=None)
    if prev and prev.plant["feeder"] == "fixer" and (inst.start - prev.end).days <= 90:
        return None  # a legume already goes right before it
    covers = _legume_covers()
    start = dates.doy(inst.start)
    free_from = (dates.doy(prev.end) - 365 * (inst.start.year - prev.end.year)
                 if prev else -365)
    # fall-sown legume, cut ~3 weeks before a spring/early-summer planting
    for pid in ("hairy_vetch", "crimson_clover"):
        p = covers.get(pid)
        if not p or start > 181:
            continue
        sow_by, cut = _winter_legume(p, lsf, fff)
        if free_from + 7 <= sow_by and cut + 21 <= start:
            credit = p["n_fix"] * RESIDUE_RELEASE["low"][0]
            sow = dates.to_date(inst.start.year, sow_by % 365)
            return (f"Grow nitrogen first: sow {p['name'].lower()} in this bed by about "
                    f"{_md(sow)} the fall before, cut it at the soil line when it starts "
                    f"to bloom (about 3 weeks before planting) and leave or dig in the "
                    f"tops. It fixes roughly {p['n_fix']:.0f} lb N/acre, of which about "
                    f"{credit:.0f} feeds the next crop. My food → Add winter cover crops "
                    "places it for you.")
    # summer legume in a warm-season gap
    gap_from, gap_to = max(free_from + 3, lsf + 21), min(start - 14, fff - 7)
    for pid in ("cowpea_cover", "sunn_hemp"):
        p = covers.get(pid)
        if p and gap_to - gap_from >= p["dtm"][0]:
            sow = dates.to_date(inst.start.year, gap_from % 365)
            return (f"Grow nitrogen first: there's room for a summer legume. Sow "
                    f"{p['name'].lower().replace(' (cover crop)', '')} around {_md(sow)}, "
                    f"mow it at flowering ({p['dtm'][0]}–{p['dtm'][1]} days) and turn it in "
                    f"2 weeks before planting — about {p['n_fix']:.0f} lb N/acre.")
    if not (prev and prev.plant["feeder"] == "fixer"):
        return ("Grow nitrogen first: there's no gap for a cover crop here, so in your "
                "rotation put this crop in a bed that grew beans or peas the season "
                "before, and leave the legume roots in the soil when you pull them.")
    return None


def _recommendations(crops, yearly, uptakes, area, om0, settings, clim,
                     amendments=()) -> list[dict]:
    recs = []
    seen = set()
    lsf, fff = clim.anchors()
    # the last time each planting comes round has the full bed history before it
    latest: dict[int, Instance] = {}
    for u in uptakes:
        latest[u.inst.planting["id"]] = u.inst
    insts = [u.inst for u in uptakes]
    for c in crops:
        if c["fixer"] or c["deficit_lb_acre"] < 8:
            continue
        key = (c["planting_id"], c["name"])
        if key in seen:
            continue
        seen.add(key)
        oz_n = c["deficit_n_oz_bed"] * 1.25  # allow for incomplete recovery
        bm = blood_meal_oz(oz_n)
        start = dt.date.fromisoformat(c["start"])
        short = dt.date.fromisoformat(c["short_from"]) if c["short_from"] else \
            start + dt.timedelta(days=30)
        if short <= start + dt.timedelta(days=7):
            short = start + dt.timedelta(days=21)
        options = [
            f"Feed it: work about {bm / 2:.1f} oz blood meal (12-0-0) into the bed at "
            f"planting ({_md(start)}) and side-dress another {bm / 2:.1f} oz around "
            f"{_md(short)}, when it starts drawing hardest. Same N as "
            f"{oz_n / 0.05:.0f} oz of a 5-5-5, {oz_n / 0.12:.1f} oz feather meal (slower — "
            f"put it all in at planting) or {oz_n / 0.10:.1f} oz of 10-10-10. Add it under "
            "Planned amendments to see the effect.",
        ]
        inst = latest.get(c["planting_id"])
        first = _grow_n_first(inst, insts, lsf, fff) if inst else None
        if first:
            options.append(first)
        recs.append({
            "severity": "warn" if c["deficit_lb_acre"] < 30 else "high",
            "kind": "deficit", "year": c["year"], "planting_id": c["planting_id"],
            "text": f"{c['name']} ({c['year']} planting) is projected to run about "
                    f"{c['deficit_lb_acre']:.0f} lb N/acre short"
                    + (f" from {c['short_from']}" if c["short_from"] else "") +
                    f". Side-dress ~{bm:.1f} oz blood meal "
                    f"(or {oz_n / 0.05:.1f} oz of a 5-5-5) for this bed, split over two "
                    "feedings, or grow a legume cover crop beforehand.",
            "headline": f"{c['name']} ({c['year']} planting) is projected to run about "
                        f"{c['deficit_lb_acre']:.0f} lb N/acre short"
                        + (f" from {_md(short)}" if c["short_from"] else "") + ".",
            "options": options,
        })
    n_years = max(len(yearly), 1)
    fed = [a for a in amendments if a.get("auto")]
    if recs or fed:
        demand = sum(c["demand_lb_acre"] for c in crops if not c["fixer"]) / n_years
        supply = sum(yr.get("mineralized", 0) for yr in yearly.values()) / n_years
        lost = sum(yr.get("leached", 0) for yr in yearly.values()) / n_years
        why = (f"This bed's soil ({om0:.1f}% organic matter) releases about {supply:.0f} lb "
               f"N/acre a year as it breaks down. Rain draining through it carries off "
               f"about {lost:.0f}, and the crops planned here want about {demand:.0f}. ")
        if recs:
            why += ("Low nitrogen here is a real shortfall, not a measuring error: most "
                    "vegetable beds need added nitrogen, especially in soil under 3% "
                    "organic matter or where winters are wet.")
        else:
            added = sum(yr.get("amendments", 0) for yr in yearly.values()) / n_years
            why += (f"The planned feedings and amendments (below) add about {added:.0f} lb N/acre a year "
                    f"({lb_acre_to_bed_oz(added, area):.1f} oz of N for this bed) to make up "
                    "the difference, so every crop gets what it needs.")
        options = []
        if om0 < 5:
            cuft = area / 12
            options.append(
                f"Build the soil for the long run: each 1% of organic matter releases "
                f"about 20 lb N/acre a year. Spreading about an inch of compost "
                f"(~{cuft:.1f} cu ft for this bed) each year raises it over several "
                "seasons and helps the soil hold water.")
        recs.insert(0, {"severity": "info", "kind": "budget", "text": why,
                        "options": options})
    # nitrogen left over going into winter on a bare bed
    leach = [yr for yr in yearly.values() if yr.get("leached", 0) > 15]
    if leach:
        worst = max(leach, key=lambda yr: yr["leached"])
        avg = sum(yr.get("leached", 0) for yr in yearly.values()) / len(yearly)
        recs.append({
            "severity": "info", "kind": "leaching", "year": worst["year"],
            "text": f"About {avg:.0f} lb N/acre a year ({lb_acre_to_bed_oz(avg, area):.2f} oz for "
                    f"this bed) washes below the roots, up to {worst['leached']:.0f} in "
                    f"{worst['year']} (rotation year {worst['cycle_year']}) — mostly in wet "
                    "months with nothing growing. A fall cover crop holds it: cereal rye "
                    "catches the most, while a legume such as crimson clover catches less "
                    "but adds nitrogen of its own.",
        })
    if yearly:
        last = list(yearly.values())[-1]
        end_om = last.get("end_om_pct", om0)
        if end_om < om0 - 0.1:
            years = len(yearly)
            lost_frac = (om0 - end_om) / years / 100
            n_lb_acre = lost_frac * SOIL_LB_PER_ACRE_6IN * N_FRACTION_OF_OM
            compost_lb_acre = n_lb_acre / 0.01 / 0.9
            per_bed = compost_lb_acre * area / SQFT_PER_ACRE
            recs.append({
                "severity": "info", "kind": "organic_matter",
                "text": f"Soil organic matter drifts from {om0:.1f}% to {end_om:.1f}% "
                        f"over {years} years. Roughly {per_bed:.0f} lb of compost per "
                        "year (or a cover crop turned in) holds it steady.",
            })
    return recs


def outlook(native: dict, raised: dict, clim: Climate, auto_feed: bool = True) -> dict:
    """What the soil at this site can feed on its own, before anything is
    planted: an empty bed of native soil and of raised-bed mix, run for three
    years so the starting nitrate washes out of the numbers."""
    def bare(soil: dict) -> dict:
        bed = {"id": 0, "name": "", "length_ft": 1, "width_ft": 1, "initial_no3_ppm": 10}
        return simulate(bed, soil, [], [], clim, 2001, 3, {}, lambda y: 1)["years"][-1]

    nat, mix = bare(native), bare(raised)
    supply, lost = round(nat["mineralized"]), round(nat["leached"])
    short = supply < 100
    name = native.get("name") or "the soil survey"
    text = (f"The native soil here ({name.split(' — ')[0]}, {native['om_pct']:.1f}% organic "
            f"matter) releases about {supply} lb of nitrogen per acre a year as it breaks "
            f"down, and about {lost} lb washes out in wet months when nothing is growing. "
            "Heavy feeders such as tomatoes, sweet corn, cabbage and broccoli use 110–150 lb "
            "a year and leafy greens about 90")
    text += (", so in-ground beds won't reach full yields on soil nitrogen alone." if short
             else ", so most crops will do well on soil nitrogen alone.")
    text += (f" A compost-rich raised-bed mix releases about {round(mix['mineralized'])} lb "
             "a year while it stays rich.")
    if auto_feed:
        plan = ("As you add foods, I'll plan feedings for each crop that needs them and put "
                "them on your calendar. Cover crops, compost and anything you add yourself "
                "count first. Change the fertilizer or turn this off in Setup → Preferences.")
    else:
        plan = ("Automatic feeding is off. The Feeding & soil page shows what each bed is short "
                "and how to make it up.")
    return {"supply_lb_acre": supply, "leached_lb_acre": lost,
            "raised_supply_lb_acre": round(mix["mineralized"]), "needs_feeding": short,
            "headline": "Your soil needs help feeding hungry crops" if short
            else "Your soil can feed most crops", "text": text, "plan": plan}
