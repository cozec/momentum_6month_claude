"""Tests for portfolio execution helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest import (
    _calculate_leaderboard,
    _calculate_next_selections,
    calculate_portfolio_return,
    calculate_turnover,
)
from src.config import BacktestConfig
from src.nyse_calendar import next_session_after
from src.signals import calculate_month_end_prices, calculate_monthly_returns


def test_portfolio_return_equal_weight() -> None:
    """Portfolio return should be the average selected stock return."""

    prices = pd.DataFrame(
        {
            "AAA": [100.0, 110.0],
            "BBB": [50.0, 45.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-02-01"]),
    )
    portfolio_return, details = calculate_portfolio_return(
        ["AAA", "BBB"], prices, "2024-01-02", "2024-02-01"
    )
    assert round(portfolio_return, 10) == round(((0.10 + -0.10) / 2), 10)
    assert len(details) == 2


def test_turnover_from_one_equal_weight_basket_to_another() -> None:
    """One replacement in a three-stock equal-weight basket is 1/3 turnover."""

    turnover = calculate_turnover({"AAA", "BBB", "CCC"}, {"AAA", "BBB", "DDD"})
    assert round(turnover, 10) == round(1 / 3, 10)


def test_turnover_first_portfolio_is_full_turnover() -> None:
    """Opening a new portfolio should count as full turnover."""

    assert calculate_turnover(set(), {"AAA", "BBB", "CCC"}) == 1.0


def test_delisted_holding_exits_at_last_traded_price() -> None:
    """A stock acquired mid-month counts at its last price, not dropped."""

    prices = pd.DataFrame(
        {
            "AAA": [100.0, 105.0, 110.0],
            "ESRX": [100.0, 92.0, float("nan")],
        },
        index=pd.to_datetime(["2018-12-03", "2018-12-21", "2019-01-02"]),
    )
    portfolio_return, details = calculate_portfolio_return(
        ["AAA", "ESRX"], prices, "2018-12-03", "2019-01-02"
    )
    assert round(portfolio_return, 10) == round((0.10 + -0.08) / 2, 10)
    esrx = next(row for row in details if row["ticker"] == "ESRX")
    assert esrx["exit_date"] == "2018-12-21"
    assert esrx["exit_price"] == 92.0


def _next_basket_inputs(last_day: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build membership, monthly returns and prices for five trending tickers."""

    dates = pd.bdate_range("2025-09-01", last_day)
    growth = {"AAA": 0.004, "BBB": 0.003, "CCC": 0.002, "DDD": 0.001, "EEE": -0.001}
    adj_close = pd.DataFrame(
        {t: 100.0 * np.exp(g * np.arange(len(dates))) for t, g in growth.items()},
        index=dates,
    )
    membership = pd.DataFrame(
        {
            "ticker": list(growth),
            "company_name": list(growth),
            "start_date": pd.NaT,
            "end_date": pd.NaT,
            "sector": "Tech",
        }
    )
    monthly_returns = calculate_monthly_returns(calculate_month_end_prices(adj_close))
    return membership, monthly_returns, adj_close


def test_next_session_skips_weekend_and_holiday() -> None:
    """Friday rolls to Monday; the day before Thanksgiving rolls to Friday."""

    assert next_session_after("2026-10-30") == pd.Timestamp("2026-11-02")
    assert next_session_after("2026-11-25") == pd.Timestamp("2026-11-27")


def test_next_basket_locked_after_last_session_of_month() -> None:
    """Data through Fri 2026-10-30 locks the Mon 2026-11-02 basket."""

    membership, monthly_returns, adj_close = _next_basket_inputs("2026-10-30")
    config = BacktestConfig(end_date="2026-10-30", top_n=3)
    picks = _calculate_next_selections(config, membership, monthly_returns, adj_close)
    assert picks["ticker"].tolist() == ["AAA", "BBB", "CCC"]
    assert set(picks["rebalance_date"]) == {"2026-11-02"}
    assert set(picks["as_of_date"]) == {"2026-10-30"}
    assert picks["entry_price_estimate"].iloc[0] == adj_close.loc["2026-10-30", "AAA"]


def test_next_basket_backfills_after_exclusion() -> None:
    """Excluded tickers are dropped and the next ranks backfill, keeping ranks."""

    membership, monthly_returns, adj_close = _next_basket_inputs("2026-10-30")
    config = BacktestConfig(end_date="2026-10-30", top_n=3)
    picks = _calculate_next_selections(
        config, membership, monthly_returns, adj_close, excluded=["AAA"]
    )
    assert picks["ticker"].tolist() == ["BBB", "CCC", "DDD"]
    assert picks["rank"].tolist() == [2, 3, 4]


def test_next_basket_empty_mid_month() -> None:
    """Mid-month data has not locked the next signal yet."""

    membership, monthly_returns, adj_close = _next_basket_inputs("2026-10-29")
    config = BacktestConfig(end_date="2026-10-29", top_n=3)
    assert _calculate_next_selections(config, membership, monthly_returns, adj_close).empty


def test_leaderboard_ranks_all_names_and_flags_held() -> None:
    """Top-N ranking flags the baseline top 3 and reports rank changes."""

    membership, monthly_returns, adj_close = _next_basket_inputs("2026-10-30")
    config = BacktestConfig(end_date="2026-10-30", top_n=3)
    board = _calculate_leaderboard(
        config,
        membership,
        monthly_returns,
        adj_close,
        pd.Timestamp("2026-11-02"),
        prev_date=pd.Timestamp("2026-10-01"),
        n=4,
    )
    assert board["ticker"].tolist() == ["AAA", "BBB", "CCC", "DDD"]
    assert board["held"].tolist() == [True, True, True, False]
    assert board["rank_change"].tolist() == [0, 0, 0, 0]
    assert set(board["as_of_date"]) == {"2026-10-30"}
