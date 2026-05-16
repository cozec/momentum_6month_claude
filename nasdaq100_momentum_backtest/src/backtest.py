"""Core backtest loop for the Nasdaq-100 momentum rotation strategy.

The strategy rebalances on the first trading day of each month:

1. Compute the previous ``lookback_months`` completed monthly returns
   for each eligible ticker.
2. Rank by the chosen score method (average or compound).
3. Hold the top ``top_n`` names at equal weight for one month.

Trades incur a per-side cost equal to ``transaction_cost_bps`` plus
``slippage_bps``. Turnover is the L1 difference between the new and
prior weight vectors; the dollar cost is ``turnover * cost_rate``.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import BacktestConfig
from .download_data import download_price_data
from .membership import get_eligible_universe, load_nasdaq100_membership
from .signals import (
    calculate_momentum_scores,
    calculate_monthly_returns,
    get_first_trading_days,
    select_top_n,
)
from .utils import get_logger, to_business_date

LOGGER = get_logger("backtest")


def _price_on_or_before(prices: pd.Series, date: pd.Timestamp) -> Optional[float]:
    """Return the price at ``date`` or the most recent trading day before."""
    aligned = prices.loc[:date].dropna()
    if aligned.empty:
        return None
    return float(aligned.iloc[-1])


def calculate_portfolio_return(
    selected_tickers: List[str],
    prices: pd.DataFrame,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> Tuple[float, Dict[str, float], Dict[str, float], Dict[str, float]]:
    """Return the equal-weight gross portfolio return over the holding period.

    Returns
    -------
    portfolio_return : float
    entries : dict[ticker -> entry_price]
    exits : dict[ticker -> exit_price]
    stock_returns : dict[ticker -> per-ticker holding return]
    """
    if not selected_tickers:
        return 0.0, {}, {}, {}

    weight = 1.0 / len(selected_tickers)
    entries: Dict[str, float] = {}
    exits: Dict[str, float] = {}
    stock_returns: Dict[str, float] = {}

    port_return = 0.0
    for ticker in selected_tickers:
        if ticker not in prices.columns:
            continue
        series = prices[ticker]
        entry_price = _price_on_or_before(series, entry_date)
        exit_price = _price_on_or_before(series, exit_date)
        if entry_price is None or exit_price is None or entry_price == 0:
            continue
        stock_ret = exit_price / entry_price - 1.0
        entries[ticker] = entry_price
        exits[ticker] = exit_price
        stock_returns[ticker] = stock_ret
        port_return += weight * stock_ret

    return port_return, entries, exits, stock_returns


def _build_membership(config: BacktestConfig) -> pd.DataFrame:
    """Construct (or load) the membership table used to gate eligibility."""
    if config.use_historical_membership:
        return load_nasdaq100_membership()
    # Build an in-memory current-snapshot membership table so the rest of
    # the code path is identical.
    df = pd.DataFrame(
        {
            "ticker": [t.upper() for t in config.tickers],
            "start_date": pd.Timestamp("2000-01-01"),
            "end_date": pd.NaT,
        }
    )
    return df


def run_backtest(config: BacktestConfig) -> Dict[str, pd.DataFrame]:
    """Run the monthly momentum rotation backtest.

    Returns a dict with keys ``selections``, ``portfolio_returns``,
    ``equity``, and ``prices``.
    """
    LOGGER.info("Starting backtest with config: %s", asdict(config))

    universe_tickers = sorted(set(t.upper() for t in config.tickers))
    benchmark = config.benchmark.upper()
    secondary = (config.secondary_benchmark or "").upper()
    extras = {benchmark}
    if secondary:
        extras.add(secondary)
    all_tickers = sorted(set(universe_tickers) | extras)

    prices = download_price_data(
        all_tickers,
        config.start_date,
        config.end_date,
        force_refresh=config.force_refresh,
    )
    LOGGER.info(
        "Downloaded %d trading days for %d tickers",
        len(prices),
        prices.shape[1],
    )

    membership_df = _build_membership(config)

    monthly_returns = calculate_monthly_returns(prices)
    first_days = get_first_trading_days(prices)
    if len(first_days) < 2:
        raise RuntimeError("Not enough trading data for any rebalance.")

    # We can only start trading once we have lookback_months of completed
    # monthly returns available.
    start_threshold = to_business_date(config.start_date) + pd.DateOffset(
        months=config.lookback_months + 1
    )
    rebalance_days = [d for d in first_days if d >= start_threshold]
    # Hold each position for ``rebalance_period_months`` months — keep
    # every Nth first-trading-day in the schedule.
    period = max(1, int(config.rebalance_period_months))
    if period > 1:
        rebalance_days = [d for i, d in enumerate(rebalance_days) if i % period == 0]
    if len(rebalance_days) < 2:
        raise RuntimeError("Not enough rebalance dates after warm-up period.")

    cost_per_side = config.transaction_cost_rate() + config.slippage_rate()

    selection_rows: List[dict] = []
    return_rows: List[dict] = []

    prior_weights: Dict[str, float] = {}
    portfolio_value = config.initial_capital
    qqq_value = config.initial_capital
    tqqq_value = config.initial_capital
    has_secondary = bool(secondary) and secondary in prices.columns

    excluded_from_universe = {benchmark}
    if secondary:
        excluded_from_universe.add(secondary)

    for i in range(len(rebalance_days) - 1):
        entry_date = rebalance_days[i]
        exit_date = rebalance_days[i + 1]

        available = [t for t in prices.columns if t not in excluded_from_universe]
        eligible = get_eligible_universe(
            membership_df, entry_date, available_tickers=available
        )

        scores = calculate_momentum_scores(
            monthly_returns[eligible] if eligible else monthly_returns.iloc[:, :0],
            entry_date,
            lookback_months=config.lookback_months,
            score_method=config.score_method,
        )

        selected = select_top_n(scores, n=config.top_n)
        if not selected:
            LOGGER.warning("No eligible names on %s; staying in cash", entry_date.date())
            new_weights: Dict[str, float] = {}
            gross_return = 0.0
            entries: Dict[str, float] = {}
            exits: Dict[str, float] = {}
            stock_returns: Dict[str, float] = {}
        else:
            new_weights = {t: 1.0 / len(selected) for t in selected}
            gross_return, entries, exits, stock_returns = calculate_portfolio_return(
                selected, prices, entry_date, exit_date
            )

        turnover = _compute_turnover(prior_weights, new_weights)
        trade_cost = turnover * cost_per_side
        # Apportion the cost between transaction cost and slippage for the
        # output file, in the same proportion as the inputs.
        if cost_per_side > 0:
            transaction_cost = trade_cost * (
                config.transaction_cost_rate() / cost_per_side
            )
            slippage_cost = trade_cost - transaction_cost
        else:
            transaction_cost = 0.0
            slippage_cost = 0.0
        net_return = gross_return - trade_cost

        qqq_entry = _price_on_or_before(prices[benchmark], entry_date)
        qqq_exit = _price_on_or_before(prices[benchmark], exit_date)
        qqq_return = (
            qqq_exit / qqq_entry - 1.0
            if qqq_entry and qqq_exit
            else 0.0
        )

        if has_secondary:
            tqqq_entry = _price_on_or_before(prices[secondary], entry_date)
            tqqq_exit = _price_on_or_before(prices[secondary], exit_date)
            tqqq_return = (
                tqqq_exit / tqqq_entry - 1.0
                if tqqq_entry and tqqq_exit
                else 0.0
            )
        else:
            tqqq_return = float("nan")

        portfolio_value *= 1.0 + net_return
        qqq_value *= 1.0 + qqq_return
        if has_secondary and not np.isnan(tqqq_return):
            tqqq_value *= 1.0 + tqqq_return

        for rank, ticker in enumerate(selected, start=1):
            selection_rows.append(
                {
                    "rebalance_date": entry_date,
                    "ticker": ticker,
                    "rank": rank,
                    "momentum_score": float(scores.get(ticker, np.nan)),
                    "weight": new_weights[ticker],
                    "entry_price": entries.get(ticker, np.nan),
                    "exit_date": exit_date,
                    "exit_price": exits.get(ticker, np.nan),
                    "stock_return": stock_returns.get(ticker, np.nan),
                }
            )

        return_rows.append(
            {
                "rebalance_date": entry_date,
                "next_rebalance_date": exit_date,
                "portfolio_return_gross": gross_return,
                "transaction_cost": transaction_cost,
                "slippage_cost": slippage_cost,
                "portfolio_return_net": net_return,
                "qqq_return": qqq_return,
                "tqqq_return": tqqq_return,
                "excess_return": net_return - qqq_return,
                "excess_return_vs_tqqq": net_return - tqqq_return
                if not np.isnan(tqqq_return)
                else np.nan,
                "portfolio_value": portfolio_value,
                "qqq_value": qqq_value,
                "tqqq_value": tqqq_value if has_secondary else np.nan,
                "turnover": turnover,
            }
        )

        prior_weights = new_weights

    selections = pd.DataFrame(selection_rows)
    portfolio_returns = pd.DataFrame(return_rows)

    LOGGER.info("Completed %d rebalances", len(portfolio_returns))

    # The completed loop pairs (entry=rebalance_days[i], exit=rebalance_days[i+1])
    # for i in [0, len-1), so rebalance_days[-1] is only ever used as an exit.
    # That date is the entry of the currently-open holding period whose exit
    # (next month's first trading day) is still in the future.
    open_position = pd.DataFrame()
    next_position = pd.DataFrame()
    if len(rebalance_days) >= 1:
        open_entry = rebalance_days[-1]
        open_position = compute_open_position(
            prices, monthly_returns, config, open_entry
        )
        if not open_position.empty:
            LOGGER.info(
                "Open position (entry %s, MTD as of %s): %s",
                open_entry.date(),
                pd.Timestamp(open_position["exit_date"].iloc[0]).date(),
                list(open_position["ticker"]),
            )
        # Once the last trading day of the current rebalance period has
        # passed, we can already score the *upcoming* entry — that's the
        # "Next picks" preview the dashboard shows on Friday evening
        # before the new month begins.
        next_position = compute_next_position(
            prices, monthly_returns, config, open_entry
        )
        if not next_position.empty:
            LOGGER.info(
                "Next position (planned entry %s): %s",
                pd.Timestamp(next_position["rebalance_date"].iloc[0]).date(),
                list(next_position["ticker"]),
            )

    return {
        "selections": selections,
        "portfolio_returns": portfolio_returns,
        "prices": prices,
        "monthly_returns": monthly_returns,
        "open_position": open_position,
        "next_position": next_position,
    }


def _compute_turnover(
    prior: Dict[str, float], new: Dict[str, float]
) -> float:
    """L1 turnover between two weight dicts (sum of absolute weight changes)."""
    tickers = set(prior) | set(new)
    return float(sum(abs(new.get(t, 0.0) - prior.get(t, 0.0)) for t in tickers))


def _predict_next_first_trading_day(
    current_entry: pd.Timestamp, period_months: int
) -> pd.Timestamp:
    """Predict the next rebalance entry date.

    Uses generic business-day logic — rolls the 1st of the target month
    forward over weekends. NYSE holidays falling on the 1st (very rare:
    only New Year's Day on a weekday matters here) can shift the actual
    first trading day by 1–2 days, but scoring is robust to that
    because ``calculate_momentum_scores`` keys on ``index < asof``.
    """
    target = current_entry + pd.DateOffset(months=int(period_months))
    candidate = pd.Timestamp(target.year, target.month, 1)
    while candidate.weekday() >= 5:  # Sat=5, Sun=6
        candidate += pd.Timedelta(days=1)
    return candidate


def compute_next_position(
    prices: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    config: BacktestConfig,
    current_open_entry,
) -> pd.DataFrame:
    """Score the *upcoming* rebalance, if the signal is already locked.

    The signal for entry date ``E`` is locked once we have prices through
    the last trading day of the month preceding ``E``. Concretely, after
    the close of Friday 2026-05-29 (last trading day of May) the picks
    that the model will enter on Mon 2026-06-01 are fully determined.

    This helper:
      * predicts the next entry date as ``current_open_entry +
        rebalance_period_months months → first business day``,
      * checks the locked-signal condition,
      * if locked, computes scores at that next entry date and returns a
        DataFrame in the same shape as ``compute_open_position``, with
        ``is_next=True`` and ``stock_return=0.0`` (we haven't entered
        yet; ``entry_price`` is the most recent close as a planning
        estimate).
      * if not locked, returns an empty DataFrame.
    """
    if prices.empty or monthly_returns.empty:
        return pd.DataFrame()

    benchmark = config.benchmark.upper()
    secondary = (config.secondary_benchmark or "").upper()
    excluded = {benchmark}
    if secondary:
        excluded.add(secondary)

    period = max(1, int(config.rebalance_period_months))
    current_entry = to_business_date(current_open_entry)
    next_entry = _predict_next_first_trading_day(current_entry, period)

    # Signal-locked check: we need data through the last business day of
    # the calendar month before next_entry.
    last_required = next_entry - pd.offsets.BDay(1)
    if pd.Timestamp(prices.index.max()) < last_required:
        return pd.DataFrame()

    available = [t for t in prices.columns if t not in excluded]
    membership_df = _build_membership(config)
    eligible = get_eligible_universe(
        membership_df, next_entry, available_tickers=available
    )
    scores = calculate_momentum_scores(
        monthly_returns[eligible] if eligible else monthly_returns.iloc[:, :0],
        next_entry,
        lookback_months=config.lookback_months,
        score_method=config.score_method,
    )
    selected = select_top_n(scores, n=config.top_n)
    if not selected:
        return pd.DataFrame()

    latest_date = pd.Timestamp(prices.index.max())
    rows = []
    for rank, ticker in enumerate(selected, start=1):
        series = prices[ticker]
        entry_estimate = _price_on_or_before(series, latest_date)
        if entry_estimate is None or entry_estimate == 0:
            continue
        rows.append({
            "rebalance_date": next_entry,
            "ticker": ticker,
            "rank": rank,
            "momentum_score": float(scores.get(ticker, np.nan)),
            "weight": 1.0 / len(selected),
            "entry_price": entry_estimate,    # planning estimate
            "exit_date": latest_date,         # "as-of" latest known price
            "exit_price": entry_estimate,     # same as entry → return = 0
            "stock_return": 0.0,
            "is_next": True,
        })
    return pd.DataFrame(rows)


def compute_open_position(
    prices: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    config: BacktestConfig,
    entry_date,
) -> pd.DataFrame:
    """Score and price an open (still-held) rebalance at ``entry_date``.

    The standard backtest loop only emits *completed* holding periods. This
    helper exposes the picks for the period that began on ``entry_date``
    but whose exit (the next month's first trading day) hasn't happened
    yet. The exit price is the most recent close available in ``prices``,
    so the per-stock return is mark-to-market (MTD) rather than the
    realized one-month return.

    Returns a DataFrame with the same columns as ``monthly_selections.csv``
    plus a boolean ``is_open`` flag.
    """
    benchmark = config.benchmark.upper()
    secondary = (config.secondary_benchmark or "").upper()
    excluded = {benchmark}
    if secondary:
        excluded.add(secondary)

    entry_date = to_business_date(entry_date)
    available = [t for t in prices.columns if t not in excluded]

    membership_df = _build_membership(config)
    eligible = get_eligible_universe(
        membership_df, entry_date, available_tickers=available
    )

    scores = calculate_momentum_scores(
        monthly_returns[eligible] if eligible else monthly_returns.iloc[:, :0],
        entry_date,
        lookback_months=config.lookback_months,
        score_method=config.score_method,
    )
    selected = select_top_n(scores, n=config.top_n)
    if not selected:
        return pd.DataFrame()

    latest_date = pd.Timestamp(prices.index.max())
    rows = []
    for rank, ticker in enumerate(selected, start=1):
        series = prices[ticker]
        entry_price = _price_on_or_before(series, entry_date)
        latest_price = _price_on_or_before(series, latest_date)
        if entry_price is None or latest_price is None or entry_price == 0:
            continue
        rows.append({
            "rebalance_date": entry_date,
            "ticker": ticker,
            "rank": rank,
            "momentum_score": float(scores.get(ticker, np.nan)),
            "weight": 1.0 / len(selected),
            "entry_price": entry_price,
            "exit_date": latest_date,
            "exit_price": latest_price,
            "stock_return": latest_price / entry_price - 1.0,
            "is_open": True,
        })
    return pd.DataFrame(rows)
