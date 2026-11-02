"""Command-line entry point for Titan-12 Momentum Rotation."""

from __future__ import annotations

import argparse
import subprocess
import sys

from src.backtest import run_backtest
from src.config import BacktestConfig

# Supported universes and their default benchmark.
UNIVERSES = {"sp500": "SPY", "nasdaq100": "QQQ"}


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for a backtest run."""

    parser = argparse.ArgumentParser(description="Run Titan-12 Momentum Rotation.")
    parser.add_argument("--start-date", default=BacktestConfig.start_date)
    parser.add_argument("--end-date", default=BacktestConfig.end_date)
    parser.add_argument("--top-n", type=int, default=BacktestConfig.top_n)
    parser.add_argument(
        "--universe",
        choices=sorted(UNIVERSES),
        default="sp500",
        help="Stock universe; nasdaq100 writes to outputs/nasdaq100/.",
    )
    parser.add_argument(
        "--benchmark",
        default=None,
        help="Benchmark ticker. Defaults to SPY for sp500 and QQQ for nasdaq100.",
    )
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=BacktestConfig.transaction_cost_bps,
    )
    parser.add_argument("--slippage-bps", type=float, default=BacktestConfig.slippage_bps)
    parser.add_argument(
        "--membership-mode",
        choices=["historical_constituents", "current_constituents"],
        default="historical_constituents",
    )
    parser.add_argument(
        "--refresh-data",
        action="store_true",
        help="Redownload market data instead of using cached CSV files.",
    )
    parser.add_argument(
        "--include-gspc",
        action="store_true",
        help="Also cache ^GSPC data for optional research.",
    )
    return parser.parse_args()


def universe_settings(universe: str) -> dict[str, object]:
    """Return the config overrides for a non-default universe.

    The S&P 500 run keeps the stock defaults. Other universes get their own
    membership file, benchmark, outputs, data-quality log and summary file so
    they never overwrite the S&P 500 results.
    """

    if universe == "sp500":
        return {}
    root = BacktestConfig.project_root
    return {
        "universe": universe,
        "benchmark": UNIVERSES[universe],
        "membership_path": root / "data" / f"{universe}_membership.csv",
        "output_dir": root / "outputs" / universe,
        "chart_dir": root / "outputs" / universe / "charts",
        "data_quality_path": root / "logs" / f"data_quality_report_{universe}.csv",
        "backtest_log_path": root / "logs" / f"backtest_{universe}.log",
        "summary_path": root / f"summary_{universe}.md",
    }


def run_tests() -> str:
    """Run the pytest suite and return its final status line for summary.md."""

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:warnings"],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    status = lines[-1] if lines else "pytest produced no output"
    return f"`pytest -q`: {status}"


def main() -> None:
    """Run the CLI."""

    args = parse_args()
    overrides = universe_settings(args.universe)
    if args.benchmark:
        overrides["benchmark"] = args.benchmark
    config = BacktestConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        transaction_cost_bps=args.transaction_cost_bps,
        slippage_bps=args.slippage_bps,
        use_historical_membership=args.membership_mode == "historical_constituents",
        refresh_data=args.refresh_data,
        include_gspc=args.include_gspc,
        **overrides,
    )
    results = run_backtest(config, test_results=run_tests())
    stats = results["summary_stats"]
    if not stats.empty:
        print(stats.to_string(index=False))
    print(f"Wrote outputs to {config.output_dir} and {config.summary_path}")


if __name__ == "__main__":
    main()
