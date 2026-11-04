"""Run the local Titan-12 dashboard.

Usage:
    python run_webapp.py

By default the app binds to the local loopback host on port 8766. Override with:
    TITAN12_HOST=0.0.0.0 TITAN12_PORT=8766 python run_webapp.py
"""

from __future__ import annotations

import json
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_ROOT / "webapp" / "static"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
CHART_DIR = OUTPUT_DIR / "charts"
# Dashboard tabs. Only the S&P 500 tab applies the sister Nasdaq-overlap
# exclusion; the Nasdaq-100 tab shows the plain Titan-12 ranking.
UNIVERSES = {
    "sp500": {
        "label": "S&P 500",
        "benchmark": "SPY",
        "output_dir": OUTPUT_DIR,
        "excludes_sister": True,
        "bias_warning": (
            "Approximate historical S&P 500 membership from Wikipedia selected "
            "changes. Results still depend on Yahoo Finance data availability "
            "for removed tickers."
        ),
    },
    "nasdaq100": {
        "label": "Nasdaq-100",
        "benchmark": "QQQ",
        "output_dir": OUTPUT_DIR / "nasdaq100",
        "excludes_sister": False,
        "bias_warning": (
            "Point-in-time Nasdaq-100 membership borrowed from the sister "
            "project. About 29 former members Yahoo no longer prices (CELG, "
            "XLNX, ATVI, ...) are missing, so some survivorship bias remains."
        ),
    },
}


def _safe_float(value: object) -> Optional[float]:
    """Return a JSON-safe float or None."""

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def _row_values(df: pd.DataFrame, date: object) -> list[dict[str, object]]:
    """Return sorted selection rows for one rebalance date."""

    date_rows = df[df["rebalance_date"].eq(date)].sort_values("rank")
    rows = []
    for _, row in date_rows.iterrows():
        rows.append(
            {
                "ticker": row["ticker"],
                "rank": int(row["rank"]),
                "stock_return": _safe_float(row.get("stock_return")),
                "score": _safe_float(row.get("weighted_momentum_score")),
                "sector": row.get("sector", "Unknown"),
            }
        )
    return rows


def _split_tickers(value: object) -> list[str]:
    """Parse a comma-joined ``excluded_tickers`` cell; empty when blank."""

    return [t for t in str(value).split(",") if t] if pd.notna(value) else []


def _latest_open(
    output_dir: Path = OUTPUT_DIR, name: str = "open_rebalance_picks.csv"
) -> list[dict[str, object]]:
    """Load an open basket file written by the backtest, if present."""

    path = output_dir / name
    if not path.exists() or path.stat().st_size <= 1:
        return []
    open_df = pd.read_csv(path)
    rows = []
    for _, row in open_df.sort_values("rank").iterrows():
        rows.append(
            {
                "ticker": row["ticker"],
                "rank": int(row["rank"]),
                "date": row["rebalance_date"],
                "as_of": row["as_of_date"],
                "entry_price": _safe_float(row.get("entry_price")),
                "latest_price": _safe_float(row.get("as_of_price")),
                "stock_return": _safe_float(row.get("stock_return", row.get("mtd_return"))),
                "score": _safe_float(row.get("weighted_momentum_score")),
                "sector": row.get("sector", "Unknown"),
            }
        )
    return rows


def _next_picks(output_dir: Path, excludes_sister: bool) -> dict[str, object]:
    """Load the upcoming, signal-locked basket written by the backtest.

    The S&P 500 tab shows the overlap-excluded basket; other tabs the baseline.
    Returns empty picks when no next basket is locked yet.
    """

    name = "next_final_rebalance_picks.csv" if excludes_sister else "next_rebalance_picks.csv"
    path = output_dir / name
    if not path.exists() or path.stat().st_size <= 1:
        return {"picks": [], "date": None, "as_of": None, "excluded": []}
    next_df = pd.read_csv(path).sort_values("rank")
    picks = [
        {
            "ticker": row["ticker"],
            "rank": int(row["rank"]),
            "sector": row.get("sector", "Unknown"),
            "score": _safe_float(row.get("weighted_momentum_score")),
            "entry_price_estimate": _safe_float(row.get("entry_price_estimate")),
        }
        for _, row in next_df.iterrows()
    ]
    excluded = _split_tickers(next_df["excluded_tickers"].iloc[0]) if excludes_sister else []
    return {
        "picks": picks,
        "date": next_df["rebalance_date"].iloc[0],
        "as_of": next_df["as_of_date"].iloc[0],
        "excluded": excluded,
    }


