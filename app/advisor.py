"""Forecast-driven advice: what to do in the garden over the next two weeks."""

from __future__ import annotations

import datetime as dt

from . import dates
from .climate import Climate
from .garden import Instance
from .plant_data import FROST_THRESHOLD_F
from .scheduler import project_maturity

DISEASE_NAMES = {
    "late_blight": "late blight", "fungal_leaf": "leaf-spot fungi",
    "downy_mildew": "downy mildew", "powdery_mildew": "powdery mildew",
}


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _fmt(d: dt.date) -> str:
    return d.strftime("%a %b %-d")


def advise(insts: list[Instance], forecast: dict, clim: Climate,
           beds: dict[int, dict], today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    days = forecast["days"]
    fut = [w for w in days if _d(w["date"]) >= today]
    by_date = {w["date"]: w for w in days}
    alerts: list[dict] = []
    tasks: list[dict] = []
    progress: list[dict] = []

    def bed_name(inst):
        return beds.get(inst.planting["bed_id"], {}).get("name", "?")

    in_ground = [i for i in insts if i.establish is None or i.establish <= today + dt.timedelta(16)]
    in_ground = [i for i in in_ground if i.end >= today]

    # ---------------------------------------------------------------- frost
    frost_hits: dict[str, list[str]] = {}
    for w in fut:
        if w["tmin_f"] is None:
            continue
        d = _d(w["date"])
        for i in in_ground:
            if i.establish and i.establish > d:
                continue
            if not i.active_on(d):
                continue
            thr = FROST_THRESHOLD_F[i.plant["frost"]]
            margin = 3 if i.plant["frost"] in ("tender", "semi") else 0
            if w["tmin_f"] <= thr + margin:
                frost_hits.setdefault(w["date"], []).append(
                    f"{i.plant['name']} ({bed_name(i)})")
    for date, crops in sorted(frost_hits.items()):
        w = by_date[date]
        alerts.append({
            "severity": "high", "kind": "frost", "date": date,
            "title": f"Frost risk {_fmt(_d(date))} — low {w['tmin_f']:.0f}°F",
            "text": "Cover or harvest: " + ", ".join(sorted(set(crops))) +
                    ". Row cover or sheets buy 4–6°F; water the soil in the afternoon "
                    "(moist soil releases more heat overnight).",
        })

    if not frost_hits:
        freeze = [w for w in fut if w["tmin_f"] is not None and w["tmin_f"] <= 28]
        if freeze:
            w = min(freeze, key=lambda x: x["tmin_f"])
            alerts.append({
                "severity": "info", "kind": "freeze", "date": freeze[0]["date"],
                "title": f"Hard freeze {_fmt(_d(freeze[0]['date']))}"
                         f" (low {w['tmin_f']:.0f}°F)",
                "text": "None of your planted crops are at risk, but drain hoses and drip "
                        "lines and bring in potted herbs and tender perennials.",
            })

    # ----------------------------------------------------------------- heat
    for i in in_ground:
        p = i.plant
        hot = [w for w in fut[:10] if w["tmax_f"] is not None and i.active_on(_d(w["date"]))
               and (i.establish is None or i.establish <= _d(w["date"]))]
        if p.get("heat_stress"):
            stress = [w for w in hot if w["tmax_f"] >= p["heat_stress"]]
            if stress:
                peak = max(stress, key=lambda w: w["tmax_f"])
                alerts.append({
                    "severity": "warn", "kind": "heat", "date": stress[0]["date"],
                    "title": f"Heat stress for {p['name']} ({bed_name(i)})",
                    "text": f"{len(stress)} day(s) at or above {p['heat_stress']}°F "
                            f"(peak {peak['tmax_f']:.0f}°F {_fmt(_d(peak['date']))}). "
                            + ("Expect blossom drop; 30–40% shade cloth and deep morning "
                               "watering help." if p["season"] == "warm" else
                               "Harvest what's ready, shade the rest, keep soil moist."),
                })
        if p.get("heat_max") and p["season"] == "cool":
            bolt = [w for w in hot if w["tmax_f"] >= p["heat_max"] + 5]
            if len(bolt) >= 3:
                alerts.append({
                    "severity": "warn", "kind": "bolt", "date": bolt[0]["date"],
                    "title": f"Bolting risk: {p['name']} ({bed_name(i)})",
                    "text": f"{len(bolt)} hot days ahead. Harvest mature plants early "
                            "and keep the rest well watered under shade.",
                })

    # -------------------------------------------------------------- disease
    window = [w for w in days if today - dt.timedelta(3) <= _d(w["date"]) <= today + dt.timedelta(5)]
    wet_days = [w for w in window if w.get("wet_hours", 0) >= 10]
    humid_warm = [w for w in window if (w.get("rh_mean") or 0) >= 70
                  and w["tmax_f"] is not None and 68 <= w["tmax_f"] <= 90]
    tags: dict[str, set[str]] = {}
    for i in in_ground:
        if i.establish and i.establish > today:
            continue
        for t in i.plant.get("diseases", []):
            if (t == "powdery_mildew" and len(humid_warm) >= 3) or \
                    (t != "powdery_mildew" and len(wet_days) >= 2):
                tags.setdefault(t, set()).add(i.plant["name"])
    for t, crops in tags.items():
        alerts.append({
            "severity": "warn", "kind": "disease", "date": today.isoformat(),
            "title": f"Weather favours {DISEASE_NAMES.get(t, t)}",
            "text": f"Affects: {', '.join(sorted(crops))}. Water at the soil (not leaves) "
                    "in the morning, improve airflow, remove spotted leaves; apply an "
                    "organic preventive (copper/bicarbonate/biofungicide) before the wet spell "
                    "if you use one.",
        })

    # ---------------------------------------------------------------- wind
    windy = [w for w in fut[:7] if (w.get("wind_mph") or 0) >= 30]
    if windy and in_ground:
        alerts.append({
            "severity": "info", "kind": "wind", "date": windy[0]["date"],
            "title": f"Strong wind {_fmt(_d(windy[0]['date']))} "
                     f"({windy[0]['wind_mph']:.0f} mph)",
            "text": "Stake tall crops, secure row covers, delay transplanting.",
        })

    # ---------------------------------------------------------- planting go/wait
    horizon = today + dt.timedelta(days=14)
    for i in insts:
        p = i.plant
        if i.indoor_start and today - dt.timedelta(3) <= i.indoor_start[0] <= horizon:
            tasks.append({"date": i.indoor_start[0].isoformat(), "kind": "indoor",
                          "title": f"Start {p['name']} indoors",
                          "text": f"For {bed_name(i)}; transplant around "
                                  f"{_fmt(i.establish)}. Germinates at "
                                  f"{p['germ_min']}°F+ (heat mat for warm crops)."})
        if i.harden_off and today <= i.harden_off <= horizon:
            tasks.append({"date": i.harden_off.isoformat(), "kind": "harden",
                          "title": f"Harden off {p['name']}",
                          "text": "Set seedlings outside a few hours a day, building up over "
                                  "7–10 days."})
        if i.establish and not i.actual and today - dt.timedelta(5) <= i.establish <= horizon:
            tasks.append({**_go_wait(i, days, today), "kind": "plant",
                          "planting_id": i.planting["id"], "bed": bed_name(i)})
        if i.harvest_this_year and today <= i.maturity <= horizon:
            tasks.append({"date": i.maturity.isoformat(), "kind": "harvest",
                          "title": f"Harvest begins: {p['name']} ({bed_name(i)})",
                          "text": f"Harvest window through {_fmt(i.harvest_end)}."})
        if p["category"] == "cover" and today <= i.harvest_end <= horizon:
            tasks.append({"date": i.harvest_end.isoformat(), "kind": "terminate",
                          "title": f"Terminate {p['name']} ({bed_name(i)})",
                          "text": "Cut at the soil line at early flowering; leave as mulch "
                                  "or turn in, then wait 2–3 weeks before sowing."})

    # ---------------------------------------------------- growth vs. normal
    observed = {w["date"]: w["tmean_f"] for w in days if w["tmean_f"] is not None}
    for i in insts:
        if i.kind != "annual" or not i.establish or i.establish > today \
                or i.maturity < today - dt.timedelta(3):
            continue
        proj = project_maturity(i.plant, i.method, i.planting.get("dtm_override"),
                                i.establish, clim, observed)
        if proj:
            delta = (proj - i.maturity).days
            progress.append({
                "planting_id": i.planting["id"], "name": i.plant["name"],
                "bed": bed_name(i), "planned": i.maturity.isoformat(),
                "projected": proj.isoformat(), "delta_days": delta,
                "text": ("on schedule" if abs(delta) <= 3 else
                         f"{abs(delta)} days {'behind' if delta > 0 else 'ahead of'} normal "
                         f"({'cool' if delta > 0 else 'warm'} weather)"),
            })

    tasks.sort(key=lambda t: t["date"])
    order = {"high": 0, "warn": 1, "info": 2}
    alerts.sort(key=lambda a: (order[a["severity"]], a["date"]))
    return {"alerts": alerts, "tasks": tasks, "progress": progress}


def _go_wait(i: Instance, days: list[dict], today: dt.date) -> dict:
    p = i.plant
    target = max(i.establish, today)
    after = [w for w in days if target <= _d(w["date"]) <= target + dt.timedelta(7)]
    thr = FROST_THRESHOLD_F[p["frost"]]
    margin = 3 if p["frost"] in ("tender", "semi") else 0
    reasons = []
    cold = [w for w in after if w["tmin_f"] is not None and w["tmin_f"] <= thr + margin]
    if cold:
        reasons.append(f"low of {cold[0]['tmin_f']:.0f}°F on {_fmt(_d(cold[0]['date']))}")
    soil_day = next((w for w in days if w["date"] == target.isoformat()), None)
    if i.method == "direct" and soil_day:
        soil = soil_day.get("soil_f") or soil_day.get("tmean_f")
        if soil is not None and soil < p["germ_min"]:
            reasons.append(f"soil {soil:.0f}°F (needs {p['germ_min']}°F)")
        if soil is not None and p.get("germ_max") and soil > p["germ_max"]:
            reasons.append(f"soil {soil:.0f}°F is too warm to germinate "
                           f"(max {p['germ_max']}°F) — sow in shade or presprout")
    heavy = [w for w in after[:2] if (w["precip_in"] or 0) >= 1.0]
    if heavy and i.method == "direct":
        reasons.append(f"{heavy[0]['precip_in']:.1f}\" rain {_fmt(_d(heavy[0]['date']))} "
                       "can wash out seed")
    hot = [w for w in after[:3] if w["tmax_f"] and p.get("heat_max")
           and w["tmax_f"] >= p["heat_max"] + 5]
    verb = "Transplant" if i.method == "transplant" else "Sow"
    if p.get("special"):
        verb = "Plant"
    if reasons:
        return {"date": target.isoformat(), "verdict": "wait",
                "title": f"Wait to {verb.lower()} {p['name']}",
                "text": "Forecast: " + "; ".join(reasons) +
                        ". Re-check in a few days — the window stays open until "
                        f"later in the season."}
    note = " Hot days ahead — plant in the evening and shade for a few days." if hot else ""
    return {"date": target.isoformat(), "verdict": "go",
            "title": f"{verb} {p['name']}" + (" now" if target <= today else
                                               f" {_fmt(target)}"),
            "text": "Forecast looks good." + note}


def plant_now(engine, plants: list[dict], today: dt.date | None = None) -> list[dict]:
    """Library plants whose climate window is open this week."""
    today = today or dt.date.today()
    t = dates.doy(today)
    out = []
    for p in plants:
        try:
            w = engine.windows(p)
        except Exception:  # noqa: BLE001 — a bad custom plant shouldn't break the page
            continue
        for win in w["windows"]:
            s, e = win["start"], win["end"]
            for tt in (t, t + 365):
                if s <= tt + 7 and tt <= e:
                    out.append({"id": p["id"], "name": p["name"],
                                "category": p["category"], "method": w["method"],
                                "until": win["end_label"], "season": win["season"]})
                    break
            else:
                continue
            break
    return out
