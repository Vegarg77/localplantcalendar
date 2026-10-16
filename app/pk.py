"""Phosphorus, potassium and pH for each bed.

Nitrogen needs a day-by-day model because it moves: rain washes it out and
warm soil releases it.  Phosphorus and potassium barely move, so extension
services manage them once a year from a soil test:

* **Build up** a nutrient the test calls low, a little each year until the next
  test (Mehlich-3 phosphorus rises ~1 ppm for every 18 lb P2O5 per acre added,
  potassium ~1 ppm per 8 lb K2O; real soils vary, which is why you retest).
* **Maintain** an optimum level by putting back what the harvest carries off.
* **Hold off** when the test is high: the soil has years of reserve, and extra
  phosphorus runs off into streams.

Without a test nothing is built up; the plan just replaces what crops remove,
and the page asks for a test.  Amounts are lb of P2O5 / K2O per acre, the
same units as fertilizer labels and extension reports.
"""

from __future__ import annotations

from . import nitrogen, products

NUTRIENTS = ("p", "k")
NAME = {"p": "phosphorus", "k": "potassium"}
OXIDE = {"p": 1, "k": 2}                 # index into an N-P-K tuple

# Mehlich-3 ppm thresholds for vegetables (upper bound of each class)
LEVELS = {
    "p": [(15, "very_low"), (30, "low"), (50, "optimum"), (100, "high")],
    "k": [(60, "very_low"), (110, "low"), (175, "optimum"), (300, "high")],
}
LEVEL_LABEL = {"very_low": "Very low", "low": "Low", "optimum": "Just right",
               "high": "High", "very_high": "Very high"}
TARGET_PPM = {"p": 35, "k": 130}         # a little inside the optimum range
LB_PER_PPM = {"p": 18.0, "k": 8.0}       # lb oxide/acre to raise the test 1 ppm
MAX_BUILD = {"p": 150.0, "k": 200.0}     # lb/acre a year; bigger fixes take several
SOURCE = {"p": "bone_meal", "k": "potassium_sulfate"}
MIN_LB_ACRE = 6.0                        # below this, not worth a separate step

# Typical levels for bagged/compost-rich mixes, used until the bed is tested
ASSUMED = {"raised_mix": {"p": 80, "k": 250}, "container_mix": {"p": 60, "k": 200}}

ROLE = {"p": "Phosphorus feeds roots, flowers and fruit set.",
        "k": "Potassium keeps plants sturdy, helps them handle drought and disease, and "
             "ripens fruit."}

# Ground limestone to raise pH by one unit / elemental sulfur to lower it,
# lb per 100 sq ft, by texture (extension rules of thumb)
LIME_PER_UNIT = {"sand": 3.0, "loamy sand": 3.5, "sandy loam": 4.5, "loam": 6.0,
                 "silt loam": 7.0, "silt": 7.0, "sandy clay loam": 7.0, "clay loam": 8.0,
                 "silty clay loam": 8.0, "sandy clay": 8.5, "silty clay": 9.0, "clay": 9.0}
SULFUR_PER_UNIT = {"sand": 1.0, "loamy sand": 1.0, "sandy loam": 1.2, "loam": 1.5}


def level(nutrient: str, ppm: float | None) -> str | None:
    if ppm is None:
        return None
    for top, name in LEVELS[nutrient]:
        if ppm < top:
            return name
    return "very_high"


def soil_test(bed: dict) -> dict:
    """{"p": ppm|None, "k": ppm|None, "source": tested|assumed|unknown} for a bed."""
    soil = bed.get("soil") or {}
    got = {n: _num(soil.get(f"{n}_ppm")) for n in NUTRIENTS}
    if any(v is not None for v in got.values()):
        return {**got, "source": "tested"}
    preset = soil.get("preset") or {"raised": "raised_mix", "container": "container_mix"}.get(
        bed.get("kind"), "native")
    if preset in ASSUMED:
        return {**ASSUMED[preset], "source": "assumed"}
    return {"p": None, "k": None, "source": "unknown"}


def _num(v) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def removal(insts, area: float) -> dict[str, float]:
    """lb P2O5 and K2O per acre the year's harvests carry off this bed."""
    out = {"p": 0.0, "k": 0.0}
    for i in insts:
        if not i.harvest_this_year:
            continue
        frac = min(i.area / area, 1.0) if area else 1.0
        out["p"] += float(i.plant.get("p_remove") or 0) * frac
        out["k"] += float(i.plant.get("k_remove") or 0) * frac
    return out