def _top20(output_dir: Path) -> dict[str, object]:
    """Load the plain top-20 Titan-12 ranking written by the backtest."""

    path = output_dir / "top20_ranking.csv"
    if not path.exists() or path.stat().st_size <= 1:
        return {"rows": [], "rank_date": None, "as_of": None}
    board = pd.read_csv(path).sort_values("rank")
    rows = [
        {
            "rank": int(row["rank"]),
            "ticker": row["ticker"],
            "company": row.get("company_name", ""),
            "sector": row.get("sector", "Unknown"),
            "held": bool(row["held"]),
            "score": _safe_float(row["weighted_momentum_score"]),
            "prev_rank": _safe_float(row["prev_rank"]),
            "rank_change": _safe_float(row["rank_change"]),
            "latest_price": _safe_float(row["latest_price"]),
            "ret_1m": _safe_float(row["ret_1m"]),
            "off_6m_high": _safe_float(row["off_6m_high"]),
        }
        for _, row in board.iterrows()
    ]
    return {
        "rows": rows,
        "rank_date": board["rank_date"].iloc[0],
        "as_of": board["as_of_date"].iloc[0],
    }


def _nasdaq_excluded_open(output_dir: Path) -> dict[str, object]:
    """Return the overlap-excluded open basket the backtest wrote, with its exclusions."""

    adjusted = _latest_open(output_dir, "final_rebalance_picks.csv")
    path = output_dir / "final_rebalance_picks.csv"
    excluded = (
        _split_tickers(pd.read_csv(path)["excluded_tickers"].iloc[0]) if adjusted else []
    )
    return {"excluded": excluded, "adjusted": adjusted}


