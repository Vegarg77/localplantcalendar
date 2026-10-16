"""Feedings the planner schedules so each crop gets the nitrogen it needs.

Whenever the plan for a bed changes, the bed's automatic feedings are thrown
away and re-planned: the nitrogen model runs with the bed's own (manual)
amendments, and every crop it projects to run short gets a feeding at planting
plus a side-dressing when it starts drawing hardest.  The model is re-run with
those feedings and topped up until the crops are fed, so cover crops, legumes
and compost the user adds are credited before anything is bought.

Feedings are ordinary amendments flagged ``auto`` and tied to their planting,
so they repeat every cycle, appear on the calendar, and disappear with the
planting.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from . import dates, db, nitrogen, products, services as svc
from .garden import cycle_index

SHORT_LB_ACRE = 8.0          # the same threshold the Soil page warns at
FEED_PRODUCTS = ("blood_meal", "feather_meal", "soybean_meal", "cottonseed_meal",
                 "alfalfa_meal", "organic_555", "synthetic_101010", "ammonium_sulfate",
                 "urea")
SKIP_CATEGORIES = {"cover", "flower"}
PASSES = 3


def product(settings: dict) -> str:
    p = settings.get("feed_product") or "blood_meal"
    return p if p in FEED_PRODUCTS else "blood_meal"


def refresh(bed_ids: Iterable[int] | None = None) -> None:
    """Re-plan automatic feedings for these beds (all beds when None)."""
    wanted = None if bed_ids is None else set(bed_ids)
    beds = [b["id"] for b in svc.beds() if wanted is None or b["id"] in wanted]
    if not beds:
        return
    for bid in beds:
        db.execute("DELETE FROM amendments WHERE bed_id = ? AND auto = 1", (bid,))
    if svc.settings().get("auto_feed") is False:
        return
    try:
        by_year = {y: svc.year_instances(y) for y in svc.nitrogen_years()}
    except svc.NotConfigured:
        return
    for bid in beds:
        _plan_bed(bid, by_year)


def _plan_bed(bed_id: int, by_year: dict) -> None:
    s = svc.settings()
    try:
        bed, run = svc.nitrogen_inputs(bed_id, by_year=by_year)
    except KeyError:
        return
    area = bed["length_ft"] * bed["width_ft"]
    prod = product(s)
    _, n_pct, avail, _ = nitrogen.PRODUCTS[prod]
    manual = [a for a in svc.amendments() if a["bed_id"] == bed_id]
    feeds: dict[tuple, list[dict]] = {}

    for i in range(PASSES):
        res = run(manual + [f for fs in feeds.values() for f in fs])
        # top-ups chase smaller leftovers than the first pass
        short = _shortfalls(res["crops"], s, SHORT_LB_ACRE if i == 0 else 4.0)
        if not short:
            break
        for key, c in short.items():
            extra = c["deficit_lb_acre"] / avail * 1.15
            if key not in feeds:      # split: some at planting, most when it peaks
                feeds[key] = _schedule(c, s, prod)
                shares = [0.4, 0.6] if len(feeds[key]) == 2 else [1.0]
            else:                     # top up the last feeding
                shares = [0.0] * (len(feeds[key]) - 1) + [1.0]
            for f, share in zip(feeds[key], shares):
                f["lb_acre"] = f.get("lb_acre", 0.0) + extra * share
                f["amount_lb"] = f["lb_acre"] * area / nitrogen.SQFT_PER_ACRE / (n_pct / 100)

    for f in _merge([f for fs in feeds.values() for f in fs if f["amount_lb"] > 0]):
        db.execute(
            "INSERT INTO amendments(bed_id, cycle_year, doy, product, amount_lb, n_pct, "
            "notes, auto, planting_id) VALUES(?,?,?,?,?,?,?,1,?)",
            (bed_id, f["cycle_year"], f["doy"], prod, round(f["amount_lb"], 3), None,
             f["notes"], f["planting_id"]))


def _merge(feeds: list[dict], days: int = 10) -> list[dict]:
    """Fold a planting's feedings that land within 10 days of each other (e.g.
    succession sowings) into one, so the calendar isn't a drip of tiny doses."""
    out: list[dict] = []
    for f in sorted(feeds, key=lambda f: (f["planting_id"], f["cycle_year"], f["doy"])):
        last = out[-1] if out else None
        if last and last["planting_id"] == f["planting_id"] \
                and last["cycle_year"] == f["cycle_year"] and f["doy"] - last["doy"] < days:
            last["amount_lb"] += f["amount_lb"]
            if "at planting" in last["notes"] and "Side-dress" in f["notes"]:
                last["notes"] = (f"Feed {f['notes'].split(':')[0][len('Side-dress '):]}: "
                                 "mix it in where you sow and scatter it beside the plants "
                                 "already up, then water in.")
        else:
            out.append(dict(f))
    return out


