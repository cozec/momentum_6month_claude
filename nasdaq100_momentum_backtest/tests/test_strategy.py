"""Unit tests for the momentum rotation strategy."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.backtest import (  # noqa: E402
    _predict_next_first_trading_day,
    _signal_locked_for_next_entry,
    calculate_portfolio_return,
    compute_leaderboard,
    compute_next_position,
)
from src import download_data  # noqa: E402
from src.config import BacktestConfig  # noqa: E402
from src.nyse_calendar import NYSEHolidayCalendar  # noqa: E402
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

    def test_good_friday_at_month_end(self):
        # Good Friday 2018 was Fri Mar 30, so Thu Mar 29 was March's last
        # session and its close locks the Mon Apr 2 entry.
        self.assertEqual(
            _predict_next_first_trading_day(pd.Timestamp("2018-03-01"), 1),
            pd.Timestamp("2018-04-02"),
        )
        prices = _make_daily_prices("2017-01-01", "2018-03-29", ["AAA"])
        self.assertTrue(_signal_locked_for_next_entry(prices, pd.Timestamp("2018-04-02")))

    def test_calendar_holidays(self):
        holidays = NYSEHolidayCalendar().holidays("2026-01-01", "2027-12-31")
        for day in ["2026-01-01", "2026-04-03", "2026-06-19", "2026-07-03",
                    "2026-11-26", "2026-12-25", "2027-03-26", "2027-12-24"]:
            self.assertIn(pd.Timestamp(day), holidays, day)
        # New Year's Day on a Saturday is not observed on the prior Friday.
        self.assertNotIn(pd.Timestamp("2021-12-31"),
                         NYSEHolidayCalendar().holidays("2021-12-01", "2022-01-31"))


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
        # 2027-05-31 is a Monday = Memorial Day, so Fri 2027-05-28 is the
        # last trading day of May and its close locks the June signal.
        prices = self._prices_ending("2027-05-28")
        self.assertTrue(
            _signal_locked_for_next_entry(prices, pd.Timestamp("2027-06-01"))
        )


    def test_not_locked_before_the_last_trading_day(self):
        # October 2026 ends on Fri Oct 30: data through Wed Oct 28 or
        # Thu Oct 29 is still missing the month's final close.
        for end in ["2026-10-28", "2026-10-29"]:
            self.assertFalse(
                _signal_locked_for_next_entry(self._prices_ending(end), pd.Timestamp("2026-11-02")),
                end,
            )
        self.assertTrue(
            _signal_locked_for_next_entry(self._prices_ending("2026-10-30"), pd.Timestamp("2026-11-02"))
        )

    def test_not_locked_once_entry_day_has_data(self):
        prices = self._prices_ending("2026-11-02")
        self.assertFalse(_signal_locked_for_next_entry(prices, pd.Timestamp("2026-11-02")))


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


class TestLeaderboard(unittest.TestCase):
    def setUp(self):
        tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "QQQ"]
        self.prices = _make_daily_prices("2025-01-01", "2026-10-09", tickers, seed=7)
        self.monthly = calculate_monthly_returns(self.prices)
        self.config = BacktestConfig(
            tickers=tickers[:-1], benchmark="QQQ", secondary_benchmark="", top_n=2,
        )
        self.entry = pd.Timestamp("2026-10-01")

    def test_ranking_matches_scores_and_flags_held(self):
        board = compute_leaderboard(self.prices, self.monthly, self.config, self.entry, n=4)
        scores = calculate_momentum_scores(self.monthly[self.config.tickers], self.entry)
        self.assertEqual(list(board["ticker"]), list(scores.index[:4]))
        self.assertEqual(list(board["held"]), [True, True, False, False])
        self.assertNotIn("QQQ", set(board["ticker"]))

    def test_trend_columns(self):
        board = compute_leaderboard(self.prices, self.monthly, self.config, self.entry)
        row = board.iloc[0]
        series = self.prices[row["ticker"]]
        self.assertAlmostEqual(row["since_entry"], series.iloc[-1] / series.loc[self.entry] - 1)
        self.assertAlmostEqual(row["ret_1m"], series.iloc[-1] / series.iloc[-22] - 1)
        self.assertLessEqual(row["off_6m_high"], 0.0)

    def test_exclude_drops_tickers(self):
        first = compute_leaderboard(self.prices, self.monthly, self.config, self.entry)["ticker"].iloc[0]
        board = compute_leaderboard(self.prices, self.monthly, self.config, self.entry, exclude={first})
        self.assertNotIn(first, set(board["ticker"]))

    def test_trend_tag_rule(self):
        from webapp.server import _trend_tag
        self.assertEqual(_trend_tag(-0.05, 0.02), "Buy")
        self.assertEqual(_trend_tag(-0.05, -0.02), "Hold")
        self.assertEqual(_trend_tag(-0.15, 0.10), "Hold")
        self.assertEqual(_trend_tag(-0.25, -0.05), "Watch")
        self.assertEqual(_trend_tag(-0.25, -0.12), "Caution")
        self.assertEqual(_trend_tag(-0.40, 0.20), "Caution")


class TestSp500Membership(unittest.TestCase):
    """Point-in-time spans rebuilt from today's list plus the change log."""

    def setUp(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from build_sp500 import build_membership
        self.build = build_membership
        self.constituents = pd.DataFrame({
            "Symbol": ["AAA", "NEW", "BACK"],
            "Date added": ["1990-01-01", "2024-03-18", "2010-01-01"],
        })
        # Newest first, as on Wikipedia.
        self.changes = pd.DataFrame({
            "date": pd.to_datetime(["2024-03-18", "2022-06-01", "2019-01-02", "2012-05-01"]),
            "added": ["NEW", "BACK", None, None],
            "removed": ["OLD", None, "BACK", "GONE"],
        })

    def spans(self, ticker):
        m = self.build(self.constituents, self.changes)
        return [(str(r.start_date.date()), None if pd.isna(r.end_date) else str(r.end_date.date()))
                for r in m[m.ticker == ticker].itertuples()]

    def test_current_member_added_by_change(self):
        self.assertEqual(self.spans("NEW"), [("2024-03-18", None)])

    def test_current_member_from_date_added(self):
        self.assertEqual(self.spans("AAA"), [("1990-01-01", None)])

    def test_removed_member_ends_day_before_removal(self):
        self.assertEqual(self.spans("OLD"), [("2000-01-01", "2024-03-17")])

    def test_removed_and_readded_member_has_two_spans(self):
        self.assertEqual(self.spans("BACK"), [("2000-01-01", "2019-01-01"), ("2022-06-01", None)])

    def test_spans_ending_before_since_are_dropped(self):
        self.assertEqual(self.spans("GONE"), [])

    def test_former_members_join_universe_with_capped_window(self):
        from src.backtest import FORMER_MEMBER_TAIL, _former_member_ends
        membership = pd.DataFrame({
            "ticker": ["CUR", "OLD", "BACK", "BACK", "NODATA"],
            "start_date": pd.to_datetime(["2010-01-01", "2010-01-01", "2010-01-01", "2022-01-01", "2010-01-01"]),
            "end_date": pd.to_datetime([None, "2020-06-30", "2019-01-01", None, "2021-01-01"]),
        })
        has_file = lambda t: t != "NODATA"  # noqa: E731
        with mock.patch("src.backtest._cache_path", side_effect=lambda t: t), \
                mock.patch("src.backtest.os.path.exists", side_effect=has_file):
            pit = _former_member_ends(BacktestConfig(use_historical_membership=True), membership)
            snap = _former_member_ends(BacktestConfig(use_historical_membership=False), membership)
        self.assertEqual(pit, {"OLD": pd.Timestamp("2020-06-30") + FORMER_MEMBER_TAIL})
        self.assertEqual(snap, {})

    def test_membership_path_is_used(self):
        path = os.path.join(tempfile.mkdtemp(), "m.csv")
        self.addCleanup(shutil.rmtree, os.path.dirname(path))
        pd.DataFrame({"ticker": ["ZZZ"], "start_date": ["2020-01-01"], "end_date": [""]}).to_csv(path, index=False)
        from src.backtest import _build_membership
        cfg = BacktestConfig(use_historical_membership=True, membership_path=path)
        self.assertEqual(list(_build_membership(cfg)["ticker"]), ["ZZZ"])


class TestPicksEmail(unittest.TestCase):
    """Month-end trade email: when to send and what the trades are."""

    def setUp(self):
        import send_picks_email
        self.mod = send_picks_email
        self.a = {
            "strategy": {"universe": "Nasdaq-100", "label": "6-month momentum", "benchmark": "QQQ"},
            "open": [{"ticker": "MU", "rank": 1, "stock_return": 0.05, "entry_price": 100.0, "latest_price": 105.0},
                     {"ticker": "INTC", "rank": 2, "stock_return": None, "entry_price": None, "latest_price": None},
                     {"ticker": "SNDK", "rank": 3, "stock_return": -0.1, "entry_price": 10.0, "latest_price": 9.0}],
            "open_meta": {"entry_date": "2026-10-01", "mtd_portfolio_return": None},
            "next": [{"ticker": "MU", "rank": 1, "momentum_score": 0.2, "entry_price_estimate": 105.0},
                     {"ticker": "AMD", "rank": 2, "momentum_score": None, "entry_price_estimate": None},
                     {"ticker": "CRWD", "rank": 3, "momentum_score": 0.18, "entry_price_estimate": 300.0}],
            "next_meta": {"planned_entry_date": "2026-11-02", "signal_locked_as_of": "2026-10-30"},
            "stats": {"strategy": {"cagr": 0.5, "sharpe": None, "max_drawdown": -0.3}, "benchmark": {}},
        }
        self.bundle = {"strategies": [self.a]}

    def test_sends_only_on_the_lock_day(self):
        self.assertTrue(self.mod.should_send(self.bundle, "2026-10-30"))
        self.assertFalse(self.mod.should_send(self.bundle, "2026-10-31"))  # weekend rerun
        self.assertFalse(self.mod.should_send({"strategies": [dict(self.a, next=[])]}, "2026-10-30"))
        self.assertTrue(self.mod.should_send({"strategies": [dict(self.a, next=[])]}, "2026-10-27", force=True))

    def test_trade_list(self):
        self.assertEqual(self.mod.trades(self.a),
                         {"sell": ["INTC", "SNDK"], "buy": ["AMD", "CRWD"], "keep": ["MU"]})

    def test_email_builds_with_missing_values(self):
        email = self.mod.build_email(self.bundle)
        self.assertIn("2026-11-02", email["subject"])
        self.assertIn("sell INTC, SNDK; buy AMD, CRWD; keep MU", email["subject"])
        self.assertIn("market-on-close", email["html"])
        self.assertIn("—", email["html"])


class TestIncrementalCacheAdjustment(unittest.TestCase):
    """A split between cache refreshes must not splice two price bases."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        patcher = mock.patch.object(download_data, "RAW_PRICES_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        download_data._FAILED_REFRESH.clear()
        self.addCleanup(download_data._FAILED_REFRESH.clear)
        dates = pd.bdate_range("2026-05-01", "2026-07-31")
        # Closes around 700 until a 4:1 split on 2026-06-26; afterwards the
        # provider serves the whole history split-adjusted (divided by 4).
        raw = pd.Series(700.0 + np.arange(len(dates)), index=dates)
        self.provider = raw / 4.0
        # Cache written before the split, on the old adjustment basis.
        self._write_cache(raw.loc[:"2026-06-24"])

    def _write_cache(self, close: pd.Series) -> None:
        df = pd.DataFrame({c: close for c in ["Open", "High", "Low", "Close"]})
        df["Volume"] = 1_000
        df.to_csv(download_data._cache_path("XYZ"), index_label="Date")

    def _fake_download(self, ticker, start, end, retries=3):
        close = self.provider.loc[start:end]
        df = pd.DataFrame({c: close for c in ["Open", "High", "Low", "Close"]})
        df["Volume"] = 1_000
        return df.rename_axis("Date")

    def test_split_triggers_full_redownload(self):
        with mock.patch.object(download_data, "_download_one", side_effect=self._fake_download) as dl:
            close = download_data._fetch_ticker_close(
                "XYZ", pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-31"),
                force_refresh=True, full_refresh=False,
            )
        self.assertEqual(dl.call_count, 2)
        self.assertGreater(close.pct_change().min(), -0.05)
        pd.testing.assert_series_equal(close, self.provider.rename("XYZ"), check_names=False,
                                       check_freq=False)

    def test_stub_full_download_keeps_cache(self):
        # Delisted names can return only a handful of recent bars.
        self.provider = self.provider.loc["2026-06-19":]
        with mock.patch.object(download_data, "_download_one", side_effect=self._fake_download):
            download_data._fetch_ticker_close(
                "XYZ", pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-31"),
                force_refresh=True, full_refresh=False,
            )
        cached = download_data._load_cached("XYZ")
        self.assertEqual(cached.index.min(), pd.Timestamp("2026-05-01"))

    def test_unsettled_bar_is_dropped_until_after_the_close(self):
        df = pd.DataFrame({"Close": [1.0, 2.0]},
                          index=pd.to_datetime(["2026-10-29", "2026-10-30"]))
        ny = lambda s: pd.Timestamp(s, tz="America/New_York")  # noqa: E731
        intraday = download_data._drop_unsettled_bar(df, now=ny("2026-10-30 11:00"))
        self.assertEqual(list(intraday.index), [pd.Timestamp("2026-10-29")])
        evening = download_data._drop_unsettled_bar(df, now=ny("2026-10-30 18:00"))
        self.assertEqual(len(evening), 2)
        next_morning = download_data._drop_unsettled_bar(df, now=ny("2026-10-31 09:00"))
        self.assertEqual(len(next_morning), 2)

    def test_failed_refresh_is_not_retried_immediately(self):
        with mock.patch.object(download_data, "_download_one", return_value=None) as dl:
            for _ in range(3):
                close = download_data._fetch_ticker_close(
                    "XYZ", pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-31"),
                    force_refresh=False, full_refresh=False,
                )
        self.assertEqual(dl.call_count, 1)
        self.assertEqual(close.index.max(), pd.Timestamp("2026-06-24"))

    def test_unchanged_basis_merges_tail_only(self):
        self.provider = pd.Series(700.0 + np.arange(len(self.provider)), index=self.provider.index)
        with mock.patch.object(download_data, "_download_one", side_effect=self._fake_download) as dl:
            download_data._fetch_ticker_close(
                "XYZ", pd.Timestamp("2026-05-01"), pd.Timestamp("2026-07-31"),
                force_refresh=True, full_refresh=False,
            )
        self.assertEqual(dl.call_count, 1)


if __name__ == "__main__":
    unittest.main()
