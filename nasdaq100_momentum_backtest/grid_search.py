"""CLI: grid search with walk-forward validation.

Default grid:
    lookback  ∈ {3, 6, 9, 12}  months
    period    ∈ {1, 2, 3}      months
Default split:
    train_end = 2023-01-01  (≈ 6.5 yr train, 3.3 yr test)
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from src.config import BacktestConfig, OUTPUTS_DIR
from src.grid_search import run_grid, summarize_walkforward
from src.plots import plot_grid_heatmap, plot_walkforward_scatter
from src.utils import ensure_dir, get_logger

LOGGER = get_logger("grid_search_cli")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start-date", default="2016-01-01")
    p.add_argument("--end-date", default="2026-05-13")
    p.add_argument(
        "--train-end", default="2023-01-01",
        help="Walk-forward split date. Entries strictly before this are "
             "in-sample; entries on/after are out-of-sample.",
    )
    p.add_argument(
        "--lookbacks", type=int, nargs="+", default=[3, 6, 9, 12],
        help="Lookback windows in months.",
    )
    p.add_argument(
        "--periods", type=int, nargs="+", default=[1, 2, 3],
        help="Rebalance periods in months.",
    )
    p.add_argument(
        "--top-n", type=int, default=3,
        help="Top-N stocks held each rebalance.",
    )
    p.add_argument(
        "--score-method",
        choices=["average_monthly_return", "compound_6m_return"],
        default="average_monthly_return",
    )
    p.add_argument("--force-refresh", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    config = BacktestConfig(
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        score_method=args.score_method,
        force_refresh=args.force_refresh,
    )
    LOGGER.info(
        "Grid: lookbacks=%s × periods=%s  train_end=%s",
        args.lookbacks, args.periods, args.train_end,
    )

    grid = run_grid(
        config,
        lookbacks=args.lookbacks,
        periods=args.periods,
        train_end=args.train_end,
    )

    grid_dir = os.path.join(OUTPUTS_DIR, "grid_search")
    ensure_dir(grid_dir)
    csv_path = os.path.join(grid_dir, "grid_results.csv")
    grid.to_csv(csv_path, index=False)
    LOGGER.info("Wrote %s (%d rows)", csv_path, len(grid))

    # Render heatmaps and the IS/OOS scatter.
    charts_dir = os.path.join(OUTPUTS_DIR, "charts")
    plot_grid_heatmap(
        grid, "full_sharpe",
        title=f"Sharpe — full window ({args.start_date} → {args.end_date})",
        filename=os.path.join("grid_full_sharpe.png").rsplit("/", 1)[-1],
        center_at_zero=True,
    )
    plot_grid_heatmap(
        grid, "full_cagr",
        title="CAGR — full window",
        filename="grid_full_cagr.png",
        fmt="{:.1%}",
        center_at_zero=False,
    )
    plot_grid_heatmap(
        grid, "is_sharpe",
        title=f"Sharpe — in-sample (< {args.train_end})",
        filename="grid_is_sharpe.png",
        center_at_zero=True,
    )
    plot_grid_heatmap(
        grid, "oos_sharpe",
        title=f"Sharpe — out-of-sample (≥ {args.train_end})",
        filename="grid_oos_sharpe.png",
        center_at_zero=True,
    )
    plot_walkforward_scatter(grid, filename="grid_walkforward_scatter.png")

    # Plain-text summary
    summary = summarize_walkforward(grid)
    if summary:
        w = summary["is_winner"]
        o = summary["oos_winner"]
        LOGGER.info("")
        LOGGER.info("=== Walk-forward summary ===")
        LOGGER.info(
            "IS winner: lookback=%dm period=%dm  IS_sharpe=%.2f → OOS_sharpe=%.2f "
            "(IS_CAGR=%.1f%% → OOS_CAGR=%.1f%%)",
            w["lookback"], w["period"],
            w["is_sharpe"], w["oos_sharpe"],
            100 * w["is_cagr"], 100 * w["oos_cagr"],
        )
        LOGGER.info(
            "OOS winner: lookback=%dm period=%dm  IS_sharpe=%.2f  OOS_sharpe=%.2f",
            o["lookback"], o["period"], o["is_sharpe"], o["oos_sharpe"],
        )
        LOGGER.info(
            "Grid-wide mean Sharpe: IS=%.2f, OOS=%.2f  (degradation %.2f)",
            summary["mean_is_sharpe"], summary["mean_oos_sharpe"],
            summary["mean_is_sharpe"] - summary["mean_oos_sharpe"],
        )

    LOGGER.info("Charts written to %s/", charts_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