def _shortfalls(crops: list[dict], s: dict, threshold: float) -> dict[tuple, dict]:
    """Worst shortfall for each crop slot (planting, cycle year, planting day),
    across both passes through the cycle."""
    plants = svc.plants()
    out: dict[tuple, dict] = {}
    for c in crops:
        p = plants.get(c["plant_id"], {})
        if c["fixer"] or p.get("category") in SKIP_CATEGORIES:
            continue
        if c["deficit_lb_acre"] < threshold:
            continue
        start = dt.date.fromisoformat(c["start"])
        key = (c["planting_id"], cycle_index(start.year, s), dates.doy(start))
        if key not in out or c["deficit_lb_acre"] > out[key]["deficit_lb_acre"]:
            out[key] = c
    return out


def _schedule(c: dict, s: dict, prod: str) -> list[dict]:
    start = dt.date.fromisoformat(c["start"])
    end = dt.date.fromisoformat(c["end"])
    side = dt.date.fromisoformat(c["short_from"]) if c["short_from"] else \
        start + dt.timedelta(days=30)
    side = max(side, start + dt.timedelta(days=21))
    base = {"planting_id": c["planting_id"], "product": prod, "n_pct": None, "amount_lb": 0.0}

    def at(d: dt.date, notes: str) -> dict:
        return {**base, "cycle_year": cycle_index(d.year, s), "doy": dates.doy(d),
                "notes": notes}

    first = at(start, f"Feed {c['name']} at planting: mix it into the top few inches "
                      "where it will grow, then water in.")
    if side >= end - dt.timedelta(days=14):   # short crops get one feeding
        return [first]
    return [first, at(side, f"Side-dress {c['name']}: scatter it beside the plants, "
                            "scratch it in and water well.")]


def describe(planting_ids: list[int]) -> list[str]:
    """Plain-language list of the feedings planned for these plantings."""
    if not planting_ids:
        return []
    rows = db.query(
        f"SELECT a.*, b.name AS bed, b.length_ft * b.width_ft AS area FROM amendments a "
        f"JOIN beds b ON b.id = a.bed_id WHERE a.auto = 1 AND a.planting_id IN "
        f"({','.join('?' * len(planting_ids))}) ORDER BY a.cycle_year, a.doy",
        tuple(planting_ids))
    if not rows:
        return []
    s = svc.settings()
    out = []
    by_bed: dict[tuple[str, int], list[str]] = {}
    for r in rows:
        name = nitrogen.PRODUCTS[r["product"]][0].split(" (")[0].lower()
        what = "at planting" if "at planting" in r["notes"] else \
            "side-dress" if r["notes"].startswith("Side-dress") else "feeding"
        by_bed.setdefault((r["bed"], r["cycle_year"]), []).append(
            f"{amount_text(r['amount_lb'])} {name} {what} ({dates.label(r['doy'])})")
    for (bed, cyc), items in by_bed.items():
        year = int(s["start_year"]) + cyc - 1
        out.append(f"{bed}, {year}: " + "; ".join(items) + ".")
    return out


