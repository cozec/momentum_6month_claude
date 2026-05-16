"""FastAPI server exposing the latest momentum picks as JSON.

Every refresh hits ``/api/picks`` (or ``/api/picks-multi`` for multiple
strategies in one request). On the first trading day of a new month
the prior open holding period naturally closes out — the rebalance
loop reads the fresh price data, the new month-end appears as a
completed exit, and the next entry becomes the new open position.

Caching
-------
A small in-memory cache short-circuits repeated requests within
``CACHE_TTL_SECONDS`` for the same (lookback, period, today) tuple.
Forcing ``refresh=true`` bypasses the cache so the next call gets
fresh yfinance data. The cache lives in this process — when Render's
Free-plan worker sleeps and wakes, it starts cold again. That's
fine: cold-start cost is dominated by yfinance, and the project
ships a seed price cache (``data/raw_prices/*.csv``) so the worker
boots with prices already on disk.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.backtest import run_backtest
from src.config import BacktestConfig
from src.metrics import calculate_summary_stats


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
# How long to reuse a previously-computed payload for the same
# (lookback, period, today) tuple. 5 min keeps refreshes responsive
# without showing stale prices for long.
CACHE_TTL_SECONDS = 300

app = FastAPI(title="Nasdaq-100 Momentum Picks")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# (lookback, period, as_of_date) -> (computed_at_ts, payload)
_RESULT_CACHE: Dict[Tuple[int, int, str], Tuple[float, Dict[str, Any]]] = {}
_CACHE_LOCK = Lock()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health() -> Dict[str, str]:
    """Cheap liveness probe — no backtest run, returns instantly."""
    return {"status": "ok"}


def _safe_float(x: Any) -> Optional[float]:
    try:
        f = float(x)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def _compute_payload(
    lookback: int,
    period: int,
    history: int,
    refresh: bool,
    today: pd.Timestamp,
) -> Dict[str, Any]:
    """Run the backtest pipeline for one (lookback, period) and return
    the JSON payload. Heavy: ~0.5–2 s on a warm Render worker."""
    started = time.time()
    config = BacktestConfig(
        start_date="2016-01-01",
        end_date=today.strftime("%Y-%m-%d"),
        force_refresh=refresh,
        lookback_months=lookback,
        rebalance_period_months=period,
    )
    results = run_backtest(config)
    selections: pd.DataFrame = results["selections"]
    portfolio: pd.DataFrame = results["portfolio_returns"]
    open_pos: Optional[pd.DataFrame] = results.get("open_position")
    next_pos: Optional[pd.DataFrame] = results.get("next_position")

    portfolio["rebalance_date"] = pd.to_datetime(portfolio["rebalance_date"])
    selections["rebalance_date"] = pd.to_datetime(selections["rebalance_date"])
    selections["exit_date"] = pd.to_datetime(selections["exit_date"])

    completed_dates = (
        portfolio["rebalance_date"].sort_values().tail(history).tolist()
    )
    recent_picks = selections[
        selections["rebalance_date"].isin(completed_dates)
    ].sort_values(["rebalance_date", "rank"])

    summary = calculate_summary_stats(
        portfolio,
        periods_per_year=12.0 / max(1, period),
    )

    recent_pr = portfolio[portfolio["rebalance_date"].isin(completed_dates)]
    window_cum_strategy = float((1.0 + recent_pr["portfolio_return_net"]).prod() - 1.0)
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

    next_payload: List[Dict[str, Any]] = []
    next_meta: Dict[str, Any] = {}
    if next_pos is not None and not next_pos.empty:
        np_ = next_pos.copy()
        np_["rebalance_date"] = pd.to_datetime(np_["rebalance_date"])
        np_["exit_date"] = pd.to_datetime(np_["exit_date"])
        for _, r in np_.sort_values("rank").iterrows():
            next_payload.append({
                "date": r["rebalance_date"].strftime("%Y-%m-%d"),
                "as_of": r["exit_date"].strftime("%Y-%m-%d"),
                "ticker": r["ticker"],
                "rank": int(r["rank"]),
                "stock_return": 0.0,
                "momentum_score": _safe_float(r["momentum_score"]),
                "entry_price_estimate": _safe_float(r["entry_price"]),
            })
        next_meta = {
            "planned_entry_date": pd.Timestamp(np_["rebalance_date"].iloc[0]).strftime("%Y-%m-%d"),
            "signal_locked_as_of": pd.Timestamp(np_["exit_date"].iloc[0]).strftime("%Y-%m-%d"),
        }

    def _row(stat: str, col: str) -> Optional[float]:
        try:
            return _safe_float(summary.loc[stat, col])
        except KeyError:
            return None

    return {
        "as_of": today.strftime("%Y-%m-%d"),
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "took_seconds": round(time.time() - started, 2),
        "strategy": {
            "lookback_months": lookback,
            "rebalance_period_months": period,
            "label": f"L={lookback}m / P={period}m",
        },
        "completed": completed_payload,
        "open": open_payload,
        "open_meta": open_meta,
        "next": next_payload,
        "next_meta": next_meta,
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


def _get_cached_or_compute(
    lookback: int, period: int, history: int, refresh: bool, today: pd.Timestamp,
) -> Dict[str, Any]:
    """Memoized wrapper around ``_compute_payload``.

    A 5-minute TTL (``CACHE_TTL_SECONDS``) keeps page refreshes
    near-instant without serving stale prices for long. Forcing
    ``refresh=True`` bypasses the cache *and* tells yfinance to
    re-download, which the monthly email cron uses.
    """
    cache_key = (lookback, period, today.strftime("%Y-%m-%d"))
    now = time.time()
    if not refresh:
        with _CACHE_LOCK:
            entry = _RESULT_CACHE.get(cache_key)
        if entry and now - entry[0] < CACHE_TTL_SECONDS:
            payload = dict(entry[1])
            payload["cache_hit"] = True
            payload["cache_age_seconds"] = round(now - entry[0], 1)
            return payload
    payload = _compute_payload(lookback, period, history, refresh, today)
    payload["cache_hit"] = False
    payload["cache_age_seconds"] = 0.0
    with _CACHE_LOCK:
        _RESULT_CACHE[cache_key] = (now, payload)
    return payload


@app.get("/api/picks")
def api_picks(
    refresh: bool = Query(False, description="Re-download fresh prices"),
    history: int = Query(12, ge=1, le=120, description="Past months to return"),
    lookback: int = Query(6, ge=1, le=24, description="Lookback months for momentum"),
    period: int = Query(1, ge=1, le=12, description="Months between rebalances"),
) -> Dict[str, Any]:
    today = pd.Timestamp.now().normalize()
    return _get_cached_or_compute(lookback, period, history, refresh, today)


@app.get("/api/picks-multi")
def api_picks_multi(
    configs: str = Query(
        "6-1,3-2",
        description='Comma-separated "lookback-period" pairs, e.g. "6-1,3-2"',
    ),
    refresh: bool = Query(False),
    history: int = Query(12, ge=1, le=120),
) -> Dict[str, Any]:
    """Return picks for several strategies in one round-trip.

    Lets the frontend collapse two parallel ``/api/picks`` calls into
    one request — the in-memory cache further short-circuits the heavy
    work if both strategies were already computed in the last 5 min.
    """
    today = pd.Timestamp.now().normalize()
    parsed: List[Tuple[int, int]] = []
    for token in configs.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            lb_str, p_str = token.split("-", 1)
            parsed.append((int(lb_str), int(p_str)))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid config token {token!r}; expected 'lookback-period'.",
            ) from exc
    if not parsed:
        raise HTTPException(status_code=400, detail="No valid configs provided.")

    strategies = [
        _get_cached_or_compute(lb, p, history, refresh, today) for lb, p in parsed
    ]
    return {
        "as_of": today.strftime("%Y-%m-%d"),
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "strategies": strategies,
    }
