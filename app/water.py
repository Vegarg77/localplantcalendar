"""Irrigation scheduling with the FAO-56 single crop-coefficient method.

Each day:  crop water use ETc = Kc(stage) x ET0   (ET0 from Open-Meteo)
           root-zone depletion  Dr = Dr - effective rain - irrigation + ETc

Water when depletion passes the crop's "readily available water" (RAW = p x
TAW, where TAW = soil available-water capacity x root depth), and apply enough
to bring the root zone back to field capacity.
"""

from __future__ import annotations

import datetime as dt

from .garden import Instance

GALLONS_PER_INCH_SQFT = 0.623
BARE_KC = 0.3          # wet-soil evaporation from unplanted, unmulched beds
MULCH_FACTOR = 0.85    # organic mulch trims soil evaporation


def kc_at(p: dict, frac: float) -> float:
    """FAO-56 Kc curve: initial (15%), development (25%), mid (40%), late (20%)."""
    ini, mid, end = p["kc"]
    if frac < 0.15:
        return ini
    if frac < 0.40:
        return ini + (mid - ini) * (frac - 0.15) / 0.25
    if frac < 0.80:
        return mid
    return mid + (end - mid) * min(1.0, (frac - 0.80) / 0.20)


def stage_fraction(inst: Instance, day: dt.date) -> float:
    span = max((inst.end - inst.start).days, 1)
    return min(max((day - inst.start).days / span, 0.0), 1.0)


def root_depth(inst: Instance, frac: float) -> float:
    full = float(inst.plant["root_in"])
    if inst.kind == "perennial" and inst.establish is None:
        return full
    return 4.0 + (full - 4.0) * min(frac / 0.5, 1.0)


def bed_state(bed: dict, soil: dict, insts: list[Instance], day: dt.date) -> dict | None:
    """Area-weighted Kc, root depth and depletion fraction for a bed on a day."""
    area = bed["length_ft"] * bed["width_ft"]
    active = [i for i in insts if i.active_on(day)]
    if not active or area <= 0:
        return None
    kc_sum = used = 0.0
    roots, ps = [], []
    for i in active:
        frac = stage_fraction(i, day)
        a = min(i.area, area)
        kc_sum += kc_at(i.plant, frac) * a
        used += a
        roots.append(root_depth(i, frac))
        ps.append(i.plant["p"])
    bare = max(area - used, 0.0)
    kc = (kc_sum + BARE_KC * bare) / max(used + bare, 1e-6)
    if bed.get("mulched"):
        kc *= MULCH_FACTOR
    root = min(roots)
    if bed.get("kind") == "container":
        root = min(root, 12.0)
    taw = soil["awc"] * root
    p = min(ps)
    return {"kc": kc, "root_in": root, "taw": taw, "raw": p * taw, "p": p,
            "crops": [i.plant["name"] for i in active]}


def effective_rain(inches: float) -> float:
    return 0.0 if inches < 0.1 else 0.9 * inches


def schedule(bed: dict, soil: dict, insts: list[Instance], weather_days: list[dict],
             logged: dict[str, float], today: dt.date | None = None) -> dict:
    """Run the balance over recent past days, then plan the next 16 days."""
    today = today or dt.date.today()
    area = bed["length_ft"] * bed["width_ft"]
    days = [w for w in weather_days
            if dt.date.fromisoformat(w["date"]) >= today - dt.timedelta(days=21)]
    tracked = any(dt.date.fromisoformat(k) >= today - dt.timedelta(days=21)
                  for k in logged)
    dr = 0.0
    series, plan = [], []
    for idx, w in enumerate(days):
        day = dt.date.fromisoformat(w["date"])
        st = bed_state(bed, soil, insts, day)
        rain = effective_rain(w["precip_in"] or 0.0)
        if st is None:
            # fallow bed: just track rain, nothing to irrigate
            dr = max(0.0, dr - rain)
            series.append({"date": w["date"], "past": day < today, "etc": 0.0,
                           "rain": round(w["precip_in"] or 0, 2), "irrigation": 0.0,
                           "depletion": None, "raw": None, "taw": None})
            continue
        etc = st["kc"] * (w["et0_in"] or 0.0)
        irrigation = 0.0
        if day < today:
            if tracked:
                irrigation = logged.get(w["date"], 0.0)
            elif dr >= st["raw"]:
                irrigation = dr  # assume the gardener watered when it was due
        else:
            if dr + etc - rain >= st["raw"]:
                # hold off if decent rain is likely today/tomorrow
                look = days[idx: idx + 2]
                expect = sum((x["precip_in"] or 0) * (x.get("precip_prob") or 50) / 100
                             for x in look)
                if expect >= 0.5 * (dr + etc) and dr < 0.9 * st["taw"]:
                    pass
                else:
                    irrigation = dr + etc - rain
                    plan.append({
                        "date": w["date"], "inches": round(irrigation, 2),
                        "gallons": round(irrigation * area * GALLONS_PER_INCH_SQFT, 1),
                        "crops": st["crops"],
                    })
        dr = min(max(0.0, dr - rain - irrigation + etc), st["taw"])
        series.append({"date": w["date"], "past": day < today, "etc": round(etc, 3),
                       "rain": round(w["precip_in"] or 0, 2),
                       "irrigation": round(irrigation, 2), "depletion": round(dr, 2),
                       "raw": round(st["raw"], 2), "taw": round(st["taw"], 2),
                       "kc": round(st["kc"], 2)})
    cur = next((s for s in series if s["date"] == today.isoformat()), None)
    week = [s for s in series if not s["past"]][:7]
    need = sum(s["etc"] for s in week)
    rain = sum(effective_rain(s["rain"]) for s in week)
    status = None
    if cur and cur["taw"]:
        status = round(100 * (1 - cur["depletion"] / cur["taw"]))
    return {
        "bed_id": bed["id"], "bed": bed["name"], "area_sqft": area,
        "available_water_pct": status, "tracked": tracked,
        "next": plan[0] if plan else None, "plan": plan,
        "week": {"crop_use_in": round(need, 2), "rain_in": round(rain, 2),
                 "irrigation_in": round(sum(p["inches"] for p in plan
                                            if p["date"] <= week[-1]["date"]), 2)
                 if week else 0.0},
        "series": series,
    }
