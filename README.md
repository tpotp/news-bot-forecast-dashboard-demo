# News Bot Forecast Dashboard

Demo web app for selecting macroeconomic calendar events for paper-trading
experiments. It fetches the weekly ForexFactory JSON export, filters USD
Medium/High events, auto-fills forecast/previous values when available, and
lets the user save a paper-trading watchlist.

This is not a real-money trading system. Keep it in paper/demo mode unless a
separate broker integration, risk review, and live-forward validation are added.

## Run locally

```powershell
pip install -r requirements.txt
python forecast_dashboard.py
```

Open:

```text
http://127.0.0.1:8090/
```

## Deploy

Render can use `render.yaml` directly:

```text
Build: pip install -r requirements.txt
Start: python forecast_dashboard.py
Health check: /healthz
```
