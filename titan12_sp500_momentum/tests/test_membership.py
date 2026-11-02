"""Tests for S&P 500 membership filtering."""

from __future__ import annotations

import pandas as pd

from src.membership import get_eligible_universe


def test_historical_membership_filtering() -> None:
    """Eligibility should respect start and end dates."""

    membership = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC"],
            "company_name": ["A", "B", "C"],
            "start_date": pd.to_datetime(["2020-01-01", "2024-01-01", pd.NaT]),
            "end_date": pd.to_datetime(["2023-12-31", pd.NaT, pd.NaT]),
            "sector": ["Tech", "Health", "Energy"],
            "source": ["test", "test", "test"],
            "notes": ["", "", ""],
        }
    )
    eligible = get_eligible_universe(membership, "2024-02-01")
    assert eligible["ticker"].tolist() == ["BBB", "CCC"]
