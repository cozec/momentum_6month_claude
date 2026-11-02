"""Tests for Titan-12 signal calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.signals import (
    calculate_month_end_prices,
    calculate_monthly_returns,
    calculate_titan12_score,
    get_first_trading_days,
    select_top_n,
)


def test_monthly_return_calculation() -> None:
    """Month-end prices should produce simple percent returns."""

    daily = pd.DataFrame(
        {"AAA": [10.0, 11.0, 12.0, 15.0]},
        index=pd.to_datetime(["2024-01-02", "2024-01-31", "2024-02-01", "2024-02-29"]),
    )
    month_end = calculate_month_end_prices(daily)
    returns = calculate_monthly_returns(month_end)
    assert returns.loc[pd.Timestamp("2024-02-29"), "AAA"] == (15.0 / 11.0) - 1.0


def test_titan12_score_uses_completed_months_only() -> None:
    """A rebalance in February must not use February's current-month return."""

    dates = pd.date_range("2023-01-31", periods=14, freq="ME")
    monthly_returns = pd.DataFrame(
        {"AAA": np.arange(1, 15, dtype=float) / 100.0},
        index=dates,
    )
    scores = calculate_titan12_score(
        monthly_returns,
        rebalance_date="2024-02-01",
        lookback_months=12,
        weights=range(1, 13),
    )
    expected_values = np.arange(2, 14, dtype=float) / 100.0
    expected_score = float(np.dot(np.arange(1, 13), expected_values))
    assert scores.loc[0, "weighted_momentum_score"] == expected_score
    assert scores.loc[0, "lookback_end"] == "2024-01-31"


def test_select_top_n_ranks_descending() -> None:
    """Top-N selection should choose the highest scores with equal weights."""

    scores = pd.DataFrame(
        {
            "ticker": ["CCC", "AAA", "BBB"],
            "weighted_momentum_score": [0.2, 0.3, 0.1],
        }
    )
    selected = select_top_n(scores, n=2)
    assert selected["ticker"].tolist() == ["AAA", "CCC"]
    assert selected["rank"].tolist() == [1, 2]
    assert selected["weight"].tolist() == [0.5, 0.5]


def test_first_trading_day_generation() -> None:
    """First trading day detection should use first available row per month."""

    prices = pd.DataFrame(
        {"AAA": [1, 2, 3, 4]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-02-01", "2024-02-05"]),
    )
    assert get_first_trading_days(prices) == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-02-01"),
    ]
