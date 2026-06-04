from __future__ import annotations

from datetime import datetime

import ff_calendar
import forecast_dashboard


def test_normalize_ff_event_uses_forecast_and_timezones() -> None:
    event = ff_calendar.normalize_ff_event(
        {
            "title": "Non-Farm Employment Change",
            "country": "USD",
            "date": "2026-06-05T08:30:00-04:00",
            "impact": "High",
            "forecast": "85K",
            "previous": "115K",
        }
    )
    assert event.country == "USD"
    assert event.impact == "High"
    assert event.forecast == "85K"
    assert event.previous == "115K"
    assert event.time_et == "08:30"
    assert "non_farm_employment_change" in event.id


def test_filter_events_defaults_to_usd_medium_high() -> None:
    high = ff_calendar.CalendarEvent(
        id="1",
        title="NFP",
        country="USD",
        impact="High",
        date_iso=datetime.now().isoformat(),
        date_et="2026-06-05",
        time_et="08:30",
        date_santiago="2026-06-05",
        time_santiago="08:30",
        forecast="85K",
        previous="115K",
    )
    low = ff_calendar.CalendarEvent(
        id="2",
        title="Low Event",
        country="USD",
        impact="Low",
        date_iso=datetime.now().isoformat(),
        date_et="2026-06-05",
        time_et="09:00",
        date_santiago="2026-06-05",
        time_santiago="09:00",
        forecast="",
        previous="",
    )
    assert ff_calendar.filter_events([high, low]) == [high]


def test_event_status_waits_only_when_forecast_missing() -> None:
    assert forecast_dashboard._event_status("85K") == "listo"
    assert forecast_dashboard._event_status("") == "esperando_forecast"


def test_auth_cookie_validation_accepts_only_expected_token() -> None:
    password = "demo-secret"
    token = forecast_dashboard._auth_token(password)
    assert forecast_dashboard._cookie_is_valid(f"forecast_dashboard_auth={token}", password)
    assert not forecast_dashboard._cookie_is_valid("forecast_dashboard_auth=wrong", password)


def test_auth_cookie_validation_uses_default_demo_token() -> None:
    assert forecast_dashboard._configured_password_token() == forecast_dashboard.DEFAULT_DEMO_PASSWORD_TOKEN
    assert not forecast_dashboard._cookie_is_valid("")
