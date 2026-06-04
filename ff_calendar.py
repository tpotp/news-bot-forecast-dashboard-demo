"""ForexFactory weekly calendar connector.

Uses the public weekly JSON export linked from the ForexFactory calendar page.
This is intentionally for paper/research workflow only; values should be
confirmed by the user before trading decisions are made.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests


PROJECT_ROOT = Path(__file__).resolve().parent
OUT_DIR = PROJECT_ROOT / "out"
DATA_DIR = OUT_DIR / "data"
FF_THIS_WEEK_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
NY_TZ = ZoneInfo("America/New_York")
SANTIAGO_TZ = ZoneInfo("America/Santiago")


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    country: str
    impact: str
    date_iso: str
    date_et: str
    time_et: str
    date_santiago: str
    time_santiago: str
    forecast: str
    previous: str
    source: str = "forexfactory_weekly_json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def parse_ff_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(NY_TZ)


def normalize_event_id(title: str, country: str, dt: datetime) -> str:
    safe_title = "".join(ch.lower() if ch.isalnum() else "_" for ch in title).strip("_")
    while "__" in safe_title:
        safe_title = safe_title.replace("__", "_")
    return f"{dt.strftime('%Y%m%d_%H%M')}_{country.lower()}_{safe_title}"


def normalize_ff_event(raw: Dict[str, Any]) -> CalendarEvent:
    dt_et = parse_ff_datetime(str(raw["date"]))
    dt_santiago = dt_et.astimezone(SANTIAGO_TZ)
    title = str(raw.get("title", "")).strip()
    country = str(raw.get("country", "")).strip()
    return CalendarEvent(
        id=normalize_event_id(title, country, dt_et),
        title=title,
        country=country,
        impact=str(raw.get("impact", "")).strip(),
        date_iso=dt_et.isoformat(),
        date_et=dt_et.date().isoformat(),
        time_et=dt_et.strftime("%H:%M"),
        date_santiago=dt_santiago.date().isoformat(),
        time_santiago=dt_santiago.strftime("%H:%M"),
        forecast=str(raw.get("forecast", "")).strip(),
        previous=str(raw.get("previous", "")).strip(),
    )


def fetch_forexfactory_weekly_events(url: str = FF_THIS_WEEK_JSON_URL) -> List[CalendarEvent]:
    ensure_dirs()
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("ForexFactory weekly export did not return a list")
    raw_path = DATA_DIR / "forexfactory_thisweek_raw.json"
    raw_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    events = [normalize_ff_event(item) for item in payload]
    write_events_csv(events, DATA_DIR / "forexfactory_thisweek.csv")
    return events


def filter_events(
    events: Iterable[CalendarEvent],
    countries: Optional[set[str]] = None,
    impacts: Optional[set[str]] = None,
) -> List[CalendarEvent]:
    country_filter = countries or {"USD"}
    impact_filter = impacts or {"High", "Medium"}
    return [
        event
        for event in events
        if event.country in country_filter and event.impact in impact_filter
    ]


def write_events_csv(events: Iterable[CalendarEvent], path: Path) -> None:
    rows = [asdict(event) for event in events]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_selected_forecasts(path: Path | None = None) -> Dict[str, Dict[str, str]]:
    target = path or DATA_DIR / "manual_forecasts.csv"
    if not target.exists():
        return {}
    with target.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {row.get("id", ""): row for row in rows if row.get("id")}


def write_manual_forecasts(rows: List[Dict[str, str]], path: Path | None = None) -> None:
    target = path or DATA_DIR / "manual_forecasts.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id",
        "date",
        "event",
        "country",
        "impact",
        "time_et",
        "time_santiago",
        "forecast",
        "previous",
        "source",
        "status",
        "notes",
    ]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (DATA_DIR / "selected_ff_events.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

