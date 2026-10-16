import datetime as dt

from app import products
from tests.test_foods import _in_ground, _setup


def test_kitchen_measures():
    assert products.measure("blood_meal", 3.1 / 16) == "about ½ cup"
    assert products.measure("blood_meal", 0.02) == "about 1 tablespoon"
    assert products.measure("blood_meal", 1.2) == "about 3¾ cups"
    assert products.measure("compost", 60).startswith("about 1.3 cu ft")
    assert products.measure("compost", 9) == "about 1½ gallons"
    assert "of concentrate" in products.measure("fish_emulsion", 0.1)
    assert products.measure("unknown_thing", 1) is None
    assert products.npk_text("blood_meal") == "12-0-0"
    assert products.npk_text("synthetic_101010") == "10-10-10"


def test_feeding_plan_reads_as_steps(located):
    c = located
    _in_ground(c)
    c.post("/api/foods/mine", json={"food_id": "tomatoes", "amount_lb": 150})
    plan = c.get("/api/feeding-plan", params={"year": 2026}).json()
    assert plan["year"] == 2026 and plan["steps"]
    st = next(s for s in plan["steps"] if s["crop"])
    assert st["crop"].startswith("Tomato") and st["auto"]
    assert st["measure"].startswith("about ") and st["npk"] == "12-0-0"
    assert st["how"] and "heavy feeder" in st["why"]
    assert {s["stage"] for s in plan["steps"]} <= {"planting", "side_dress", "feeding", "soil_prep"}
    assert [s["date"] for s in plan["steps"]] == sorted(s["date"] for s in plan["steps"])
    assert {"id": "blood_meal", "name": "Blood meal", "npk": "12-0-0"} in plan["products"]
    assert "N-P-K" in plan["npk_help"]
    # a manual amendment shows up too, with default instructions
    bid = st["bed_id"]
    c.post("/api/amendments", json={"bed_id": bid, "cycle_year": 1, "date": "03-15",
                                    "product": "compost", "amount_lb": 40})
    plan = c.get("/api/feeding-plan", params={"year": 2026}).json()
    mine = [s for s in plan["steps"] if not s["auto"]]
    assert mine and mine[0]["stage"] == "amendment" and "gallon" in mine[0]["measure"]


def test_feedings_show_up_on_today(located):
    c = located
    _in_ground(c)
    c.post("/api/foods/mine", json={"food_id": "tomatoes", "amount_lb": 150})
    first = next(s for s in c.get("/api/feeding-plan", params={"year": 2026}).json()["steps"]
                 if s["crop"])
    from app import main
    tasks = main._feeding_tasks(dt.date.fromisoformat(first["date"]))
    assert any(t["kind"] == "feed" and "cup" in t["text"] and t["bed"] == first["bed"]
               for t in tasks)


def test_rotation_groups_repeated_notes(located):
    c = located
    _setup(c, beds=3)
    c.post("/api/foods/bundle/salsa")
    issues = c.get("/api/rotation").json()["issues"]
    cover = [i for i in issues if i["kind"] == "cover"]
    assert len(cover) <= 1
    if cover:
        assert cover[0]["action"] == "cover_crops" and cover[0]["by_year"]
    # at most one feeding-order note per bed
    seq = [i["bed_id"] for i in issues if i["kind"] == "sequence"]
    assert len(seq) == len(set(seq))
    assert all("years" in i for i in issues)


def _one_bed(c, soil):
    c.put("/api/settings", json={"cycle_years": 3, "auto_size": False})
    bid = c.post("/api/beds", json={"name": "Plot", "kind": "in_ground",
                                    "soil": soil}).json()["id"]
    c.post("/api/foods/mine", json={"food_id": "tomatoes", "amount_lb": 20})
    return bid


def _prep(c, bid):
    return [a for a in c.get("/api/amendments").json()["amendments"]
            if a["bed_id"] == bid and a["auto"] and a["planting_id"] is None]


def test_low_soil_test_builds_phosphorus_up(located):
    bid = _one_bed(located, {"om_pct": 2.0, "p_ppm": 12, "k_ppm": 140})
    n = located.get(f"/api/nutrients/{bid}", params={"year": 2026}).json()
    assert n["source"] == "tested"
    assert n["p"]["level"] == "very_low" and n["p"]["build"] > 0
    assert n["k"]["level"] == "optimum" and n["k"]["build"] == 0
    prep = _prep(located, bid)
    assert {a["product"] for a in prep} == {"bone_meal", "potassium_sulfate"}
    plan = located.get("/api/feeding-plan", params={"year": 2026}).json()["steps"]
    bone = next(s for s in plan if s["product"] == "bone_meal")
    assert bone["stage"] == "soil_prep" and "very low" in bone["why"]
    # soil prep goes down before the crop goes in
    cal = located.get("/api/calendar", params={"year": int(bone["date"][:4])}).json()["events"]
    planted = [e["date"] for e in cal if e["type"] == "plant" and "Tomato" in e["title"]]
    assert planted and bone["date"] < min(planted)


def test_high_soil_test_skips_phosphorus(located):
    bid = _one_bed(located, {"om_pct": 2.0, "p_ppm": 120, "k_ppm": 400})
    located.put("/api/settings", json={"feed_product": "synthetic_101010"})
    assert not _prep(located, bid)
    n = located.get(f"/api/nutrients/{bid}", params={"year": 2026}).json()
    assert n["p"]["level"] == "very_high" and n["p"]["need"] == 0
    assert n["high_p_warning"]


def test_untested_soil_only_replaces_what_crops_take(located):
    bid = _one_bed(located, {"om_pct": 2.0})
    n = located.get(f"/api/nutrients/{bid}", params={"year": 2026}).json()
    assert n["source"] == "unknown" and n["p"]["build"] == 0
    assert 0 < n["p"]["need"] <= n["p"]["removed"]
    assert any("soil test" in s["why"] for s in located.get(
        "/api/feeding-plan", params={"year": 2026}).json()["steps"] if s["stage"] == "soil_prep")


def test_compost_counts_toward_p_and_k(located):
    bid = _one_bed(located, {"om_pct": 2.0})
    before = located.get(f"/api/nutrients/{bid}", params={"year": 2026}).json()
    located.post("/api/amendments", json={"bed_id": bid, "cycle_year": 1, "date": "03-01",
                                          "product": "compost", "amount_lb": 100})
    after = located.get(f"/api/nutrients/{bid}", params={"year": 2026}).json()
    assert after["k"]["supplied"] > before["k"]["supplied"]
    assert after["k"]["need"] < before["k"]["need"]


def test_acid_soil_gets_lime_advice(located):
    bid = _one_bed(located, {"om_pct": 2.0, "ph": 5.4})
    n = located.get(f"/api/nutrients/{bid}", params={"year": 2026}).json()
    assert n["ph_advice"] and "lime" in n["ph_advice"]["text"] and n["ph_advice"]["lb"] > 0


def test_upgrade_replans_existing_gardens_once(located):
    from app import db, feeding
    bid = _one_bed(located, {"om_pct": 2.0})
    db.execute("DELETE FROM amendments WHERE auto = 1 AND planting_id IS NULL")
    db.execute("DELETE FROM settings WHERE key = 'plan_version'")
    feeding.upgrade()
    assert _prep(located, bid)
    db.execute("DELETE FROM amendments WHERE auto = 1 AND planting_id IS NULL")
    feeding.upgrade()                       # already at this version: no re-plan
    assert not _prep(located, bid)
