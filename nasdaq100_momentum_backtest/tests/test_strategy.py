"""Unit tests for the momentum rotation strategy."""

from __future__ import annotations

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.backtest import (  # noqa: E402
    _is_nyse_month_first_holiday,
    _predict_next_first_trading_day,
    _signal_locked_for_next_entry,
    calculate_portfolio_return,
    compute_next_position,
)
from src.config import BacktestConfig  # noqa: E402
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


class TestPredictNextFirstTradingDay(unittest.TestCase):
    """Edge cases for the next-entry predictor used by the dashboard's
    "Next Picks" preview."""

    def test_normal_weekday_first_of_month(self):
        # 2026-07-01 is a Wednesday, regular trading day.
        result = _predict_next_first_trading_day(pd.Timestamp("2026-06-01"), 1)
        self.assertEqual(result, pd.Timestamp("2026-07-01"))

    def test_first_of_month_on_saturday(self):
        # 2026-08-01 is a Saturday → first trading day = Mon 2026-08-03.
        result = _predict_next_first_trading_day(pd.Timestamp("2026-07-01"), 1)
        self.assertEqual(result, pd.Timestamp("2026-08-03"))

    def test_new_years_day_weekday_holiday(self):
        # 2026-01-01 is a Thursday — NYSE closed. First trading day = Fri Jan 2.
        result = _predict_next_first_trading_day(pd.Timestamp("2025-12-01"), 1)
        self.assertEqual(result, pd.Timestamp("2026-01-02"))

    def test_new_years_observed_when_jan1_is_sunday(self):
        # 2023-01-01 is a Sunday → NYSE observes the holiday on Mon Jan 2.
        # First trading day = Tue Jan 3.
        result = _predict_next_first_trading_day(pd.Timestamp("2022-12-01"), 1)
        self.assertEqual(result, pd.Timestamp("2023-01-03"))

    def test_labor_day_when_sep1_is_monday(self):
        # 2025-09-01 is the first Monday of September → Labor Day.
        # First trading day = Tue Sep 2.
        result = _predict_next_first_trading_day(pd.Timestamp("2025-08-01"), 1)
        self.assertEqual(result, pd.Timestamp("2025-09-02"))

    def test_period_two_months(self):
        # P=2: skips a month.
        result = _predict_next_first_trading_day(pd.Timestamp("2026-05-01"), 2)
        self.assertEqual(result, pd.Timestamp("2026-07-01"))

    def test_is_nyse_holiday_helper(self):
        self.assertTrue(_is_nyse_month_first_holiday(pd.Timestamp("2026-01-01")))   # NYD
        self.assertTrue(_is_nyse_month_first_holiday(pd.Timestamp("2023-01-02")))   # observed
        self.assertTrue(_is_nyse_month_first_holiday(pd.Timestamp("2025-09-01")))   # Labor Day
        self.assertTrue(_is_nyse_month_first_holiday(pd.Timestamp("2031-09-01")))   # Labor Day
        self.assertFalse(_is_nyse_month_first_holiday(pd.Timestamp("2026-06-01")))  # regular Mon
        self.assertFalse(_is_nyse_month_first_holiday(pd.Timestamp("2026-01-02")))  # not observed (Jan 1 = Thu)


class TestSignalLockedCheck(unittest.TestCase):
    """The condition that decides whether to show the 'Next Picks' panel."""

    def _prices_ending(self, end: str) -> pd.DataFrame:
        return _make_daily_prices("2020-01-01", end, ["AAA"])

    def test_locked_when_data_ends_on_last_trading_day(self):
        prices = self._prices_ending("2026-05-29")  # Fri, last trading day of May
        self.assertTrue(
            _signal_locked_for_next_entry(prices, pd.Timestamp("2026-06-01"))
        )

    def test_not_locked_mid_month(self):
        prices = self._prices_ending("2026-05-15")  # mid-May
        self.assertFalse(
            _signal_locked_for_next_entry(prices, pd.Timestamp("2026-06-01"))
        )

    def test_not_locked_when_data_in_wrong_month(self):
        # Strategy B (P=2m): next_entry = 2026-07-01, prev month = June.
        # Data through May 29 → not in June → not locked.
        prices = self._prices_ending("2026-05-29")
        self.assertFalse(
            _signal_locked_for_next_entry(prices, pd.Timestamp("2026-07-01"))
        )

    def test_locked_when_data_through_june_for_strategy_b(self):
        prices = self._prices_ending("2026-06-30")  # Tue, last trading day of June 2026
        self.assertTrue(
            _signal_locked_for_next_entry(prices, pd.Timestamp("2026-07-01"))
        )

    def test_locked_when_month_starts_on_weekend(self):
        # 2026-08-01 is a Saturday, so the first trading day of August is
        # Mon 2026-08-03. Data through Fri 2026-07-31 (last trading day of
        # July) must lock the August signal.
        prices = self._prices_ending("2026-07-31")
        self.assertTrue(
            _signal_locked_for_next_entry(prices, pd.Timestamp("2026-08-03"))
        )

    def test_memorial_day_landing_on_31st(self):
        # 2027-05-31 is a Monday = Memorial Day. Last trading day of May 2027
        # is Fri 2027-05-28. The generic BDay walks May 28 → May 31 (same
        # month), so a naive BDay(1) check would say "not locked" incorrectly.
        # Our 3-day look-ahead absorbs this: May 28 + 2 BDays = Jun 1.
        prices = self._prices_ending("2027-05-28")
        self.assertTrue(
            _signal_locked_for_next_entry(prices, pd.Timestamp("2027-06-01"))
        )


