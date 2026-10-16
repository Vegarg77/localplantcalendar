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
    located.put("/api/settings", json={"auto_size": False})
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


def _beds(c):
    return c.get("/api/beds").json()["beds"]


def test_no_beds_needed_garden_is_sized_for_you(located):
    r = located.post("/api/foods/mine", json={"food_id": "pinto_beans", "amount_lb": 2}).json()
    a = r["assessment"]
    assert a["verdict"] in ("good", "fixable") and r["planting_ids"]
    beds = _beds(located)
    assert beds and all(b["auto"] and b["kind"] == "raised" for b in beds)
    assert r["beds_added"] == len(beds)
    # legumes still rotate: a different bed every year of the cycle
    assert len({p["bed_id"] for p in a["placements"]}) == 3


def test_sizing_adds_to_your_beds_and_cleans_up(located):
    _setup(located, beds=2)
    item = located.post("/api/foods/mine", json={"food_id": "pinto_beans",
                                                 "amount_lb": 20}).json()
    assert item["assessment"]["verdict"] in ("good", "fixable")
    beds = _beds(located)
    assert [b["name"] for b in beds if not b["auto"]] == ["Bed 1", "Bed 2"]
    assert item["beds_added"] == len(beds) - 2 > 0
    assert len({b["name"] for b in beds}) == len(beds)
    # removing the food removes the beds the planner added, never yours
    located.delete(f"/api/foods/mine/{item['id']}")
    assert [b["name"] for b in _beds(located)] == ["Bed 1", "Bed 2"]


def test_bed_template_and_keeping_a_bed(located):
    located.put("/api/settings", json={"auto_bed": {"kind": "in_ground", "length_ft": 10,
                                                    "width_ft": 3}})
    item = located.post("/api/foods/mine", json={"food_id": "carrots"}).json()
    beds = _beds(located)
    assert beds and all(b["kind"] == "in_ground" and b["area_sqft"] == 30 for b in beds)
    kept = beds[0]
    located.put(f"/api/beds/{kept['id']}", json={"name": "Carrot patch", "length_ft": 10,
                                                "width_ft": 3, "kind": "in_ground"})
    located.delete(f"/api/foods/mine/{item['id']}")
    assert [b["name"] for b in _beds(located)] == ["Carrot patch"]


def test_turning_sizing_off_keeps_the_beds(located):
    located.post("/api/foods/mine", json={"food_id": "carrots"})
    n = len(_beds(located))
    located.put("/api/settings", json={"auto_size": False})
    assert len(_beds(located)) == n and not any(b["auto"] for b in _beds(located))
    a = located.post("/api/foods/mine", json={"food_id": "pinto_beans",
                                              "amount_lb": 40}).json()["assessment"]
    assert a["verdict"] == "partial" and len(_beds(located)) == n


def test_perennials_get_room_every_year(located):
    for f, amt in (("tomatoes", None), ("pinto_beans", 5), ("carrots", None),
                   ("potatoes", 30), ("strawberries", None)):
        located.post("/api/foods/mine", json={"food_id": f, "amount_lb": amt})
    issues = located.get("/api/rotation").json()["issues"]
    assert not [i for i in issues if i["kind"] in ("space", "family")], issues


def _in_ground(c, n=3):
    c.put("/api/settings", json={"cycle_years": n, "auto_size": False})
    return [c.post("/api/beds", json={"name": f"Plot {i + 1}", "kind": "in_ground",
                                      "soil": {"om_pct": 1.5}}).json()["id"]
            for i in range(n)]


def test_site_warns_about_soil_nitrogen_up_front(located):
    n = located.get("/api/site").json()["nitrogen"]
    assert n["supply_lb_acre"] > 0 and n["raised_supply_lb_acre"] > n["supply_lb_acre"]
    assert n["headline"] and "feedings" in n["plan"]


def test_planner_feeds_crops_the_soil_cannot(located):
    c = located
    _in_ground(c)
    r = c.post("/api/foods/mine", json={"food_id": "tomatoes", "amount_lb": 150}).json()
    ids = r["planting_ids"]
    feeds = [a for a in c.get("/api/amendments").json()["amendments"] if a["auto"] and a["planting_id"]]
    assert feeds and {a["planting_id"] for a in feeds} <= set(ids)
    assert any(s["title"] == "Feed" and "oz" in s["text"] for s in r["assessment"]["steps"])
    # with the feedings in place, the model no longer projects a real shortfall
    for bid in {a["bed_id"] for a in feeds}:
        n = c.get(f"/api/nitrogen/{bid}").json()
        assert all(x["deficit_lb_acre"] < 8 for x in n["crops"] if x["name"].startswith("Tomato"))
        assert n["recommendations"][0]["kind"] == "budget"
    cal = c.get("/api/calendar", params={"year": 2026}).json()["events"]
    assert any(e["type"] == "amend" and "Tomato" in e["title"] for e in cal)

    # your own amendment counts first, so the planned feeding shrinks
    bid, total = feeds[0]["bed_id"], sum(a["amount_lb"] for a in feeds
                                         if a["bed_id"] == feeds[0]["bed_id"])
    first = min((a for a in feeds if a["bed_id"] == bid), key=lambda a: a["doy"])
    c.post("/api/amendments", json={"bed_id": bid, "cycle_year": first["cycle_year"],
                                    "date": "04-20", "product": "blood_meal",
                                    "amount_lb": 0.3})
    after = sum(a["amount_lb"] for a in c.get("/api/amendments").json()["amendments"]
                if a["bed_id"] == bid and a["auto"] and a["planting_id"])
    assert after < total

    # off switch, and feedings leave with the food
    c.put("/api/settings", json={"auto_feed": False})
    assert not [a for a in c.get("/api/amendments").json()["amendments"] if a["auto"]]
    c.put("/api/settings", json={"auto_feed": True, "feed_product": "feather_meal"})
    feeds = [a for a in c.get("/api/amendments").json()["amendments"] if a["auto"] and a["planting_id"]]
    assert feeds and {a["product"] for a in feeds} == {"feather_meal"}
    fid = c.get("/api/foods/mine").json()["foods"][0]["id"]
    c.delete(f"/api/foods/mine/{fid}")
    assert not [a for a in c.get("/api/amendments").json()["amendments"] if a["auto"]]
    assert c.put("/api/settings", json={"feed_product": "compost"}).status_code == 400


def test_legumes_are_not_fed_nitrogen(located):
    _in_ground(located)
    located.post("/api/foods/mine", json={"food_id": "pinto_beans", "amount_lb": 2})
    assert not [a for a in located.get("/api/amendments").json()["amendments"] if a["auto"] and a["planting_id"]]


def test_products_list_matches_feeding_choices(client):
    from app import feeding
    prods = client.get("/api/products").json()
    assert {k for k, v in prods.items() if v["feed"]} == set(feeding.FEED_PRODUCTS)
