"""Synthetic Open-Meteo / SDA / SoilGrids responses for offline tests.

The archive generator produces a plausible seasonal climate (sinusoidal
normals + autocorrelated weather noise) in the exact JSON shape the real API
returns, so the whole pipeline is exercised end-to-end.
"""

from __future__ import annotations

import datetime as dt
import math
import random

CLIMATES = {
    # annual mean °F, seasonal amplitude °F, diurnal range °F, noise °F, precip in/yr
    "denver": (50.5, 22.0, 28.0, 7.0, 15.0),
    "seattle": (52.5, 13.0, 16.0, 4.0, 38.0),
    "atlanta": (63.0, 17.0, 20.0, 6.0, 50.0),
    "minneapolis": (46.0, 30.0, 20.0, 8.0, 31.0),
    "miami": (77.5, 7.0, 14.0, 3.0, 60.0),
}


def _c(f):
    return round((f - 32) * 5 / 9, 2)


def archive(kind: str = "denver", start_year: int = 1995, end_year: int = 2025,
            seed: int = 1) -> dict:
    mean, amp, diurnal, noise, precip_yr = CLIMATES[kind]
    rng = random.Random(seed)
    d = dt.date(start_year, 1, 1)
    end = dt.date(end_year, 12, 31)
    out = {k: [] for k in ("time", "temperature_2m_max", "temperature_2m_min",
                           "temperature_2m_mean", "precipitation_sum",
                           "et0_fao_evapotranspiration")}
    anomaly = 0.0
    p_rain = 0.3
    while d <= end:
        doy = d.timetuple().tm_yday
        seasonal = mean - amp * math.cos(2 * math.pi * (doy - 15) / 365)
        anomaly = 0.7 * anomaly + rng.gauss(0, noise * 0.7)
        tmean = seasonal + anomaly
        tmax, tmin = tmean + diurnal / 2, tmean - diurnal / 2
        rain = 0.0
        if rng.random() < p_rain:
            rain = rng.expovariate(1 / (precip_yr / 365 / p_rain))
        et0 = max(0.0, 0.004 * (tmean - 32) * (1 + 0.5 * math.sin(math.pi * doy / 365)))
        out["time"].append(d.isoformat())
        out["temperature_2m_max"].append(_c(tmax))
        out["temperature_2m_min"].append(_c(tmin))
        out["temperature_2m_mean"].append(_c(tmean))
        out["precipitation_sum"].append(round(rain * 25.4, 1))
        out["et0_fao_evapotranspiration"].append(round(et0 * 25.4, 2))
        d += dt.timedelta(days=1)
    return {"latitude": 39.74, "longitude": -104.99, "timezone": "America/Denver",
            "daily_units": {"temperature_2m_max": "°C"}, "daily": out}


