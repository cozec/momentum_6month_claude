"""Signal generation for Titan-12 weighted momentum."""

from __future__ import annotations

import logging
from collections.abc import Iterable

import numpy as np
import pandas as pd

from src.utils import append_quality_issue


LOGGER = logging.getLogger(__name__)


def prices_to_adj_close_frame(price_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Combine per-ticker price frames into a wide adjusted-close dataframe."""

    series = {}
    for ticker, prices in price_data.items():
        if "Adj Close" in prices.columns:
            series[ticker] = prices["Adj Close"].rename(ticker)
    if not series:
        return pd.DataFrame()
    frame = pd.concat(series.values(), axis=1).sort_index()
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    return frame


def get_first_trading_days(price_df: pd.DataFrame) -> list[pd.Timestamp]:
    """Return the first available trading day for each month in a price frame."""

    if price_df.empty:
        return []
    dates = pd.Series(pd.to_datetime(price_df.index), index=price_df.index)
    first_dates = dates.groupby(dates.dt.to_period("M")).min()
    return [pd.Timestamp(value).normalize() for value in first_dates.tolist()]


def calculate_month_end_prices(price_df: pd.DataFrame) -> pd.DataFrame:
    """Convert daily adjusted close prices to month-end prices.

    The returned index is the last available trading date for each calendar
    month, not a synthetic calendar month-end date. That makes the rows auditable
    against the underlying daily price cache.
    """

    if price_df.empty:
        return pd.DataFrame()
    monthly = price_df.sort_index().resample("ME").last()
    monthly.index = monthly.index.normalize()
    return monthly


def calculate_monthly_returns(month_end_prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate simple monthly returns from month-end adjusted prices."""

    if month_end_prices.empty:
        return pd.DataFrame()
    return month_end_prices.sort_index().pct_change(fill_method=None)


def completed_monthly_returns(
    monthly_returns: pd.DataFrame,
    rebalance_date: object,
    lookback_months: int,
) -> pd.DataFrame:
    """Return monthly returns completed before a rebalance date."""

    rebalance = pd.Timestamp(rebalance_date).normalize()
    completed = monthly_returns.loc[monthly_returns.index < rebalance].dropna(how="all")
    return completed.tail(lookback_months)


def calculate_titan12_score(
    monthly_returns: pd.DataFrame,
    rebalance_date: object,
    lookback_months: int = 12,
    weights: Iterable[float] | None = None,
    eligible_tickers: Iterable[str] | None = None,
    metadata: pd.DataFrame | None = None,
    quality_issues: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    """Calculate no-lookahead Titan-12 weighted momentum scores.

    Parameters
    ----------
    monthly_returns
        Wide dataframe of monthly returns indexed by month-end date.
    rebalance_date
        First trading day on which the score will be used.
    lookback_months
        Number of completed monthly returns required.
    weights
        Momentum weights from oldest to newest. Defaults to 1..lookback_months.
    eligible_tickers
        Optional ticker universe to score. If omitted, all columns are used.
    metadata
        Optional ticker-indexed dataframe with company_name and sector columns.
    quality_issues
        Optional mutable list that receives exclusion records.

    Returns
    -------
    pandas.DataFrame
        Ranked score input table with one row per ticker that has enough valid
        history. It includes the lookback return columns used for auditability.
    """

    if weights is None:
        weights_array = np.arange(1, lookback_months + 1, dtype=float)
    else:
        weights_array = np.array(list(weights), dtype=float)
    if len(weights_array) != lookback_months:
        raise ValueError("weights length must match lookback_months")

    rebalance = pd.Timestamp(rebalance_date).normalize()
    tickers = list(eligible_tickers) if eligible_tickers is not None else list(monthly_returns)
    window = completed_monthly_returns(monthly_returns, rebalance, lookback_months)
    rows: list[dict[str, object]] = []
    return_columns = [f"return_m{i}" for i in range(1, lookback_months + 1)]

    for ticker in tickers:
        if ticker not in monthly_returns.columns:
            if quality_issues is not None:
                append_quality_issue(
                    quality_issues,
                    ticker,
                    "missing_price_history",
                    "Ticker not present in monthly returns.",
                    rebalance,
                )
            continue
        ticker_returns = window[ticker].dropna()
        if len(ticker_returns) < lookback_months:
            if quality_issues is not None:
                append_quality_issue(
                    quality_issues,
                    ticker,
                    "insufficient_history",
                    f"Needed {lookback_months} monthly returns, found {len(ticker_returns)}.",
                    rebalance,
                )
            continue

        values = ticker_returns.tail(lookback_months).to_numpy(dtype=float)
        score = float(np.dot(weights_array, values))
        company_name = ""
        sector = "Unknown"
        if metadata is not None and ticker in metadata.index:
            company_name = metadata.loc[ticker, "company_name"]
            sector = metadata.loc[ticker, "sector"]
        row = {
            "rebalance_date": rebalance.date().isoformat(),
            "ticker": ticker,
            "company_name": company_name,
            "sector": sector,
            "weighted_momentum_score": score,
            "lookback_start": ticker_returns.tail(lookback_months).index[0].date().isoformat(),
            "lookback_end": ticker_returns.tail(lookback_months).index[-1].date().isoformat(),
        }
        row.update(dict(zip(return_columns, values)))
        rows.append(row)

    return pd.DataFrame(rows)


def rank_stocks_by_score(scores: pd.DataFrame) -> pd.DataFrame:
    """Rank stocks by descending weighted momentum score."""

    if scores.empty:
        return scores.copy()
    ranked = scores.sort_values(
        ["weighted_momentum_score", "ticker"], ascending=[False, True]
    ).reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def select_top_n(scores: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Return the top-N ranked stocks with equal target weights."""

    ranked = rank_stocks_by_score(scores)
    selected = ranked.head(n).copy()
    if selected.empty:
        selected["weight"] = pd.Series(dtype=float)
    else:
        selected["weight"] = 1.0 / len(selected)
    return selected
