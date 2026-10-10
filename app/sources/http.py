"""Cached JSON fetching with stale-cache fallback.

All external data sources are free and keyless.  Responses are cached in
SQLite so the app keeps working (with slightly stale data) if a service is
briefly down or the internet connection drops.
"""

from __future__ import annotations

import json
import logging

import httpx

from .. import db

log = logging.getLogger("plantcal.http")

USER_AGENT = "localplantcalendar/1.0 (self-hosted garden planner)"


class SourceError(RuntimeError):
    pass


def _fetch(method: str, url: str, params: dict | None, body: dict | None, timeout: float):
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True) as client:
        r = client.request(method, url, params=params, json=body)
        r.raise_for_status()
        return r.json()


# Tests replace this to serve fixtures without network access.
FETCH = _fetch


def get_json(url: str, params: dict | None = None, *, ttl: float = 3600,
             method: str = "GET", body: dict | None = None, timeout: float = 45,
             cache_key: str | None = None):
    key = cache_key or f"{method} {url} {json.dumps(params, sort_keys=True)} " \
                       f"{json.dumps(body, sort_keys=True)}"
    cached = db.cache_get(key)
    if cached and cached[1] < ttl:
        return cached[0]
    try:
        data = FETCH(method, url, params, body, timeout)
    except Exception as exc:  # network error, HTTP error, bad JSON
        if cached:
            log.warning("using stale cache for %s: %s", url, exc)
            return cached[0]
        raise SourceError(f"{url}: {exc}") from exc
    db.cache_put(key, data)
    return data
