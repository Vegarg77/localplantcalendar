"""Turns ~30 years of daily weather history into the climate facts the
planner needs: frost-date probabilities, smoothed day-by-day normals, soil
temperature estimates and growing-degree-day curves.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np

from . import dates
from .sources.geo import zone_from_temp

FROST_THRESHOLDS = (32, 28, 24, 15)
SPRING_END = dates.month_day_to_idx("07-15")  # spring half: Jan 1 .. Jul 15


def _f(c):
    return c * 9 / 5 + 32


def _smooth(a: np.ndarray, window: int) -> np.ndarray:
    """Circular moving average over a 365-day array."""
    pad = window // 2
    ext = np.concatenate([a[-pad:], a, a[:pad]])
    kernel = np.ones(window) / window
    return np.convolve(ext, kernel, mode="valid")[: len(a)]


def _shift(a: np.ndarray, k: int, fill: bool) -> np.ndarray:
    out = np.full_like(a, fill)
    if k > 0:
        out[k:] = a[:-k]
    elif k < 0:
        out[:k] = a[-k:]
    else:
        out[:] = a
    return out


@dataclass
class Climate:
    years: list[int]
    tmax: np.ndarray        # 365 smoothed normals, °F
    tmin: np.ndarray
    tmean: np.ndarray
    precip: np.ndarray      # in/day
    et0: np.ndarray         # in/day
    soil: np.ndarray        # estimated 2–4" soil temperature, °F
    year_tmin: np.ndarray   # (n_years, 365) raw daily minima, °F
    frost_masks: dict = field(default_factory=dict)  # thr -> (n_pairs, 730) bool
    frost_prefix: dict = field(default_factory=dict)  # thr -> cumsum with leading 0
    overrides: dict = field(default_factory=dict)

    # --------------------------------------------------------------- frost
    def frost_doys(self, thr: int) -> tuple[list[int | None], list[int | None]]:
        """Per-year last spring and first fall frost day index (or None)."""
        last, first = [], []
        for row in self.frost_masks_single(thr):
            spring = np.nonzero(row[:SPRING_END])[0]
            fall = np.nonzero(row[SPRING_END:365])[0]
            last.append(int(spring[-1]) if len(spring) else None)
            first.append(int(fall[0]) + SPRING_END if len(fall) else None)
        return last, first

    def frost_masks_single(self, thr: int) -> np.ndarray:
        return self.frost_masks[thr][:, :365]

    def frost_dates(self, thr: int = 32) -> dict:
        last, first = self.frost_doys(thr)
        n = len(last)
        lv = np.array([x if x is not None else -1 for x in last], dtype=float)
        fv = np.array([x if x is not None else 365 for x in first], dtype=float)
        out = {"threshold_f": thr, "years": n,
               "frost_free_years": int(sum(1 for x in last if x is None)),
               "spring": {}, "fall": {}}
        for r in (0.1, 0.3, 0.5, 0.9):
            s = float(np.quantile(lv, 1 - r))
            f = float(np.quantile(fv, r))
            out["spring"][str(r)] = None if s < 0 else int(round(s))
            out["fall"][str(r)] = None if f >= 365 else int(round(f))
        s50, f50 = out["spring"]["0.5"], out["fall"]["0.5"]
        out["season_days"] = (f50 if f50 is not None else 365) - (s50 if s50 is not None else 0)
        return out

    def anchors(self) -> tuple[int, int]:
        """Median last-spring and first-fall frost (32°F) used as calendar anchors.

        Frost-free sites fall back to mid-Feb / mid-Nov so that "plant garlic
        after first frost" style rules still land in the cool season.
        """
        fd = self.frost_dates(32)
        lsf = fd["spring"]["0.5"]
        fff = fd["fall"]["0.5"]
        return (lsf if lsf is not None else 45), (fff if fff is not None else 320)

    def frost_risk(self, thr: int, start: np.ndarray, end: np.ndarray) -> np.ndarray:
        """Fraction of years with any frost <= thr between day indices
        start..end inclusive (indices may run into the following year)."""
        thr = min(self.frost_prefix, key=lambda t: abs(t - thr))
        pre = self.frost_prefix[thr]
        start = np.clip(start, 0, pre.shape[1] - 2)
        end = np.clip(end, 0, pre.shape[1] - 2)
        hits = pre[:, end + 1] - pre[:, start]
        return (hits > 0).mean(axis=0)

    # ----------------------------------------------------------------- GDD
    def gdd_daily(self, base: float, cap: float) -> np.ndarray:
        """Daily growing degree days over two years of normals (730 values)."""
        mean = np.clip(self.tmean, None, cap)
        g = np.clip(mean - base, 0, None)
        return np.concatenate([g, g])

    def two_year(self, arr: np.ndarray) -> np.ndarray:
        return np.concatenate([arr, arr])

    # ------------------------------------------------------------- summary
    def monthly(self) -> list[dict]:
        out = []
        frost_days = self.frost_masks_single(32).mean(axis=0)
        for m in range(1, 13):
            idx = [i for i in range(365) if dates.month_of_idx(i) == m]
            out.append({
                "month": dates.MONTH_ABBR[m - 1],
                "high_f": round(float(self.tmax[idx].mean()), 1),
                "low_f": round(float(self.tmin[idx].mean()), 1),
                "precip_in": round(float(self.precip[idx].sum()), 2),
                "et0_in": round(float(self.et0[idx].sum()), 2),
                "frost_days": round(float(frost_days[idx].sum()), 1),
            })
        return out

    def summary(self) -> dict:
        fd = self.frost_dates(32)
        hard = self.frost_dates(28)

        def lab(x):
            return dates.label(x) if x is not None else None

        avg_min = float(self.year_tmin.min(axis=1).mean())
        return {
            "years": f"{self.years[0]}–{self.years[-1]}",
            "last_spring_frost": {k: lab(v) for k, v in fd["spring"].items()},
            "first_fall_frost": {k: lab(v) for k, v in fd["fall"].items()},
            "last_spring_frost_idx": fd["spring"],
            "first_fall_frost_idx": fd["fall"],
            "last_hard_freeze": {k: lab(v) for k, v in hard["spring"].items()},
            "first_hard_freeze": {k: lab(v) for k, v in hard["fall"].items()},
            "frost_free_years": fd["frost_free_years"],
            "season_days": fd["season_days"],
            "avg_annual_min_f": round(avg_min, 1),
            "zone_estimate": zone_from_temp(avg_min),
            "annual_precip_in": round(float(self.precip.sum()), 1),
            "annual_et0_in": round(float(self.et0.sum()), 1),
            "overrides": self.overrides,
            "monthly": self.monthly(),
            "daily": {
                "tmax": [round(float(x), 1) for x in self.tmax],
                "tmin": [round(float(x), 1) for x in self.tmin],
                "soil": [round(float(x), 1) for x in self.soil],
                "frost_prob": [round(float(x), 3)
                               for x in self.frost_masks_single(32).mean(axis=0)],
            },
        }


def build(archive: dict, lsf_override: str | None = None,
          fff_override: str | None = None) -> Climate:
    d = archive["daily"]
    times = d["time"]

    def arr(key, conv=None):
        vals = d.get(key) or [None] * len(times)
        out = np.array([np.nan if v is None else v for v in vals], dtype=float)
        return conv(out) if conv else out

    tmax = arr("temperature_2m_max", _f)
    tmin = arr("temperature_2m_min", _f)
    tmean = arr("temperature_2m_mean", _f)
    tmean = np.where(np.isnan(tmean), (tmax + tmin) / 2, tmean)
    precip = arr("precipitation_sum") / 25.4
    et0 = arr("et0_fao_evapotranspiration") / 25.4

    years_set: dict[int, np.ndarray] = {}
    grids = {k: {} for k in ("tmax", "tmin", "tmean", "precip", "et0")}
    for i, t in enumerate(times):
        day = dt.date.fromisoformat(t)
        if day.month == 2 and day.day == 29:
            continue
        j = dates.doy(day)
        for name, a in (("tmax", tmax), ("tmin", tmin), ("tmean", tmean),
                        ("precip", precip), ("et0", et0)):
            grids[name].setdefault(day.year, np.full(365, np.nan))[j] = a[i]
        years_set[day.year] = True
    years = sorted(y for y in years_set
                   if np.isfinite(grids["tmin"][y]).sum() > 330)
    if len(years) < 5:
        raise ValueError("not enough historical weather data for this location")

    def stack(name):
        m = np.vstack([grids[name][y] for y in years])
        # fill isolated gaps with that day's mean across years
        col_mean = np.nanmean(m, axis=0)
        return np.where(np.isnan(m), col_mean, m)

    st = {k: stack(k) for k in grids}
    norm_tmax = _smooth(st["tmax"].mean(axis=0), 15)
    norm_tmin = _smooth(st["tmin"].mean(axis=0), 15)
    norm_tmean = _smooth(st["tmean"].mean(axis=0), 15)
    norm_precip = _smooth(st["precip"].mean(axis=0), 31)
    norm_et0 = _smooth(st["et0"].mean(axis=0), 31)
    # Soil 2–4" deep lags the air by roughly a week and damps the swings:
    # trailing 10-day mean of the daily mean air temperature.
    ext = np.concatenate([norm_tmean[-10:], norm_tmean])
    soil = np.array([ext[i + 1:i + 11].mean() for i in range(365)])

    clim = Climate(years=years, tmax=norm_tmax, tmin=norm_tmin, tmean=norm_tmean,
                   precip=norm_precip, et0=norm_et0, soil=soil, year_tmin=st["tmin"])
    _build_masks(clim, None, None)

    # Local knowledge beats a 10–25 km reanalysis grid: shift the frost
    # climatology so its median dates match the user's dates.
    if lsf_override or fff_override:
        base = clim.frost_dates(32)
        ds = df = 0
        if lsf_override and base["spring"]["0.5"] is not None:
            ds = dates.month_day_to_idx(lsf_override) - base["spring"]["0.5"]
        if fff_override and base["fall"]["0.5"] is not None:
            df = dates.month_day_to_idx(fff_override) - base["fall"]["0.5"]
        _build_masks(clim, ds, df)
        clim.overrides = {"last_spring_frost": lsf_override,
                          "first_fall_frost": fff_override,
                          "spring_shift_days": ds, "fall_shift_days": df}
    return clim


def _build_masks(clim: Climate, ds: int | None, df: int | None) -> None:
    n = len(clim.years)
    for thr in FROST_THRESHOLDS:
        single = clim.year_tmin <= thr
        if ds or df:
            single = single.copy()
            for y in range(n):
                if ds:
                    single[y, :SPRING_END] = _shift(single[y, :SPRING_END], ds,
                                                    fill=ds > 0 and bool(single[y, 0]))
                if df:
                    single[y, SPRING_END:] = _shift(single[y, SPRING_END:], df,
                                                    fill=df < 0 and bool(single[y, -1]))
        # pair each year with the next so windows can cross New Year
        pairs = np.concatenate([single[:-1], single[1:]], axis=1) if n > 1 else \
            np.concatenate([single, single], axis=1)
        clim.frost_masks[thr] = np.vstack([pairs, np.concatenate(
            [single[-1:], single[-1:]], axis=1)])
        pre = np.zeros((pairs.shape[0] + 1, 731), dtype=np.int32)
        pre[:, 1:] = np.cumsum(clim.frost_masks[thr], axis=1)
        clim.frost_prefix[thr] = pre
