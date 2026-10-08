import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import db, services  # noqa: E402
from app.sources import http  # noqa: E402
from tests import fixtures  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    monkeypatch.setenv("PLANTCAL_DB", str(tmp_path / "test.db"))
    db.reset()
    services.invalidate()
    monkeypatch.setattr(http, "FETCH", fixtures.fake_fetch("denver"))
    with TestClient(app) as c:
        yield c
    db.reset()
    services.invalidate()


@pytest.fixture
def located(client):
    loc = client.get("/api/geocode", params={"q": "80202"}).json()[0]
    r = client.put("/api/settings", json={"location": loc, "cycle_years": 3,
                                           "start_year": 2026})
    assert r.status_code == 200
    return client
