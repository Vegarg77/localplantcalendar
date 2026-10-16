"""What a gardener needs to know about each amendment: its N-P-K, and how to
measure an amount without a scale.

N-P-K is the label's guaranteed analysis — percent by weight of nitrogen (N),
phosphate (P2O5) and potash (K2O).  Bag labels for blood meal, bone meal etc.
read the same way, so the numbers here match what people see in the store.
Bulk organic materials (compost, manure, castings) vary a lot; their numbers
are typical values, not a guarantee.

Weights per cup are loose-scooped averages from product bulk densities; they
are close enough for garden feeding, which is never more precise than a
heaping-vs-level scoop anyway.
"""

from __future__ import annotations

from fractions import Fraction

# key: (N, P2O5, K2O) %, how it is measured, oz per cup (dry) or lb per cu ft (bulk)
INFO = {
    "compost":          ((1.0, 1.0, 1.0), "bulk", 45.0),
    "aged_manure":      ((1.5, 1.0, 1.5), "bulk", 40.0),
    "worm_castings":    ((1.0, 0.0, 0.0), "dry", 4.5),
    "blood_meal":       ((12.0, 0.0, 0.0), "dry", 5.0),
    "feather_meal":     ((12.0, 0.0, 0.0), "dry", 4.0),
    "fish_emulsion":    ((5.0, 1.0, 1.0), "liquid", None),
    "alfalfa_meal":     ((2.5, 1.0, 2.0), "dry", 4.0),
    "soybean_meal":     ((7.0, 1.0, 2.0), "dry", 5.0),
    "cottonseed_meal":  ((6.0, 2.0, 1.0), "dry", 5.0),
    "organic_555":      ((5.0, 5.0, 5.0), "dry", 5.5),
    "urea":             ((46.0, 0.0, 0.0), "dry", 6.5),
    "ammonium_sulfate": ((21.0, 0.0, 0.0), "dry", 8.0),
    "synthetic_101010": ((10.0, 10.0, 10.0), "dry", 8.5),
}

NPK_HELP = ("The three numbers on a fertilizer label (like 12-0-0) are its N-P-K: the "
            "percent nitrogen (N), phosphorus (P) and potassium (K), always in that order. "
            "Nitrogen grows leaves and stems, phosphorus feeds roots and flowers, potassium "
            "keeps plants sturdy and helps fruit ripen.")

GALLON_CUFT = 0.1337


def npk(product: str) -> tuple[float, float, float] | None:
    info = INFO.get(product)
    return info[0] if info else None


def npk_text(product: str) -> str | None:
    v = npk(product)
    return "-".join(f"{x:g}" for x in v) if v else None


def _fraction(x: float, step: int) -> str:
    """1.25 -> "1¼" with ``step`` = 4 (quarters)."""
    f = Fraction(round(x * step), step)
    whole, part = divmod(f.numerator, f.denominator)
    glyph = {Fraction(1, 4): "¼", Fraction(1, 2): "½", Fraction(3, 4): "¾",
             Fraction(1, 3): "⅓", Fraction(2, 3): "⅔"}.get(Fraction(part, f.denominator), "")
    if not part:
        return str(whole)
    return f"{whole if whole else ''}{glyph}"


def _plural(n: str, word: str) -> str:
    return f"{n} {word}" if n in ("1", "¼", "½", "¾", "⅓", "⅔") or n.startswith("0") \
        else f"{n} {word}s"


def measure(product: str, amount_lb: float) -> str | None:
    """Kitchen measure for an amount, e.g. "about ½ cup" or "about 3 tablespoons"."""
    info = INFO.get(product)
    if not info or amount_lb <= 0:
        return None
    kind, per = info[1], info[2]
    if kind == "liquid":
        tbsp = max(round(amount_lb * 16 * 0.92 * 2), 1)    # ~0.92 fl oz per oz; 2 tbsp per fl oz
        return (f"about {tbsp} tablespoon{'s' if tbsp != 1 else ''} of concentrate, mixed into "
                f"{tbsp} gallon{'s' if tbsp != 1 else ''} of water")
    if kind == "bulk":
        cuft = amount_lb / per
        if cuft >= 1:
            buckets = cuft / (5 * GALLON_CUFT)
            return f"about {cuft:.1f} cu ft (roughly {buckets:.0f} five-gallon buckets)"
        gal = cuft / GALLON_CUFT
        if gal >= 0.5:
            return f"about {_plural(_fraction(gal, 2), 'gallon')}"
        per = per * GALLON_CUFT           # lb per cu ft -> oz per cup (16 cups a gallon)
    cups = amount_lb * 16 / per
    if cups < 0.22:
        tbsp = max(round(cups * 16), 1)
        return f"about {tbsp} tablespoon{'s' if tbsp != 1 else ''}"
    return f"about {_plural(_fraction(cups, 4), 'cup')}"


def amount_text(lb: float) -> str:
    return f"{lb * 16:.1f} oz" if lb < 1 else f"{lb:.1f} lb"
