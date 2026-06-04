"""Calendar/forecast selection dashboard for paper trading.

Run:
    python forecast_dashboard.py

Then open http://127.0.0.1:8090/

For hosted demos, set PORT and optionally HOST. If PORT is present and HOST is
not, the server binds to 0.0.0.0 so platforms like Render/Railway can route it.
"""

from __future__ import annotations

from dataclasses import asdict
import html
import http.server
import json
import os
from pathlib import Path
import socketserver
from typing import Any, Dict, List
from urllib.parse import parse_qs

from ff_calendar import (
    DATA_DIR,
    CalendarEvent,
    fetch_forexfactory_weekly_events,
    filter_events,
    load_selected_forecasts,
    write_manual_forecasts,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PORT", "8090"))


class DashboardServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _event_status(forecast: str) -> str:
    return "listo" if forecast.strip() else "esperando_forecast"


def _checked(event: CalendarEvent, previous_selection: Dict[str, str]) -> bool:
    if event.id in previous_selection:
        return True
    return event.country == "USD" and event.impact == "High"


def _render_event_row(event: CalendarEvent, selected: Dict[str, Dict[str, str]]) -> str:
    previous = selected.get(event.id, {})
    forecast = previous.get("forecast") or event.forecast
    previous_value = previous.get("previous") or event.previous
    notes = previous.get("notes", "")
    checked = "checked" if _checked(event, previous) else ""
    status = _event_status(forecast)
    status_class = "ready" if status == "listo" else "waiting"
    return f"""
    <tr>
      <td><input type="checkbox" name="select_{html.escape(event.id)}" {checked}></td>
      <td><strong>{html.escape(event.date_et)}</strong><br><span>{html.escape(event.time_et)} ET / {html.escape(event.time_santiago)} CL</span></td>
      <td><span class="pill {html.escape(event.impact.lower())}">{html.escape(event.impact)}</span></td>
      <td>{html.escape(event.country)}</td>
      <td><strong>{html.escape(event.title)}</strong><br><span>{html.escape(event.source)}</span></td>
      <td><input name="forecast_{html.escape(event.id)}" value="{html.escape(forecast)}" placeholder="forecast"></td>
      <td><input name="previous_{html.escape(event.id)}" value="{html.escape(previous_value)}" placeholder="previous"></td>
      <td><span class="status {status_class}">{html.escape(status)}</span></td>
      <td><input name="notes_{html.escape(event.id)}" value="{html.escape(notes)}" placeholder="notas"></td>
    </tr>
    """


def render_dashboard(events: List[CalendarEvent], message: str = "") -> str:
    selected = load_selected_forecasts()
    filtered = filter_events(events, countries={"USD"}, impacts={"High", "Medium"})
    rows = "\n".join(_render_event_row(event, selected) for event in filtered)
    event_json = html.escape(json.dumps([asdict(event) for event in filtered], ensure_ascii=False))
    message_html = f"<p class='message'>{html.escape(message)}</p>" if message else ""
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Forecast Calendar</title>
  <style>
    :root {{ --bg:#101216; --panel:#1d222b; --line:#303846; --text:#f4f7fb; --muted:#9ba7b8; --green:#22c55e; --amber:#f59e0b; --red:#ef4444; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    main {{ max-width:1280px; margin:0 auto; padding:22px; }}
    header {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:16px; }}
    h1 {{ margin:0; font-size:24px; }}
    p {{ color:var(--muted); }}
    .toolbar {{ display:flex; gap:10px; flex-wrap:wrap; }}
    button, .button {{ border:1px solid var(--line); background:#243044; color:var(--text); padding:10px 12px; border-radius:6px; cursor:pointer; text-decoration:none; font-weight:700; }}
    button.primary {{ background:#1f6feb; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:auto; }}
    table {{ width:100%; border-collapse:collapse; min-width:1120px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; vertical-align:middle; font-size:13px; }}
    th {{ color:#bfdbfe; background:#161b24; position:sticky; top:0; }}
    td span {{ color:var(--muted); font-size:12px; }}
    input[type="text"], input:not([type]) {{ width:100%; box-sizing:border-box; background:#111827; color:var(--text); border:1px solid var(--line); border-radius:6px; padding:8px; }}
    input[type="checkbox"] {{ width:18px; height:18px; }}
    .pill {{ display:inline-block; padding:4px 7px; border-radius:999px; color:#111; font-weight:800; }}
    .pill.high {{ background:#f87171; }}
    .pill.medium {{ background:#fbbf24; }}
    .pill.low {{ background:#93c5fd; }}
    .status {{ display:inline-block; padding:5px 8px; border-radius:6px; font-weight:800; color:#111; }}
    .ready {{ background:var(--green); }}
    .waiting {{ background:var(--amber); }}
    .message {{ padding:10px 12px; background:#13251b; border:1px solid #1f6b3a; border-radius:8px; color:#d1fae5; }}
    .note {{ color:var(--muted); font-size:12px; max-width:780px; }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Calendario ForexFactory para paper trading</h1>
        <p class="note">Auto-rellena forecast y previous desde el export JSON semanal. Edita solo si falta o quieres sobrescribir. Guardar crea <code>out/data/manual_forecasts.csv</code>.</p>
      </div>
      <div class="toolbar">
        <a class="button" href="/refresh">Refrescar FF</a>
        <button form="calendarForm" class="primary" type="submit">Guardar seleccion</button>
      </div>
    </header>
    {message_html}
    <form id="calendarForm" method="post" action="/save">
      <input type="hidden" name="events_json" value="{event_json}">
      <section class="panel">
        <table>
          <thead>
            <tr><th>Usar</th><th>Fecha</th><th>Impacto</th><th>Moneda</th><th>Evento</th><th>Forecast</th><th>Previous</th><th>Estado</th><th>Notas</th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    </form>
  </main>
</body>
</html>
"""


class ForecastHandler(http.server.BaseHTTPRequestHandler):
    events: List[CalendarEvent] = []

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path.startswith("/healthz"):
            self._send_html("ok")
            return
        if self.path.startswith("/refresh") or not self.events:
            try:
                self.events = fetch_forexfactory_weekly_events()
                message = f"Calendario actualizado: {len(self.events)} eventos descargados."
            except Exception as exc:
                message = f"No se pudo actualizar ForexFactory: {exc}"
        else:
            message = ""
        self._send_html(render_dashboard(self.events, message=message))

    def do_POST(self) -> None:
        if self.path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        form = parse_qs(payload, keep_blank_values=True)
        events_json = form.get("events_json", ["[]"])[0]
        events = json.loads(events_json)
        rows: List[Dict[str, str]] = []
        for event in events:
            event_id = str(event["id"])
            if f"select_{event_id}" not in form:
                continue
            forecast = form.get(f"forecast_{event_id}", [""])[0].strip()
            previous = form.get(f"previous_{event_id}", [""])[0].strip()
            notes = form.get(f"notes_{event_id}", [""])[0].strip()
            rows.append(
                {
                    "id": event_id,
                    "date": str(event["date_et"]),
                    "event": str(event["title"]),
                    "country": str(event["country"]),
                    "impact": str(event["impact"]),
                    "time_et": str(event["time_et"]),
                    "time_santiago": str(event["time_santiago"]),
                    "forecast": forecast,
                    "previous": previous,
                    "source": "forexfactory_weekly_json_user_confirmed",
                    "status": _event_status(forecast),
                    "notes": notes,
                }
            )
        write_manual_forecasts(rows)
        message = f"Guardados {len(rows)} eventos seleccionados en out/data/manual_forecasts.csv."
        self._send_html(render_dashboard(self.events, message=message))

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> int:
    candidates = [port] if "PORT" in os.environ else range(port, port + 10)
    for candidate in candidates:
        try:
            handler = ForecastHandler
            handler.events = fetch_forexfactory_weekly_events()
            with DashboardServer((host, candidate), handler) as httpd:
                display_host = "127.0.0.1" if host in {"0.0.0.0", ""} else host
                print(f"Forecast dashboard: http://{display_host}:{candidate}/")
                httpd.serve_forever()
            return candidate
        except OSError:
            continue
    if "PORT" in os.environ:
        raise RuntimeError(f"Could not bind hosted port {port} on {host}")
    raise RuntimeError(f"No free port found from {port} to {port + 9}")


if __name__ == "__main__":
    run_server()
