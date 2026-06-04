# Deploy online demo

This project is currently safest as a paper-trading demo. Do not expose real
broker credentials or real-money order routes in a public deployment.

## What works online

- `forecast_dashboard.py` serves the ForexFactory weekly calendar selector.
- Forecast and previous values are auto-filled when ForexFactory provides them.
- Selected rows are saved to `out/data/manual_forecasts.csv` on the server.
- `dashboard.html`, `conditional_report.md`, and JSON result files can be shown
  as static research outputs.

## Important limitation

Free hosting file systems are usually ephemeral. On services like Render free,
saved selections can disappear after a restart/redeploy. For a real shared demo,
move saved selections to Postgres, SQLite on persistent disk, or object storage.

## Render quick deploy

1. Push this folder to a GitHub repository.
2. In Render, create a new Web Service from the repository.
3. Render can read `render.yaml`, or use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python forecast_dashboard.py`
4. Open the public Render URL and share it with your friend.

## Railway quick deploy

1. Push this folder to GitHub.
2. Create a Railway project from the repository.
3. Railway can use the `Procfile` command:
   - `web: python forecast_dashboard.py`
4. Open the generated Railway domain.

## Local check

```powershell
venv\Scripts\python.exe forecast_dashboard.py
```

Then open:

```text
http://127.0.0.1:8090/
```
