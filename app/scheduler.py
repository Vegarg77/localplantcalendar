"""Planting-window engine.

For every possible establishment day (sowing for direct-seeded crops,
transplanting otherwise) the scan asks five climate questions using 30 years
of local data:

1. Will the crop reach maturity before the season runs out?  Maturity is
   tracked in growing degree days, so seed-packet "days to maturity" (rated
   for a typical ~72°F summer / ~62°F spring) stretch in cool weather and
   compress (a little) in warm weather.
2. Is the chance of a damaging frost for *this* crop's hardiness, during its
   vulnerable period, within the user's risk tolerance?
3. Is the soil warm (and, for lettuce/spinach, cool) enough to germinate or
   establish transplants?
4. Is it warm enough for the young plants to actually grow?
5. For cool-season crops: will maturity land in heat that causes bolting or
   bitterness?

Contiguous runs of "yes" days become planting windows — which naturally
produces spring + fall windows for cool crops in the North, winter windows in
the Deep South, and no window at all when the season is too short.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from . import dates
from .climate import Climate
from .plant_data import FROST_THRESHOLD_F

# Seed-catalog "days to maturity" come from trials in fairly mild summers
# (e.g. coastal New England): roughly a 68°F mean day for warm-season crops
# and a 60°F mean day for cool-season crops.
REF_MEAN_F = {"warm": 68.0, "cool": 60.0}
MAX_SEASON_DAYS = 300
REASONS = {
    "season": "season too short / too cold to mature",
    "frost": "frost risk too high",
    "soil": "soil temperature outside germination range",
    "cold": "too cold for young plants to grow",
    "heat": "matures into heat (bolting, bitterness or poor fruit set)",
}


def gdd_cap(p: dict) -> float:
    return 86.0 if p["season"] == "warm" else 75.0


def ref_gdd(p: dict) -> float:
    return max(REF_MEAN_F[p["season"]] - p["base_f"], 10.0)


def resolve_method(p: dict, method: str | None) -> str:
    if p.get("special"):
        return p["method"] if p["method"] != "either" else p["prefer"]
    if method in ("direct", "transplant"):
        if p["method"] == "either" or p["method"] == method:
            return method
    return p["prefer"] if p["method"] == "either" else p["method"]


def effective_dtm(p: dict, method: str, dtm_override: int | None = None) -> float:
    """Days from establishment (sow or transplant) to first harvest."""
    dtm = float(dtm_override) if dtm_override else float(sum(p["dtm"]) / 2)
    weeks = p.get("indoor_weeks") or [4, 6]
    indoor_days = sum(weeks) / 2 * 7
    if method == "transplant" and p["dtm_from"] == "sow":
        dtm -= min(21.0, indoor_days * 0.5)
    elif method == "direct" and p["dtm_from"] == "transplant":
        dtm += indoor_days * 0.6
    return max(dtm, 10.0)


def _prefix(a: np.ndarray) -> np.ndarray:
    out = np.zeros(len(a) + 1)
    out[1:] = np.cumsum(a)
    return out


def _wmean(pre: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Mean over inclusive index ranges [a, b] using a prefix-sum array."""
    a = np.clip(a, 0, len(pre) - 2)
    b = np.clip(b, a, len(pre) - 2)
    return (pre[b + 1] - pre[a]) / (b - a + 1)


