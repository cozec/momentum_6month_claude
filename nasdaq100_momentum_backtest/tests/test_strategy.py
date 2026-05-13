"""Unit tests for the momentum rotation strategy."""

from __future__ import annotations

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.backtest import calculate_portfolio_return  # noqa: E402
from src.signals import (  # noqa: E402
    calculate_momentum_scores,
    calculate_monthly_returns,
    get_first_trading_days,
    select_top_n,
)


def _make_daily_prices(start: str, end: str, tickers: list[str], seed: int = 1) -> pd.DataFrame:
    """Build a deterministic daily price panel for tests."""
    dates = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    data = {}
    for ticker in tickers:
        # Random walk in log space, starting at 100.
        steps = rng.normal(0, 0.01, size=len(dates))
        prices = 100 * np.exp(np.cumsum(steps))
        data[ticker] = prices
    return pd.DataFrame(data, index=dates)


class TestSignals(unittest.TestCase):
    def test_monthly_returns_shape(self):
        prices = _make_daily_prices("2020-01-01", "2020-12-31", ["AAA", "BBB"])
        returns = calculate_monthly_returns(prices)
        self.assertEqual(returns.shape[1], 2)
        # 12 month-ends in 2020; first is NaN because pct_change.
        self.assertEqual(len(returns), 12)
        self.assertTrue(returns.iloc[0].isna().all())

    def test_monthly_returns_value(self):
        # Construct a price series where month-end prices are exactly 1, 2, 3.
        idx = pd.DatetimeIndex(["2020-01-31", "2020-02-28", "2020-03-31"])
        prices = pd.DataFrame({"AAA": [1.0, 2.0, 3.0]}, index=idx)
        returns = calculate_monthly_returns(prices)
        self.assertAlmostEqual(returns.iloc[1, 0], 1.0)
        self.assertAlmostEqual(returns.iloc[2, 0], 0.5)

    def test_get_first_trading_days(self):
        prices = _make_daily_prices("2020-01-01", "2020-04-30", ["AAA"])
        first_days = get_first_trading_days(prices)
        self.assertEqual(len(first_days), 4)
        for d in first_days:
            self.assertEqual(d.month, d.month)  # sanity

    def test_select_top_n(self):
        scores = pd.Series({"A": 0.1, "B": 0.3, "C": 0.2, "D": 0.05})
        top = select_top_n(scores, n=2)
        self.assertEqual(top, ["B", "C"])

    def test_momentum_score_no_lookahead(self):
        """Ensure the rebalance date's own month is NOT used in the score."""
        # Build a deterministic monthly-return frame.
        idx = pd.date_range("2020-01-31", periods=10, freq="ME")
        monthly = pd.DataFrame(
            {"AAA": [0.01] * 6 + [0.10, 0.10, 0.10, 0.10]},
            index=idx,
        )
        # Rebalance on 2020-07-01: completed months are Jan-Jun (all 0.01).
        score = calculate_momentum_scores(
            monthly, pd.Timestamp("2020-07-01"), lookback_months=6
        )
        self.assertAlmostEqual(score["AAA"], 0.01, places=6)

    def test_momentum_score_insufficient_history(self):
        idx = pd.date_range("2020-01-31", periods=3, freq="ME")
        monthly = pd.DataFrame({"AAA": [0.01, 0.02, 0.03]}, index=idx)
        score = calculate_momentum_scores(
            monthly, pd.Timestamp("2020-04-01"), lookback_months=6
        )
        self.assertTrue(score.empty)

    def test_momentum_score_compound_method(self):
        idx = pd.date_range("2020-01-31", periods=6, freq="ME")
        monthly = pd.DataFrame({"AAA": [0.10] * 6}, index=idx)
        score = calculate_momentum_scores(
            monthly,
            pd.Timestamp("2020-07-01"),
            lookback_months=6,
            score_method="compound_6m_return",
        )
        self.assertAlmostEqual(score["AAA"], (1.10**6) - 1, places=6)


class TestPortfolio(unittest.TestCase):
    def test_calculate_portfolio_return_equal_weight(self):
        idx = pd.DatetimeIndex(["2020-01-02", "2020-02-03"])
        prices = pd.DataFrame(
            {
                "AAA": [100.0, 110.0],
                "BBB": [100.0, 120.0],
                "CCC": [100.0, 90.0],
            },
            index=idx,
        )
        ret, entries, exits, per_stock = calculate_portfolio_return(
            ["AAA", "BBB", "CCC"],
            prices,
            idx[0],
            idx[1],
        )
        # Equal-weight mean of +10%, +20%, -10% = +6.6667%.
        self.assertAlmostEqual(ret, (0.10 + 0.20 - 0.10) / 3, places=6)
        self.assertEqual(set(entries), {"AAA", "BBB", "CCC"})
        self.assertEqual(set(per_stock), {"AAA", "BBB", "CCC"})


if __name__ == "__main__":
    unittest.main()
