"""Location lookup: ZIP codes (Zippopotam.us), place names (Open-Meteo
geocoding) and USDA hardiness zones (phzmapi.org)."""

from __future__ import annotations

import re

from .http import SourceError, get_json

ZIP_RE = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")


def geocode(q: str) -> list[dict]:
    q = q.strip()
    m = ZIP_RE.match(q)
    if m:
        z = m.group(1)
        data = get_json(f"https://api.zippopotam.us/us/{z}", ttl=86400 * 365)
        out = []
        for p in data.get("places", []):
            out.append({
                "name": f"{p['place name']}, {p['state abbreviation']} {z}",
                "lat": float(p["latitude"]), "lon": float(p["longitude"]),
                "zip": z, "state": p["state abbreviation"],
            })
        return out
    data = get_json("https://geocoding-api.open-meteo.com/v1/search",
                    {"name": q, "count": 8, "language": "en", "format": "json",
                     "countryCode": "US"}, ttl=86400 * 30)
    out = []
    for r in data.get("results", []) or []:
        zips = r.get("postcodes") or []
        out.append({
            "name": ", ".join(x for x in [r.get("name"), r.get("admin1")] if x),
            "lat": r["latitude"], "lon": r["longitude"],
            "zip": zips[0] if zips else None, "state": r.get("admin1"),
            "elevation": r.get("elevation"), "timezone": r.get("timezone"),
        })
    return out


def hardiness_zone(zip_code: str | None) -> dict | None:
    """USDA plant hardiness zone for a ZIP code, or None if unavailable."""
    if not zip_code:
        return None
    try:
        data = get_json(f"https://phzmapi.org/{zip_code}.json", ttl=86400 * 365)
    except SourceError:
        return None
    if not isinstance(data, dict) or "zone" not in data:
        return None
    return {"zone": data["zone"], "temperature_range": data.get("temperature_range"),
            "source": "USDA Plant Hardiness Zone Map (phzmapi.org)"}


def zone_from_temp(avg_annual_min_f: float) -> str:
    """USDA zone from the average annual extreme minimum temperature."""
    idx = int((avg_annual_min_f + 60) // 5)
    idx = max(0, min(idx, 25))
    return f"{idx // 2 + 1}{'ab'[idx % 2]}"
