def test_needs_location_first(client):
    r = client.get("/api/site")
    assert r.status_code == 409 and r.json()["code"] == "no_location"
    # the library still works without a location
    plants = client.get("/api/plants").json()
    assert len(plants["plants"]) >= 140 and plants["located"] is False


def test_site_summary(located):
    site = located.get("/api/site").json()
    assert site["zone"]["zone"] == "6a"
    assert site["soil"]["source"].startswith("USDA")
    assert site["climate"]["last_spring_frost"]["0.5"]
    assert len(site["climate"]["monthly"]) == 12


def _bed(c, **kw):
    body = {"name": "Bed", "length_ft": 8, "width_ft": 4, **kw}
    r = c.post("/api/beds", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_full_rotation_flow(located):
    c = located
    a = _bed(c, name="A")
    b = _bed(c, name="B", kind="in_ground")
    assert a["soil_profile"]["om_pct"] == 8.0           # raised-bed mix default
    assert b["soil_profile"]["texture"] == "sandy clay loam"  # from SSURGO fixture

    for bed, year, pid in [(a, 1, "tomato"), (a, 2, "eggplant"), (a, 3, "bush_bean"),
                           (b, 1, "peas_shell"), (b, 1, "cereal_rye")]:
        r = c.post("/api/plantings", json={"bed_id": bed["id"], "plant_id": pid,
                                           "cycle_year": year})
        assert r.status_code == 200, r.text
    pl = c.get("/api/plantings").json()["plantings"]
    rye = next(p for p in pl if p["plant_id"] == "cereal_rye")
    assert rye["residue"] == "incorporate"

    rot = c.get("/api/rotation").json()
    texts = " ".join(i["text"] for i in rot["issues"])
    assert "Nightshades" in texts  # tomato -> eggplant in consecutive years
    assert len(rot["rows"]) == 2 and len(rot["rows"][0]["cells"]) == 3

    cal = c.get("/api/calendar", params={"year": 2026}).json()
    kinds = {e["type"] for e in cal["events"]}
    assert {"indoor", "plant", "harvest"} <= kinds

    fc = c.get("/api/forecast").json()
    assert len(fc["watering"]) == 2
    assert "plant_now" in fc and "alerts" in fc

    n = c.get(f"/api/nitrogen/{a['id']}").json()
    assert len(n["years"]) == 6 and n["series"]
    assert c.get("/api/nitrogen").json()["beds"]


def test_planting_validation(located):
    c = located
    bed = _bed(c)
    r = c.post("/api/plantings", json={"bed_id": bed["id"], "plant_id": "nope"})
    assert r.status_code == 400
    r = c.post("/api/plantings", json={"bed_id": bed["id"], "plant_id": "tomato",
                                       "cycle_year": 7})
    assert r.status_code == 400  # cycle is only 3 years
    r = c.post("/api/plantings", json={"bed_id": bed["id"], "plant_id": "tomato",
                                       "date": "06-01"})
    assert r.json()["doy"] == 151


def test_custom_variety(located):
    c = located
    r = c.post("/api/plants/custom", json={"name": "Glacier tomato", "base_id": "tomato",
                                           "overrides": {"dtm": [55, 60]}})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    d = c.get(f"/api/plants/{pid}").json()
    assert d["plant"]["dtm"] == [55, 60] and d["plant"]["family"] == "Solanaceae"
    assert c.post("/api/plants/custom", json={"name": "x", "base_id": "tomato",
                                              "overrides": {"evil": 1}}).status_code == 400
    assert c.delete(f"/api/plants/custom/{pid}").status_code == 200


def test_settings_validation(located):
    assert located.put("/api/settings", json={"lsf_override": "May 5"}).status_code == 400
    r = located.put("/api/settings", json={"lsf_override": "05-05", "frost_risk": 0.3})
    assert r.status_code == 200 and r.json()["frost_risk"] == 0.3


def test_stale_cache_survives_outage(located, monkeypatch):
    from app import services
    from app.sources import http
    located.get("/api/site")
    services.invalidate()

    def down(*a, **k):
        raise ConnectionError("offline")
    monkeypatch.setattr(http, "FETCH", down)
    # TTLs have not expired, so nothing is refetched; force expiry by clearing memory only
    assert located.get("/api/site").status_code == 200


def test_old_database_gets_the_auto_bed_column(tmp_path, monkeypatch):
    import sqlite3

    from app import db
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE beds (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                "length_ft REAL NOT NULL DEFAULT 8, width_ft REAL NOT NULL DEFAULT 4, "
                "kind TEXT NOT NULL DEFAULT 'raised', soil TEXT NOT NULL DEFAULT '{}', "
                "mulched INTEGER NOT NULL DEFAULT 0, initial_no3_ppm REAL NOT NULL DEFAULT 10, "
                "notes TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0)")
    old.execute("INSERT INTO beds(name) VALUES('Bed 1')")
    old.commit()
    old.close()
    monkeypatch.setenv("PLANTCAL_DB", str(path))
    db.reset()
    try:
        assert db.query("SELECT name, auto FROM beds") == [{"name": "Bed 1", "auto": 0}]
    finally:
        db.reset()
