# Local Plant Calendar

A self-hosted garden planner for your home network. Tell it where your garden is and what's in each bed, and it works out:

- **When to plant**: planting windows for 140+ vegetables, herbs, fruits, flowers and cover crops, from 30 years of your local weather. Includes indoor seed-starting dates, hardening off, transplanting, succession sowings and expected harvest windows.
- **How the forecast affects things**: frost, freeze and heat alerts for what's actually in the ground, plus go/wait advice on sowing (soil temperature, frost, washout rain). It also flags disease-favourable weather and re-projects harvest dates from actual temperatures.
- **How much to water**: a per-bed watering schedule in inches and gallons, from a FAO-56 crop water balance that uses forecast evapotranspiration, rain and your soil's water-holding capacity.
- **Your rotation**: a 1–8 year repeating cycle per bed. It checks plant-family return intervals, heavy-feeder sequencing, companion conflicts, bed space and bare winter beds.
- **Soil and nitrogen over time**: a daily nitrogen budget across the whole cycle. It models organic-matter mineralization, crop uptake, legume fixation, residue and cover-crop release, compost and fertilizer, and winter leaching. It projects shortfalls with side-dress amounts and organic-matter trends.

All data sources are free and need no account or API key.

## Run it

### Docker (recommended)

```bash
git clone <this repo> && cd localplantcalendar
docker compose up -d --build
```

Open `http://<server-ip>:8080` from any device on your network. Your plan and cached data live in `./data/plantcal.db`; back it up by copying that file. Set `TZ` in `docker-compose.yml` to your time zone.

### Without Docker

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Python 3.11+. Set `PLANTCAL_DB=/path/to/plantcal.db` to choose where data is stored (default `./data/plantcal.db`).

## First steps

1. **Setup**: enter your ZIP code. The first load downloads 30 years of daily weather for your spot (a few seconds), then caches it.
2. **Setup → Beds**: add each bed with its size. Raised beds default to a compost-rich mix. In-ground beds use the USDA soil survey for your location. Enter soil-test numbers (OM %, pH, nitrate) when you have them.
3. **Plants**: browse or search, open a plant, and use **Add to my rotation** to pick the bed, the rotation year and a planting window.
4. **Rotation** shows the multi-year plan and its warnings. **Calendar** is the year's schedule. **Today** is the daily dashboard. **Soil & N** shows each bed's nitrogen and organic-matter projection.

## How it works

| Question | Method | Data |
|---|---|---|
| Frost dates & risk | Per-year last/first frost at 32/28/24/15 °F → empirical probabilities (10/30/50/90 %) | Open-Meteo Historical (ERA5), 31 years of daily data |
| Planting windows | Each day of the year is scored for (1) reaching maturity before season end, (2) frost risk for the crop's hardiness during its vulnerable period, (3) germination soil temperature, (4) warmth to establish, (5) heat at maturity (bolting, poor fruit set). Contiguous good days become windows. | Climatology above + plant parameters |
| Days to maturity | Growing degree days with crop-specific base temperature, calibrated so seed-packet DTM holds in a ~68 °F (warm crops) / ~60 °F (cool crops) mean day | Normals, plus actual temperatures for crops in the ground |
| Watering | FAO-56 single crop coefficient: ETc = Kc(stage) × ET₀; root-zone depletion vs. readily-available water (p × AWC × root depth) | Open-Meteo forecast ET₀ + rain; soil AWC; FAO-56 Kc, root depth, p |
| Soil | Dominant SSURGO component, top 30 cm, depth-weighted; SoilGrids fallback | USDA NRCS Soil Data Access; ISRIC SoilGrids |
| Nitrogen | Daily pools: OM mineralization (~1.7 %/yr of organic N, Q10 = 2 temperature response; ≈ "20 lb N/acre per 1 % OM"), logistic crop uptake by GDD, legume credits, residue release by C:N (high-C residue immobilizes), amendment release curves, drainage-driven nitrate leaching | Extension nutrient-management rules of thumb |
| Hardiness zone | USDA zone by ZIP, or estimated from 30-year winter lows | phzmapi.org |

### Data sources

- [Open-Meteo](https://open-meteo.com/): forecast, ET₀, soil temperature, humidity; and the ERA5 historical archive. Free for non-commercial use.
- [USDA NRCS Soil Data Access](https://sdmdataaccess.sc.egov.usda.gov/) (SSURGO).
- [ISRIC SoilGrids](https://soilgrids.org/), as a fallback.
- [phzmapi.org](https://phzmapi.org/): USDA Plant Hardiness Zones by ZIP.
- [Zippopotam.us](https://zippopotam.us/): ZIP → coordinates; plus Open-Meteo geocoding for town names.
- Plant parameters are compiled into `app/plant_data.py` from university extension planting guides and FAO Irrigation & Drainage Paper 56.

Responses are cached in SQLite, and the app keeps working on stale data if a service is briefly down.

## Adding plants

- In the app, open any plant and choose **Make a custom variety**. It copies the plant and lets you change days to maturity, spacing, frost tolerance, heat limit and N demand to match your seed packet.
- For a planting, the **Days to maturity** field in the rotation dialog overrides the default.
- To add to the built-in library, add a `P(...)` line to `app/plant_data.py`. Pick the closest profile and override what differs; the field reference is at the top of the file.

## Limitations

- ERA5 is a ~10–25 km grid. Frost pockets, slopes and urban heat can shift your dates by a week or more. If you know your local frost dates, enter them in **Setup → Preferences** and the 30-year record is shifted to match.
- Planting windows assume open ground. Row cover, cold frames and greenhouses extend them.
- The nitrogen model is for planning and spotting trends. Calibrate it with a soil nitrate test, and use a lab test before making big fertilizer decisions.
- Day length isn't modelled. Onion day-length type and spinach bolting are covered in the plant tips.

## Development

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests run fully offline against synthetic Open-Meteo, SSURGO and SoilGrids responses in `tests/fixtures.py`, which mimic five US climates.

Layout: `app/main.py` (API), `app/scheduler.py` (planting windows), `app/climate.py` (frost & normals), `app/water.py`, `app/nitrogen.py`, `app/rotation.py`, `app/advisor.py` (forecast advice), `app/sources/` (data fetchers), `app/static/` (vanilla-JS UI with no build step).
