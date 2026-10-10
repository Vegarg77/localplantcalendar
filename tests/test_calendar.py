import datetime as dt


def _plan(c):
    for i in range(3):
        c.post("/api/beds", json={"name": f"Bed {i + 1}", "length_ft": 8, "width_ft": 4})
    for f in ("tomato_sauce", "salad", "garlic_food"):
        assert c.post("/api/foods/mine", json={"food_id": f}).status_code == 200
    c.post("/api/amendments", json={"bed_id": 1, "cycle_year": 1, "date": "04-01",
                                    "product": "compost", "amount_lb": 40})


def test_month_events_cover_the_plan(located):
    _plan(located)
    r = located.get("/api/calendar/events", params={"start": "2026-03-01", "end": "2026-10-31",
                                                    "forecast": "false"})
    assert r.status_code == 200
    data = r.json()
    kinds = {e["kind"] for e in data["events"]}
    assert {"indoor", "care", "plant", "harvest", "soil", "frost"} <= kinds
    tomato = [e for e in data["events"] if "Tomato" in e["title"]]
    titles = " ".join(e["title"] for e in tomato)
    assert "indoors" in titles and "Transplant" in titles and "ready to harvest" in titles
    harvest = next(e for e in tomato if "ready to harvest" in e["title"])
    assert harvest["end"] > harvest["date"]          # harvest window spans days
    assert any(s["kind"] == "harvesting" for s in data["spans"])
    for e in data["events"]:
        assert "2026-03-01" <= e["end"] and e["date"] <= "2026-10-31"


def test_forecast_items_in_the_next_two_weeks(located):
    _plan(located)
    today = dt.date.today()
    r = located.get("/api/calendar/events", params={
        "start": today.isoformat(), "end": (today + dt.timedelta(days=20)).isoformat()}).json()
    assert len(r["weather"]) >= 14
    assert all("hi" in w and "lo" in w for w in r["weather"].values())


def test_bad_ranges_rejected(located):
    assert located.get("/api/calendar/events",
                       params={"start": "2026-05-01", "end": "2026-04-01"}).status_code == 400
    assert located.get("/api/calendar/events",
                       params={"start": "nope", "end": "2026-04-01"}).status_code == 400


def test_ics_feed_is_valid(located):
    _plan(located)
    r = located.get("/api/calendar.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    text = r.text
    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert text.count("BEGIN:VEVENT") == text.count("END:VEVENT") > 10
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    uids = [ln for ln in text.split("\r\n") if ln.startswith("UID:")]
    assert len(uids) == len(set(uids))
    only_harvest = located.get("/api/calendar.ics", params={"kinds": "harvest"}).text
    assert "CATEGORIES:Harvest" in only_harvest and "CATEGORIES:Start indoors" not in only_harvest


def test_recording_finish_keeps_planting_date(located):
    _plan(located)
    pid = located.get("/api/plantings").json()["plantings"][0]["id"]
    located.put(f"/api/plantings/{pid}/actual", json={"year": 2026, "established": "2026-05-25"})
    located.put(f"/api/plantings/{pid}/actual", json={"year": 2026, "finished": "2026-09-01"})
    from app import db
    row = db.query("SELECT * FROM actuals WHERE planting_id = ?", (pid,))[0]
    assert row["established"] == "2026-05-25" and row["finished"] == "2026-09-01"
