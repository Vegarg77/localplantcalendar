import datetime as dt

import numpy as np
import pytest

from app import climate, dates, nitrogen, water
from app.garden import Instance
from app.plant_data import builtin_plants
from app.scheduler import Engine
from app.sources import soil
from tests import fixtures

PLANTS = {p["id"]: p for p in builtin_plants()}


@pytest.fixture(scope="module")
def denver():
    return climate.build(fixtures.archive("denver"))


@pytest.fixture(scope="module")
def engine(denver):
    return Engine(denver, 0.1)


# ------------------------------------------------------------------ dates
def test_date_roundtrip():
    for idx in (0, 58, 59, 180, 364, 365, 400):
        d = dates.to_date(2026, idx)
        assert dates.doy(d) == idx % 365
    assert dates.doy(dt.date(2024, 2, 29)) == dates.doy(dt.date(2024, 2, 28))
    assert dates.month_day_to_idx("05-20") == dates.doy(dt.date(2026, 5, 20))


# ------------------------------------------------------------------- data
def test_plant_library_is_consistent():
    ids = set(PLANTS)
    assert len(PLANTS) >= 140
    for p in PLANTS.values():
        for ref in p["companions"] + p["avoid"]:
            assert ref in ids, f"{p['id']} references unknown {ref}"
        assert p["dtm"][0] <= p["dtm"][1]
        assert len(p["kc"]) == 3


# ------------------------------------------------------------------- soil
@pytest.mark.parametrize("sand,silt,clay,expected", [
    (90, 5, 5, "sand"), (40, 40, 20, "loam"), (20, 65, 15, "silt loam"),
    (20, 30, 50, "clay"), (65, 20, 15, "sandy loam"), (30, 35, 35, "clay loam"),
])
def test_texture_triangle(sand, silt, clay, expected):
    assert soil.texture_class(sand, silt, clay) == expected


def test_bed_soil_overrides_recompute_water():
    site = soil.finish({"sand": 40, "silt": 40, "clay": 20, "om_pct": 2.0, "ph": 6.5})
    sandy = soil.bed_soil(site, {"sand": 85, "silt": 10, "clay": 5})
    assert sandy["texture"] in ("loamy sand", "sand")
    assert sandy["awc"] < site["awc"]
    raised = soil.bed_soil(site, {"preset": "raised_mix"})
    assert raised["om_pct"] == 8.0


# ---------------------------------------------------------------- climate
def test_frost_dates_are_ordered(denver):
    fd = denver.frost_dates(32)
    s, f = fd["spring"], fd["fall"]
    assert s["0.1"] >= s["0.5"] >= s["0.9"]
    assert f["0.1"] <= f["0.5"] <= f["0.9"]
    assert 100 < fd["season_days"] < 220


def test_frost_override_shifts_median():
    base = climate.build(fixtures.archive("denver"))
    shifted = climate.build(fixtures.archive("denver"), lsf_override="05-15")
    assert shifted.frost_dates(32)["spring"]["0.5"] == pytest.approx(
        dates.month_day_to_idx("05-15"), abs=3)
    assert shifted.frost_dates(32)["spring"]["0.5"] > base.frost_dates(32)["spring"]["0.5"]


def test_frost_free_climate():
    miami = climate.build(fixtures.archive("miami"))
    assert miami.frost_dates(32)["spring"]["0.5"] is None
    assert miami.anchors() == (45, 320)


# --------------------------------------------------------------- scheduler
def test_tomato_goes_out_after_frost(engine, denver):
    w = engine.windows(PLANTS["tomato"])
    assert w["method"] == "transplant"
    win = w["windows"][0]
    assert win["establish"] >= denver.frost_dates(32)["spring"]["0.5"]
    assert win["indoor_start"][0] < win["establish"] - 35
    assert win["maturity"] < win["harvest_end"]


