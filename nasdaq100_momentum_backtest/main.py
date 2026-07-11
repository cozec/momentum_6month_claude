"""CLI entry point for the Nasdaq-100 monthly momentum rotation backtest."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict

import pandas as pd

# Ensure imports work when run from the project root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backtest import run_backtest
from src.config import BacktestConfig, OUTPUTS_DIR
from src.metrics import calculate_summary_stats
from src.plots import generate_all_charts
from src.utils import ensure_dir, get_logger

LOGGER = get_logger("main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest a Nasdaq-100 monthly 6-month momentum strategy."
    )
    parser.add_argument("--start-date", default="2016-01-01")
    parser.add_argument("--end-date", default="2026-05-12")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--lookback-months", type=int, default=6)
    parser.add_argument("--benchmark", default="QQQ")
    parser.add_argument(
        "--secondary-benchmark", default="TQQQ",
        help="Additional buy-and-hold benchmark to track (e.g. TQQQ). Pass an "
             "empty string to disable.",
    )
    parser.add_argument(
        "--score-method",
        choices=["average_monthly_return", "compound_6m_return"],
        default="average_monthly_return",
    )
    parser.add_argument(
        "--transaction-cost-bps", type=float, default=0.0,
        help="Per-trade transaction cost in basis points.",
    )
    parser.add_argument(
        "--slippage-bps", type=float, default=0.0,
        help="Per-trade slippage in basis points.",
    )
    parser.add_argument(
        "--initial-capital", type=float, default=100_000.0,
    )
    parser.add_argument(
        "--use-historical-membership", action="store_true",
        help="Load membership from data/nasdaq100_membership.csv instead of the "
             "current-constituents snapshot.",
    )
    parser.add_argument(
        "--full-refresh", action="store_true",
        help="Ignore the price cache and re-download the full history, "
             "overwriting cached files. Use to pick up split/dividend "
             "re-adjustments an incremental refresh would miss.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = BacktestConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        lookback_months=args.lookback_months,
        benchmark=args.benchmark,
        secondary_benchmark=args.secondary_benchmark,
        score_method=args.score_method,
        transaction_cost_bps=args.transaction_cost_bps,
        slippage_bps=args.slippage_bps,
        initial_capital=args.initial_capital,
        use_historical_membership=args.use_historical_membership,
        full_refresh=args.full_refresh,
    )

    ensure_dir(OUTPUTS_DIR)
    results = run_backtest(config)
    selections: pd.DataFrame = results["selections"]
    portfolio_returns: pd.DataFrame = results["portfolio_returns"]

    summary = calculate_summary_stats(portfolio_returns)

    selections_path = os.path.join(OUTPUTS_DIR, "monthly_selections.csv")
    returns_path = os.path.join(OUTPUTS_DIR, "portfolio_returns.csv")
    summary_path = os.path.join(OUTPUTS_DIR, "summary_stats.csv")

    selections.to_csv(selections_path, index=False)
    portfolio_returns.to_csv(returns_path, index=False)
    summary.to_csv(summary_path)

    open_position = results.get("open_position")
    if open_position is not None and not open_position.empty:
        LOGGER.info(
            "Open (uncompleted) rebalance %s — picks: %s",
            pd.Timestamp(open_position["rebalance_date"].iloc[0]).date(),
            list(open_position["ticker"]),
        )
    chart_paths = generate_all_charts(portfolio_returns, selections, open_position)
    LOGGER.info("Charts written: %s", chart_paths)

    LOGGER.info("Summary statistics:\n%s", summary.to_string())
    LOGGER.info("Outputs written to %s", OUTPUTS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