class Engine:
    """Caches per-location arrays; one instance per climate."""

    def __init__(self, clim: Climate, risk: float):
        self.clim = clim
        self.risk = risk
        self.tmean2 = clim.two_year(clim.tmean)
        self.tmax2 = clim.two_year(clim.tmax)
        self.soil2 = clim.two_year(clim.soil)
        self.pre_tmean = _prefix(self.tmean2)
        self.pre_tmax = _prefix(self.tmax2)
        self.pre_tmin = _prefix(clim.two_year(clim.tmin))
        self.lsf, self.fff = clim.anchors()
        self._gdd: dict[tuple, np.ndarray] = {}

    # --------------------------------------------------------------- basics
    def gdd_prefix(self, p: dict) -> np.ndarray:
        key = (p["base_f"], gdd_cap(p))
        if key not in self._gdd:
            self._gdd[key] = _prefix(self.clim.gdd_daily(*key))
        return self._gdd[key]

    def maturity(self, p: dict, d: np.ndarray, dtm: float) -> np.ndarray:
        G = self.gdd_prefix(p)
        target = G[d] + dtm * ref_gdd(p)
        j = np.searchsorted(G, target, side="left") - 1
        j = np.maximum(j, d + np.round(0.8 * dtm).astype(int))
        return j

    def resolve_anchor(self, anchor: str, offset: int) -> int:
        base = {"lsf": self.lsf, "fff": self.fff, "lsf+1": self.lsf + 365}[anchor]
        return base + offset

    # ----------------------------------------------------------------- scan
    def evaluate(self, p: dict, d: np.ndarray, method: str,
                 dtm_override: int | None = None) -> dict:
        """Vectorised suitability test for establishment days ``d``."""
        dtm = effective_dtm(p, method, dtm_override)
        j = self.maturity(p, d, dtm)
        # Crops that would sit stalled in cold soil for months (e.g. peas sown in
        # January) rot or bolt in practice, so cap the stretch at ~1.75x.
        ok_season = (j < 729) & (j - d <= min(MAX_SEASON_DAYS, 1.75 * dtm + 14))
        jc = np.clip(j, 0, 728)

        thr = FROST_THRESHOLD_F[p["frost"]]
        start = d if method == "transplant" else d + int(sum(p["germ_days"]) / 2)
        if p["frost"] == "tender":
            # tender crops must dodge frost from emergence to first harvest
            end, tolerance = jc, self.risk
        else:
            # hardy crops are vulnerable mainly as seedlings and recover from
            # an occasional frost, so accept a somewhat higher chance
            end, tolerance = start + 21, min(self.risk + 0.2, 0.5)
        risk = self.clim.frost_risk(thr, start, np.maximum(end, start))
        ok_frost = risk <= tolerance + 1e-9

        soil = self.soil2[d]
        if method == "direct":
            ok_soil = soil >= p["germ_min"]
            if p.get("germ_max"):
                ok_soil &= soil <= p["germ_max"]
        else:
            ok_soil = soil >= p["grow_min"] - 5
        ok_cold = _wmean(self.pre_tmean, d, d + 14) >= p["grow_min"]
        if p.get("heat_max"):
            ok_heat = _wmean(self.pre_tmax, jc - 14, jc) <= p["heat_max"]
        else:
            ok_heat = np.ones_like(d, dtype=bool)
        if p["season"] == "warm" and p["category"] != "cover":
            # sustained heat (or hot nights for tomatoes) during flowering and
            # early harvest stops fruit set
            if p.get("heat_stress"):
                ok_heat &= _wmean(self.pre_tmax, jc - 14, jc + 14) <= p["heat_stress"]
            if p.get("night_max"):
                ok_heat &= _wmean(self.pre_tmin, jc - 14, jc + 14) <= p["night_max"]
        ok = ok_season & ok_frost & ok_soil & ok_cold & ok_heat
        return {"ok": ok, "maturity": j, "risk": risk, "dtm": dtm,
                "fails": {"season": ~ok_season, "frost": ~ok_frost, "soil": ~ok_soil,
                          "cold": ~ok_cold, "heat": ~ok_heat}}

    def windows(self, p: dict, method: str | None = None,
                dtm_override: int | None = None) -> dict:
        method = resolve_method(p, method)
        if p.get("special"):
            return self._special_windows(p, method)
        d = np.arange(365)
        ev = self.evaluate(p, d, method, dtm_override)
        ok = ev["ok"]
        runs: list[list[int]] = []
        i = 0
        while i < 365:
            if ok[i]:
                k = i
                while k + 1 < 365 and ok[k + 1]:
                    k += 1
                runs.append([i, k])
                i = k + 1
            else:
                i += 1
        # close tiny gaps (noise in the 30-year record)
        merged: list[list[int]] = []
        for r in runs:
            if merged and r[0] - merged[-1][1] <= 6:
                merged[-1][1] = r[1]
            else:
                merged.append(r)
        runs = merged
        # merge a window that wraps around New Year
        if len(runs) > 1 and runs[0][0] == 0 and runs[-1][1] == 364:
            first = runs.pop(0)
            runs[-1][1] = first[1] + 365
        wins = [self._window(p, method, s, e, dtm_override, ev) for s, e in runs
                if e - s >= 2]
        reasons = []
        if not wins:
            counts = {k: int(v.sum()) for k, v in ev["fails"].items()}
            for k, _ in sorted(counts.items(), key=lambda kv: -kv[1]):
                if counts[k] > 0:
                    reasons.append(REASONS[k])
        return {"method": method, "windows": wins, "reasons": reasons[:3],
                "dtm_effective": round(ev["dtm"])}

    def _window(self, p: dict, method: str, s: int, e: int,
                dtm_override: int | None, ev: dict) -> dict:
        length = e - s
        year_round = length >= 364
        if year_round:
            rec = max(s, self.lsf)
        else:
            # Earliest date (plus a little margin) that doesn't leave the crop
            # sitting stalled in cold soil; that gives the longest harvest.
            idx = np.arange(s, e + 1)
            dur = ev["maturity"][idx % 365] - (idx % 365)
            brisk = np.nonzero(dur <= 1.25 * ev["dtm"])[0]
            first = int(idx[brisk[0]]) if len(brisk) else s
            rec = min(first + min(7, (e - first) // 4), e)
        return {**self.plan(p, rec, method, dtm_override),
                "start": s, "end": e,
                "start_label": dates.label(s), "end_label": dates.label(e),
                "season": "Year-round" if year_round else season_label(s),
                "successions": self.succession_days(p, rec, e)}

    def succession_days(self, p: dict, rec: int, end: int) -> list[int]:
        step = p.get("succession")
        if not step:
            return [rec]
        return list(range(rec, end + 1, step))[:12]

    def _special_windows(self, p: dict, method: str) -> dict:
        sp = p["special"]
        a1, o1, a2, o2 = sp["plant"]
        s, e = self.resolve_anchor(a1, o1), self.resolve_anchor(a2, o2)
        if e < s:
            e = s
        rec = s + (e - s) // 3
        win = {**self.plan(p, rec, method), "start": s, "end": e,
               "start_label": dates.label(s), "end_label": dates.label(e),
               "season": season_label(s), "successions": [rec]}
        return {"method": method, "windows": [win], "reasons": [],
                "dtm_effective": win["days_to_harvest"]}

    # ----------------------------------------------------------- one date
    def plan(self, p: dict, d: int, method: str | None = None,
             dtm_override: int | None = None) -> dict:
        """Full timeline for one establishment day index (may be >= 365)."""
        method = resolve_method(p, method)
        notes: list[str] = []
        d0 = d % 365
        shift = d - d0
        if p.get("special"):
            sp = p["special"]
            h1, ho1, h2, ho2 = sp["harvest"]
            pa1, po1, _, _ = sp["plant"]
            plant_anchor = self.resolve_anchor(pa1, po1)
            delta = d - plant_anchor  # keep harvest relative to the actual planting
            hs = self.resolve_anchor(h1, ho1)
            he = self.resolve_anchor(h2, ho2)
            if sp["kind"] == "perennial":
                hs_rel, he_rel = hs - d, he - d
                if hs_rel < 0:
                    hs_rel += 365
                    he_rel += 365
                maturity, harvest_end = d + hs_rel, d + he_rel
                fy = sp.get("first_harvest_year", 1)
                if fy > 1:
                    notes.append(f"Perennial: first real harvest in year {fy}.")
            else:
                maturity, harvest_end = hs + delta, he + delta
                if p["category"] == "cover":
                    # aim for the first third of the termination window
                    maturity = maturity + (harvest_end - maturity) // 3
                    harvest_end = maturity + 3
            out = {
                "method": method, "establish": d, "maturity": int(maturity),
                "harvest_end": int(max(harvest_end, maturity)),
                "days_to_harvest": int(maturity - d), "frost_risk": None,
                "kind": sp["kind"], "first_harvest_year": sp.get("first_harvest_year", 1),
            }
            if p["category"] == "cover":
                out["terminate"] = out["maturity"]
        else:
            ev = self.evaluate(p, np.array([d0]), method, dtm_override)
            j = int(ev["maturity"][0]) + shift
            harvest_end = j + int(p["harvest_days"])
            # frost ends the harvest of tender/semi-hardy crops
            if p["frost"] in ("tender", "semi") and j - shift < 729:
                thr = FROST_THRESHOLD_F[p["frost"]]
                ks = np.arange(j - shift, min(j - shift + p["harvest_days"], 728) + 1)
                if len(ks):
                    r = self.clim.frost_risk(thr, np.full_like(ks, j - shift), ks)
                    hit = np.nonzero(r >= 0.5)[0]
                    if len(hit):
                        harvest_end = min(harvest_end, int(ks[hit[0]]) + shift)
                        notes.append("Harvest typically ends at the first fall frost.")
            if p.get("heat_max"):
                jj = j - shift
                ks = np.arange(jj, min(jj + p["harvest_days"], 728) + 1)
                hot = np.nonzero(self.tmax2[ks] > p["heat_max"] + 5)[0]
                if len(hot):
                    cut = int(ks[hot[0]]) + shift
                    if cut < harvest_end:
                        harvest_end = max(cut, j)
                        notes.append("Heat will likely end the harvest (bolting).")
            for k, failed in ev["fails"].items():
                if failed[0]:
                    notes.append("Warning: " + REASONS[k] + " for this date.")
            if p["season"] == "warm" and p.get("heat_stress") and j - shift < 700:
                jj = j - shift
                hot_share = float((self.tmax2[jj - 7: jj + 21] > p["heat_stress"]).mean())
                if hot_share > 0.3:
                    notes.append(f"Typical highs above {p['heat_stress']}°F around harvest "
                                 "can stall fruit set — shade cloth helps.")
            out = {
                "method": method, "establish": d, "maturity": j,
                "harvest_end": max(harvest_end, j), "days_to_harvest": j - d,
                "frost_risk": round(float(ev["risk"][0]), 2), "kind": "annual",
                "ok": bool(ev["ok"][0]),
            }
            if p["category"] == "cover":
                out["terminate"] = j
        if method == "transplant" and p.get("indoor_weeks"):
            w0, w1 = p["indoor_weeks"]
            out["indoor_start"] = [d - w1 * 7, d - w0 * 7]
            out["harden_off"] = d - 7
        out["notes"] = notes
        out["labels"] = {k: dates.label(v) for k, v in out.items()
                         if k in ("establish", "maturity", "harvest_end", "harden_off",
                                  "terminate") and isinstance(v, int)}
        if "indoor_start" in out:
            out["labels"]["indoor_start"] = " – ".join(dates.label(x)
                                                       for x in out["indoor_start"])
        return out


def season_label(idx: int) -> str:
    m = dates.month_of_idx(idx)
    if m in (12, 1, 2):
        return "Winter"
    if m in (3, 4, 5):
        return "Spring"
    if m in (6, 7):
        return "Summer"
    return "Fall"


def project_maturity(p: dict, method: str, dtm_override: int | None,
                     established: dt.date, clim: Climate,
                     observed: dict[str, float]) -> dt.date | None:
    """Maturity date using actual temperatures since planting + forecast,
    falling back to normals for the remaining days."""
    if p.get("special"):
        return None
    need = effective_dtm(p, method, dtm_override) * ref_gdd(p)
    cap, base = gdd_cap(p), p["base_f"]
    acc, day = 0.0, established
    for _ in range(400):
        t = observed.get(day.isoformat())
        if t is None:
            t = float(clim.tmean[dates.doy(day)])
        acc += max(0.0, min(t, cap) - base)
        if acc >= need:
            floor_day = established + dt.timedelta(
                days=int(round(0.8 * effective_dtm(p, method, dtm_override))))
            return max(day, floor_day)
        day += dt.timedelta(days=1)
    return None
