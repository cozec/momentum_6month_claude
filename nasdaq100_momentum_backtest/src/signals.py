"""Signal calculations for the momentum rotation strategy.

The momentum score is the average of the previous ``lookback_months``
**completed** monthly returns. The current (partial) month is never
included, eliminating lookahead bias.
"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from .utils import to_business_date


def get_first_trading_days(price_df: pd.DataFrame) -> List[pd.Timestamp]:
    """Return the first trading day of each month in ``price_df``."""
    if price_df.empty:
        return []
    idx = pd.DatetimeIndex(price_df.index).sort_values()
    grouped = pd.Series(idx, index=idx).groupby(
        [idx.year, idx.month]
    ).min()
    return [pd.Timestamp(d) for d in grouped.tolist()]


def calculate_monthly_returns(price_df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily adjusted close prices to month-end and compute returns.

    The returned DataFrame is indexed by month-end timestamps and has
    one column per ticker.
    """
    if price_df.empty:
        return price_df.copy()
    monthly = price_df.resample("ME").last()
    returns = monthly.pct_change()
    return returns


def calculate_momentum_scores(
    monthly_returns: pd.DataFrame,
    rebalance_date,
    lookback_months: int = 6,
    score_method: str = "average_monthly_return",
) -> pd.Series:
    """Compute momentum scores using only completed monthly returns.

    Parameters
    ----------
    monthly_returns : pd.DataFrame
        Output of :func:`calculate_monthly_returns`.
    rebalance_date : date-like
        The first trading day of the rebalance month. Only monthly
        returns whose month-end is strictly before this date are
        included.
    lookback_months : int
        Number of completed monthly returns to use.
    score_method : str
        Either ``"average_monthly_return"`` or ``"compound_6m_return"``.

    Returns
    -------
    pd.Series
        Momentum score per ticker. Tickers with fewer than
        ``lookback_months`` valid returns are excluded.
    """
    if monthly_returns.empty:
        return pd.Series(dtype=float)

    asof = to_business_date(rebalance_date)
    # Use only month-end returns strictly before the rebalance date so
    # the current partial month is excluded.
    completed = monthly_returns.loc[monthly_returns.index < asof]
    if completed.empty:
        return pd.Series(dtype=float)

    window = completed.tail(lookback_months)
    if len(window) < lookback_months:
        return pd.Series(dtype=float)

    valid_counts = window.notna().sum(axis=0)
    valid_tickers = valid_counts[valid_counts >= lookback_months].index

    window = window[valid_tickers]
    if score_method == "average_monthly_return":
        scores = window.mean(axis=0)
    elif score_method == "compound_6m_return":
        scores = (1.0 + window).prod(axis=0) - 1.0
    else:
        raise ValueError(f"Unknown score_method: {score_method!r}")

    scores = scores.replace([np.inf, -np.inf], np.nan).dropna()
    return scores.sort_values(ascending=False)


def select_top_n(momentum_scores: pd.Series, n: int = 3) -> List[str]:
    """Return the tickers of the top ``n`` momentum scores (descending)."""
    if momentum_scores.empty:
        return []
    return momentum_scores.sort_values(ascending=False).head(n).index.tolist()
