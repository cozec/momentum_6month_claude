"""Chart generation for Titan-12 backtest outputs."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd


def _save_current_figure(path: Path) -> None:
    """Save and close the current matplotlib figure."""

    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def plot_equity_curve(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    path: Path,
    benchmark_label: str = "SPY",
) -> None:
    """Plot strategy and benchmark equity curves."""

    plt.figure(figsize=(10, 5))
    strategy_returns.plot(label="Titan-12")
    benchmark_returns.plot(label=benchmark_label)
    plt.title(f"Equity Curve vs {benchmark_label}")
    plt.ylabel("Portfolio Value")
    plt.legend()
    _save_current_figure(path)


def plot_drawdowns(portfolio_values: pd.Series, path: Path) -> None:
    """Plot strategy drawdown curve."""

    drawdown = portfolio_values / portfolio_values.cummax() - 1.0
    plt.figure(figsize=(10, 4))
    drawdown.plot(color="crimson")
    plt.title("Drawdown Curve")
    plt.ylabel("Drawdown")
    _save_current_figure(path)


def plot_sector_exposure(monthly_selections: pd.DataFrame, path: Path) -> None:
    """Plot selected-stock sector exposure through time."""

    if monthly_selections.empty:
        return
    exposure = (
        monthly_selections.groupby(["rebalance_date", "sector"])["weight"]
        .sum()
        .unstack(fill_value=0.0)
    )
    exposure.index = pd.to_datetime(exposure.index)
    exposure.plot.area(figsize=(11, 5))
    plt.title("Sector Exposure Over Time")
    plt.ylabel("Weight")
    _save_current_figure(path)


def _format_month_label(value: object) -> str:
    """Format a date-like value as a compact month label."""

    return pd.Timestamp(value).strftime("%b %Y")


def _compound_return(returns: pd.Series) -> float:
    """Compound a series of simple returns."""

    clean_returns = pd.to_numeric(returns, errors="coerce").dropna()
    if clean_returns.empty:
        return float("nan")
    return float((1.0 + clean_returns).prod() - 1.0)


def _ticker_color_map(tickers: list[str]) -> dict[str, str]:
    """Assign stable accent colors to tickers for recent rebalance cards."""

    palette = [
        "#6366f1",
        "#10b981",
        "#ec4899",
        "#8b5cf6",
        "#06b6d4",
        "#84cc16",
        "#f97316",
        "#22c55e",
        "#f59e0b",
        "#ef4444",
        "#14b8a6",
    ]
    colors: dict[str, str] = {}
    for ticker in tickers:
        if ticker not in colors:
            colors[ticker] = palette[len(colors) % len(palette)]
    return colors


def plot_recent_rebalances(
    monthly_selections: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    path: Path,
    open_selections: pd.DataFrame | None = None,
    benchmark_label: str = "SPY",
    completed_periods: int = 12,
) -> None:
    """Plot recent completed rebalances plus an optional open basket.

    The visual is designed for a quick audit of recent rotation behavior: each
    column is a rebalance month, each row is a portfolio rank, and each card
    shows ticker plus realized or month-to-date return.
    """

    if monthly_selections.empty or portfolio_returns.empty:
        return

    selections = monthly_selections.copy()
    returns = portfolio_returns.copy()
    selections["rebalance_date"] = pd.to_datetime(selections["rebalance_date"])
    returns["rebalance_date"] = pd.to_datetime(returns["rebalance_date"])
    returns["next_rebalance_date"] = pd.to_datetime(returns["next_rebalance_date"])

    recent_returns = returns.tail(completed_periods).copy()
    recent_dates = recent_returns["rebalance_date"].tolist()
    recent_selections = selections[selections["rebalance_date"].isin(recent_dates)].copy()
    recent_selections = recent_selections.sort_values(["rebalance_date", "rank"])

    open_df = pd.DataFrame() if open_selections is None else open_selections.copy()
    if not open_df.empty:
        open_df["rebalance_date"] = pd.to_datetime(open_df["rebalance_date"])
        open_df = open_df.sort_values("rank")

    ticker_sequence = recent_selections["ticker"].astype(str).tolist()
    if not open_df.empty:
        ticker_sequence.extend(open_df["ticker"].astype(str).tolist())
    colors = _ticker_color_map(ticker_sequence)

    completed_count = len(recent_dates)
    has_open = not open_df.empty
    total_columns = completed_count + int(has_open)
    if total_columns == 0:
        return

    strategy_return = _compound_return(recent_returns["portfolio_return_net"])
    benchmark_return = _compound_return(recent_returns["spy_return"])
    start_label = _format_month_label(recent_returns["rebalance_date"].iloc[0])
    end_label = _format_month_label(recent_returns["rebalance_date"].iloc[-1])
    open_title = ""
    if has_open:
        open_date = _format_month_label(open_df["rebalance_date"].iloc[0])
        open_tickers = ", ".join(open_df["ticker"].astype(str).tolist())
        open_title = f"  ·  Open {open_date}: {open_tickers}"

    fig_width = max(16.0, 1.55 * total_columns + 3.5)
    fig, ax = plt.subplots(figsize=(fig_width, 7.2))
    ax.set_xlim(-0.9, total_columns - 0.1)
    ax.set_ylim(-0.45, 3.25)
    ax.axis("off")

    title = (
        f"{completed_count} Completed Rebalances · {start_label} -> {end_label}"
        f"{open_title}\n"
        f"Strategy {strategy_return:+.1%}   vs {benchmark_label} {benchmark_return:+.1%}"
    )
    ax.text(
        -0.75,
        3.18,
        title,
        ha="left",
        va="top",
        fontsize=14,
        fontweight="bold",
        color="#111827",
        linespacing=1.15,
    )

    for rank in (1, 2, 3):
        y = 3 - rank
        ax.text(
            -0.82,
            y + 0.47,
            f"Rank {rank}",
            ha="right",
            va="center",
            fontsize=11,
            color="#475569",
        )

    card_width = 0.88
    card_height = 0.78
    card_y_offset = 0.08
    for column_idx, rebalance_date in enumerate(recent_dates):
        month_rows = recent_selections[
            recent_selections["rebalance_date"] == rebalance_date
        ]
        for _, row in month_rows.iterrows():
            rank = int(row["rank"])
            y = 3 - rank + card_y_offset
            ticker = str(row["ticker"])
            stock_return = float(row["stock_return"])
            fill = "#e7f6ee" if stock_return >= 0 else "#fbf7fa"
            if stock_return > 0.20:
                fill = "#d7f1df"
            card = FancyBboxPatch(
                (column_idx - card_width / 2, y),
                card_width,
                card_height,
                boxstyle="round,pad=0.018,rounding_size=0.08",
                linewidth=1.0,
                edgecolor="#dbe5ef",
                facecolor=fill,
            )
            ax.add_patch(card)
            bar = FancyBboxPatch(
                (column_idx - card_width / 2, y + card_height - 0.10),
                card_width,
                0.10,
                boxstyle="round,pad=0.0,rounding_size=0.04",
                linewidth=0,
                facecolor=colors[ticker],
            )
            ax.add_patch(bar)
            ax.text(
                column_idx,
                y + 0.50,
                ticker,
                ha="center",
                va="center",
                fontsize=17,
                fontweight="bold",
                color="#111827",
            )
            ax.text(
                column_idx,
                y + 0.20,
                f"{stock_return:+.1%}",
                ha="center",
                va="center",
                fontsize=12.5,
                fontweight="bold",
                color="#047857" if stock_return >= 0 else "#b91c1c",
            )
        ax.text(
            column_idx,
            -0.08,
            _format_month_label(rebalance_date),
            ha="center",
            va="top",
            fontsize=11,
            color="#475569",
        )

    if has_open:
        open_idx = completed_count
        ax.axvline(open_idx - 0.5, ymin=0.07, ymax=0.90, color="#94a3b8", linestyle="--", lw=1)
        for _, row in open_df.iterrows():
            rank = int(row["rank"])
            y = 3 - rank + card_y_offset
            ticker = str(row["ticker"])
            stock_return = float(row["stock_return"])
            card = FancyBboxPatch(
                (open_idx - card_width / 2, y),
                card_width,
                card_height,
                boxstyle="round,pad=0.018,rounding_size=0.08",
                linewidth=1.1,
                linestyle="--",
                edgecolor="#64748b",
                facecolor="#eef8f4" if stock_return >= 0 else "#fbf7fa",
            )
            ax.add_patch(card)
            bar = FancyBboxPatch(
                (open_idx - card_width / 2, y + card_height - 0.10),
                card_width,
                0.10,
                boxstyle="round,pad=0.0,rounding_size=0.04",
                linewidth=0,
                facecolor=colors[ticker],
            )
            ax.add_patch(bar)
            ax.text(
                open_idx,
                y + 0.54,
                ticker,
                ha="center",
                va="center",
                fontsize=17,
                fontweight="bold",
                color="#111827",
            )
            ax.text(
                open_idx,
                y + 0.27,
                f"{stock_return:+.1%}",
                ha="center",
                va="center",
                fontsize=12.5,
                fontweight="bold",
                color="#047857" if stock_return >= 0 else "#b91c1c",
            )
            ax.text(
                open_idx,
                y + 0.09,
                "MTD",
                ha="center",
                va="center",
                fontsize=9,
                color="#64748b",
            )
        open_label = _format_month_label(open_df["rebalance_date"].iloc[0])
        if "as_of_date" in open_df.columns:
            as_of = pd.Timestamp(open_df["as_of_date"].iloc[0]).strftime("%b %-d")
            open_label = f"{open_label}\n(open · MTD {as_of})"
        ax.text(
            open_idx,
            -0.08,
            open_label,
            ha="center",
            va="top",
            fontsize=11,
            color="#475569",
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def create_all_charts(
    portfolio_returns: pd.DataFrame,
    monthly_selections: pd.DataFrame,
    chart_dir: Path,
    benchmark_label: str = "SPY",
) -> None:
    """Create all required charts for a completed backtest."""

    chart_dir.mkdir(parents=True, exist_ok=True)
    if portfolio_returns.empty:
        return

    returns = portfolio_returns.copy()
    returns["rebalance_date"] = pd.to_datetime(returns["rebalance_date"])
    returns = returns.set_index("rebalance_date")

    plot_equity_curve(
        returns["portfolio_value"],
        returns["spy_value"],
        chart_dir / "equity_curve_vs_spy.png",
        benchmark_label=benchmark_label,
    )
    plot_drawdowns(returns["portfolio_value"], chart_dir / "drawdown_curve.png")

    plt.figure(figsize=(8, 5))
    returns["portfolio_return_net"].hist(bins=30)
    plt.title("Monthly Return Distribution")
    plt.xlabel("Monthly Return")
    _save_current_figure(chart_dir / "monthly_return_distribution.png")

    plt.figure(figsize=(10, 4))
    returns["portfolio_return_net"].rolling(6).apply(lambda x: (1 + x).prod() - 1).plot()
    plt.title("Rolling 6-Month Return")
    _save_current_figure(chart_dir / "rolling_6_month_return.png")

    plt.figure(figsize=(10, 4))
    returns["portfolio_return_net"].rolling(12).apply(lambda x: (1 + x).prod() - 1).plot()
    plt.title("Rolling 12-Month Return")
    _save_current_figure(chart_dir / "rolling_12_month_return.png")

    plt.figure(figsize=(10, 4))
    rolling_sharpe = (
        returns["portfolio_return_net"].rolling(12).mean()
        / returns["portfolio_return_net"].rolling(12).std()
        * (12**0.5)
    )
    rolling_sharpe.plot()
    plt.title("Rolling Sharpe Ratio")
    _save_current_figure(chart_dir / "rolling_sharpe_ratio.png")

    annual_returns = returns["portfolio_return_net"].groupby(returns.index.year).apply(
        lambda x: (1 + x).prod() - 1
    )
    plt.figure(figsize=(10, 4))
    annual_returns.plot(kind="bar")
    plt.title("Annual Return Bar Chart")
    plt.ylabel("Return")
    _save_current_figure(chart_dir / "annual_return_bar_chart.png")

    if not monthly_selections.empty:
        plt.figure(figsize=(10, 5))
        monthly_selections["ticker"].value_counts().head(25).plot(kind="bar")
        plt.title("Top Selected Stocks Frequency")
        plt.ylabel("Selection Count")
        _save_current_figure(chart_dir / "top_selected_stocks_frequency.png")
        plot_sector_exposure(
            monthly_selections, chart_dir / "sector_exposure_over_time.png"
        )
        plot_recent_rebalances(
            monthly_selections,
            portfolio_returns,
            chart_dir / "recent_rebalances.png",
        )

    plt.figure(figsize=(10, 4))
    returns["excess_return_vs_spy"].cumsum().plot()
    plt.title(f"Excess Return vs {benchmark_label} Over Time")
    plt.ylabel("Cumulative Excess Return")
    _save_current_figure(chart_dir / "excess_return_vs_spy_over_time.png")
