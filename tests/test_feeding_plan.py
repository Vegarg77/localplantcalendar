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
    st = plan["steps"][0]
    assert st["crop"].startswith("Tomato") and st["auto"]
    assert st["measure"].startswith("about ") and st["npk"] == "12-0-0"
    assert st["how"] and "heavy feeder" in st["why"]
    assert {s["stage"] for s in plan["steps"]} <= {"planting", "side_dress", "feeding"}
    assert [s["date"] for s in plan["steps"]] == sorted(s["date"] for s in plan["steps"])
    assert plan["products"] == [{"id": "blood_meal", "name": "Blood meal", "npk": "12-0-0"}]
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
    first = c.get("/api/feeding-plan", params={"year": 2026}).json()["steps"][0]
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
