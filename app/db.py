"""SQLite persistence (single file, safe to back up by copying)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, fetched REAL NOT NULL);
CREATE TABLE IF NOT EXISTS beds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    length_ft REAL NOT NULL DEFAULT 8,
    width_ft REAL NOT NULL DEFAULT 4,
    kind TEXT NOT NULL DEFAULT 'raised',
    soil TEXT NOT NULL DEFAULT '{}',
    mulched INTEGER NOT NULL DEFAULT 0,
    initial_no3_ppm REAL NOT NULL DEFAULT 10,
    notes TEXT NOT NULL DEFAULT '',
    sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS plantings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bed_id INTEGER NOT NULL REFERENCES beds(id) ON DELETE CASCADE,
    plant_id TEXT NOT NULL,
    cycle_year INTEGER NOT NULL DEFAULT 1,
    doy INTEGER NOT NULL,
    method TEXT NOT NULL DEFAULT 'direct',
    area_sqft REAL NOT NULL DEFAULT 0,
    successions INTEGER NOT NULL DEFAULT 1,
    dtm_override INTEGER,
    residue TEXT NOT NULL DEFAULT 'remove',
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS actuals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    planting_id INTEGER NOT NULL REFERENCES plantings(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    established TEXT,
    finished TEXT,
    UNIQUE(planting_id, year)
);
CREATE TABLE IF NOT EXISTS amendments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bed_id INTEGER NOT NULL REFERENCES beds(id) ON DELETE CASCADE,
    cycle_year INTEGER NOT NULL DEFAULT 1,
    doy INTEGER NOT NULL,
    product TEXT NOT NULL,
    amount_lb REAL NOT NULL,
    n_pct REAL,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS waterings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bed_id INTEGER NOT NULL REFERENCES beds(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    inches REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS custom_plants (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    food_id TEXT NOT NULL,
    amount_lb REAL,
    verdict TEXT NOT NULL,
    assessment TEXT NOT NULL,
    planting_ids TEXT NOT NULL DEFAULT '[]',
    created TEXT NOT NULL
);
"""

_conn: sqlite3.Connection | None = None
_path: str | None = None


def db_path() -> str:
    default = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "plantcal.db")
    return os.environ.get("PLANTCAL_DB", default)


def _connection() -> sqlite3.Connection:
    global _conn, _path
    path = db_path()
    if _conn is None or _path != path:
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.executescript(SCHEMA)
        _path = path
    return _conn


def reset() -> None:
    """Drop the cached connection (tests point PLANTCAL_DB elsewhere)."""
    global _conn, _path
    if _conn is not None:
        _conn.close()
    _conn, _path = None, None


@contextmanager
def tx():
    with _lock:
        conn = _connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query(sql: str, args: tuple = ()) -> list[dict]:
    with tx() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def execute(sql: str, args: tuple = ()) -> int:
    with tx() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


# --------------------------------------------------------------- settings
DEFAULT_SETTINGS = {
    "location": None,          # {name, lat, lon, zip, state, timezone, elevation}
    "frost_risk": 0.1,         # acceptable chance of a damaging frost
    "cycle_years": 3,          # length of the rotation cycle
    "start_year": None,        # calendar year that is "cycle year 1"
    "lsf_override": None,      # "MM-DD" local knowledge beats reanalysis
    "fff_override": None,
}


def get_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    for row in query("SELECT key, value FROM settings"):
        out[row["key"]] = json.loads(row["value"])
    if not out["start_year"]:
        out["start_year"] = time.localtime().tm_year
    return out


def put_settings(values: dict) -> dict:
    with tx() as c:
        for k, v in values.items():
            if k in DEFAULT_SETTINGS:
                c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                          (k, json.dumps(v)))
    return get_settings()


# ------------------------------------------------------------------ cache
def cache_get(key: str) -> tuple[object, float] | None:
    rows = query("SELECT value, fetched FROM cache WHERE key = ?", (key,))
    if not rows:
        return None
    return json.loads(rows[0]["value"]), time.time() - rows[0]["fetched"]


def cache_put(key: str, value: object) -> None:
    execute("INSERT INTO cache(key, value, fetched) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, fetched = excluded.fetched",
            (key, json.dumps(value), time.time()))


def cache_clear(prefix: str = "") -> None:
    execute("DELETE FROM cache WHERE key LIKE ?", (prefix + "%",))
