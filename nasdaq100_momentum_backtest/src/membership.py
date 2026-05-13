"""Nasdaq-100 membership handling.

This project ships with a current-constituents snapshot. A historical
membership CSV can be supplied for a survivorship-bias-free backtest.
"""

from __future__ import annotations

import os
from typing import Iterable, List, Optional

import pandas as pd

from .config import CURRENT_NASDAQ100, MEMBERSHIP_CSV
from .utils import ensure_dir, to_business_date


def write_current_membership_template(filepath: str = MEMBERSHIP_CSV) -> str:
    """Write a sample membership CSV using the current Nasdaq-100 list.

    Each row marks a ticker as a constituent indefinitely (open-ended),
    which represents the survivorship-biased current snapshot.
    """
    ensure_dir(os.path.dirname(filepath))
    df = pd.DataFrame(
        {
            "ticker": CURRENT_NASDAQ100,
            "start_date": "2000-01-01",
            "end_date": "",
        }
    )
    df.to_csv(filepath, index=False)
    return filepath


def load_nasdaq100_membership(filepath: str = MEMBERSHIP_CSV) -> pd.DataFrame:
    """Load a Nasdaq-100 membership CSV.

    Expected columns: ``ticker``, ``start_date``, ``end_date`` (end_date
    may be empty for currently-active members).
    """
    if not os.path.exists(filepath):
        write_current_membership_template(filepath)
    df = pd.read_csv(filepath)
    df["ticker"] = df["ticker"].str.upper().str.strip()
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    return df


def get_eligible_universe(
    membership_df: pd.DataFrame,
    as_of_date,
    available_tickers: Optional[Iterable[str]] = None,
) -> List[str]:
    """Return the list of Nasdaq-100 constituents as of ``as_of_date``.

    Parameters
    ----------
    membership_df : pd.DataFrame
        Output of :func:`load_nasdaq100_membership`.
    as_of_date : date-like
        The rebalance date to evaluate membership against.
    available_tickers : Optional[Iterable[str]]
        Restrict the eligible universe to this set (e.g. tickers that
        actually have price data).
    """
    asof = to_business_date(as_of_date)
    mask = (membership_df["start_date"] <= asof) & (
        membership_df["end_date"].isna() | (membership_df["end_date"] >= asof)
    )
    eligible = membership_df.loc[mask, "ticker"].tolist()
    if available_tickers is not None:
        available = set(t.upper() for t in available_tickers)
        eligible = [t for t in eligible if t in available]
    return sorted(set(eligible))
