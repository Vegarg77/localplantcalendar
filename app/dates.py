"""Day-of-year helpers on a fixed 365-day calendar.

Climatology is indexed 0..364 (Feb 29 folded into Feb 28) so every year lines
up.  Indices >= 365 roll into the following year, which lets a planting sown
in the fall finish in the spring.
"""

from __future__ import annotations

import datetime as dt

_MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_CUM = [0]
for _d in _MONTH_DAYS:
    _CUM.append(_CUM[-1] + _d)

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def doy(d: dt.date) -> int:
    """0-based day index on a 365-day calendar."""
    day = min(d.day, 28) if d.month == 2 else d.day
    return _CUM[d.month - 1] + day - 1


def idx_to_month_day(idx: int) -> tuple[int, int]:
    idx %= 365
    for m in range(12):
        if idx < _CUM[m + 1]:
            return m + 1, idx - _CUM[m] + 1
    return 12, 31


def to_date(year: int, idx: int) -> dt.date:
    """Calendar date for day index ``idx`` counted from Jan 1 of ``year``."""
    year += idx // 365 if idx >= 0 else -((-idx + 364) // 365)
    m, d = idx_to_month_day(idx)
    return dt.date(year, m, d)


def label(idx: int) -> str:
    m, d = idx_to_month_day(idx)
    return f"{MONTH_ABBR[m - 1]} {d}"


def iso(d: dt.date | None) -> str | None:
    return d.isoformat() if d else None


def parse(s: str | None) -> dt.date | None:
    if not s:
        return None
    return dt.date.fromisoformat(s[:10])


def month_day_to_idx(s: str) -> int:
    """'05-12' or '2026-05-12' -> day index."""
    parts = s.split("-")
    m, d = int(parts[-2]), int(parts[-1])
    return _CUM[m - 1] + min(d, _MONTH_DAYS[m - 1]) - 1


def month_of_idx(idx: int) -> int:
    return idx_to_month_day(idx)[0]
