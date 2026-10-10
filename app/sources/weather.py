"""Open-Meteo: 16-day forecast (+ recent past) and the ERA5 historical archive.

Both endpoints are free for non-commercial use and need no API key.  We ask
for metric units and convert ourselves so the unit handling is unambiguous.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from .http import get_json

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


def c_to_f(c):
    return None if c is None else c * 9 / 5 + 32


def mm_to_in(mm):
    return None if mm is None else mm / 25.4


def _r(lat: float, lon: float) -> tuple[float, float]:
    # ~1 km precision keeps cache keys stable for the same garden
    return round(lat, 3), round(lon, 3)


def fetch_forecast(lat: float, lon: float, past_days: int = 92) -> dict:
    lat, lon = _r(lat, lon)
    data = get_json(FORECAST_URL, {
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "past_days": past_days, "forecast_days": 16,
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
            "precipitation_probability_max", "et0_fao_evapotranspiration",
            "wind_speed_10m_max", "weather_code",
        ]),
        "hourly": ",".join([
            "temperature_2m", "relative_humidity_2m", "soil_temperature_6cm",
            "soil_moisture_3_to_9cm",
        ]),
    }, ttl=3 * 3600)
    return normalize_forecast(data)


def normalize_forecast(data: dict) -> dict:
    d = data["daily"]
    hourly = data.get("hourly") or {}
    per_day: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for i, t in enumerate(hourly.get("time", [])):
        day = t[:10]
        for key in ("temperature_2m", "relative_humidity_2m", "soil_temperature_6cm",
                    "soil_moisture_3_to_9cm"):
            vals = hourly.get(key)
            if vals is not None and i < len(vals):
                per_day[day][key].append(vals[i])
        temps = hourly.get("temperature_2m") or []
        rhs = hourly.get("relative_humidity_2m") or []
        if i < len(temps) and i < len(rhs) and temps[i] is not None and rhs[i] is not None:
            # leaf-wetness proxy: saturated air at temperatures fungi like
            if rhs[i] >= 90 and 10 <= temps[i] <= 27:
                per_day[day]["wet_hours"].append(1)

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    today = dt.date.today().isoformat()
    days = []
    for i, date in enumerate(d["time"]):
        def g(key):
            vals = d.get(key)
            return vals[i] if vals is not None and i < len(vals) else None
        h = per_day.get(date, {})
        tmax, tmin = g("temperature_2m_max"), g("temperature_2m_min")
        tmean = mean(h.get("temperature_2m", [])) if h else None
        if tmean is None and tmax is not None and tmin is not None:
            tmean = (tmax + tmin) / 2
        soil = [x for x in h.get("soil_temperature_6cm", []) if x is not None] if h else []
        days.append({
            "date": date,
            "past": date < today,
            "tmax_f": c_to_f(tmax), "tmin_f": c_to_f(tmin), "tmean_f": c_to_f(tmean),
            "precip_in": mm_to_in(g("precipitation_sum")) or 0.0,
            "precip_prob": g("precipitation_probability_max"),
            "et0_in": mm_to_in(g("et0_fao_evapotranspiration")) or 0.0,
            "wind_mph": None if g("wind_speed_10m_max") is None
            else g("wind_speed_10m_max") * 0.621371,
            "weather_code": g("weather_code"),
            "soil_f": c_to_f(mean(soil)) if soil else None,
            "soil_min_f": c_to_f(min(soil)) if soil else None,
            "soil_moisture": mean(h.get("soil_moisture_3_to_9cm", [])) if h else None,
            "rh_mean": mean(h.get("relative_humidity_2m", [])) if h else None,
            "wet_hours": len(h.get("wet_hours", [])) if h else 0,
        })
    return {"timezone": data.get("timezone"), "elevation": data.get("elevation"),
            "days": days}


def fetch_archive(lat: float, lon: float, years: int = 31) -> dict:
    """Daily history for the last ``years`` complete calendar years."""
    lat, lon = _r(lat, lon)
    end_year = dt.date.today().year - 1
    start_year = end_year - years + 1
    data = get_json(ARCHIVE_URL, {
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "start_date": f"{start_year}-01-01", "end_date": f"{end_year}-12-31",
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
            "precipitation_sum", "et0_fao_evapotranspiration",
        ]),
    }, ttl=86400 * 60, timeout=120)
    return data
