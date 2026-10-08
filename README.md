# Local Plant Calendar

A self-hosted garden planner for your home network, built around **the food you want to eat**.

Type a food, such as "pinto beans", "salsa", "french fries" or "strawberries", and the app does the work:

1. It figures out the crop and variety (refried beans → bush pinto bean such as 'Othello', ~85 days).
2. It checks your climate. Perennials are checked against your hardiness zone. For annuals it tries the usual method, then starting indoors or direct sowing instead, then a faster variety, then row cover. If none of that works, it says the food isn't suitable and explains why (for example "Avocado survives only to zone 9b; you're zone 6a"). It then suggests what would work, such as a container you bring indoors.
3. It checks each bed's soil (pH, heavy clay, drainage, organic matter) and gives lime, sulfur or compost amounts where the soil is fixable.
4. It sizes the planting from how much you eat ("5 lb of dried beans a year" → ~70 sq ft).
5. It places the crop in your rotation every year of the cycle. Each year it goes in a different bed, keeping plant families apart long enough, in a bed with free space during its season, after a good preceding crop. If there isn't room, it says how much more bed space you'd need.
6. It writes a dated growing guide for your location: variety, soil prep, start-indoors and planting dates, spacing, weekly water at peak, feeding (from the nitrogen model), harvest and processing.

Dish bundles (salsa, pesto, three sisters, chili, tacos…) add every ingredient at once. "Add winter cover crops" fills beds that would sit bare over winter, using a legume ahead of heavy feeders and a nitrogen catch crop otherwise.

Under the hood it works out:

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

1. Open the app and enter your ZIP code. The first load downloads 30 years of daily weather for your spot (a few seconds).
2. Describe your garden, for example "3 raised beds, 8×4 ft". Raised beds default to a compost-rich mix; in-ground beds use the USDA soil survey for your location. You can add soil-test numbers later in **Setup**.
3. On **My food**, type what you want to eat, optionally add how many pounds a year, and press **Grow it**.
4. **Today** is the daily dashboard (alerts, go/wait, watering). **Calendar** has three views. **Month** is a real calendar grid: start-indoors, harden-off, sow/transplant (each succession), harvest windows, last harvests, cover-crop cut-down, soil amendments, and average and 1-in-10 frost dates. For the next 16 days it also shows the forecast high/low, frost and heat alerts, "wait" advice and per-bed watering; click a day for details and "I planted this / I watered" buttons. **Agenda** lists the next 90 days. **Timeline** is the year as a Gantt chart. Filters by bed and event type are remembered. **Rotation** shows and edits the multi-year plan. **Soil & N** has the nitrogen and organic-matter projections. **Plants** is the full library; use **Plan it for me** or **Place it myself** there.

## How it works

| Question | Method | Data |
|---|---|---|
| Food → crop | ~150 foods, dishes and products mapped to crops and varieties, with typical yields per sq ft; every edible plant in the library is also searchable | `app/food_data.py` |
| Can it grow here? | Zone range for perennials; for annuals the planting-window engine below, retried with the other method, a faster variety, and row cover | — |
| Soil fit | pH vs. crop range (lime/sulfur rates by soil texture), clay for root crops, drainage, organic matter for heavy feeders | Bed soil profile |
| Where & when | Every rotation year: beds scored on soil fit, plant-family return interval (hard rule), preceding crop group, companions and free space during the crop's season | Your beds & plantings |
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

## Your garden in your phone's calendar

**Calendar → Add to my phone calendar** gives a subscription address (`http://<server>:8080/api/calendar.ics`, optionally filtered by `?kinds=plant,harvest&bed=2`). Subscribe to it from Apple Calendar (iPhone: Settings → Calendar → Accounts → Add Subscribed Calendar), Outlook or Thunderbird. Every planting, transplant and harvest window then appears as an all-day event and updates as your plan changes. Your devices refresh it whenever they can reach the server on your network. Google Calendar can't reach a home server, so download the `.ics` file and import it instead.

## Adding plants

- To make a food searchable by another name, add an `F(...)` line to `app/food_data.py` (aliases, yield, variety tip).
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

Layout: `app/main.py` (API), `app/foods.py` + `app/food_data.py` (food-first planner), `app/calendar_events.py` (calendar + iCal feed), `app/scheduler.py` (planting windows), `app/climate.py` (frost & normals), `app/water.py`, `app/nitrogen.py`, `app/rotation.py`, `app/advisor.py` (forecast advice), `app/sources/` (data fetchers), `app/static/` (vanilla-JS UI with no build step).
