"""Calendar/forecast selection dashboard for paper trading.

Run:
    python forecast_dashboard.py

Then open http://127.0.0.1:8090/

For hosted demos, set PORT and optionally HOST. If PORT is present and HOST is
not, the server binds to 0.0.0.0 so platforms like Render/Railway can route it.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import hmac
import html
import http.server
import json
import os
from pathlib import Path
import re
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
from research_state import RESEARCH_STATE, build_conditional_report_markdown, ensure_conditional_report


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_HOST = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PORT", "8090"))
AUTH_COOKIE_NAME = "forecast_dashboard_auth"
AUTH_COOKIE_MAX_AGE = 60 * 60 * 12
DEFAULT_DEMO_PASSWORD_TOKEN = "f586ca415f105ac81e6d84f2284cb48899192a7df29c0b939096666d220fe7ea"


class DashboardServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _event_status(forecast: str) -> str:
    return "listo" if forecast.strip() else "esperando_forecast"


def _event_runtime_status(forecast: str, actual: str) -> str:
    if not forecast.strip():
        return "esperando_forecast"
    if not actual.strip():
        return "esperando_actual"
    return "paper_signal"


def _parse_macro_value(value: str) -> float | None:
    text = value.strip().replace(",", "")
    if not text:
        return None
    multiplier = 1.0
    if text.endswith("%"):
        text = text[:-1]
    if text.upper().endswith("K"):
        multiplier = 1_000.0
        text = text[:-1]
    elif text.upper().endswith("M"):
        multiplier = 1_000_000.0
        text = text[:-1]
    elif text.upper().endswith("B"):
        multiplier = 1_000_000_000.0
        text = text[:-1]
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group(0)) * multiplier


def _event_surprise(title: str, actual: str, forecast: str) -> Dict[str, str]:
    actual_value = _parse_macro_value(actual)
    forecast_value = _parse_macro_value(forecast)
    if actual_value is None or forecast_value is None:
        return {
            "surprise": "",
            "signal": "sin_senal",
            "reason": "actual/forecast no numerico",
        }
    diff = actual_value - forecast_value
    lower_title = title.lower()
    inverse_growth = any(key in lower_title for key in ["unemployment", "jobless", "claims"])
    inflation_bad = any(key in lower_title for key in ["cpi", "inflation", "pce", "prices", "earnings"])
    growth_good = any(
        key in lower_title
        for key in ["non-farm", "employment", "pmi", "retail", "gdp", "durable", "manufacturing", "services"]
    )

    if abs(diff) < 1e-12:
        signal = "sin_senal"
        reason = "actual igual al forecast"
    elif inverse_growth:
        signal = "paper_long_es" if diff < 0 else "paper_short_es"
        reason = "menor desempleo/claims favorece riesgo; mayor dato lo presiona"
    elif inflation_bad:
        signal = "paper_short_es" if diff > 0 else "paper_long_es"
        reason = "inflacion/salarios sobre forecast endurece tasas; menor dato favorece riesgo"
    elif growth_good:
        signal = "paper_long_es" if diff > 0 else "paper_short_es"
        reason = "crecimiento/empleo sobre forecast favorece riesgo en modo paper"
    else:
        signal = "observacion"
        reason = "evento sin mapa direccional validado"

    return {
        "surprise": f"{diff:g}",
        "signal": signal,
        "reason": reason,
    }


def _signal_badge_class(signal: str) -> str:
    if "long" in signal:
        return "ready"
    if "short" in signal:
        return "danger"
    return "waiting"


def _source_status_class(status: str) -> str:
    if status == "ok":
        return "ready"
    if status in {"missing", "paid_needed"}:
        return "danger"
    return "waiting"


def _configured_password() -> str:
    return os.environ.get("DASHBOARD_PASSWORD", "").strip()


def _auth_token(password: str) -> str:
    payload = f"forecast-dashboard:{password}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _configured_password_token() -> str:
    password = _configured_password()
    if password:
        return _auth_token(password)
    return os.environ.get("DASHBOARD_PASSWORD_TOKEN", DEFAULT_DEMO_PASSWORD_TOKEN).strip()


def _parse_cookies(header: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


def _cookie_is_valid(cookie_header: str, password: str = "") -> bool:
    expected_token = _auth_token(password) if password else _configured_password_token()
    if not expected_token:
        return True
    cookies = _parse_cookies(cookie_header)
    token = cookies.get(AUTH_COOKIE_NAME, "")
    return hmac.compare_digest(token, expected_token)


def _render_login(message: str = "") -> str:
    message_html = f"<p class='message'>{html.escape(message)}</p>" if message else ""
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acceso Forecast Calendar</title>
  <style>
    :root {{ --bg:#101216; --panel:#1d222b; --line:#303846; --text:#f4f7fb; --muted:#9ba7b8; --blue:#1f6feb; --red:#ef4444; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    main {{ width:min(420px, calc(100vw - 32px)); background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:22px; box-sizing:border-box; }}
    h1 {{ margin:0 0 8px; font-size:22px; }}
    p {{ margin:0 0 18px; color:var(--muted); }}
    label {{ display:block; margin-bottom:8px; color:#bfdbfe; font-weight:700; }}
    input {{ width:100%; box-sizing:border-box; background:#111827; color:var(--text); border:1px solid var(--line); border-radius:6px; padding:11px; font-size:16px; }}
    button {{ width:100%; margin-top:14px; border:1px solid var(--blue); background:var(--blue); color:white; padding:11px 12px; border-radius:6px; cursor:pointer; font-weight:800; }}
    .message {{ color:#fecaca; background:#3b1117; border:1px solid var(--red); border-radius:6px; padding:10px; }}
  </style>
</head>
<body>
  <main>
    <h1>Acceso privado</h1>
    <p>Calendario protegido para paper trading.</p>
    {message_html}
    <form method="post" action="/login">
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" autofocus>
      <button type="submit">Entrar</button>
    </form>
  </main>
</body>
</html>
"""


