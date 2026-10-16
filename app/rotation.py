"""Rotation rules: family return intervals, feeding sequence, companion
conflicts, bed space and winter cover."""

from __future__ import annotations

import datetime as dt

from .garden import Instance
from .plant_data import FAMILY_COMMON, FAMILY_RETURN_YEARS

GROUPS = {
    "fixer": "Legumes (build N)",
    "heavy": "Heavy feeders",
    "medium": "Leafy & medium feeders",
    "light": "Roots & light feeders",
}
NEXT_GROUP = {"fixer": "heavy", "heavy": "medium", "medium": "light", "light": "fixer"}


def _counts_for_rotation(p: dict) -> bool:
    if p["lifecycle"] == "perennial":
        return False
    if p["category"] in ("vegetable", "herb"):
        return True
    # brassica covers (mustard, tillage radish) still carry clubroot
    return p["category"] == "cover" and p["family"] == "Brassicaceae"


def main_group(plantings: list[dict], plants: dict) -> str | None:
    best, area = None, -1.0
    for pl in plantings:
        p = plants.get(pl["plant_id"])
        if not p or p["category"] in ("cover", "flower") or p["lifecycle"] == "perennial":
            continue
        a = pl["area_sqft"] or 1e9
        if a > area:
            best, area = p["feeder"], a
    return best


