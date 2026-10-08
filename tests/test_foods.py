import pytest

from app import foods
from app.plant_data import builtin_plants

PLANTS = {p["id"]: p for p in builtin_plants()}


@pytest.mark.parametrize("query,expected", [
    ("pinto beans", "pinto_beans"), ("refried beans", "pinto_beans"), ("Hummus", "chickpeas"),
    ("french fries", "potatoes"), ("jalapeños", "hot_peppers"), ("frijoles negros", "black_beans"),
    ("tomatoes", "tomatoes"), ("guacamole", "avocados"), ("coffee", "coffee"),
    ("kimchi", "napa_food"), ("okra", "okra_food"), ("Chinese broccoli", "gai_lan_food"),
])
def test_food_search(query, expected):
    assert foods.search(query, PLANTS)[0]["id"] == expected


def test_every_food_points_at_a_real_plant():
    for f in foods.FOODS:
        assert f["plant_id"] is None or f["plant_id"] in PLANTS, f["id"]
        assert f["plant_id"] or f["note"], f["id"]
    for b in foods.bundle_list():
        ids = {f["id"] for f in foods.catalog(PLANTS)}
        assert set(b["foods"]) <= ids, b["id"]


def test_every_edible_plant_is_searchable():
    cat = {f["plant_id"] for f in foods.catalog(PLANTS)}
    for p in PLANTS.values():
        if p["category"] in foods.EDIBLE_CATEGORIES:
            assert p["id"] in cat


def test_soil_fit_flags_ph_and_clay():
    bed = {"length_ft": 8, "width_ft": 4, "kind": "in_ground"}
    soil = {"ph": 7.9, "clay": 48, "sand": 20, "om_pct": 1.2, "drainage": "Poorly drained"}
    carrot = foods.soil_fit(PLANTS["carrot"], soil, bed)
    assert carrot["fit"] == "poor" and any("clay" in i for i in carrot["issues"])
    blue = foods.soil_fit(PLANTS["blueberry"], {**soil, "clay": 20, "drainage": None}, bed)
    assert blue["fit"] == "poor" and "acidic mix" in " ".join(blue["fixes"])
    acid = foods.soil_fit(PLANTS["bush_bean"], {"ph": 5.2, "clay": 20, "sand": 40, "om_pct": 3},
                          bed)
    assert acid["fit"] == "fixable" and "lime" in acid["fixes"][0]


def _setup(c, beds=3, cycle=3):
    c.put("/api/settings", json={"cycle_years": cycle})
    for i in range(beds):
        r = c.post("/api/beds", json={"name": f"Bed {i + 1}", "length_ft": 8, "width_ft": 4})
        assert r.status_code == 200


def test_grow_pinto_beans_rotates_every_year(located):
    _setup(located)
    r = located.post("/api/foods/mine", json={"food_id": "pinto_beans", "amount_lb": 2})
    assert r.status_code == 200, r.text
    a = r.json()["assessment"]
    assert a["verdict"] in ("good", "fixable")
    years = {p["cycle_year"] for p in a["placements"]}
    beds = [p["bed_id"] for p in a["placements"]]
    assert years == {1, 2, 3}
    assert len(set(beds)) == 3  # legumes move to a new bed each year
    assert a["expected_yield"] == pytest.approx(2, rel=0.2)
    titles = [s["title"] for s in a["steps"]]
    assert "Pick the variety" in titles and "Harvest" in titles
    assert len(r.json()["planting_ids"]) == 3
    pl = located.get("/api/plantings").json()["plantings"]
    assert all(p["dtm_override"] for p in pl)  # variety-specific maturity


def test_unsuitable_foods_are_explained_not_planted(located):
    _setup(located, beds=1)
    for fid in ("avocados", "coffee"):
        a = located.post("/api/foods/mine", json={"food_id": fid}).json()
        assert a["verdict"] == "unsuitable" and a["planting_ids"] == []
        assert a["assessment"]["reasons"]
    assert located.get("/api/plantings").json()["plantings"] == []


def test_too_much_reports_partial(located):
    _setup(located, beds=2)
    a = located.post("/api/foods/mine", json={"food_id": "pinto_beans",
                                              "amount_lb": 20}).json()["assessment"]
    assert a["verdict"] == "partial"
    assert any("more sq ft" in r for r in a["reasons"])


def test_replan_and_remove(located):
    _setup(located)
    item = located.post("/api/foods/mine", json={"food_id": "carrots"}).json()
    n0 = len(located.get("/api/plantings").json()["plantings"])
    again = located.post(f"/api/foods/mine/{item['id']}/replan",
                         json={"food_id": "carrots", "amount_lb": 8}).json()
    assert len(located.get("/api/foods/mine").json()["foods"]) == 1
    assert len(located.get("/api/plantings").json()["plantings"]) == len(again["planting_ids"])
    assert n0 > 0
    located.delete(f"/api/foods/mine/{again['id']}")
    assert located.get("/api/plantings").json()["plantings"] == []


def test_bundle_and_cover_crops(located):
    _setup(located)
    r = located.post("/api/foods/bundle/salsa").json()
    assert len(r["foods"]) == 5
    added = located.post("/api/rotation/cover-crops").json()["added"]
    assert all(a["plant"] for a in added)
    # nothing in the rotation breaks a family return interval
    issues = located.get("/api/rotation").json()["issues"]
    assert not [i for i in issues if i["kind"] == "family"]