def forecast(kind: str = "denver", today: dt.date | None = None, past_days: int = 92,
             seed: int = 7, cold_snap: bool = False) -> dict:
    mean, amp, diurnal, noise, precip_yr = CLIMATES[kind]
    rng = random.Random(seed)
    today = today or dt.date.today()
    start = today - dt.timedelta(days=past_days)
    days = past_days + 16
    daily = {k: [] for k in ("time", "temperature_2m_max", "temperature_2m_min",
                             "precipitation_sum", "precipitation_probability_max",
                             "et0_fao_evapotranspiration", "wind_speed_10m_max",
                             "weather_code")}
    hourly = {k: [] for k in ("time", "temperature_2m", "relative_humidity_2m",
                              "soil_temperature_6cm", "soil_moisture_3_to_9cm")}
    anomaly = 0.0
    for i in range(days):
        d = start + dt.timedelta(days=i)
        doy = d.timetuple().tm_yday
        seasonal = mean - amp * math.cos(2 * math.pi * (doy - 15) / 365)
        anomaly = 0.7 * anomaly + rng.gauss(0, noise * 0.5)
        tmean = seasonal + anomaly
        if cold_snap and d == today + dt.timedelta(days=3):
            tmean = 30.0
        tmax, tmin = tmean + diurnal / 2, tmean - diurnal / 2
        rain = rng.expovariate(1 / 0.3) if rng.random() < 0.25 else 0.0
        daily["time"].append(d.isoformat())
        daily["temperature_2m_max"].append(_c(tmax))
        daily["temperature_2m_min"].append(_c(tmin))
        daily["precipitation_sum"].append(round(rain * 25.4, 1))
        daily["precipitation_probability_max"].append(60 if rain else 10)
        daily["et0_fao_evapotranspiration"].append(
            round(max(0.0, 0.006 * (tmean - 32)) * 25.4, 2))
        daily["wind_speed_10m_max"].append(12.0)
        daily["weather_code"].append(61 if rain else 1)
        for h in range(24):
            t = tmean - diurnal / 2 * math.cos(2 * math.pi * (h - 3) / 24)
            hourly["time"].append(f"{d.isoformat()}T{h:02d}:00")
            hourly["temperature_2m"].append(_c(t))
            hourly["relative_humidity_2m"].append(95 if rain and h < 10 else 55)
            hourly["soil_temperature_6cm"].append(_c(tmean + 2))
            hourly["soil_moisture_3_to_9cm"].append(0.25)
    return {"latitude": 39.74, "longitude": -104.99, "timezone": "America/Denver",
            "elevation": 1609.0, "daily": daily, "hourly": hourly}


SDA_RESPONSE = {"Table": [
    ["muname", "compname", "comppct_r", "drainagecl", "cokey", "hzdept_r", "hzdepb_r",
     "sandtotal_r", "silttotal_r", "claytotal_r", "om_r", "ph1to1h2o_r", "awc_r",
     "cec7_r"],
    ["Ascalon sandy loam, 0 to 3 percent slopes", "Ascalon", "85", "Well drained",
     "123", "0", "15", "65.0", "20.0", "15.0", "1.5", "7.2", "0.14", "11"],
    ["Ascalon sandy loam, 0 to 3 percent slopes", "Ascalon", "85", "Well drained",
     "123", "15", "48", "52.0", "20.0", "28.0", "0.8", "7.6", "0.16", "18"],
]}

SOILGRIDS_RESPONSE = {"type": "Feature", "properties": {"layers": [
    {"name": n, "unit_measure": {"d_factor": f},
     "depths": [{"label": lab, "values": {"mean": v}} for lab in ("0-5cm", "5-15cm",
                                                                  "15-30cm")]}
    for n, f, v in [("clay", 10, 220), ("sand", 10, 400), ("silt", 10, 380),
                    ("phh2o", 10, 68), ("soc", 10, 180), ("nitrogen", 100, 180),
                    ("cec", 10, 150)]
]}}


def fake_fetch(kind: str = "denver", cold_snap: bool = False):
    arch = archive(kind)
    fc = forecast(kind, cold_snap=cold_snap)

    def fetch(method, url, params, body, timeout):
        if "archive-api" in url:
            return arch
        if "api.open-meteo.com/v1/forecast" in url:
            return fc
        if "zippopotam" in url:
            return {"post code": "80202", "places": [
                {"place name": "Denver", "longitude": "-104.9963", "state": "Colorado",
                 "state abbreviation": "CO", "latitude": "39.7495"}]}
        if "geocoding-api" in url:
            return {"results": [{"name": "Denver", "latitude": 39.74, "longitude": -104.99,
                                 "admin1": "Colorado", "postcodes": ["80202"],
                                 "timezone": "America/Denver", "elevation": 1609}]}
        if "phzmapi" in url:
            return {"zone": "6a", "temperature_range": "-10 to -5",
                    "coordinates": {"lat": 39.75, "lon": -104.99}}
        if "sdmdataaccess" in url:
            return SDA_RESPONSE
        if "soilgrids" in url:
            return SOILGRIDS_RESPONSE
        raise RuntimeError(f"unexpected url {url}")
    return fetch
