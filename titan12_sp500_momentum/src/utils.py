"""Shared utility helpers for logging, dates, files, and tabular outputs."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd


def setup_logging(log_path: Path) -> None:
    """Configure console and file logging for a backtest run."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="a", encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def normalize_ticker(ticker: str) -> str:
    """Normalize a ticker for Yahoo Finance while preserving readable symbols."""

    return str(ticker).strip().upper().replace(".", "-")


def save_csv(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    """Save a dataframe to CSV after creating its parent directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index)


def append_quality_issue(
    issues: list[dict[str, object]],
    ticker: str,
    issue_type: str,
    message: str,
    date: object | None = None,
) -> None:
    """Append a normalized data quality issue record to a mutable list."""

    issues.append(
        {
            "date": "" if date is None else pd.Timestamp(date).date().isoformat(),
            "ticker": ticker,
            "issue_type": issue_type,
            "message": message,
        }
    )


def write_summary_markdown(
    path: Path,
    config: object,
    summary_stats: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    monthly_selections: pd.DataFrame,
    data_quality: pd.DataFrame,
    test_results: str = "Not run by backtest command.",
    open_selections: pd.DataFrame | None = None,
    final_selections: pd.DataFrame | None = None,
    excluded_tickers: list[str] | None = None,
    next_selections: pd.DataFrame | None = None,
    next_final_selections: pd.DataFrame | None = None,
    next_excluded_tickers: list[str] | None = None,
    strategy_comparison: pd.DataFrame | None = None,
    data_quality_path: Path | None = None,
) -> None:
    """Write a human-readable run summary to markdown."""

    path.parent.mkdir(parents=True, exist_ok=True)
    bias_warning = ""
    if getattr(config, "membership_mode", "") == "current_constituents":
        bias_warning = (
            "\n> WARNING: This run used current S&P 500 constituents and is "
            "survivorship-biased.\n"
        )

    latest_rebalance = "No completed rebalance."
    current_basket = "No current basket."
    if not monthly_selections.empty:
        latest_date = monthly_selections["rebalance_date"].max()
        latest_rows = monthly_selections[
            monthly_selections["rebalance_date"] == latest_date
        ].copy()
        tickers = ", ".join(latest_rows["ticker"].astype(str).tolist())
        latest_rebalance = f"{latest_date}: {tickers}"
        current_basket = tickers
    # Prefer the open basket (the freshly computed, not-yet-closed rebalance)
    # over the last completed selection, and stamp it with its rebalance date.
    if open_selections is not None and not open_selections.empty:
        open_rows = open_selections.sort_values("rank")
        open_date = open_rows["rebalance_date"].iloc[0]
        open_tickers = ", ".join(open_rows["ticker"].astype(str).tolist())
        current_basket = f"{open_date}: {open_tickers}"

    # The final tradeable basket excludes the sister Nasdaq strategy's top picks.
    final_basket = "No final basket."
    if final_selections is not None and not final_selections.empty:
        final_rows = final_selections.sort_values("rank")
        final_date = final_rows["rebalance_date"].iloc[0]
        final_tickers = ", ".join(final_rows["ticker"].astype(str).tolist())
        final_basket = f"{final_date}: {final_tickers}"
    elif open_selections is not None and not open_selections.empty:
        final_basket = current_basket
    excluded_note = ", ".join(excluded_tickers) if excluded_tickers else "none"
    final_heading = "Final Top 3 (Nasdaq-Overlap Excluded)"
    excluded_line = f"Excluded sister Nasdaq top picks: {excluded_note}"
    if getattr(config, "universe", "sp500") != "sp500":
        final_heading = "Final Top 3"
        excluded_line = "Sister Nasdaq overlap exclusion is not applied to this universe."

    # Upcoming basket, present only once the prior month's last close locks it.
    next_section = ""
    if next_selections is not None and not next_selections.empty:
        next_rows = next_selections.sort_values("rank")
        next_date = next_rows["rebalance_date"].iloc[0]
        as_of = next_rows["as_of_date"].iloc[0]
        baseline_next = ", ".join(next_rows["ticker"].astype(str).tolist())
        final_next = baseline_next
        if next_final_selections is not None and not next_final_selections.empty:
            final_next = ", ".join(
                next_final_selections.sort_values("rank")["ticker"].astype(str).tolist()
            )
        if getattr(config, "universe", "sp500") != "sp500":
            next_excluded_line = "Sister Nasdaq overlap exclusion is not applied to this universe."
        elif next_excluded_tickers:
            next_excluded_line = (
                "Excluded sister Nasdaq next picks: " + ", ".join(next_excluded_tickers)
            )
        else:
            next_excluded_line = (
                "Sister Nasdaq next basket unavailable; no overlap exclusion applied."
            )
        next_section = (
            f"\n## Next Rebalance {next_date} (signal locked {as_of})\n\n"
            f"Final: {final_next}\n\n"
            f"Baseline (pre-exclusion): {baseline_next}\n\n"
            f"{next_excluded_line}\n\n"
            "Signal uses monthly returns through the last close; the fill is "
            "the next open.\n"
        )

    trades_section = ""
    if len(monthly_selections) < 30 and not monthly_selections.empty:
        trades_section = "\n## Trade Details\n\n"
        trades_section += monthly_selections.to_markdown(index=False)
        trades_section += "\n"

    stats_section = "No summary statistics generated."
    if not summary_stats.empty:
        stats_section = summary_stats.to_markdown(index=False)

    comparison_section = "No strategy comparison generated."
    if strategy_comparison is not None and not strategy_comparison.empty:
        comparison_section = (
            "Start capital $10,000. Buy & hold uses "
            "$10,000 x (last_close / first_close) on adjusted closes over the "
            "same window. Alpha (annualized) and Beta are versus the "
            "benchmark's monthly returns; Sharpe and Alpha assume a 0% "
            "risk-free rate.\n\n"
            + strategy_comparison.to_markdown(
                index=False,
                floatfmt=("", ",.2f", ".2%", ".2%", ".2%", ".2f", ".2%", ".2f"),
            )
        )

    quality_section = "No data quality warnings."
    if not data_quality.empty:
        # Counts first so issues beyond the 50-row preview are still visible.
        counts = (
            data_quality["issue_type"].value_counts().rename_axis("issue_type")
            .reset_index(name="count")
        )
        quality_section = counts.to_markdown(index=False)
        if len(data_quality) > 50:
            full_report = data_quality_path or "the data quality CSV"
            quality_section += (
                f"\n\nShowing the first 50 of {len(data_quality):,} issues. "
                f"Full list: {full_report}"
            )
        quality_section += "\n\n" + data_quality.head(50).to_markdown(
            index=False
        )

    config_rows = {
        "start_date": getattr(config, "start_date", ""),
        "end_date": getattr(config, "end_date", ""),
        "top_n": getattr(config, "top_n", ""),
        "benchmark": getattr(config, "benchmark", ""),
        "transaction_cost_bps": getattr(config, "transaction_cost_bps", ""),
        "slippage_bps": getattr(config, "slippage_bps", ""),
        "membership_mode": getattr(config, "membership_mode", ""),
    }
    config_table = pd.DataFrame(
        [{"setting": key, "value": value} for key, value in config_rows.items()]
    ).to_markdown(index=False)

    universe_label = {"sp500": "S&P 500", "nasdaq100": "Nasdaq-100"}.get(
        getattr(config, "universe", "sp500"), "S&P 500"
    )
    chart_dir = Path(getattr(config, "chart_dir", "outputs/charts"))
    project_root = getattr(config, "project_root", None)
    if project_root is not None and chart_dir.is_relative_to(project_root):
        chart_dir = chart_dir.relative_to(project_root)
    chart_list = "\n".join(
        f"- {chart_dir / name}"
        for name in [
            "equity_curve_vs_spy.png",
            "drawdown_curve.png",
            "monthly_return_distribution.png",
            "rolling_6_month_return.png",
            "rolling_12_month_return.png",
            "rolling_sharpe_ratio.png",
            "annual_return_bar_chart.png",
            "top_selected_stocks_frequency.png",
            "sector_exposure_over_time.png",
            "excess_return_vs_spy_over_time.png",
        ]
    )

    run_timestamp = pd.Timestamp.now(tz="UTC").isoformat()
    data_freshness = run_timestamp
    if not portfolio_returns.empty:
        data_freshness = str(portfolio_returns["next_rebalance_date"].max())

    content = f"""# Titan-12 Momentum Rotation Summary ({universe_label})

Run timestamp: {run_timestamp}

Data freshness timestamp: {data_freshness}

{bias_warning}
## Active Configuration

{config_table}

## Strategy Comparison

{comparison_section}

## Summary Stats

{stats_section}

## Latest Completed Rebalance

{latest_rebalance}

{next_section}
## {final_heading}

{final_basket}

{excluded_line}

## Baseline Open Basket (pre-exclusion)

{current_basket}

## Charts

{chart_list}

## Data Quality Notes

{quality_section}

## Test Results

{test_results}
{trades_section}
"""
    path.write_text(content, encoding="utf-8")
