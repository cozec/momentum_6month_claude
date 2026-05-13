"""Charting helpers for the momentum rotation strategy."""

from __future__ import annotations

import os
from typing import Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from .config import CHARTS_DIR
from .utils import ensure_dir


def _save(fig: plt.Figure, filename: str) -> str:
    ensure_dir(CHARTS_DIR)
    path = os.path.join(CHARTS_DIR, filename)
    fig.savefig(path, bbox_inches="tight", dpi=120)
    plt.close(fig)
    return path


def _has_tqqq(df: pd.DataFrame) -> bool:
    return "tqqq_value" in df.columns and df["tqqq_value"].notna().any()


def plot_equity_curve(portfolio_returns: pd.DataFrame) -> str:
    """Strategy vs QQQ (and TQQQ buy-and-hold, if available) over time."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(
        portfolio_returns["rebalance_date"],
        portfolio_returns["portfolio_value"],
        label="Strategy",
        linewidth=2,
    )
    ax.plot(
        portfolio_returns["rebalance_date"],
        portfolio_returns["qqq_value"],
        label="QQQ (buy & hold)",
        linewidth=2,
    )
    if _has_tqqq(portfolio_returns):
        ax.plot(
            portfolio_returns["rebalance_date"],
            portfolio_returns["tqqq_value"],
            label="TQQQ (buy & hold)",
            linewidth=2,
            color="purple",
        )
    ax.set_title("Equity Curve: Top-3 6-Month Momentum vs QQQ vs TQQQ")
    ax.set_xlabel("Date")
    ax.set_ylabel("Portfolio Value ($)")
    ax.set_yscale("log")
    ax.legend()
    ax.grid(True, alpha=0.3, which="both")
    return _save(fig, "equity_curve.png")


def _drawdown(returns: pd.Series) -> pd.Series:
    eq = (1.0 + returns).cumprod()
    peak = eq.cummax()
    return eq / peak - 1.0


def plot_drawdowns(portfolio_returns: pd.DataFrame) -> str:
    """Strategy vs QQQ (and TQQQ) drawdown curves."""
    dates = portfolio_returns["rebalance_date"]
    strat_dd = _drawdown(portfolio_returns["portfolio_return_net"].astype(float))
    qqq_dd = _drawdown(portfolio_returns["qqq_return"].astype(float))
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.fill_between(dates, strat_dd, 0, color="red", alpha=0.25, label="Strategy")
    ax.plot(dates, strat_dd, color="red", linewidth=1)
    ax.plot(dates, qqq_dd, color="orange", linewidth=1.2, label="QQQ")
    if _has_tqqq(portfolio_returns):
        tqqq_dd = _drawdown(portfolio_returns["tqqq_return"].astype(float))
        ax.plot(dates, tqqq_dd, color="purple", linewidth=1.2, label="TQQQ")
    ax.set_title("Drawdown — Strategy vs QQQ vs TQQQ")
    ax.set_xlabel("Date")
    ax.set_ylabel("Drawdown")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return _save(fig, "drawdown.png")


def plot_monthly_return_distribution(portfolio_returns: pd.DataFrame) -> str:
    """Histogram of monthly net returns vs QQQ."""
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(
        portfolio_returns["portfolio_return_net"],
        bins=20,
        alpha=0.6,
        label="Strategy",
        color="steelblue",
    )
    ax.hist(
        portfolio_returns["qqq_return"],
        bins=20,
        alpha=0.6,
        label="QQQ",
        color="orange",
    )
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title("Monthly Return Distribution")
    ax.set_xlabel("Monthly Return")
    ax.set_ylabel("Frequency")
    ax.legend()
    ax.grid(True, alpha=0.3)
    return _save(fig, "monthly_return_distribution.png")


def _rolling_return(returns: pd.Series, window: int) -> pd.Series:
    """Compute rolling cumulative return over ``window`` periods."""
    return (1.0 + returns).rolling(window).apply(np.prod, raw=True) - 1.0


def plot_rolling_returns(portfolio_returns: pd.DataFrame) -> tuple[str, str]:
    """Rolling 6-month and 12-month return charts."""
    strat = portfolio_returns["portfolio_return_net"].astype(float)
    qqq = portfolio_returns["qqq_return"].astype(float)
    dates = portfolio_returns["rebalance_date"]

    tqqq = (
        portfolio_returns["tqqq_return"].astype(float)
        if _has_tqqq(portfolio_returns)
        else None
    )

    paths = []
    for window in (6, 12):
        roll_strat = _rolling_return(strat, window)
        roll_qqq = _rolling_return(qqq, window)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(dates, roll_strat, label="Strategy", linewidth=2)
        ax.plot(dates, roll_qqq, label="QQQ", linewidth=2)
        if tqqq is not None:
            ax.plot(dates, _rolling_return(tqqq, window), label="TQQQ", linewidth=2, color="purple")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(f"Rolling {window}-Month Return")
        ax.set_xlabel("Date")
        ax.set_ylabel("Cumulative Return")
        ax.legend()
        ax.grid(True, alpha=0.3)
        paths.append(_save(fig, f"rolling_{window}m_return.png"))
    return paths[0], paths[1]


def plot_top_ticker_frequency(selections: pd.DataFrame, top: int = 20) -> str:
    """Bar chart of how often each ticker appeared in the top-3 selection."""
    counts = selections["ticker"].value_counts().head(top)
    fig, ax = plt.subplots(figsize=(10, 6))
    counts.iloc[::-1].plot(kind="barh", ax=ax, color="steelblue")
    ax.set_title(f"Top {top} Selected Tickers (Frequency)")
    ax.set_xlabel("Number of Selections")
    ax.grid(True, alpha=0.3, axis="x")
    return _save(fig, "top_ticker_frequency.png")


def plot_monthly_excess_return(portfolio_returns: pd.DataFrame) -> str:
    """Bar chart of monthly excess return vs QQQ."""
    fig, ax = plt.subplots(figsize=(10, 6))
    excess = portfolio_returns["excess_return"].astype(float)
    colors = ["green" if v >= 0 else "red" for v in excess]
    ax.bar(portfolio_returns["rebalance_date"], excess, color=colors, width=20)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_title("Monthly Excess Return vs QQQ")
    ax.set_xlabel("Date")
    ax.set_ylabel("Excess Return")
    ax.grid(True, alpha=0.3)
    return _save(fig, "monthly_excess_return.png")


def plot_recent_rebalances(
    selections: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    n: int = 10,
    since: Optional[str] = None,
    open_position: Optional[pd.DataFrame] = None,
) -> str:
    """Visualize the most recent ``n`` rebalances as a colored grid.

    Layout
    ------
    Rows   = rank slot 1 / 2 / 3 (top of figure = rank 1).
    Cols   = the last ``n`` rebalance dates (oldest left, newest right).
    Each cell is a rounded card showing the ticker (large, dark text on
    a soft pastel background) and the holding return below it in a
    sign-colored pill. A thin colored bar along the top of every card
    is a stable per-ticker hue, so the same name reads consistently
    across columns.
    """
    if selections.empty or portfolio_returns.empty:
        fig, ax = plt.subplots(figsize=(6, 2))
        ax.text(0.5, 0.5, "No rebalances available", ha="center", va="center")
        ax.axis("off")
        return _save(fig, "recent_rebalances.png")

    sel = selections.copy()
    sel["rebalance_date"] = pd.to_datetime(sel["rebalance_date"])
    pr = portfolio_returns.copy()
    pr["rebalance_date"] = pd.to_datetime(pr["rebalance_date"])

    if since is not None:
        cutoff = pd.Timestamp(since)
        last_dates = (
            pr["rebalance_date"]
            .sort_values()
            .loc[pr["rebalance_date"] >= cutoff]
            .tolist()
        )
    else:
        last_dates = pr["rebalance_date"].sort_values().tail(n).tolist()
    sel = sel[sel["rebalance_date"].isin(last_dates)]
    pr = pr[pr["rebalance_date"].isin(last_dates)].sort_values("rebalance_date")

    ranks = sorted(sel["rank"].unique())

    open_df = None
    open_date = None
    if open_position is not None and not open_position.empty:
        open_df = open_position.copy()
        open_df["rebalance_date"] = pd.to_datetime(open_df["rebalance_date"])
        open_date = pd.Timestamp(open_df["rebalance_date"].iloc[0])
        # Use the same ranks the rest of the chart uses.
        open_df = open_df[open_df["rank"].isin(ranks)]
        if open_df.empty:
            open_df = None
            open_date = None

    n_completed = len(last_dates)
    n_dates = n_completed + (1 if open_df is not None else 0)
    n_ranks = len(ranks)

    # Modern, deliberately-soft accent palette (Tailwind-ish 500 shades).
    accent_palette = [
        "#6366F1", "#10B981", "#F59E0B", "#EC4899", "#06B6D4",
        "#8B5CF6", "#EF4444", "#84CC16", "#0EA5E9", "#F97316",
        "#14B8A6", "#A855F7", "#22C55E", "#E11D48", "#3B82F6",
        "#EAB308", "#D946EF", "#0891B2", "#65A30D", "#DB2777",
    ]
    # Build a stable ticker→color map including the open-column tickers.
    sources = [sel.sort_values(["rebalance_date", "rank"])]
    if open_df is not None:
        sources.append(open_df.sort_values("rank"))
    unique_tickers = list(pd.unique(pd.concat(sources)["ticker"]))
    ticker_color = {
        t: accent_palette[i % len(accent_palette)]
        for i, t in enumerate(unique_tickers)
    }

    # Soft sign-tinted fills (very low saturation so dark text reads well).
    POS_BASE = np.array([0.85, 0.95, 0.88])   # mint
    NEG_BASE = np.array([0.99, 0.90, 0.91])   # rose
    NEUTRAL  = np.array([0.97, 0.98, 0.99])   # near-white
    TEXT     = "#0F172A"                       # slate-900
    POS_TXT  = "#047857"                       # emerald-700
    NEG_TXT  = "#B91C1C"                       # red-700

    combined_returns = sel["stock_return"].abs()
    if open_df is not None:
        combined_returns = pd.concat([combined_returns, open_df["stock_return"].abs()])
    max_abs_ret = float(combined_returns.max() or 1e-9)

    def _fill_color(ret: float):
        intensity = min(1.0, abs(ret) / max_abs_ret) ** 0.6
        base = POS_BASE if ret >= 0 else NEG_BASE
        return tuple(NEUTRAL + intensity * (base - NEUTRAL))

    fig, ax = plt.subplots(figsize=(max(14, 1.5 * n_dates + 2), 7.0))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    pad = 0.06   # gap between cards (in cell units)
    for col, date in enumerate(last_dates):
        for row_idx, rank in enumerate(ranks):
            cell_row = sel[
                (sel["rebalance_date"] == date) & (sel["rank"] == rank)
            ]
            if cell_row.empty:
                continue
            row = cell_row.iloc[0]
            ticker = row["ticker"]
            ret = float(row["stock_return"])

            y = (n_ranks - 1) - row_idx
            x = col

            # Rounded card body.
            ax.add_patch(mpatches.FancyBboxPatch(
                (x + pad, y + pad),
                1.0 - 2 * pad, 1.0 - 2 * pad,
                boxstyle="round,pad=0,rounding_size=0.08",
                facecolor=_fill_color(ret),
                edgecolor="#E2E8F0",  # slate-200
                linewidth=1.0,
            ))
            # Ticker accent bar across the top of the card.
            ax.add_patch(mpatches.FancyBboxPatch(
                (x + pad, y + 1.0 - pad - 0.10),
                1.0 - 2 * pad, 0.10,
                boxstyle="round,pad=0,rounding_size=0.04",
                facecolor=ticker_color[ticker],
                edgecolor="none",
            ))
            # Ticker text — large, dark, easy to read.
            ax.text(
                x + 0.5, y + 0.58, ticker,
                ha="center", va="center",
                fontsize=18, fontweight="bold", color=TEXT,
                family="DejaVu Sans",
            )
            ret_color = POS_TXT if ret >= 0 else NEG_TXT
            ax.text(
                x + 0.5, y + 0.28, f"{ret * 100:+.1f}%",
                ha="center", va="center",
                fontsize=13, fontweight="bold", color=ret_color,
                family="DejaVu Sans",
            )

    # Render the open (in-progress) rebalance as the rightmost column,
    # with a dashed border and a small "open" badge to distinguish it.
    if open_df is not None:
        col = n_completed
        # Light divider so the open column is visually separate.
        ax.axvline(col, color="#CBD5E1", linewidth=0.8, linestyle=(0, (3, 3)))
        for _, row in open_df.iterrows():
            ticker = row["ticker"]
            ret = float(row["stock_return"])
            rank = int(row["rank"])
            row_idx = ranks.index(rank)
            y = (n_ranks - 1) - row_idx
            x = col

            ax.add_patch(mpatches.FancyBboxPatch(
                (x + pad, y + pad),
                1.0 - 2 * pad, 1.0 - 2 * pad,
                boxstyle="round,pad=0,rounding_size=0.08",
                facecolor=_fill_color(ret),
                edgecolor="#64748B",   # slate-500, dashed for in-progress
                linewidth=1.2,
                linestyle="--",
            ))
            ax.add_patch(mpatches.FancyBboxPatch(
                (x + pad, y + 1.0 - pad - 0.10),
                1.0 - 2 * pad, 0.10,
                boxstyle="round,pad=0,rounding_size=0.04",
                facecolor=ticker_color[ticker],
                edgecolor="none",
            ))
            ax.text(
                x + 0.5, y + 0.62, ticker,
                ha="center", va="center",
                fontsize=18, fontweight="bold", color=TEXT,
                family="DejaVu Sans",
            )
            ret_color = POS_TXT if ret >= 0 else NEG_TXT
            ax.text(
                x + 0.5, y + 0.34, f"{ret * 100:+.1f}%",
                ha="center", va="center",
                fontsize=13, fontweight="bold", color=ret_color,
                family="DejaVu Sans",
            )
            ax.text(
                x + 0.5, y + 0.16, "MTD",
                ha="center", va="center",
                fontsize=9, color="#64748B",
                family="DejaVu Sans",
            )

    ax.set_xlim(0, n_dates)
    ax.set_ylim(0, n_ranks)
    ax.set_xticks([i + 0.5 for i in range(n_dates)])
    xtick_labels = [d.strftime("%b %Y") for d in last_dates]
    if open_df is not None:
        latest_eval = pd.Timestamp(open_df["exit_date"].iloc[0])
        xtick_labels.append(
            f"{open_date.strftime('%b %Y')}\n(open · MTD {latest_eval.strftime('%b %d')})"
        )
    ax.set_xticklabels(
        xtick_labels,
        rotation=0, fontsize=11, color="#475569",
    )
    ax.set_yticks([n_ranks - 0.5 - i for i in range(n_ranks)])
    ax.set_yticklabels(
        [f"Rank {r}" for r in ranks],
        fontsize=11, color="#475569",
    )
    ax.tick_params(left=False, bottom=False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    span = f"{last_dates[0].strftime('%b %Y')} → {last_dates[-1].strftime('%b %Y')}"
    cum_strategy = (1.0 + pr["portfolio_return_net"]).prod() - 1.0
    cum_qqq = (1.0 + pr["qqq_return"]).prod() - 1.0
    open_suffix = ""
    if open_df is not None:
        open_suffix = (
            f"   ·   Open {open_date.strftime('%b %Y')}: "
            + ", ".join(open_df.sort_values('rank')['ticker'].tolist())
        )
    ax.set_title(
        f"{n_completed} Completed Rebalances · {span}{open_suffix}\n"
        f"Strategy {cum_strategy * 100:+.1f}%   vs QQQ {cum_qqq * 100:+.1f}%",
        fontsize=14, color=TEXT, pad=14, loc="left", fontweight="bold",
    )

    fig.tight_layout()
    return _save(fig, "recent_rebalances.png")


def generate_all_charts(
    portfolio_returns: pd.DataFrame,
    selections: pd.DataFrame,
    open_position: Optional[pd.DataFrame] = None,
) -> dict[str, str]:
    """Generate every chart described in the spec."""
    paths = {
        "equity_curve": plot_equity_curve(portfolio_returns),
        "drawdown": plot_drawdowns(portfolio_returns),
        "monthly_distribution": plot_monthly_return_distribution(portfolio_returns),
        "monthly_excess_return": plot_monthly_excess_return(portfolio_returns),
        "top_ticker_frequency": plot_top_ticker_frequency(selections),
        "recent_rebalances": plot_recent_rebalances(
            selections, portfolio_returns,
            since="2025-05-01",
            open_position=open_position,
        ),
    }
    rolling_6, rolling_12 = plot_rolling_returns(portfolio_returns)
    paths["rolling_6m"] = rolling_6
    paths["rolling_12m"] = rolling_12
    return paths