def check(beds: list[dict], plantings: list[dict], plants: dict, settings: dict,
          instances: list[Instance], winter_matters: bool) -> dict:
    n = max(1, int(settings["cycle_years"]))
    issues: list[dict] = []
    grid: dict[int, dict[int, dict]] = {}

    for bed in beds:
        bp = [pl for pl in plantings if pl["bed_id"] == bed["id"]]
        grid[bed["id"]] = {}
        for c in range(1, n + 1):
            cell = [pl for pl in bp if pl["cycle_year"] == c
                    and plants.get(pl["plant_id"], {}).get("lifecycle") != "perennial"]
            grid[bed["id"]][c] = {"group": main_group(cell, plants)}

        # 1. family return intervals (cyclic: the plan repeats every n years)
        fam_years: dict[str, set[int]] = {}
        for pl in bp:
            p = plants.get(pl["plant_id"])
            if p and _counts_for_rotation(p):
                fam_years.setdefault(p["family"], set()).add(pl["cycle_year"])
        for fam, yrs in fam_years.items():
            need = FAMILY_RETURN_YEARS.get(fam)
            if not need:
                continue
            ys = sorted(yrs)
            for y in ys:
                gaps = [((o - y) % n) or n for o in ys]
                gap = min(gaps)
                if gap < need:
                    common = FAMILY_COMMON.get(fam, fam)
                    issues.append({
                        "severity": "warn", "kind": "family", "bed_id": bed["id"],
                        "cycle_year": y,
                        "text": f"{bed['name']}: {common} ({fam}) return to this bed after "
                                f"{gap} year{'s' if gap != 1 else ''}; at least {need} "
                                "years breaks disease and pest cycles."
                                + (" Your rotation cycle is shorter than that — "
                                   "lengthen it or move this family between beds."
                                   if n < need and len(ys) == 1 else ""),
                    })
                    break

        # 2. heavy after heavy with no legume between (one note per bed)
        runs = []
        for c in range(1, n + 1):
            g = grid[bed["id"]][c]["group"]
            nxt = grid[bed["id"]][c % n + 1]["group"] if n > 1 else None
            if g == "heavy" and nxt == "heavy":
                runs.append((c, c % n + 1))
        if runs:
            every = len(runs) == n
            issues.append({
                "severity": "info", "kind": "sequence", "bed_id": bed["id"],
                "cycle_year": runs[0][1], "years": sorted({b for _, b in runs}),
                "text": f"{bed['name']}: "
                        + ("hungry crops grow here every year"
                           if every else "hungry crops grow here two years running ("
                           + ", ".join(f"year {a} → {b}" for a, b in runs) + ")")
                        + ", so the soil never gets a rest. A legume cover crop between "
                          "them adds nitrogen back; the feeding plan makes up the rest.",
            })

        # suggestions for the next group in sequence
        for c in range(1, n + 1):
            prev = grid[bed["id"]][(c - 2) % n + 1]["group"] if n > 1 else None
            cell = grid[bed["id"]][c]
            if prev and not cell["group"]:
                cell["suggest"] = GROUPS[NEXT_GROUP[prev]]
            elif not cell["group"] and not prev:
                cell["suggest"] = None

    # 3/4. per-year overlap checks on concrete instances
    by_bed: dict[int, list[Instance]] = {}
    for inst in instances:
        by_bed.setdefault(inst.planting["bed_id"], []).append(inst)
    bed_by_id = {b["id"]: b for b in beds}
    seen = set()
    for bid, insts in by_bed.items():
        bed = bed_by_id.get(bid)
        if not bed:
            continue
        area = bed["length_ft"] * bed["width_ft"]
        for i, a in enumerate(insts):
            for b in insts[i + 1:]:
                if a.start > b.end or b.start > a.end:
                    continue
                if b.plant["id"] in a.plant["avoid"] or a.plant["id"] in b.plant["avoid"]:
                    key = ("comp", bid, a.plant["id"], b.plant["id"])
                    if key not in seen:
                        seen.add(key)
                        issues.append({
                            "severity": "info", "kind": "companion", "bed_id": bid,
                            "cycle_year": a.planting["cycle_year"],
                            "text": f"{bed['name']}: {a.plant['name']} and {b.plant['name']} "
                                    "grow poorly together — give them separate beds.",
                        })
        # space: sample each week
        days = sorted({i.start for i in insts})
        for d in days:
            used = sum(i.area for i in insts if i.active_on(d))
            if used > area * 1.05:
                names = ", ".join(sorted({i.plant["name"] for i in insts if i.active_on(d)}))
                key = ("space", bid, d.year)
                if key not in seen:
                    seen.add(key)
                    issues.append({
                        "severity": "warn", "kind": "space", "bed_id": bid,
                        "cycle_year": next(i.planting["cycle_year"] for i in insts
                                           if i.active_on(d)),
                        "text": f"{bed['name']}: {used:.0f} sq ft planned on "
                                f"{d.strftime('%b %d')} but the bed is {area:.0f} sq ft "
                                f"({names}).",
                    })

    # 5. winter cover (one note for the whole garden)
    bare_by_year: dict[int, list[str]] = {}
    bare_beds: list[int] = []
    if winter_matters:
        for bed in beds:
            if any(pl["bed_id"] == bed["id"] and
                   plants.get(pl["plant_id"], {}).get("lifecycle") == "perennial"
                   for pl in plantings):
                continue
            bare = []
            for c in range(1, n + 1):
                insts = [i for i in instances if i.planting["bed_id"] == bed["id"]
                         and i.planting["cycle_year"] == c]
                if not insts:
                    continue
                dec = dt.date(insts[0].year, 12, 15)
                if not any(i.active_on(dec) for i in instances
                           if i.planting["bed_id"] == bed["id"]):
                    bare.append(c)
            if bare:
                bare_beds.append(bed["id"])
                for c in bare:
                    bare_by_year.setdefault(c, []).append(bed["name"])
    if bare_beds:
        k = len(bare_beds)
        issues.append({
            "severity": "info", "kind": "cover", "bed_ids": bare_beds, "cycle_year": None,
            "years": sorted(bare_by_year), "by_year": bare_by_year, "action": "cover_crops",
            "text": f"{k} bed{'s' if k != 1 else ''} sit{'' if k != 1 else 's'} bare over "
                    "winter. A winter cover crop protects the soil from washing away, holds "
                    "nitrogen that rain would otherwise carry off, and legumes like crimson "
                    "clover add more for next year.",
        })

    # 6. plan dates outside the climate window
    for inst in instances:
        if not inst.ok and inst.kind == "annual":
            key = ("fit", inst.planting["id"])
            if key in seen:
                continue
            seen.add(key)
            bed = bed_by_id.get(inst.planting["bed_id"], {"name": "?"})
            warn = [n for n in inst.notes if n.startswith("Warning")]
            issues.append({
                "severity": "warn", "kind": "timing", "bed_id": inst.planting["bed_id"],
                "cycle_year": inst.planting["cycle_year"],
                "planting_id": inst.planting["id"],
                "text": f"{bed['name']}: {inst.plant['name']} on "
                        f"{inst.establish.strftime('%b %d') if inst.establish else '?'} — "
                        + "; ".join(w.replace('Warning: ', '') for w in warn),
            })
    for i in issues:
        i.setdefault("years", [i["cycle_year"]] if i.get("cycle_year") else [])
    return {"issues": issues, "grid": grid, "groups": GROUPS}
