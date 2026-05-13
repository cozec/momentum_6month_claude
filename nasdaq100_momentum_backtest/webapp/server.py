"""FastAPI server exposing the latest momentum picks as JSON.

Every refresh hits ``/api/picks``, which re-runs the backtest pipeline
end-to-end using ``end_date = today``. On the first trading day of a
new month the prior open holding period naturally closes out — the
rebalance loop reads the fresh price data, the new month-end appears as
a completed exit, and the next entry becomes the new open position.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Make the parent ``nasdaq100_momentum_backtest`` package importable when
# the server is launched directly via ``uvicorn webapp.server:app``.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backtest import run_backtest
from src.config import BacktestConfig
from src.metrics import calculate_summary_stats


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="Nasdaq-100 Momentum Picks")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


def _safe_float(x: Any) -> Optional[float]:
    try:
        f = float(x)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


@app.get("/api/picks")
def api_picks(
    refresh: bool = Query(False, description="Re-download fresh prices"),
    history: int = Query(12, ge=1, le=120, description="Past months to return"),
) -> Dict[str, Any]:
    started = time.time()
    today = pd.Timestamp.now().normalize()

    config = BacktestConfig(
        start_date="2016-01-01",
        end_date=today.strftime("%Y-%m-%d"),
        force_refresh=refresh,
    )
    results = run_backtest(config)
    selections: pd.DataFrame = results["selections"]
    portfolio: pd.DataFrame = results["portfolio_returns"]
    open_pos: Optional[pd.DataFrame] = results.get("open_position")

    portfolio["rebalance_date"] = pd.to_datetime(portfolio["rebalance_date"])
    selections["rebalance_date"] = pd.to_datetime(selections["rebalance_date"])
    selections["exit_date"] = pd.to_datetime(selections["exit_date"])

    completed_dates = (
        portfolio["rebalance_date"].sort_values().tail(history).tolist()
    )
    recent_picks = selections[
        selections["rebalance_date"].isin(completed_dates)
    ].sort_values(["rebalance_date", "rank"])

    summary = calculate_summary_stats(portfolio)

    # Cumulative return for just the requested history window.
    recent_pr = portfolio[portfolio["rebalance_date"].isin(completed_dates)]
    window_cum_strategy = float(
        (1.0 + recent_pr["portfolio_return_net"]).prod() - 1.0
    )
    window_cum_qqq = float((1.0 + recent_pr["qqq_return"]).prod() - 1.0)

    completed_payload: List[Dict[str, Any]] = []
    for _, r in recent_picks.iterrows():
        completed_payload.append({
            "date": r["rebalance_date"].strftime("%Y-%m-%d"),
            "exit_date": r["exit_date"].strftime("%Y-%m-%d"),
            "ticker": r["ticker"],
            "rank": int(r["rank"]),
            "stock_return": _safe_float(r["stock_return"]),
            "momentum_score": _safe_float(r["momentum_score"]),
            "entry_price": _safe_float(r["entry_price"]),
            "exit_price": _safe_float(r["exit_price"]),
        })

    open_payload: List[Dict[str, Any]] = []
    open_meta: Dict[str, Any] = {}
    if open_pos is not None and not open_pos.empty:
        op = open_pos.copy()
        op["rebalance_date"] = pd.to_datetime(op["rebalance_date"])
        op["exit_date"] = pd.to_datetime(op["exit_date"])
        for _, r in op.sort_values("rank").iterrows():
            open_payload.append({
                "date": r["rebalance_date"].strftime("%Y-%m-%d"),
                "as_of": r["exit_date"].strftime("%Y-%m-%d"),
                "ticker": r["ticker"],
                "rank": int(r["rank"]),
                "stock_return": _safe_float(r["stock_return"]),
                "momentum_score": _safe_float(r["momentum_score"]),
                "entry_price": _safe_float(r["entry_price"]),
                "latest_price": _safe_float(r["exit_price"]),
            })
        open_meta = {
            "entry_date": pd.Timestamp(op["rebalance_date"].iloc[0]).strftime("%Y-%m-%d"),
            "as_of": pd.Timestamp(op["exit_date"].iloc[0]).strftime("%Y-%m-%d"),
            "mtd_portfolio_return": float(op["stock_return"].mean()),
        }

    def _row(stat: str, col: str) -> Optional[float]:
        try:
            return _safe_float(summary.loc[stat, col])
        except KeyError:
            return None

    payload = {
        "as_of": today.strftime("%Y-%m-%d"),
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "took_seconds": round(time.time() - started, 2),
        "completed": completed_payload,
        "open": open_payload,
        "open_meta": open_meta,
        "window": {
            "first_date": completed_dates[0].strftime("%Y-%m-%d") if completed_dates else None,
            "last_date": completed_dates[-1].strftime("%Y-%m-%d") if completed_dates else None,
            "months": len(completed_dates),
            "cum_strategy": window_cum_strategy,
            "cum_qqq": window_cum_qqq,
        },
        "stats": {
            "strategy": {
                "cagr": _row("CAGR", "strategy"),
                "sharpe": _row("sharpe_ratio", "strategy"),
                "max_drawdown": _row("max_drawdown", "strategy"),
                "total_return": _row("total_return", "strategy"),
                "win_rate_vs_qqq": _row("win_rate_vs_qqq", "strategy"),
            },
            "qqq": {
                "cagr": _row("CAGR", "benchmark_qqq"),
                "total_return": _row("total_return", "benchmark_qqq"),
                "max_drawdown": _row("max_drawdown", "benchmark_qqq"),
            },
            "tqqq": (
                {
                    "cagr": _row("CAGR", "benchmark_tqqq"),
                    "total_return": _row("total_return", "benchmark_tqqq"),
                    "max_drawdown": _row("max_drawdown", "benchmark_tqqq"),
                }
                if "benchmark_tqqq" in summary.columns
                else None
            ),
        },
    }
    return payload