def _checked(event: CalendarEvent, previous_selection: Dict[str, str]) -> bool:
    if event.id in previous_selection:
        return True
    return event.country == "USD" and event.impact == "High"


def _render_event_row(event: CalendarEvent, selected: Dict[str, Dict[str, str]]) -> str:
    previous = selected.get(event.id, {})
    forecast = previous.get("forecast") or event.forecast
    previous_value = previous.get("previous") or event.previous
    actual = previous.get("actual") or event.actual
    notes = previous.get("notes", "")
    checked = "checked" if _checked(event, previous) else ""
    status = _event_runtime_status(forecast, actual)
    paper = _event_surprise(event.title, actual, forecast) if actual else {"signal": "esperando_actual", "surprise": "", "reason": ""}
    status_class = "ready" if status == "paper_signal" else "waiting"
    signal_class = _signal_badge_class(paper["signal"])
    return f"""
    <tr>
      <td><input type="checkbox" name="select_{html.escape(event.id)}" {checked}></td>
      <td><strong>{html.escape(event.date_et)}</strong><br><span>{html.escape(event.time_et)} ET / {html.escape(event.time_santiago)} CL</span></td>
      <td><span class="pill {html.escape(event.impact.lower())}">{html.escape(event.impact)}</span></td>
      <td>{html.escape(event.country)}</td>
      <td><strong>{html.escape(event.title)}</strong><br><span>{html.escape(event.source)}</span></td>
      <td><input name="forecast_{html.escape(event.id)}" value="{html.escape(forecast)}" placeholder="forecast"></td>
      <td><input name="actual_{html.escape(event.id)}" value="{html.escape(actual)}" placeholder="actual"></td>
      <td><input name="previous_{html.escape(event.id)}" value="{html.escape(previous_value)}" placeholder="previous"></td>
      <td><span class="status {status_class}">{html.escape(status)}</span></td>
      <td><span title="{html.escape(paper['reason'])}" class="status {signal_class}">{html.escape(paper['signal'])}</span><br><span>{html.escape(paper['surprise'])}</span></td>
      <td><input name="notes_{html.escape(event.id)}" value="{html.escape(notes)}" placeholder="notas"></td>
    </tr>
    """


def _render_score_gauge(score: int, label: str) -> str:
    clamped = max(0, min(100, score))
    return f"""
    <section class="gauge-wrap" aria-label="Health Score">
      <div class="gauge">
        <div class="needle" style="transform:rotate({-90 + (clamped * 1.8):.1f}deg)"></div>
        <div class="gauge-center">
          <strong>{clamped}</strong>
          <span>{html.escape(label)}</span>
        </div>
      </div>
    </section>
    """


def _render_source_links(sources: List[Dict[str, str]]) -> str:
    links = []
    for source in sources:
        name = html.escape(source["name"])
        url = html.escape(source["url"], quote=True)
        links.append(f'<a href="{url}" target="_blank" rel="noreferrer">{name}</a>')
    return " ".join(links)