def title(a: dict) -> str:
    """Calendar title for an amendment, e.g.
    "Side-dress Tomato — 5.7 oz blood meal (about 1 cup)"."""
    name = nitrogen.PRODUCTS.get(a["product"], (a["product"],))[0]
    cup = products.measure(a["product"], a["amount_lb"])
    what = f"{amount_text(a['amount_lb'])} {name}" + (f" ({cup})" if cup else "")
    if a.get("auto") and a.get("notes"):
        return f"{a['notes'].split(':')[0]} — {what}"
    return f"Apply {what}"


amount_text = products.amount_text

WHY_FEEDER = {
    "heavy": "{crop} is a heavy feeder: it uses more nitrogen than this bed's soil releases "
             "on its own, so it needs a boost to grow full-sized.",
    "medium": "{crop} uses a fair amount of nitrogen, and this bed's soil can't quite keep up "
              "on its own.",
    "light": "{crop} doesn't need much, but this bed runs low by the time it's growing.",
}
WHY_SIDE = (" Plants draw nitrogen hardest once they're growing fast, so the second feeding "
            "goes in then instead of all at planting, where rain could wash it away first.")
HOW_DEFAULT = {
    "bulk": "Spread it evenly over the bed and mix it into the top few inches.",
    "liquid": "Water it in around the plants with a watering can.",
    "dry": "Sprinkle it evenly over the bed, scratch it into the top inch or two and water "
           "it in.",
}


def plan(year: int) -> dict:
    """Every feeding and amendment due in a calendar year, as plain steps:
    when, which bed and crop, how much (by weight and by kitchen measure),
    how to apply it and why."""
    s = svc.settings()
    cyc = cycle_index(year, s)
    beds = {b["id"]: b for b in svc.beds()}
    plants = svc.plants()
    crop_of = {p["id"]: plants.get(p["plant_id"]) for p in svc.plantings()}
    steps, used = [], {}
    for a in svc.amendments():
        bed = beds.get(a["bed_id"])
        if a["cycle_year"] != cyc or not bed:
            continue
        crop = crop_of.get(a.get("planting_id")) if a.get("auto") else None
        name = nitrogen.PRODUCTS.get(a["product"], (a["product"],))[0]
        notes = a.get("notes") or ""
        stage = "planting" if "at planting" in notes else \
            "side_dress" if notes.startswith("Side-dress") else \
            "feeding" if a.get("auto") else "amendment"
        if a.get("auto") and crop:
            why = WHY_FEEDER.get(crop["feeder"], WHY_FEEDER["medium"]).format(crop=crop["name"])
            if stage == "side_dress":
                why += WHY_SIDE
        else:
            why = "You planned this yourself; it counts toward what the crops here need."
        info = products.INFO.get(a["product"])
        how = notes.split(": ", 1)[1] if a.get("auto") and ": " in notes else \
            notes or HOW_DEFAULT.get(info[1] if info else "dry", HOW_DEFAULT["dry"])
        how = how[:1].upper() + how[1:]
        steps.append({
            "id": a["id"], "date": dates.to_date(year, a["doy"]).isoformat(),
            "bed_id": bed["id"], "bed": bed["name"], "auto": bool(a.get("auto")),
            "crop": crop["name"] if crop else None, "stage": stage,
            "product": a["product"], "product_name": name.split(" (")[0],
            "npk": products.npk_text(a["product"]),
            "amount_lb": a["amount_lb"], "amount": amount_text(a["amount_lb"]),
            "measure": products.measure(a["product"], a["amount_lb"]),
            "how": how, "why": why,
        })
        used[a["product"]] = name.split(" (")[0]
    steps.sort(key=lambda x: (x["date"], x["bed_id"]))
    return {"year": year, "cycle_year": cyc, "steps": steps,
            "products": [{"id": k, "name": v, "npk": products.npk_text(k)}
                         for k, v in used.items()],
            "npk_help": products.NPK_HELP}
