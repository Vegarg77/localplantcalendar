"""Day-by-day garden calendar: every dated thing the plan implies, plus the
forecast-driven items (weather, alerts, watering) for the next two weeks.

Used by the month/agenda views and the subscribable iCalendar feed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging

from . import dates, nitrogen, services as svc
from .garden import cycle_index
from .sources.http import SourceError

log = logging.getLogger("plantcal.calendar")

# Event kinds -> how the UI groups and colours them.
KINDS = {
    "indoor": "Start indoors",
    "plant": "Sow & transplant",
    "harvest": "Harvest",
    "soil": "Soil & cover crops",
    "care": "Care",
    "water": "Watering",
    "frost": "Frost dates",
    "alert": "Weather alerts",
}


def _iso(d: dt.date) -> str:
    return d.isoformat()


def _uid(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:16]


def _verb(i) -> str:
    if i.plant.get("special"):
        return "Plant"
    return {"transplant": "Transplant", "direct": "Sow"}.get(i.method, "Plant")


def build(start: dt.date, end: dt.date, include_forecast: bool = True) -> dict:
    s = svc.settings()
    beds = {b["id"]: b for b in svc.beds()}
    events: list[dict] = []
    spans: list[dict] = []

    def add(kind, date, title, *, end=None, bed_id=None, detail=None, plant_id=None,
            planting_id=None, severity=None, key=None):
        e_end = end or date
        if e_end < start or date > end_:
            return
        events.append({
            "id": _uid(kind, key or title, date, bed_id),
            "kind": kind, "date": _iso(date), "end": _iso(e_end), "title": title,
            "bed_id": bed_id, "bed": beds.get(bed_id, {}).get("name") if bed_id else None,
            "detail": detail, "plant_id": plant_id, "planting_id": planting_id,
            "severity": severity,
        })

    end_ = end
    seen = set()
    for year in range(start.year - 1, end.year + 1):
        for i in svc.year_instances(year):
            key = (i.planting["id"], i.year, i.succession)
            if key in seen:
                continue
            seen.add(key)
            p, bid = i.plant, i.planting["bed_id"]
            name = p["name"]
            common = dict(bed_id=bid, plant_id=p["id"], planting_id=i.planting["id"])
            tag = f"{i.planting['id']}-{i.year}-{i.succession}"
            succ = f" (sowing {i.succession + 1})" if i.succession else ""
            if i.indoor_start:
                add("indoor", i.indoor_start[0], f"Start {name} indoors{succ}",
                    end=i.indoor_start[1], key=f"in-{tag}",
                    detail=f"Sow seeds under lights any day from {i.indoor_start[0]:%b %d} to "
                           f"{i.indoor_start[1]:%b %d}. Germinates at {p['germ_min']}°F+.",
                    **common)
            if i.harden_off and i.establish:
                add("care", i.harden_off, f"Harden off {name}", key=f"ho-{tag}",
                    end=i.establish - dt.timedelta(days=1),
                    detail="Set seedlings outside a few hours a day, building to full sun "
                           "and overnight over 7–10 days.", **common)
            if i.establish:
                add("plant", i.establish, f"{_verb(i)} {name}{succ}", key=f"pl-{tag}",
                    detail=f"{i.area:.0f} sq ft · {p['spacing']}\" spacing"
                           + (f" · {i.planting['notes']}" if i.planting.get("notes") else "")
                           + ("" if i.ok else " · outside its usual window — see Rotation"),
                    **common)
            if p["category"] == "cover":
                add("soil", i.harvest_end,
                    f"{name} winter-kills" if i.kind == "winterkill" else f"Cut down {name}",
                    key=f"term-{tag}",
                    detail="Cut at the soil line at early bloom; leave as mulch or turn in, "
                           "and wait 2–3 weeks before sowing small seeds."
                    if i.kind != "winterkill" else "Leave the dead residue as mulch.",
                    **common)
            elif i.harvest_this_year:
                add("harvest", i.maturity, f"{name} ready to harvest", key=f"hv-{tag}",
                    end=i.harvest_end,
                    detail=f"Harvest window {i.maturity:%b %d} – {i.harvest_end:%b %d}.",
                    **common)
                if (i.harvest_end - i.maturity).days >= 7:
                    add("harvest", i.harvest_end, f"Last {name} harvest", key=f"he-{tag}",
                        detail="Pull or cut back spent plants to free the bed.", **common)
                spans.append({"kind": "harvesting", "start": _iso(i.maturity),
                              "end": _iso(i.harvest_end), "name": name, "bed_id": bid,
                              "bed": beds.get(bid, {}).get("name")})
            if i.start <= end and i.end >= start:
                spans.append({"kind": "growing", "start": _iso(i.start), "end": _iso(i.end),
                              "name": name, "bed_id": bid,
                              "bed": beds.get(bid, {}).get("name")})

    # amendments repeat each cycle
    amends = svc.amendments()
    for year in range(start.year, end.year + 1):
        cyc = cycle_index(year, s)
        for a in amends:
            if a["cycle_year"] == cyc:
                prod = nitrogen.PRODUCTS.get(a["product"], (a["product"],))[0]
                add("soil", dates.to_date(year, a["doy"]), f"Apply {a['amount_lb']:g} lb {prod}",
                    bed_id=a["bed_id"], key=f"am-{a['id']}-{year}",
                    detail=a.get("notes") or "Work it into the top few inches and water in.")

    # frost dates from the 30-year record
    fd = svc.climate().frost_dates(32)
    for year in range(start.year, end.year + 1):
        sp, fa = fd["spring"], fd["fall"]
        if sp["0.5"] is not None:
            add("frost", dates.to_date(year, sp["0.5"]), "Average last spring frost",
                key=f"lsf50-{year}", detail="Half of springs have a later frost.")
        if sp["0.1"] is not None:
            add("frost", dates.to_date(year, sp["0.1"]), "Frost risk under 10%",
                key=f"lsf10-{year}",
                detail="Only 1 spring in 10 freezes after this — safe for tomatoes, peppers "
                       "and squash.")
        if fa["0.1"] is not None:
            add("frost", dates.to_date(year, fa["0.1"]), "Early fall frost possible",
                key=f"fff10-{year}", detail="1 fall in 10 freezes by now — have covers ready.")
        if fa["0.5"] is not None:
            add("frost", dates.to_date(year, fa["0.5"]), "Average first fall frost",
                key=f"fff50-{year}", detail="Harvest tender crops before this.")

    weather: dict[str, dict] = {}
    today = dt.date.today()
    if include_forecast and start <= today + dt.timedelta(days=16) and end >= today:
        try:
            ctx = svc.forecast_context(today)
        except SourceError as exc:
            log.warning("calendar without forecast: %s", exc)
            ctx = None
        if ctx:
            for d in ctx["forecast"]["days"]:
                if d["date"] >= _iso(today) and d["tmax_f"] is not None:
                    weather[d["date"]] = {
                        "hi": round(d["tmax_f"]), "lo": round(d["tmin_f"]),
                        "rain": round(d["precip_in"], 2), "rain_prob": d.get("precip_prob"),
                        "frost": d["tmin_f"] <= 32, "soil": round(d["soil_f"])
                        if d.get("soil_f") is not None else None}
            for a in ctx["advice"]["alerts"]:
                add("alert", dt.date.fromisoformat(a["date"]), a["title"], key=f"al-{a['title']}",
                    detail=a["text"], severity=a["severity"])
            for t in ctx["advice"]["tasks"]:
                if t["kind"] == "plant" and t.get("verdict") == "wait":
                    add("alert", dt.date.fromisoformat(t["date"]), t["title"],
                        key=f"wait-{t['title']}", detail=t["text"], severity="warn",
                        planting_id=t.get("planting_id"))
            for w in ctx["watering"]:
                for p in w["plan"]:
                    add("water", dt.date.fromisoformat(p["date"]), f"Water {w['bed']}",
                        bed_id=w["bed_id"], key=f"w-{w['bed_id']}",
                        detail=f"{p['inches']:.2f}\" ≈ {p['gallons']:.0f} gal for "
                               f"{', '.join(p['crops'])}.")

    # successions can produce identical same-day items: merge them with a count
    merged: dict[tuple, dict] = {}
    for e in events:
        k = (e["kind"], e["date"], e["title"], e["bed_id"])
        if k in merged:
            merged[k]["count"] += 1
            merged[k]["end"] = max(merged[k]["end"], e["end"])
        else:
            merged[k] = {**e, "count": 1}
    events = list(merged.values())
    for e in events:
        if e["count"] > 1:
            e["title"] += f" (×{e['count']})"
    order = {k: n for n, k in enumerate(KINDS)}
    events.sort(key=lambda e: (e["date"], order[e["kind"]], e["title"]))
    spans = [x for x in spans if x["start"] <= _iso(end) and x["end"] >= _iso(start)]
    return {"start": _iso(start), "end": _iso(end), "today": _iso(today),
            "cycle_years": s["cycle_years"], "kinds": KINDS, "events": events,
            "spans": spans, "weather": weather,
            "beds": [{"id": b["id"], "name": b["name"]} for b in beds.values()]}


# ------------------------------------------------------------------ iCal
def _esc(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def _fold(line: str) -> str:
    out, cur = [], line.encode("utf-8")
    while len(cur) > 75:
        cut = 75
        while (cur[cut] & 0xC0) == 0x80:  # don't split a UTF-8 sequence
            cut -= 1
        out.append(cur[:cut].decode())
        cur = b" " + cur[cut:]
    out.append(cur.decode())
    return "\r\n".join(out)


def ics(kinds: set[str] | None = None, bed_id: int | None = None) -> str:
    """All-day events for this year and next; harvest windows span their days."""
    today = dt.date.today()
    data = build(dt.date(today.year, 1, 1), dt.date(today.year + 1, 12, 31),
                 include_forecast=False)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//localplantcalendar//garden//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Garden",
             "X-PUBLISHED-TTL:PT12H", "REFRESH-INTERVAL;VALUE=DURATION:PT12H"]
    for e in data["events"]:
        if kinds and e["kind"] not in kinds:
            continue
        if bed_id and e["bed_id"] not in (None, bed_id):
            continue
        d0 = dt.date.fromisoformat(e["date"])
        # spans only for harvest windows; start-indoors etc. stay one-day reminders
        d1 = dt.date.fromisoformat(e["end"]) if e["kind"] == "harvest" else d0
        summary = e["title"] + (f" — {e['bed']}" if e["bed"] else "")
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@localplantcalendar", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{d0:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{d1 + dt.timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_esc(summary)}", f"CATEGORIES:{_esc(KINDS[e['kind']])}",
                  "TRANSP:TRANSPARENT"]
        if e.get("detail"):
            lines.append(f"DESCRIPTION:{_esc(e['detail'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"