def _render_validation_sources() -> str:
    rows = "\n".join(
        f"""
        <tr>
          <td><strong>{html.escape(source['category'])}</strong><br><span>{_render_source_links(source['sources'])}</span></td>
          <td><span class="status {_source_status_class(source['status'])}">{html.escape(source['status'])}</span></td>
          <td>{html.escape(source['coverage'])}</td>
          <td>{html.escape(source['next_step'])}</td>
          <td><span class="status {'danger' if source['blocks_champion'] else 'ready'}">{'bloquea' if source['blocks_champion'] else 'ok'}</span></td>
        </tr>
        """
        for source in RESEARCH_STATE["validation_sources"]
    )
    return f"""
      <section class="panel research-panel">
        <h2>Fuentes de validacion del edge</h2>
        <p class="note">Esta matriz separa evidencia util de piezas faltantes. Si una fila bloquea, el sistema queda en paper/conditional aunque una estrategia se vea rentable.</p>
        <table class="source-table">
          <thead>
            <tr><th>Fuente</th><th>Estado</th><th>Que valida</th><th>Proximo paso</th><th>Champion</th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    """


def _render_edge_lab() -> str:
    rows = "\n".join(
        f"""
        <tr>
          <td><strong>{html.escape(edge['name'])}</strong><br><a href="{html.escape(edge['source_url'], quote=True)}" target="_blank" rel="noreferrer">{html.escape(edge['source_name'])}</a></td>
          <td><span class="status {_source_status_class('missing' if edge['status'] == 'hard_stop' else 'partial')}">{html.escape(edge['status'])}</span></td>
          <td>{html.escape(edge['evidence'])}</td>
          <td>{html.escape(edge['implementation'])}</td>
          <td><span class="status {'danger' if edge['promise_policy'] == 'never_promise' else 'waiting'}">{html.escape(edge['promise_policy'])}</span></td>
        </tr>
        """
        for edge in RESEARCH_STATE["edge_lab"]
    )
    return f"""
      <section class="panel research-panel">
        <h2>Edge Lab: de humano ganador a sistema medible</h2>
        <p class="note">Aqui estan los caminos que si tienen evidencia publica. Ninguno autoriza prometer ganancias; solo autoriza experimentos con gates duros.</p>
        <table class="edge-table">
          <thead>
            <tr><th>Candidato</th><th>Estado</th><th>Evidencia</th><th>Implementacion</th><th>Politica</th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    """


