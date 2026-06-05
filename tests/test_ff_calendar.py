from __future__ import annotations

from datetime import datetime

import ff_calendar
import forecast_dashboard
import research_state


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
    assert forecast_dashboard._event_runtime_status("85K", "") == "esperando_actual"
    assert forecast_dashboard._event_runtime_status("85K", "100K") == "paper_signal"


def test_macro_value_parser_handles_units() -> None:
    assert forecast_dashboard._parse_macro_value("85K") == 85000
    assert forecast_dashboard._parse_macro_value("6.87M") == 6870000
    assert forecast_dashboard._parse_macro_value("4.3%") == 4.3


def test_paper_signal_direction_rules() -> None:
    nfp = forecast_dashboard._event_surprise("Non-Farm Employment Change", "120K", "85K")
    unemployment = forecast_dashboard._event_surprise("Unemployment Rate", "4.5%", "4.3%")
    cpi = forecast_dashboard._event_surprise("Core CPI m/m", "0.4%", "0.3%")
    assert nfp["signal"] == "paper_long_es"
    assert unemployment["signal"] == "paper_short_es"
    assert cpi["signal"] == "paper_short_es"


def test_auth_cookie_validation_accepts_only_expected_token() -> None:
    password = "demo-secret"
    token = forecast_dashboard._auth_token(password)
    assert forecast_dashboard._cookie_is_valid(f"forecast_dashboard_auth={token}", password)
    assert not forecast_dashboard._cookie_is_valid("forecast_dashboard_auth=wrong", password)


def test_auth_cookie_validation_uses_default_demo_token() -> None:
    assert forecast_dashboard._configured_password_token() == forecast_dashboard.DEFAULT_DEMO_PASSWORD_TOKEN
    assert not forecast_dashboard._cookie_is_valid("")


def test_validation_sources_make_missing_consensus_explicit() -> None:
    sources = research_state.RESEARCH_STATE["validation_sources"]
    consensus = next(source for source in sources if source["category"] == "Forecast consensus")
    assert consensus["status"] == "missing"
    assert consensus["blocks_champion"]


def test_conditional_report_lists_validation_sources() -> None:
    report = research_state.build_conditional_report_markdown()
    assert "## Fuentes de validacion" in report
    assert "BLS Public Data API" in report
    assert "Forecast consensus" in report
    assert "IBKR TWS API" in report


def test_dashboard_renders_validation_source_matrix() -> None:
    rendered = forecast_dashboard.render_dashboard([])
    assert "Fuentes de validacion del edge" in rendered
    assert "validation_sources.json" in rendered
    assert "Forecast consensus" in rendered
    assert "paid_needed" in rendered
