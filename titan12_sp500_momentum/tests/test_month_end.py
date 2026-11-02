"""Tests for the month-end automation gate and trade list."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.month_end import in_window, lock_date, trades


@pytest.mark.parametrize(
    "today, lock",
    [
        ("2026-10-29", "2026-10-30"),  # before the last session
        ("2026-10-30", "2026-10-30"),  # last session of October (Fri)
        ("2026-10-31", "2026-10-30"),  # weekend before the Nov 2 rebalance
        ("2026-11-01", "2026-10-30"),
        ("2026-11-02", "2026-11-30"),  # rebalance day: next lock is November's
        ("2026-11-15", "2026-11-30"),
        ("2026-12-31", "2026-12-31"),  # Jan 1 holiday, Thu Dec 31 is last
        ("2027-01-01", "2026-12-31"),
        ("2027-04-30", "2027-04-30"),
    ],
)
def test_lock_date(today: str, lock: str) -> None:
    """The lock is the last session before the next rebalance session."""

    assert lock_date(pd.Timestamp(today)) == pd.Timestamp(lock)


def test_in_window() -> None:
    """Only the lock close through the weekend before the rebalance qualify."""

    assert not in_window(pd.Timestamp("2026-10-29"))
    assert in_window(pd.Timestamp("2026-10-30"))
    assert in_window(pd.Timestamp("2026-11-01"))
    assert not in_window(pd.Timestamp("2026-11-02"))


def test_trades() -> None:
    """Held names not in the next basket are sold, new ones bought."""

    assert trades(["MRNA", "SNDK", "DELL"], ["MRNA", "AMD", "DELL"]) == {
        "sell": ["SNDK"],
        "buy": ["AMD"],
        "keep": ["MRNA", "DELL"],
    }
