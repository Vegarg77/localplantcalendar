"""Soil properties for a point.

1. USDA NRCS Soil Data Access (SSURGO) — the detailed US soil survey.
2. ISRIC SoilGrids 250 m — global machine-learning maps (fallback).
3. A neutral loam default if both fail.

Everything is converted into one profile dictionary used by the water and
nitrogen models.  Users can override any value per bed (e.g. raised-bed mix).
"""

from __future__ import annotations

import logging

from .http import SourceError, get_json

log = logging.getLogger("plantcal.soil")

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
SOILGRIDS_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Available water capacity (in water / in soil) and field-capacity volumetric
# water content by USDA texture class (Saxton & Rawls 2006 style averages).
TEXTURE_WATER = {
    "sand": (0.05, 0.10), "loamy sand": (0.07, 0.14), "sandy loam": (0.12, 0.21),
    "loam": (0.17, 0.28), "silt loam": (0.20, 0.31), "silt": (0.20, 0.30),
    "sandy clay loam": (0.15, 0.27), "clay loam": (0.17, 0.33),
    "silty clay loam": (0.19, 0.35), "sandy clay": (0.13, 0.32),
    "silty clay": (0.16, 0.38), "clay": (0.15, 0.40),
}

PRESETS = {
    "native": None,
    "raised_mix": {"name": "Raised-bed mix (topsoil + compost)", "texture": "loam",
                   "sand": 45, "silt": 35, "clay": 20, "om_pct": 8.0, "ph": 6.8,
                   "awc": 0.18, "fc": 0.30, "drainage": "Well drained"},
    "container_mix": {"name": "Potting mix", "texture": "loamy sand", "sand": 80,
                      "silt": 15, "clay": 5, "om_pct": 30.0, "ph": 6.2, "awc": 0.20,
                      "fc": 0.35, "drainage": "Excessively drained"},
}

DEFAULT_SOIL = {"name": "Unknown (assumed loam)", "texture": "loam", "sand": 40,
                "silt": 40, "clay": 20, "om_pct": 2.5, "ph": 6.5, "awc": 0.17,
                "fc": 0.28, "cec": 12.0, "drainage": "Well drained",
                "source": "default"}


def texture_class(sand: float, silt: float, clay: float) -> str:
    """USDA soil texture triangle."""
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 1.5 * clay < 30:
        return "loamy sand"
    if (7 <= clay < 20 and sand > 52 and silt + 2 * clay >= 30) or \
            (clay < 7 and silt < 50 and silt + 2 * clay >= 30):
        return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "silty clay loam"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 40 and silt >= 40:
        return "silty clay"
    if clay >= 40:
        return "clay"
    return "loam"


def finish(profile: dict) -> dict:
    """Fill derived fields (texture, water capacity) and clamp values."""
    p = {**DEFAULT_SOIL, **{k: v for k, v in profile.items() if v is not None}}
    if all(p.get(k) is not None for k in ("sand", "silt", "clay")):
        total = p["sand"] + p["silt"] + p["clay"]
        if total > 0:
            for k in ("sand", "silt", "clay"):
                p[k] = round(p[k] * 100 / total, 1)
        if not profile.get("texture"):
            p["texture"] = texture_class(p["sand"], p["silt"], p["clay"])
    awc, fc = TEXTURE_WATER.get(p["texture"], (0.17, 0.28))
    if not profile.get("awc"):
        # organic matter raises water holding ~ +0.01 in/in per 1% OM above 2%
        p["awc"] = round(awc + max(0.0, min(p["om_pct"], 10) - 2) * 0.01, 3)
    if not profile.get("fc"):
        p["fc"] = fc
    p["om_pct"] = round(float(p["om_pct"]), 2)
    p["ph"] = round(float(p["ph"]), 1)
    return p