class TestComputeNextPosition(unittest.TestCase):
    """End-to-end check that the Next Picks DataFrame populates correctly."""

    def _make_panel(self, end: str) -> pd.DataFrame:
        # Three tickers + benchmarks; deterministic random walks differ
        # enough across tickers that there's an unambiguous top-3 order.
        return _make_daily_prices(
            "2020-01-01", end, ["AAA", "BBB", "CCC", "DDD", "QQQ", "TQQQ"]
        )

    def _config(self, **overrides) -> BacktestConfig:
        defaults = dict(
            start_date="2020-01-01",
            end_date="2026-05-29",
            lookback_months=6,
            top_n=3,
            rebalance_period_months=1,
            tickers=["AAA", "BBB", "CCC", "DDD"],
        )
        defaults.update(overrides)
        return BacktestConfig(**defaults)

    def test_returns_empty_when_signal_not_locked(self):
        prices = self._make_panel("2026-05-15")  # mid-month
        monthly_returns = calculate_monthly_returns(prices)
        result = compute_next_position(
            prices, monthly_returns, self._config(), pd.Timestamp("2026-05-01")
        )
        self.assertTrue(result.empty)

    def test_returns_picks_when_signal_locked(self):
        prices = self._make_panel("2026-05-29")  # Fri, last trading day of May
        monthly_returns = calculate_monthly_returns(prices)
        result = compute_next_position(
            prices, monthly_returns, self._config(), pd.Timestamp("2026-05-01")
        )
        self.assertFalse(result.empty)
        self.assertEqual(len(result), 3)  # top_n
        # Shape check — all the columns downstream consumers expect.
        for col in (
            "rebalance_date", "ticker", "rank", "momentum_score",
            "weight", "entry_price", "exit_date", "exit_price",
            "stock_return", "is_next",
        ):
            self.assertIn(col, result.columns)
        # Next entry is June 1, 2026 (Mon, regular trading day).
        self.assertEqual(
            pd.Timestamp(result["rebalance_date"].iloc[0]),
            pd.Timestamp("2026-06-01"),
        )
        # We haven't entered yet → stock_return is 0 across all rows.
        self.assertTrue((result["stock_return"] == 0.0).all())
        # Benchmark tickers must never be picked.
        self.assertFalse(set(result["ticker"]) & {"QQQ", "TQQQ"})

    def test_period_two_locks_only_at_end_of_second_month(self):
        # Strategy B: P=2m. Current entry = May 1, next entry = July 1.
        # On May 29 (end of May), the signal for July 1 isn't locked
        # yet — we still need June's monthly return.
        config = self._config(lookback_months=3, rebalance_period_months=2)

        prices_may = self._make_panel("2026-05-29")
        monthly_may = calculate_monthly_returns(prices_may)
        result_may = compute_next_position(
            prices_may, monthly_may, config, pd.Timestamp("2026-05-01")
        )
        self.assertTrue(result_may.empty, "B should not lock after May close")

        # Once June completes, the picks for the July 1 entry appear.
        prices_june = self._make_panel("2026-06-30")
        monthly_june = calculate_monthly_returns(prices_june)
        result_june = compute_next_position(
            prices_june, monthly_june, config, pd.Timestamp("2026-05-01")
        )
        self.assertFalse(result_june.empty, "B should lock after June close")
        self.assertEqual(
            pd.Timestamp(result_june["rebalance_date"].iloc[0]),
            pd.Timestamp("2026-07-01"),
        )


if __name__ == "__main__":
    unittest.main()