def test_cool_crops_get_spring_and_fall(engine):
    for pid in ("lettuce_leaf", "spinach", "radish", "peas_shell", "broccoli"):
        seasons = {x["season"] for x in engine.windows(PLANTS[pid])["windows"]}
        assert "Spring" in seasons, pid
        assert seasons & {"Summer", "Fall"}, pid


def test_garlic_is_fall_planted(engine):
    win = engine.windows(PLANTS["garlic"])["windows"][0]
    assert win["season"] == "Fall"
    assert win["maturity"] > 365  # harvested the following summer


def test_miami_cool_crops_only_in_winter():
    e = Engine(climate.build(fixtures.archive("miami")), 0.1)
    for win in e.windows(PLANTS["spinach"])["windows"]:
        assert dates.month_of_idx(win["establish"]) in (10, 11, 12, 1, 2)
    assert not e.windows(PLANTS["rhubarb"] | {"special": None, "heat_max": 70})["windows"]
    lettuce = e.windows(PLANTS["lettuce_leaf"])["windows"]
    assert lettuce and lettuce[0]["season"] in ("Fall", "Winter")


@pytest.mark.parametrize("kind", list(fixtures.CLIMATES))
def test_every_plant_schedules_everywhere(kind):
    e = Engine(climate.build(fixtures.archive(kind)), 0.3)
    for p in PLANTS.values():
        for m in (["direct", "transplant"] if p["method"] == "either" else [None]):
            w = e.windows(p, m)
            for win in w["windows"]:
                assert win["maturity"] >= win["establish"]


def test_dtm_override_changes_maturity(engine):
    p = PLANTS["tomato"]
    fast = engine.plan(p, 140, "transplant", 55)
    slow = engine.plan(p, 140, "transplant", 95)
    assert fast["maturity"] < slow["maturity"]


# -------------------------------------------------------------------- water
def _inst(pid, start, end, area=32):
    p = PLANTS[pid]
    return Instance(planting={"id": 1, "bed_id": 1, "cycle_year": 1, "residue": "remove"},
                    plant=p, year=start.year, succession=0, method="direct", area=area,
                    establish=start, maturity=start + (end - start) * 0.7, harvest_end=end,
                    kind="annual")


def _weather(today, rain_on=None, days=30):
    out = []
    for i in range(-14, days - 14):
        d = today + dt.timedelta(days=i)
        out.append({"date": d.isoformat(), "et0_in": 0.25, "precip_in": 0.0,
                    "precip_prob": 0, "tmax_f": 85, "tmin_f": 60, "tmean_f": 72})
    if rain_on is not None:
        out[14 + rain_on].update(precip_in=1.5, precip_prob=90)
    return out


def test_water_schedule_irrigates_in_dry_heat():
    today = dt.date(2026, 7, 1)
    bed = {"id": 1, "name": "A", "length_ft": 8, "width_ft": 4, "mulched": False}
    sp = soil.finish({"texture": "loam", "om_pct": 3})
    inst = _inst("tomato", dt.date(2026, 5, 20), dt.date(2026, 9, 20))
    plan = water.schedule(bed, sp, [inst], _weather(today), {}, today)
    assert plan["plan"], "should need water in a week of 0.25 in/day ET"
    first = plan["plan"][0]
    assert first["gallons"] == pytest.approx(first["inches"] * 32 * 0.623, rel=0.01)


def test_rain_postpones_watering():
    today = dt.date(2026, 7, 1)
    bed = {"id": 1, "name": "A", "length_ft": 8, "width_ft": 4, "mulched": False}
    sp = soil.finish({"texture": "loam", "om_pct": 3})
    inst = _inst("tomato", dt.date(2026, 5, 20), dt.date(2026, 9, 20))
    dry = water.schedule(bed, sp, [inst], _weather(today), {}, today)
    wet = water.schedule(bed, sp, [inst], _weather(today, rain_on=1), {}, today)
    assert sum(p["inches"] for p in wet["plan"]) < sum(p["inches"] for p in dry["plan"])


