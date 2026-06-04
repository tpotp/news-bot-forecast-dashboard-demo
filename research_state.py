"""Embedded V4 research state for the hosted paper-trading dashboard.

The hosted demo intentionally carries the conclusion, not only the calendar.
These numbers come from the local V4 run and should not be loosened to make a
"champion" appear. If better data arrives, rerun the research pipeline and
replace this state with the new verified output.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


RESEARCH_STATE: Dict[str, Any] = {
    "generated_at_utc": "2026-06-04T22:51:00Z",
    "mode": "paper_trading_only",
    "location": "Valparaiso, Chile",
    "health_score": 10,
    "health_label": "Critico",
    "final_output": "conditional_report.md",
    "decision": "Conditional, not champion",
    "can_trade_live": False,
    "ibkr": {
        "paper_port": 7497,
        "live_trading_enabled": False,
        "cloud_limitation": "Render cannot reach IBKR Desktop/TWS on your local 127.0.0.1:7497. IBKR Paper execution must run locally or on a server that runs IB Gateway.",
    },
    "acceptance_criteria": {
        "min_oos_trades": 30,
        "min_dsr": 0.95,
        "min_oos_sharpe": 0.5,
        "min_entry_seconds_after_release": 120,
    },
    "penalties": [
        "intraday_t120_data_missing",
        "calendar_not_verified",
        "walk_forward_splits_rejected",
        "fomc_t120_intraday_negative",
        "nfp_official_actual_surprise_t120_negative",
    ],
    "savor_wilson": {
        "announcement_days": 373,
        "ann_sharpe": 2.2355,
        "p_value": 0.06012227976749429,
        "passes_stat_gate": True,
    },
    "walk_forward": {
        "splits_total": 5,
        "splits_accepted": 2,
        "splits_failed": 3,
        "weighted_mean_return_pct": 0.1897,
    },
    "strategies": [
        {
            "name": "Pre-FOMC drift USA500",
            "status": "conditional_candidate",
            "rule": "Long USA500 from 14:00 ET on the prior business day to 13:55 ET on FOMC day; exits before the scheduled statement.",
            "trades": 94,
            "compound_return_pct": 14.6607,
            "mean_return_pct": 0.1475,
            "hit_rate_pct": 51.06,
            "sharpe": 0.6803,
            "dsr": 1.0,
            "accepted": False,
            "rejection": "OOS 2013-2018 Sharpe 0.295 < 0.5 and 1 missing intraday date.",
        },
        {
            "name": "FOMC T+120s post-release USA500",
            "status": "rejected",
            "rule": "Post-release entry at T+120s using USA500 intraday data.",
            "trades": 94,
            "compound_return_pct": -12.4021,
            "mean_return_pct": -0.1369,
            "hit_rate_pct": 48.94,
            "sharpe": -0.4395,
            "dsr": 0.0,
            "accepted": False,
            "rejection": "Negative 2013-2024 result after costs.",
        },
        {
            "name": "NFP T+120s official actual surprise proxy",
            "status": "rejected",
            "rule": "NFP monthly change z-score vs trailing 36 months; T+120s entry; exit 10:00 ET.",
            "trades": 77,
            "compound_return_pct": -4.1129,
            "mean_return_pct": -0.0539,
            "hit_rate_pct": 40.26,
            "sharpe": -0.5170,
            "dsr": 0.0,
            "accepted": False,
            "rejection": "Negative OOS behavior and historical calendar verification only 8.33%.",
        },
    ],
    "required_next_data": [
        "Verified 2000-2024 macro calendar: date,event,time_et,source,verified.",
        "Historical first-release actuals and forecast consensus, not revised current values.",
        "1-minute ES/SPY/USA500 data around NFP, CPI, and FOMC.",
        "Paper broker costs: spread, commission, observed slippage, and Valparaiso latency.",
    ],
}


def _strategy_lines() -> List[str]:
    lines: List[str] = []
    for strategy in RESEARCH_STATE["strategies"]:
        lines.extend(
            [
                f"## {strategy['name']}",
                "",
                f"- Status: `{strategy['status']}`",
                f"- Rule: `{strategy['rule']}`",
                f"- Trades: `{strategy['trades']}`",
                f"- Compound return: `{strategy['compound_return_pct']:.4f}%`",
                f"- Mean return per trade: `{strategy['mean_return_pct']:.4f}%`",
                f"- Hit rate: `{strategy['hit_rate_pct']:.2f}%`",
                f"- Sharpe: `{strategy['sharpe']:.4f}`",
                f"- DSR: `{strategy['dsr']:.4f}`",
                f"- Accepted final: `{strategy['accepted']}`",
                f"- Rejection/condition: `{strategy['rejection']}`",
                "",
            ]
        )
    return lines


def build_conditional_report_markdown() -> str:
    state = RESEARCH_STATE
    lines = [
        "# Conditional Report",
        "",
        "Conclusion: V4 is deployed as a paper-trading research cockpit, not a champion live system.",
        "The best candidate is Pre-FOMC drift, but it remains conditional because it fails a required OOS robustness gate.",
        "",
        "## Estado",
        "",
        f"- Health Score: `{state['health_score']}` ({state['health_label']})",
        f"- Final output: `{state['final_output']}`",
        f"- Mode: `{state['mode']}`",
        f"- Location assumption: `{state['location']}`",
        f"- Live trading enabled: `{state['can_trade_live']}`",
        f"- IBKR Paper default port: `{state['ibkr']['paper_port']}`",
        f"- Cloud limitation: `{state['ibkr']['cloud_limitation']}`",
        "",
        "## Gates",
        "",
        f"- Savor-Wilson ann Sharpe post-2013: `{state['savor_wilson']['ann_sharpe']}`",
        f"- Savor-Wilson p-value: `{state['savor_wilson']['p_value']}`",
        f"- Savor-Wilson passes gate: `{state['savor_wilson']['passes_stat_gate']}`",
        f"- Walk-forward splits accepted: `{state['walk_forward']['splits_accepted']}/{state['walk_forward']['splits_total']}`",
        f"- Walk-forward failed splits: `{state['walk_forward']['splits_failed']}`",
        "",
        "## Penalizaciones",
        "",
    ]
    lines.extend(f"- `{penalty}`" for penalty in state["penalties"])
    lines.extend([""])
    lines.extend(_strategy_lines())
    lines.extend(
        [
            "## Datos necesarios para continuar",
            "",
            *[f"- {item}" for item in state["required_next_data"]],
            "",
            "## Veredicto",
            "",
            "No queda verificado que el sistema genere ganancias reales. El sitio permite paper-forward testing y seguimiento honesto, pero no habilita dinero real.",
            f"",
            f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
            "",
        ]
    )
    return "\n".join(lines)


def ensure_conditional_report(path: Path | None = None) -> Path:
    target = path or Path(__file__).resolve().parent / "conditional_report.md"
    target.write_text(build_conditional_report_markdown(), encoding="utf-8")
    return target