def supplied(amendments: list[dict], area: float) -> dict[str, float]:
    """lb P2O5 and K2O per acre a set of amendments adds to the bed."""
    out = {"p": 0.0, "k": 0.0}
    for a in amendments:
        npk = products.npk(a["product"])
        if not npk:
            continue
        for n in NUTRIENTS:
            out[n] += a["amount_lb"] * npk[OXIDE[n]] / 100 * nitrogen.SQFT_PER_ACRE / max(area, 1e-6)
    return out


def status(bed: dict, insts, amendments: list[dict], cycle_years: int) -> dict:
    """Where each nutrient stands for one bed in one year, and what (if
    anything) to add.  ``amendments`` are everything else going on the bed that
    year (compost, feedings) — they count first."""
    area = bed["length_ft"] * bed["width_ft"]
    test = soil_test(bed)
    rem = removal(insts, area)
    sup = supplied(amendments, area)
    out = {"source": test["source"]}
    for n in NUTRIENTS:
        ppm = test[n]
        lvl = level(n, ppm)
        build = 0.0
        if test["source"] == "tested" and lvl in ("very_low", "low"):
            build = min((TARGET_PPM[n] - ppm) * LB_PER_PPM[n], MAX_BUILD[n] * cycle_years)
            build /= max(cycle_years, 1)             # spread until the next test
        keep = 0.0 if lvl in ("high", "very_high") else rem[n]
        need = max(keep + build - sup[n], 0.0)
        out[n] = {"ppm": ppm, "level": lvl, "label": LEVEL_LABEL.get(lvl, "Unknown"),
                  "removed": round(rem[n], 1), "supplied": round(sup[n], 1),
                  "build": round(build, 1), "need": round(need, 1),
                  "role": ROLE[n]}
    return out


def why(nutrient: str, st: dict) -> str:
    """Plain reason for a soil-prep step."""
    s = st[nutrient]
    name = NAME[nutrient]
    if s["build"] > 0:
        return (f"Your soil test shows {name} is {s['label'].lower()} ({s['ppm']:g} ppm). "
                f"{ROLE[nutrient]} This adds a bit more than this year's crops use, to build "
                "it up over the rotation; retest before the cycle repeats.")
    if st["source"] == "unknown":
        return (f"Replaces the {name} this year's crops carry off. {ROLE[nutrient]} A soil "
                "test would tell whether your soil needs more or none at all.")
    return (f"Replaces the {name} this year's crops carry off, so the soil stays at a "
            f"healthy level. {ROLE[nutrient]}")


def amount_lb(nutrient: str, lb_acre: float, area: float) -> float:
    """Product weight (lb) that supplies ``lb_acre`` of P2O5/K2O to a bed."""
    pct = products.npk(SOURCE[nutrient])[OXIDE[nutrient]]
    return lb_acre * area / nitrogen.SQFT_PER_ACRE / (pct / 100)


def ph_advice(soil: dict, area: float) -> dict | None:
    """Lime or sulfur to bring pH back toward 6.5, or None when it's fine."""
    ph = soil.get("ph")
    if ph is None or 6.0 <= ph <= 7.5:
        return None
    tex = soil.get("texture") or "loam"
    if ph < 6.0:
        per = LIME_PER_UNIT.get(tex, 6.0) * (6.5 - ph)
        lb = per * area / 100
        return {"product": "garden lime (ground limestone)", "lb": round(lb, 1),
                "text": f"pH {ph:.1f} is too acidic for most vegetables: nutrients that are "
                        "in the soil get locked up. Spread about "
                        f"{lb:.1f} lb of garden lime (ground limestone) over this bed in fall or "
                        "early spring and work it in. It takes a few months to act, so retest "
                        "next year before adding more."}
    per = SULFUR_PER_UNIT.get(tex, 2.0) * (ph - 6.8)
    lb = per * area / 100
    return {"product": "elemental sulfur", "lb": round(lb, 1),
            "text": f"pH {ph:.1f} is alkaline: iron, phosphorus and other nutrients get locked "
                    f"up. About {lb:.1f} lb of elemental sulfur worked into this bed lowers it "
                    "slowly over a season; compost and pine-needle mulch help too. Retest "
                    "before adding more."}
