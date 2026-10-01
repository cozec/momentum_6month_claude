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
from src.download_data import _cache_covers, _download_one, _load_cached
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


_SP500_PATH = os.path.join(PROJECT_ROOT, "data", "sp500_constituents.csv")


def _load_sp500() -> List[str]:
    """Current S&P 500 constituents (scripts/build_sp500.py refreshes them)."""
    return (
        pd.read_csv(_SP500_PATH)["Symbol"].astype(str).str.upper().tolist()
    )


def _build_exclude_map(results: Dict[str, Any]) -> Dict[pd.Timestamp, set]:
    """Map each rebalance date -> set of tickers a strategy picked (completed,
    open, and next), so a second strategy can dedupe against it."""
    m: Dict[pd.Timestamp, set] = {}
    for key in ("selections", "open_position", "next_position"):
        df = results.get(key)
        if df is None or df.empty:
            continue
        dates = pd.to_datetime(df["rebalance_date"])
        for dt, tk in zip(dates, df["ticker"]):
            m.setdefault(pd.Timestamp(dt), set()).add(tk)
    return m


def _results_to_payload(
    results: Dict[str, Any],
    today: pd.Timestamp,
    started: float,
    period: int,
    history: int,
    strategy_meta: Dict[str, Any],
) -> Dict[str, Any]:
    """Turn a raw ``run_backtest`` result into the dashboard JSON payload."""
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
        "strategy": strategy_meta,
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


def _compute_payload(
    lookback: int,
    period: int,
    history: int,
    refresh: bool,
    today: pd.Timestamp,
) -> Dict[str, Any]:
    """Run the Nasdaq-100 backtest for one (lookback, period) → JSON payload."""
    started = time.time()
    config = BacktestConfig(
        start_date="2016-01-01",
        end_date=today.strftime("%Y-%m-%d"),
        force_refresh=refresh,
        lookback_months=lookback,
        rebalance_period_months=period,
        use_historical_membership=True,
    )
    results = run_backtest(config)
    meta = {
        "id": f"L{lookback}-P{period}",
        "lookback_months": lookback,
        "rebalance_period_months": period,
        "label": f"L={lookback}m / P={period}m",
        "universe": "Nasdaq-100",
    }
    return _results_to_payload(results, today, started, period, history, meta)


# Dashboard strategies: Nasdaq-100 (baseline) and S&P 500 deduped against it.
_NASDAQ_META = {
    "id": "nasdaq100", "lookback_months": 6, "rebalance_period_months": 1,
    "label": "6-month momentum, monthly rebalance", "universe": "Nasdaq-100",
}
_SP500_META = {
    "id": "sp500", "lookback_months": 6, "rebalance_period_months": 1,
    "label": "6-month momentum, monthly rebalance",
    "universe": "S&P 500 · excludes the Nasdaq-100 basket's picks",
}


def _compute_dashboard(
    history: int, refresh: bool, today: pd.Timestamp
) -> Dict[str, Any]:
    """Compute both dashboard strategies. The S&P 500 basket is scored after
    the Nasdaq-100 one and drops any ticker the Nasdaq basket already holds
    that month, so the two baskets never overlap."""
    end = today.strftime("%Y-%m-%d")
    common = dict(
        start_date="2016-01-01", end_date=end, force_refresh=refresh,
        lookback_months=6, rebalance_period_months=1,
    )
    started_a = time.time()
    res_a = run_backtest(BacktestConfig(use_historical_membership=True, **common))
    payload_a = _results_to_payload(res_a, today, started_a, 1, history, dict(_NASDAQ_META))

    exclude = _build_exclude_map(res_a)
    started_b = time.time()
    res_b = run_backtest(
        BacktestConfig(tickers=_load_sp500(), use_historical_membership=False, **common),
        exclude_by_date=exclude,
    )
    payload_b = _results_to_payload(res_b, today, started_b, 1, history, dict(_SP500_META))

    return {
        "as_of": today.strftime("%Y-%m-%d"),
        "computed_at": datetime.now().isoformat(timespec="seconds"),
        "strategies": [payload_a, payload_b],
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


@app.get("/api/ohlc")
def api_ohlc(
    ticker: str = Query(..., description="Ticker symbol, e.g. NVDA"),
    months: int = Query(6, ge=1, le=60, description="Trailing window in calendar months"),
    refresh: bool = Query(False, description="Force a fresh yfinance download"),
) -> Dict[str, Any]:
    """Return daily OHLCV bars for one ticker, used by the chart panel.

    Reuses the same per-ticker CSV cache the backtest pipeline writes
    to (``data/raw_prices/*.csv``). If the cache doesn't extend close
    enough to today, fetch the missing slice and merge.
    """
    sym = ticker.strip().upper()
    if not sym or not sym.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail=f"Invalid ticker {ticker!r}")
    today = pd.Timestamp.now().normalize()
    start = today - pd.DateOffset(months=months)

    cached = None if refresh else _load_cached(sym)
    if cached is None or not _cache_covers(cached, start, today):
        fetched = _download_one(sym, start, today)
        if fetched is None or fetched.empty:
            if cached is None or cached.empty:
                raise HTTPException(status_code=404, detail=f"No price data for {sym}")
        else:
            cached = pd.concat([cached, fetched]) if cached is not None else fetched
            cached = cached[~cached.index.duplicated(keep="last")].sort_index()

    window = cached.loc[(cached.index >= start) & (cached.index <= today)]
    if window.empty:
        raise HTTPException(status_code=404, detail=f"No price data for {sym} in window")

    candles: List[Dict[str, Any]] = []
    for ts, row in window.iterrows():
        candles.append({
            "date": ts.strftime("%Y-%m-%d"),
            "open": _safe_float(row.get("Open")),
            "high": _safe_float(row.get("High")),
            "low": _safe_float(row.get("Low")),
            "close": _safe_float(row.get("Close")),
            "volume": _safe_float(row.get("Volume")),
        })
    return {
        "ticker": sym,
        "months": months,
        "first_date": candles[0]["date"],
        "last_date": candles[-1]["date"],
        "count": len(candles),
        "candles": candles,
    }


@app.get("/api/dashboard")
def api_dashboard(
    refresh: bool = Query(False, description="Re-download fresh prices"),
    history: int = Query(12, ge=1, le=120, description="Past months to return"),
) -> Dict[str, Any]:
    """The two dashboard baskets in one call: Nasdaq-100, then S&P 500 deduped
    against it. Cached like the other endpoints (5-min TTL, bypassed on refresh)."""
    today = pd.Timestamp.now().normalize()
    cache_key = ("dashboard", today.strftime("%Y-%m-%d"))
    now = time.time()
    if not refresh:
        with _CACHE_LOCK:
            entry = _RESULT_CACHE.get(cache_key)
        if entry and now - entry[0] < CACHE_TTL_SECONDS:
            out = dict(entry[1])
            out["cache_hit"] = True
            return out
    out = _compute_dashboard(history, refresh, today)
    out["cache_hit"] = False
    with _CACHE_LOCK:
        _RESULT_CACHE[cache_key] = (now, out)
    return out


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
