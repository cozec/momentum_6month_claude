"""Backtest execution for Titan-12 Momentum Rotation."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.config import BacktestConfig, ensure_directories
from src.download_data import download_price_data
from src.membership import (
    create_current_membership_file,
    get_eligible_universe,
    get_member_metadata,
    load_sp500_membership,
)
from src.nyse_calendar import next_session_after
from src.metrics import calculate_strategy_comparison, calculate_summary_stats
from src.plots import create_all_charts, plot_recent_rebalances
from src.signals import (
    calculate_month_end_prices,
    calculate_monthly_returns,
    calculate_titan12_score,
    get_first_trading_days,
    prices_to_adj_close_frame,
    rank_stocks_by_score,
    select_top_n,
)
from src.utils import append_quality_issue, save_csv, setup_logging, write_summary_markdown


LOGGER = logging.getLogger(__name__)

# Sister Nasdaq strategy open basket, whose top picks are excluded from the
# final S&P basket for cross-project diversification. Override with NASDAQ_OPEN_PATH.
DEFAULT_NASDAQ_OPEN_PATH = Path(
    "/Users/adam/project/momentum_6m_claude/nasdaq100_momentum_backtest/outputs/open_rebalance_picks.csv"
)


def calculate_turnover(
    previous_holdings: set[str] | list[str],
    current_holdings: set[str] | list[str],
) -> float:
    """Calculate one-way turnover for equal-weight portfolios.

    The result is the fraction of the target portfolio that must be bought or
    sold when moving from previous holdings to current holdings.
    """

    previous = set(previous_holdings)
    current = set(current_holdings)
    if not previous and not current:
        return 0.0
    if not previous:
        return 1.0
    if not current:
        return 1.0
    previous_weight = 1.0 / len(previous)
    current_weight = 1.0 / len(current)
    all_tickers = previous | current
    weight_change = 0.0
    for ticker in all_tickers:
        old_weight = previous_weight if ticker in previous else 0.0
        new_weight = current_weight if ticker in current else 0.0
        weight_change += abs(new_weight - old_weight)
    return float(weight_change / 2.0)


def _price_at_or_before(adj_close: pd.DataFrame, ticker: str, date: pd.Timestamp) -> float:
    """Return adjusted close for a ticker on a specific trading date."""

    if ticker not in adj_close.columns or date not in adj_close.index:
        return np.nan
    return float(adj_close.loc[date, ticker])


def calculate_portfolio_return(
    selected_tickers: list[str],
    prices: pd.DataFrame,
    entry_date: object,
    exit_date: object,
) -> tuple[float, list[dict[str, object]]]:
    """Calculate equal-weight gross return and per-stock return details."""

    entry = pd.Timestamp(entry_date).normalize()
    exit_ = pd.Timestamp(exit_date).normalize()
    rows: list[dict[str, object]] = []
    returns: list[float] = []

    for ticker in selected_tickers:
        entry_price = _price_at_or_before(prices, ticker, entry)
        exit_price = _price_at_or_before(prices, ticker, exit_)
        exit_used = exit_
        if pd.isna(exit_price) and ticker in prices.columns:
            # Delisted mid-period (e.g. acquired): value the position at its
            # last traded price and hold the proceeds as cash until the exit
            # date, instead of silently dropping it from the equal weight.
            held = prices.loc[
                (prices.index > entry) & (prices.index <= exit_), ticker
            ].dropna()
            if not held.empty:
                exit_used = pd.Timestamp(held.index[-1])
                exit_price = float(held.iloc[-1])
        stock_return = np.nan
        if pd.notna(entry_price) and pd.notna(exit_price) and entry_price > 0:
            stock_return = float(exit_price / entry_price - 1.0)
            returns.append(stock_return)
        rows.append(
            {
                "ticker": ticker,
                "entry_price": entry_price,
                "exit_date": exit_used.date().isoformat(),
                "exit_price": exit_price,
                "stock_return": stock_return,
            }
        )

    if not returns:
        return np.nan, rows
    return float(np.mean(returns)), rows


def _benchmark_return(
    adj_close: pd.DataFrame,
    benchmark: str,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> float:
    """Calculate benchmark return over a rebalance holding period."""

    if benchmark not in adj_close.columns:
        return np.nan
    entry_price = _price_at_or_before(adj_close, benchmark, entry_date)
    exit_price = _price_at_or_before(adj_close, benchmark, exit_date)
    if pd.isna(entry_price) or pd.isna(exit_price) or entry_price <= 0:
        return np.nan
    return float(exit_price / entry_price - 1.0)


def _nasdaq_excluded_from_api(top_n: int, basket: str = "open") -> list[str]:
    """Fetch a sister strategy basket from its dashboard API.

    The sister project recomputes its baskets on every request, so its live
    dashboard is fresher than its on-disk CSV (which only updates when its own
    backtest is re-run). ``basket`` is ``"open"`` for the held basket or
    ``"next"`` for the upcoming, signal-locked one. Returns an empty list if the
    server is unreachable or the basket is absent.
    """

    url = os.environ.get("NASDAQ_PICKS_URL", "http://127.0.0.1:8765/api/picks")
    try:
        with urllib.request.urlopen(url, timeout=4) as response:  # noqa: S310 - local loopback
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        LOGGER.info("Sister dashboard %s unavailable (%s); will fall back to CSV.", url, exc)
        return []
    picks = payload.get(basket) or []
    ordered = sorted(picks, key=lambda p: p.get("rank", 0))
    tickers = [str(p["ticker"]) for p in ordered if p.get("ticker")][:top_n]
    if tickers:
        LOGGER.info("Excluding sister live %s picks from %s: %s", basket, url, tickers)
    return tickers


def _nasdaq_history_from_api() -> dict[pd.Timestamp, list[str]]:
    """Fetch the sister strategy's completed baskets keyed by rebalance date.

    Same freshness rationale as :func:`_nasdaq_excluded_from_api`: the sister
    dashboard recomputes on every request, while its on-disk selections CSV only
    changes when its own backtest re-runs, so recent months are often missing
    from the CSV entirely. Returns an empty mapping if the server is unreachable.
    """

    url = os.environ.get("NASDAQ_PICKS_URL", "http://127.0.0.1:8765/api/picks")
    try:
        with urllib.request.urlopen(url, timeout=4) as response:  # noqa: S310 - local loopback
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        LOGGER.info("Sister dashboard %s unavailable (%s); will fall back to CSV.", url, exc)
        return {}
    ranked: dict[pd.Timestamp, list[tuple[int, str]]] = {}
    for row in payload.get("completed") or []:
        ticker = row.get("ticker")
        if not row.get("date") or not ticker:
            continue
        date = pd.Timestamp(row["date"]).normalize()
        ranked.setdefault(date, []).append((int(row.get("rank", 0)), str(ticker)))
    return {date: [ticker for _, ticker in sorted(rows)] for date, rows in ranked.items()}


def _read_nasdaq_excluded_tickers(top_n: int) -> list[str]:
    """Return the sister Nasdaq strategy's current top-N picks to exclude.

    Prefers the live dashboard (freshest), then falls back to the on-disk CSV.
    """

    live = _nasdaq_excluded_from_api(top_n)
    if live:
        return live

    path = Path(os.environ.get("NASDAQ_OPEN_PATH", str(DEFAULT_NASDAQ_OPEN_PATH)))
    if not path.exists():
        LOGGER.info("No Nasdaq open picks at %s; skipping overlap exclusion.", path)
        return []
    ndx = pd.read_csv(path)
    if ndx.empty or "ticker" not in ndx.columns:
        return []
    if "rebalance_date" in ndx.columns:
        latest = ndx["rebalance_date"].max()
        ndx = ndx[ndx["rebalance_date"] == latest]
    if "rank" in ndx.columns:
        ndx = ndx.sort_values("rank")
    LOGGER.info("Excluding sister CSV picks from %s (CSV fallback).", path)
    return ndx["ticker"].astype(str).head(top_n).tolist()


def _calculate_open_selections(
    config: BacktestConfig,
    membership: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    adj_close: pd.DataFrame,
    open_date: pd.Timestamp,
    excluded: list[str] | None = None,
) -> pd.DataFrame:
    """Calculate an open basket and month-to-date stock returns.

    When ``excluded`` is provided, those tickers are dropped from the ranking
    before taking the top N, so the ``rank`` column keeps each name's original
    S&P 500 rank (useful for showing how far the basket was backfilled).
    """

    as_of_date = adj_close.index[adj_close.index <= pd.Timestamp(config.end_date)].max()
    if pd.isna(as_of_date) or as_of_date < open_date:
        return pd.DataFrame()

    metadata = get_member_metadata(membership, open_date)
    eligible = get_eligible_universe(membership, open_date)
    scores = calculate_titan12_score(
        monthly_returns=monthly_returns,
        rebalance_date=open_date,
        lookback_months=config.lookback_months,
        weights=config.weights,
        eligible_tickers=eligible["ticker"].tolist(),
        metadata=metadata,
    )
    if excluded:
        ranked = rank_stocks_by_score(scores)
        selected = ranked[~ranked["ticker"].isin(excluded)].head(config.top_n).copy()
    else:
        selected = select_top_n(scores, config.top_n)
    rows: list[dict[str, object]] = []
    for _, row in selected.iterrows():
        ticker = row["ticker"]
        if ticker not in adj_close.columns:
            continue
        entry_price = adj_close.loc[open_date, ticker] if open_date in adj_close.index else np.nan
        as_of_price = adj_close.loc[as_of_date, ticker]
        if pd.isna(entry_price) or pd.isna(as_of_price) or entry_price <= 0:
            continue
        rows.append(
            {
                "rebalance_date": open_date.date().isoformat(),
                "as_of_date": as_of_date.date().isoformat(),
                "ticker": ticker,
                "company_name": row.get("company_name", ""),
                "sector": row.get("sector", "Unknown"),
                "rank": int(row["rank"]),
                "weighted_momentum_score": row["weighted_momentum_score"],
                "entry_price": float(entry_price),
                "as_of_price": float(as_of_price),
                "stock_return": float(as_of_price / entry_price - 1.0),
            }
        )
    return pd.DataFrame(rows)


def _calculate_next_selections(
    config: BacktestConfig,
    membership: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    adj_close: pd.DataFrame,
    excluded: list[str] | None = None,
) -> pd.DataFrame:
    """Score the upcoming rebalance once its signal is locked.

    The signal for the first trading day of a month uses only monthly returns
    completed before it, so it is fully determined by the close of the prior
    month's last session. When the latest priced day is that session (the next
    NYSE session falls in a new month), this returns the upcoming basket. The
    ``entry_price`` is that last close, a planning estimate only: the real fill
    is the next open. Returns an empty frame when the signal is not locked yet.
    """

    as_of_date = adj_close.index[adj_close.index <= pd.Timestamp(config.end_date)].max()
    if pd.isna(as_of_date):
        return pd.DataFrame()
    next_entry = next_session_after(as_of_date)
    if next_entry.to_period("M") == pd.Timestamp(as_of_date).to_period("M"):
        return pd.DataFrame()

    metadata = get_member_metadata(membership, next_entry)
    eligible = get_eligible_universe(membership, next_entry)
    scores = calculate_titan12_score(
        monthly_returns=monthly_returns,
        rebalance_date=next_entry,
        lookback_months=config.lookback_months,
        weights=config.weights,
        eligible_tickers=eligible["ticker"].tolist(),
        metadata=metadata,
    )
    ranked = rank_stocks_by_score(scores)
    if excluded:
        ranked = ranked[~ranked["ticker"].isin(excluded)]
    rows: list[dict[str, object]] = []
    for _, row in ranked.iterrows():
        if len(rows) == config.top_n:
            break
        ticker = row["ticker"]
        if ticker not in adj_close.columns:
            continue
        price = adj_close.loc[as_of_date, ticker]
        if pd.isna(price) or price <= 0:
            continue
        rows.append(
            {
                "rebalance_date": next_entry.date().isoformat(),
                "as_of_date": pd.Timestamp(as_of_date).date().isoformat(),
                "ticker": ticker,
                "company_name": row.get("company_name", ""),
                "sector": row.get("sector", "Unknown"),
                "rank": int(row["rank"]),
                "weighted_momentum_score": row["weighted_momentum_score"],
                "entry_price_estimate": float(price),
            }
        )
    return pd.DataFrame(rows)


def _calculate_leaderboard(
    config: BacktestConfig,
    membership: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    adj_close: pd.DataFrame,
    rank_date: pd.Timestamp,
    prev_date: pd.Timestamp | None = None,
    n: int = 20,
) -> pd.DataFrame:
    """Rank the top ``n`` names at ``rank_date`` with no overlap exclusion.

    The plain Titan-12 ranking, for manual review. ``held`` flags the baseline
    top ``config.top_n``. Trend columns use the latest close on or before
    ``config.end_date``: ``ret_1m`` (last 21 trading days) and ``off_6m_high``
    (versus the highest close of the last 126 trading days). With ``prev_date``
    it adds ``prev_rank`` (NaN when unranked then) and ``rank_change``
    (positive = climbed).
    """

    def ranked_at(date: pd.Timestamp) -> pd.DataFrame:
        eligible = get_eligible_universe(membership, date)
        return rank_stocks_by_score(
            calculate_titan12_score(
                monthly_returns=monthly_returns,
                rebalance_date=date,
                lookback_months=config.lookback_months,
                weights=config.weights,
                eligible_tickers=eligible["ticker"].tolist(),
                metadata=get_member_metadata(membership, date),
            )
        )

    ranked = ranked_at(rank_date)
    if ranked.empty:
        return pd.DataFrame()
    top = ranked[ranked["ticker"].isin(adj_close.columns)].head(n).copy()
    prices = adj_close.loc[adj_close.index <= pd.Timestamp(config.end_date), top["ticker"]].ffill()
    latest = prices.iloc[-1]
    prev_rank = pd.Series(dtype=float)
    if prev_date is not None:
        prev = ranked_at(prev_date)
        if not prev.empty:
            prev_rank = prev.set_index("ticker")["rank"].astype(float)
    top_prev = prev_rank.reindex(top["ticker"]).to_numpy()
    return pd.DataFrame(
        {
            "rank_date": pd.Timestamp(rank_date).date().isoformat(),
            "as_of_date": pd.Timestamp(prices.index[-1]).date().isoformat(),
            "rank": top["rank"].to_numpy(),
            "ticker": top["ticker"].to_numpy(),
            "company_name": top.get("company_name", pd.Series("", index=top.index)).to_numpy(),
            "sector": top.get("sector", pd.Series("Unknown", index=top.index)).to_numpy(),
            "weighted_momentum_score": top["weighted_momentum_score"].to_numpy(),
            "held": (top["rank"] <= config.top_n).to_numpy(),
            "prev_rank": top_prev,
            "rank_change": top_prev - top["rank"].to_numpy(),
            "latest_price": latest.to_numpy(),
            "ret_1m": (latest / prices.iloc[-22] - 1.0).to_numpy(),
            "off_6m_high": (latest / prices.iloc[-126:].max() - 1.0).to_numpy(),
        }
    )


def _prepare_membership(config: BacktestConfig) -> pd.DataFrame:
    """Load or bootstrap membership according to the configured mode."""

    if not config.membership_path.exists() and not config.use_historical_membership:
        return create_current_membership_file(config.membership_path)
    return load_sp500_membership(config.membership_path)


def run_backtest(
    config: BacktestConfig, test_results: str = "Not run by backtest command."
) -> dict[str, pd.DataFrame]:
    """Run the Titan-12 monthly rotation backtest and write all outputs.

    Args:
        config: Backtest settings.
        test_results: Test-suite outcome to record in summary.md.
    """

    ensure_directories(config)
    setup_logging(config.backtest_log_path)
    LOGGER.info("Starting Titan-12 run with config: %s", asdict(config))

    membership = _prepare_membership(config)
    membership_tickers = sorted(membership["ticker"].dropna().unique().tolist())
    tickers = sorted(set(membership_tickers + [config.benchmark]))
    if config.include_gspc:
        tickers.append("^GSPC")

    price_data, download_issues = download_price_data(
        tickers=tickers,
        start_date=config.start_date,
        end_date=config.end_date,
        raw_price_dir=config.raw_price_dir,
        refresh=config.refresh_data,
    )
    quality_issues = download_issues.to_dict("records") if not download_issues.empty else []

    adj_close = prices_to_adj_close_frame(price_data)
    if adj_close.empty:
        raise RuntimeError("No adjusted close data available for the requested run.")

    first_trading_days = [
        date
        for date in get_first_trading_days(adj_close)
        if pd.Timestamp(config.start_date) <= date <= pd.Timestamp(config.end_date)
    ]
    if len(first_trading_days) < 2:
        raise RuntimeError("Need at least two rebalance dates to run the backtest.")

    month_end_prices = calculate_month_end_prices(
        adj_close.drop(columns=[config.benchmark, "^GSPC"], errors="ignore")
    )
    monthly_returns = calculate_monthly_returns(month_end_prices)

    portfolio_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []
    previous_holdings: set[str] = set()
    portfolio_value = float(config.initial_capital)
    spy_value = float(config.initial_capital)
    cost_rate = (config.transaction_cost_bps + config.slippage_bps) / 10000.0

    for entry_date, exit_date in zip(first_trading_days[:-1], first_trading_days[1:]):
        eligible = get_eligible_universe(membership, entry_date)
        metadata = get_member_metadata(membership, entry_date)
        scores = calculate_titan12_score(
            monthly_returns=monthly_returns,
            rebalance_date=entry_date,
            lookback_months=config.lookback_months,
            weights=config.weights,
            eligible_tickers=eligible["ticker"].tolist(),
            metadata=metadata,
            quality_issues=quality_issues,
        )
        selected = select_top_n(scores, config.top_n)
        selected_tickers = selected["ticker"].tolist() if not selected.empty else []
        if len(selected_tickers) < config.top_n:
            append_quality_issue(
                quality_issues,
                "",
                "insufficient_selection_count",
                f"Selected {len(selected_tickers)} tickers for top_n={config.top_n}.",
                entry_date,
            )
            if not selected_tickers:
                previous_holdings = set()
                continue

        gross_return, stock_details = calculate_portfolio_return(
            selected_tickers, adj_close, entry_date, exit_date
        )
        if pd.isna(gross_return):
            append_quality_issue(
                quality_issues,
                "",
                "missing_period_prices",
                "Could not calculate portfolio return for selected tickers.",
                entry_date,
            )
            previous_holdings = set(selected_tickers)
            continue

        turnover = calculate_turnover(previous_holdings, selected_tickers)
        transaction_cost = turnover * (config.transaction_cost_bps / 10000.0)
        slippage_cost = turnover * (config.slippage_bps / 10000.0)
        net_return = gross_return - transaction_cost - slippage_cost
        spy_return = _benchmark_return(adj_close, config.benchmark, entry_date, exit_date)
        portfolio_value *= 1.0 + net_return
        if pd.notna(spy_return):
            spy_value *= 1.0 + spy_return

        details_by_ticker = {row["ticker"]: row for row in stock_details}
        for _, row in selected.iterrows():
            detail = details_by_ticker.get(row["ticker"], {})
            selection_rows.append(
                {
                    "rebalance_date": entry_date.date().isoformat(),
                    "ticker": row["ticker"],
                    "company_name": row.get("company_name", ""),
                    "sector": row.get("sector", "Unknown"),
                    "rank": int(row["rank"]),
                    "weighted_momentum_score": row["weighted_momentum_score"],
                    "weight": row["weight"],
                    "entry_price": detail.get("entry_price", np.nan),
                    "exit_date": detail.get("exit_date", exit_date.date().isoformat()),
                    "exit_price": detail.get("exit_price", np.nan),
                    "stock_return": detail.get("stock_return", np.nan),
                }
            )

        portfolio_rows.append(
            {
                "rebalance_date": entry_date.date().isoformat(),
                "next_rebalance_date": exit_date.date().isoformat(),
                "selected_tickers": ",".join(selected_tickers),
                "portfolio_return_gross": gross_return,
                "transaction_cost": transaction_cost,
                "slippage_cost": slippage_cost,
                "portfolio_return_net": net_return,
                "spy_return": spy_return,
                "excess_return_vs_spy": net_return - spy_return
                if pd.notna(spy_return)
                else np.nan,
                "portfolio_value": portfolio_value,
                "spy_value": spy_value,
                "turnover": turnover,
            }
        )
        previous_holdings = set(selected_tickers)

    monthly_selections = pd.DataFrame(selection_rows)
    portfolio_returns = pd.DataFrame(portfolio_rows)
    summary_stats = calculate_summary_stats(portfolio_returns)
    strategy_comparison = pd.DataFrame()
    if not portfolio_returns.empty:
        strategy_comparison = calculate_strategy_comparison(
            portfolio_returns,
            _price_at_or_before(
                adj_close,
                config.benchmark,
                pd.Timestamp(portfolio_returns["rebalance_date"].iloc[0]),
            ),
            _price_at_or_before(
                adj_close,
                config.benchmark,
                pd.Timestamp(
                    portfolio_returns["next_rebalance_date"].iloc[-1]
                ),
            ),
            benchmark_label=config.benchmark,
        )
    data_quality = pd.DataFrame(quality_issues)

    save_csv(monthly_selections, config.output_dir / "monthly_selections.csv")
    save_csv(portfolio_returns, config.output_dir / "portfolio_returns.csv")
    save_csv(summary_stats, config.output_dir / "summary_stats.csv")
    save_csv(data_quality, config.data_quality_path)
    create_all_charts(
        portfolio_returns,
        monthly_selections,
        config.chart_dir,
        benchmark_label=config.benchmark,
    )
    open_selections = pd.DataFrame()
    final_selections = pd.DataFrame()
    nasdaq_excluded: list[str] = []
    if first_trading_days:
        open_date = first_trading_days[-1]
        open_selections = _calculate_open_selections(
            config, membership, monthly_returns, adj_close, open_date
        )
        # Final basket: drop the sister Nasdaq strategy's current top picks and
        # backfill from the next-highest S&P names for cross-project diversification.
        # The Nasdaq-100 universe run is itself a Nasdaq strategy, so it skips this.
        if config.universe == "sp500":
            nasdaq_excluded = _read_nasdaq_excluded_tickers(config.top_n)
        final_selections = _calculate_open_selections(
            config, membership, monthly_returns, adj_close, open_date, excluded=nasdaq_excluded
        )
        plot_recent_rebalances(
            monthly_selections,
            portfolio_returns,
            config.chart_dir / "recent_rebalances.png",
            open_selections=open_selections,
            benchmark_label=config.benchmark,
        )
        save_csv(open_selections, config.output_dir / "open_rebalance_picks.csv")
        save_csv(final_selections, config.output_dir / "final_rebalance_picks.csv")

    # Upcoming basket, once the prior month's last close locks its signal. Both
    # strategies rebalance on the same day, so the overlap exclusion uses the
    # sister's *next* basket, not the one it holds now.
    next_selections = _calculate_next_selections(
        config, membership, monthly_returns, adj_close
    )
    next_final_selections = pd.DataFrame()
    next_excluded: list[str] = []
    if not next_selections.empty:
        if config.universe == "sp500":
            next_excluded = _nasdaq_excluded_from_api(config.top_n, basket="next")
            if not next_excluded:
                LOGGER.warning(
                    "Sister next basket unavailable; next final basket has no overlap exclusion."
                )
        next_final_selections = _calculate_next_selections(
            config, membership, monthly_returns, adj_close, excluded=next_excluded
        )
    save_csv(next_selections, config.output_dir / "next_rebalance_picks.csv")
    save_csv(next_final_selections, config.output_dir / "next_final_rebalance_picks.csv")

    # Top-20 ranking, without the Nasdaq exclusion: the upcoming rebalance once
    # it is locked, else the open one, compared with the rebalance before it.
    leaderboard = pd.DataFrame()
    if first_trading_days:
        if not next_selections.empty:
            rank_date = pd.Timestamp(next_selections["rebalance_date"].iloc[0])
            prev_date = first_trading_days[-1]
        else:
            rank_date = first_trading_days[-1]
            prev_date = first_trading_days[-2] if len(first_trading_days) >= 2 else None
        leaderboard = _calculate_leaderboard(
            config, membership, monthly_returns, adj_close, rank_date, prev_date
        )
    save_csv(leaderboard, config.output_dir / "top20_ranking.csv")
    write_summary_markdown(
        config.summary_path,
        config,
        summary_stats,
        portfolio_returns,
        monthly_selections,
        data_quality,
        test_results=test_results,
        open_selections=open_selections,
        final_selections=final_selections,
        excluded_tickers=nasdaq_excluded,
        next_selections=next_selections,
        next_final_selections=next_final_selections,
        next_excluded_tickers=next_excluded,
        strategy_comparison=strategy_comparison,
        data_quality_path=config.data_quality_path.relative_to(
            config.summary_path.parent
        ),
    )

    LOGGER.info("Completed Titan-12 run with %s rebalance periods.", len(portfolio_returns))
    return {
        "monthly_selections": monthly_selections,
        "portfolio_returns": portfolio_returns,
        "summary_stats": summary_stats,
        "data_quality": data_quality,
    }