def build_dashboard_payload(universe: str = "sp500") -> dict[str, object]:
    """Build the JSON payload consumed by the local dashboard.

    Args:
        universe: Dashboard tab to build, a key of ``UNIVERSES``.
    """

    settings = UNIVERSES[universe]
    output_dir = settings["output_dir"]
    selections = pd.read_csv(output_dir / "monthly_selections.csv", parse_dates=["rebalance_date"])
    portfolio = pd.read_csv(output_dir / "portfolio_returns.csv", parse_dates=["rebalance_date", "next_rebalance_date"])
    stats = pd.read_csv(output_dir / "summary_stats.csv").iloc[0]
    latest_dates = sorted(selections["rebalance_date"].drop_duplicates())[-12:]

    open_picks = _latest_open(output_dir)
    open_return = None
    if open_picks:
        open_return = sum(p["stock_return"] or 0 for p in open_picks) / len(open_picks)
    # The current open basket's as-of date is the latest trading day priced in,
    # so it doubles as the true data-freshness marker for the dashboard.
    data_freshness = open_picks[0]["as_of"] if open_picks else None

    recent_portfolio = portfolio[portfolio["rebalance_date"].isin(latest_dates)]
    excluded_by_date = {
        row["rebalance_date"]: _split_tickers(row.get("excluded_tickers"))
        for _, row in recent_portfolio.iterrows()
    }
    recent = []
    for date in latest_dates:
        picks = _row_values(selections, date)
        recent.append(
            {
                "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
                "label": pd.Timestamp(date).strftime("%b %Y"),
                "picks": picks,
                "portfolio_return": sum(p["stock_return"] or 0 for p in picks) / max(len(picks), 1),
            }
        )
        if settings["excludes_sister"]:
            recent[-1]["excluded"] = excluded_by_date.get(date, [])
    overlay = {"excluded": [], "adjusted": open_picks}
    if settings["excludes_sister"]:
        overlay = _nasdaq_excluded_open(output_dir)
    # Label what was actually applied, not what was configured.
    all_excluded = settings["excludes_sister"] and all(r["excluded"] for r in recent)

    return {
        "computed_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "data_freshness": data_freshness,
        "universe": {
            "id": universe,
            "label": settings["label"],
            "benchmark": settings["benchmark"],
            "excludes_sister": settings["excludes_sister"],
        },
        "bias_warning": settings["bias_warning"],
        "stats": {
            "cagr": _safe_float(stats["CAGR"]),
            "sharpe": _safe_float(stats["Sharpe_ratio"]),
            "max_drawdown": _safe_float(stats["max_drawdown"]),
            "total_return": _safe_float(stats["total_return"]),
            "win_rate_vs_spy": _safe_float(stats["win_rate_vs_SPY"]),
            "average_turnover": _safe_float(stats["average_turnover"]),
            "final_value": _safe_float(portfolio["portfolio_value"].iloc[-1]),
            "spy_value": _safe_float(portfolio["spy_value"].iloc[-1]),
        },
        "window": {
            "first": recent[0]["date"],
            "last": recent[-1]["date"],
            "months": len(recent),
            "strategy_return": _safe_float(pd.Series([r["portfolio_return"] for r in recent]).add(1).prod() - 1),
            "spy_return": _safe_float((1 + recent_portfolio["spy_return"]).prod() - 1),
            "mode": "Nasdaq-overlap-excluded" if all_excluded else "Baseline",
        },
        "open": {
            "picks": open_picks,
            "portfolio_return": open_return,
            "date": open_picks[0]["date"] if open_picks else None,
            "as_of": open_picks[0]["as_of"] if open_picks else None,
        },
        "next": _next_picks(output_dir, settings["excludes_sister"]),
        "top20": _top20(output_dir),
        "recent": recent,
        "nasdaq_overlay": overlay,
        "charts": {
            name: f"/charts/{universe}/{file}"
            for name, file in [
                ("recent_rebalances", "recent_rebalances.png"),
                ("equity_curve", "equity_curve_vs_spy.png"),
                ("drawdown", "drawdown_curve.png"),
            ]
        },
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    """Serve static dashboard files, charts, and JSON API."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib method name
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.path = "/index.html"
            return SimpleHTTPRequestHandler.do_GET(self)
        if parsed.path == "/api/dashboard":
            universe = parse_qs(parsed.query).get("universe", ["sp500"])[0]
            if universe not in UNIVERSES:
                self.send_error(400, f"Unknown universe: {universe}")
                return
            return self._send_json(build_dashboard_payload(universe))
        if parsed.path.startswith("/charts/"):
            # /charts/<universe>/<file>; bare /charts/<file> keeps serving S&P 500.
            universe, _, name = parsed.path.removeprefix("/charts/").partition("/")
            if universe in UNIVERSES and name:
                chart = UNIVERSES[universe]["output_dir"] / "charts" / name
            else:
                chart = CHART_DIR / parsed.path.removeprefix("/charts/")
            if not chart.resolve().is_relative_to(OUTPUT_DIR.resolve()):
                self.send_error(404, "File not found")
                return
            return self._send_file(chart)
        return SimpleHTTPRequestHandler.do_GET(self)

    def _send_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "File not found")
            return
        body = path.read_bytes()
        content_type = "image/png" if path.suffix == ".png" else "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Start the local dashboard server."""

    host = os.environ.get("TITAN12_HOST", "127.0.0.1")
    port = int(os.environ.get("TITAN12_PORT", "8766"))
    os.chdir(STATIC_DIR)
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Titan-12 dashboard running on {host}, port {port}.")
    server.serve_forever()


if __name__ == "__main__":
    main()