def _render_research_cockpit() -> str:
    state = RESEARCH_STATE
    penalties = "".join(f"<li>{html.escape(item)}</li>" for item in state["penalties"])
    required = "".join(f"<li>{html.escape(item)}</li>" for item in state["required_next_data"])
    strategy_rows = "\n".join(
        f"""
        <tr>
          <td><strong>{html.escape(strategy['name'])}</strong><br><span>{html.escape(strategy['rule'])}</span></td>
          <td><span class="status {'ready' if strategy['status'] == 'conditional_candidate' else 'danger'}">{html.escape(strategy['status'])}</span></td>
          <td>{strategy['trades']}</td>
          <td>{strategy['compound_return_pct']:.2f}%</td>
          <td>{strategy['sharpe']:.3f}</td>
          <td>{strategy['dsr']:.3f}</td>
          <td>{html.escape(strategy['rejection'])}</td>
        </tr>
        """
        for strategy in state["strategies"]
    )
    return f"""
    <section class="cockpit">
      <div class="cockpit-head">
        <div>
          <p class="eyebrow">Macro Announcement Trading System V4</p>
          <h1>Control room paper-only</h1>
          <p class="note">El sitio ahora refleja el veredicto cuantitativo: <strong>{html.escape(state['decision'])}</strong>. No hay champion aprobado ni live trading.</p>
        </div>
        {_render_score_gauge(int(state['health_score']), str(state['health_label']))}
      </div>
      <div class="metric-grid">
        <div class="metric"><span>Salida final</span><strong>{html.escape(state['final_output'])}</strong></div>
        <div class="metric"><span>Savor-Wilson Sharpe</span><strong>{state['savor_wilson']['ann_sharpe']:.3f}</strong></div>
        <div class="metric"><span>Walk-forward</span><strong>{state['walk_forward']['splits_accepted']}/{state['walk_forward']['splits_total']}</strong></div>
        <div class="metric"><span>IBKR Paper</span><strong>7497 only</strong></div>
      </div>
      <div class="warning-band">
        Paper trading solamente. Render no puede alcanzar IBKR Desktop local en 127.0.0.1:7497; live trading esta deshabilitado.
      </div>
      {_render_edge_lab()}
      {_render_validation_sources()}
      <section class="panel research-panel">
        <h2>Estrategias V4</h2>
        <table class="strategy-table">
          <thead>
            <tr><th>Estrategia</th><th>Estado</th><th>Trades</th><th>Retorno</th><th>Sharpe</th><th>DSR</th><th>Condicion/Rechazo</th></tr>
          </thead>
          <tbody>{strategy_rows}</tbody>
        </table>
      </section>
      <div class="two-col">
        <section class="panel compact">
          <h2>Penalizaciones activas</h2>
          <ul>{penalties}</ul>
        </section>
        <section class="panel compact">
          <h2>Datos necesarios</h2>
          <ul>{required}</ul>
        </section>
      </div>
      <div class="toolbar report-toolbar">
        <a class="button" href="/conditional_report.md">Ver conditional_report.md</a>
        <a class="button" href="/edge_lab.json">Ver edge_lab.json</a>
        <a class="button" href="/validation_sources.json">Ver validation_sources.json</a>
        <a class="button" href="/healthz">Health check</a>
      </div>
    </section>
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
    :root {{ --bg:#101216; --panel:#1d222b; --line:#303846; --text:#f4f7fb; --muted:#9ba7b8; --green:#22c55e; --amber:#f59e0b; --red:#ef4444; --blue:#1f6feb; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
    main {{ max-width:1280px; margin:0 auto; padding:22px; }}
    header {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:16px; }}
    h1 {{ margin:0; font-size:24px; }}
    h2 {{ margin:0 0 10px; font-size:18px; }}
    p {{ color:var(--muted); }}
    ul {{ margin:0; padding-left:20px; color:var(--muted); }}
    li {{ margin:6px 0; }}
    .toolbar {{ display:flex; gap:10px; flex-wrap:wrap; }}
    button, .button {{ border:1px solid var(--line); background:#243044; color:var(--text); padding:10px 12px; border-radius:6px; cursor:pointer; text-decoration:none; font-weight:700; }}
    button.primary {{ background:var(--blue); }}
    .cockpit {{ margin-bottom:24px; }}
    .cockpit-head {{ display:flex; align-items:center; justify-content:space-between; gap:18px; margin-bottom:14px; }}
    .eyebrow {{ margin:0 0 6px; color:#bfdbfe; font-weight:800; text-transform:uppercase; font-size:12px; letter-spacing:0; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:10px; margin:12px 0; }}
    .metric {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; }}
    .metric span {{ display:block; color:var(--muted); font-size:12px; margin-bottom:6px; }}
    .metric strong {{ font-size:18px; }}
    .warning-band {{ background:#3a2811; border:1px solid #a16207; color:#fde68a; border-radius:8px; padding:12px; margin:12px 0; font-weight:700; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:auto; margin-top:12px; }}
    .research-panel {{ padding:14px; }}
    .compact {{ padding:14px; min-height:160px; }}
    .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
    .report-toolbar {{ margin-top:12px; }}
    .gauge-wrap {{ width:170px; flex:0 0 170px; }}
    .gauge {{ position:relative; width:170px; height:96px; overflow:hidden; border-radius:170px 170px 0 0; background:conic-gradient(from 270deg at 50% 100%, #ef4444 0deg 60deg, #f59e0b 60deg 125deg, #22c55e 125deg 180deg); border:1px solid var(--line); }}
    .needle {{ position:absolute; bottom:0; left:50%; width:3px; height:78px; background:#f8fafc; transform-origin:bottom center; }}
    .gauge-center {{ position:absolute; bottom:-1px; left:50%; transform:translateX(-50%); width:94px; height:58px; border-radius:94px 94px 0 0; background:var(--bg); display:grid; place-items:center; align-content:center; border:1px solid var(--line); border-bottom:0; }}
    .gauge-center strong {{ font-size:24px; line-height:1; }}
    .gauge-center span {{ color:var(--muted); font-size:12px; }}
    table {{ width:100%; border-collapse:collapse; min-width:1260px; }}
    .strategy-table {{ min-width:1040px; }}
    .edge-table {{ min-width:1180px; }}
    .edge-table a {{ color:#93c5fd; display:inline-block; margin-top:2px; text-decoration:none; font-weight:700; }}
    .edge-table a:hover {{ text-decoration:underline; }}
    .source-table {{ min-width:1160px; }}
    .source-table a {{ color:#93c5fd; display:inline-block; margin:2px 8px 0 0; text-decoration:none; font-weight:700; }}
    .source-table a:hover {{ text-decoration:underline; }}
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
    .danger {{ background:var(--red); color:white; }}
    .message {{ padding:10px 12px; background:#13251b; border:1px solid #1f6b3a; border-radius:8px; color:#d1fae5; }}
    .note {{ color:var(--muted); font-size:12px; max-width:780px; }}
    @media (max-width: 860px) {{
      .cockpit-head, header {{ display:block; }}
      .gauge-wrap {{ margin-top:14px; }}
      .metric-grid, .two-col {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    {_render_research_cockpit()}
    <header>
      <div>
        <h1>Calendario ForexFactory y paper signals</h1>
        <p class="note">Auto-rellena forecast/previous desde el export JSON semanal. Si despues del release agregas actual, calcula una senal paper para forward-test. No envia ordenes reales.</p>
      </div>
      <div class="toolbar">
        <a class="button" href="/refresh">Refrescar FF</a>
        <a class="button" href="/logout">Salir</a>
        <button form="calendarForm" class="primary" type="submit">Guardar seleccion</button>
      </div>
    </header>
    {message_html}
    <form id="calendarForm" method="post" action="/save">
      <input type="hidden" name="events_json" value="{event_json}">
      <section class="panel">
        <table>
          <thead>
            <tr><th>Usar</th><th>Fecha</th><th>Impacto</th><th>Moneda</th><th>Evento</th><th>Forecast</th><th>Actual</th><th>Previous</th><th>Estado</th><th>Paper signal</th><th>Notas</th></tr>
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

    def _send_html(self, body: str, status: int = 200, extra_headers: Dict[str, str] | None = None) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _send_text(self, body: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location: str, extra_headers: Dict[str, str] | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()

    def _secure_cookie_suffix(self) -> str:
        proto = self.headers.get("X-Forwarded-Proto", "")
        return "; Secure" if proto == "https" else ""

    def _is_authenticated(self) -> bool:
        return _cookie_is_valid(self.headers.get("Cookie", ""))

    def _require_auth(self) -> bool:
        if self._is_authenticated():
            return True
        self._send_html(_render_login(), status=401)
        return False

    def _handle_login(self, form: Dict[str, List[str]]) -> None:
        expected_token = _configured_password_token()
        submitted = form.get("password", [""])[0]
        if expected_token and hmac.compare_digest(_auth_token(submitted), expected_token):
            cookie = (
                f"{AUTH_COOKIE_NAME}={expected_token}; Path=/; HttpOnly; "
                f"SameSite=Lax; Max-Age={AUTH_COOKIE_MAX_AGE}{self._secure_cookie_suffix()}"
            )
            self._redirect("/", {"Set-Cookie": cookie})
            return
        self._send_html(_render_login("Password incorrecto."), status=401)

    def do_GET(self) -> None:
        if self.path.startswith("/healthz"):
            self._send_html("ok")
            return
        if self.path.startswith("/login"):
            self._send_html(_render_login())
            return
        if self.path.startswith("/logout"):
            cookie = f"{AUTH_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{self._secure_cookie_suffix()}"
            self._redirect("/login", {"Set-Cookie": cookie})
            return
        if not self._require_auth():
            return
        if self.path.startswith("/conditional_report.md"):
            self._send_text(build_conditional_report_markdown(), content_type="text/markdown; charset=utf-8")
            return
        if self.path.startswith("/edge_lab.json"):
            body = json.dumps(RESEARCH_STATE["edge_lab"], ensure_ascii=False, indent=2)
            self._send_text(body, content_type="application/json; charset=utf-8")
            return
        if self.path.startswith("/validation_sources.json"):
            body = json.dumps(RESEARCH_STATE["validation_sources"], ensure_ascii=False, indent=2)
            self._send_text(body, content_type="application/json; charset=utf-8")
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
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        form = parse_qs(payload, keep_blank_values=True)
        if self.path == "/login":
            self._handle_login(form)
            return
        if not self._require_auth():
            return
        if self.path != "/save":
            self.send_error(404)
            return
        events_json = form.get("events_json", ["[]"])[0]
        events = json.loads(events_json)
        rows: List[Dict[str, str]] = []
        for event in events:
            event_id = str(event["id"])
            if f"select_{event_id}" not in form:
                continue
            forecast = form.get(f"forecast_{event_id}", [""])[0].strip()
            actual = form.get(f"actual_{event_id}", [""])[0].strip()
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
                    "actual": actual,
                    "previous": previous,
                    "source": "forexfactory_weekly_json_user_confirmed",
                    "status": _event_runtime_status(forecast, actual),
                    "notes": notes,
                }
            )
        write_manual_forecasts(rows)
        message = f"Guardados {len(rows)} eventos seleccionados en out/data/manual_forecasts.csv."
        self._send_html(render_dashboard(self.events, message=message))

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_server(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> int:
    ensure_conditional_report()
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