def test_fallow_bed_needs_no_water():
    today = dt.date(2026, 7, 1)
    bed = {"id": 1, "name": "A", "length_ft": 8, "width_ft": 4, "mulched": False}
    plan = water.schedule(bed, soil.finish({}), [], _weather(today), {}, today)
    assert plan["plan"] == [] and plan["available_water_pct"] is None


# ----------------------------------------------------------------- nitrogen
def _sim(denver, insts, om=2.0, amendments=(), years=2):
    bed = {"id": 1, "name": "A", "length_ft": 10, "width_ft": 4, "initial_no3_ppm": 10}
    sp = soil.finish({"texture": "loam", "om_pct": om})
    return nitrogen.simulate(bed, sp, insts, list(amendments), denver, 2026, years,
                             {}, lambda y: 1)


def test_heavy_feeder_on_poor_soil_runs_short(denver):
    corn = _inst("sweet_corn", dt.date(2026, 5, 15), dt.date(2026, 8, 20), area=40)
    r = _sim(denver, [corn], om=1.0)
    assert r["crops"][0]["deficit_lb_acre"] > 30
    assert any(x["kind"] == "deficit" for x in r["recommendations"])


def test_shortfall_explains_why_and_how_to_fix(denver):
    tomato = _inst("tomato", dt.date(2026, 5, 20), dt.date(2026, 9, 20), area=40)
    recs = _sim(denver, [tomato], om=1.5)["recommendations"]
    assert recs[0]["kind"] == "budget" and "1.5% organic matter" in recs[0]["text"]
    assert any("compost" in o for o in recs[0]["options"])
    deficit = next(r for r in recs if r["kind"] == "deficit")
    assert deficit["options"][0].startswith("Feed it")
    assert any("vetch" in o or "clover" in o for o in deficit["options"])


def test_no_cover_crop_tip_after_a_legume(denver):
    vetch = _inst("hairy_vetch", dt.date(2025, 9, 15), dt.date(2026, 5, 1), area=40)
    vetch.planting = {**vetch.planting, "id": 2, "residue": "incorporate"}
    tomato = _inst("tomato", dt.date(2026, 5, 20), dt.date(2026, 9, 20), area=40)
    recs = _sim(denver, [vetch, tomato], om=1.0)["recommendations"]
    deficit = next(r for r in recs if r["kind"] == "deficit")
    assert not any(o.startswith("Grow nitrogen first") for o in deficit["options"])


def test_fertilizer_closes_the_gap(denver):
    corn = _inst("sweet_corn", dt.date(2026, 5, 15), dt.date(2026, 8, 20), area=40)
    base = _sim(denver, [corn], om=1.0)["crops"][0]["deficit_lb_acre"]
    fed = _sim(denver, [corn], om=1.0, amendments=[
        {"cycle_year": 1, "doy": dates.month_day_to_idx("05-20"),
         "product": "blood_meal", "amount_lb": 1.5, "n_pct": None}])["crops"][0]
    assert fed["deficit_lb_acre"] < base


def test_legume_cover_crop_adds_nitrogen(denver):
    def vetch(residue):
        i = _inst("hairy_vetch", dt.date(2026, 9, 1), dt.date(2027, 5, 15), area=40)
        i.planting = {**i.planting, "residue": residue}
        return i
    bare = _sim(denver, [])["years"][1]["end_mineral"]
    with_vetch = _sim(denver, [vetch("incorporate")])
    assert with_vetch["years"][1]["fixed"] > 50
    assert with_vetch["years"][1]["end_mineral"] > bare


def test_organic_matter_declines_without_inputs(denver):
    r = _sim(denver, [], om=4.0, years=4)
    assert r["end_om_pct"] < 4.0
    assert any(x["kind"] == "organic_matter" for x in r["recommendations"])