# ------------------------------------------------------------------- SSURGO
def _sda(lat: float, lon: float) -> dict | None:
    sql = f"""
SELECT mu.muname, c.compname, c.comppct_r, c.drainagecl, c.cokey,
       h.hzdept_r, h.hzdepb_r, h.sandtotal_r, h.silttotal_r, h.claytotal_r,
       h.om_r, h.ph1to1h2o_r, h.awc_r, h.cec7_r
FROM mapunit mu
INNER JOIN component c ON c.mukey = mu.mukey
INNER JOIN chorizon h ON h.cokey = c.cokey
WHERE mu.mukey IN (SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84(
        'point({lon:.5f} {lat:.5f})'))
  AND c.majcompflag = 'Yes'
ORDER BY c.comppct_r DESC, c.cokey, h.hzdept_r
"""
    data = get_json(SDA_URL, method="POST",
                    body={"query": sql, "format": "JSON+COLUMNNAME"},
                    ttl=86400 * 365, cache_key=f"sda {lat:.4f} {lon:.4f}")
    table = (data or {}).get("Table") or []
    if len(table) < 2:
        return None
    cols, rows = table[0], [dict(zip(table[0], r)) for r in table[1:]]
    del cols

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # take the first major component that actually has horizon data
    by_comp: dict[str, list[dict]] = {}
    for r in rows:
        by_comp.setdefault(r["cokey"], []).append(r)
    for horizons in by_comp.values():
        top = [h for h in horizons if (num(h["hzdept_r"]) or 0) < 30
               and num(h["claytotal_r"]) is not None]
        if not top:
            continue
        # depth-weighted average over the top 30 cm
        tot_w = 0.0
        acc = {k: 0.0 for k in ("sand", "silt", "clay", "om", "ph", "awc", "cec")}
        cnt = {k: 0.0 for k in acc}
        src = {"sand": "sandtotal_r", "silt": "silttotal_r", "clay": "claytotal_r",
               "om": "om_r", "ph": "ph1to1h2o_r", "awc": "awc_r", "cec": "cec7_r"}
        for h in top:
            t, b = num(h["hzdept_r"]) or 0, min(num(h["hzdepb_r"]) or 30, 30)
            w = max(b - t, 1)
            tot_w += w
            for k, col in src.items():
                v = num(h[col])
                if v is not None:
                    acc[k] += v * w
                    cnt[k] += w
        avg = {k: (acc[k] / cnt[k] if cnt[k] else None) for k in acc}
        h0 = top[0]
        return finish({
            "name": f"{h0['compname']} — {h0['muname']}",
            "sand": avg["sand"], "silt": avg["silt"], "clay": avg["clay"],
            "om_pct": avg["om"], "ph": avg["ph"], "awc": avg["awc"], "cec": avg["cec"],
            "drainage": h0.get("drainagecl"),
            "source": "USDA NRCS SSURGO (Soil Data Access)",
        })
    return None


# ---------------------------------------------------------------- SoilGrids
def _soilgrids(lat: float, lon: float) -> dict | None:
    props = ["clay", "sand", "silt", "phh2o", "soc", "nitrogen", "cec"]
    params = [("lon", f"{lon:.4f}"), ("lat", f"{lat:.4f}"), ("value", "mean")]
    params += [("property", p) for p in props]
    params += [("depth", d) for d in ("0-5cm", "5-15cm", "15-30cm")]
    data = get_json(SOILGRIDS_URL, params=params, ttl=86400 * 365,
                    cache_key=f"soilgrids {lat:.4f} {lon:.4f}")
    layers = (data or {}).get("properties", {}).get("layers", [])
    vals: dict[str, float] = {}
    weights = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
    for layer in layers:
        factor = (layer.get("unit_measure") or {}).get("d_factor", 1) or 1
        tot = wsum = 0.0
        for depth in layer.get("depths", []):
            v = (depth.get("values") or {}).get("mean")
            w = weights.get(depth.get("label"), 0)
            if v is not None and w:
                tot += v / factor * w
                wsum += w
        if wsum:
            vals[layer["name"]] = tot / wsum
    if "clay" not in vals:
        return None
    soc = vals.get("soc")  # g/kg
    return finish({
        "name": "SoilGrids 250 m estimate",
        "sand": vals.get("sand"), "silt": vals.get("silt"), "clay": vals.get("clay"),
        "om_pct": soc / 10 * 1.724 if soc is not None else None,
        "ph": vals.get("phh2o"), "cec": vals.get("cec"),
        "n_total_g_kg": vals.get("nitrogen"),
        "drainage": None, "source": "ISRIC SoilGrids 2.0",
    })


def soil_at(lat: float, lon: float) -> dict:
    for fn in (_sda, _soilgrids):
        try:
            prof = fn(lat, lon)
            if prof:
                return prof
        except SourceError as exc:
            log.warning("soil source %s failed: %s", fn.__name__, exc)
    return finish({**DEFAULT_SOIL})


def bed_soil(site_soil: dict, bed_override: dict | None) -> dict:
    """Combine the site soil with a bed's preset/overrides."""
    o = dict(bed_override or {})
    preset = PRESETS.get(o.pop("preset", "native") or "native")
    base = {**site_soil, **preset, "source": preset["name"]} if preset else dict(site_soil)
    o = {k: v for k, v in o.items() if v not in (None, "")}
    if o:
        base.update(o)
        # recompute derived values if the composition changed
        if any(k in o for k in ("sand", "silt", "clay")) and "texture" not in o:
            base.pop("texture", None)
        if "awc" not in o:
            base.pop("awc", None)
        if "fc" not in o:
            base.pop("fc", None)
        base["source"] = (base.get("source") or "") + " + your overrides"
    return finish(base)
