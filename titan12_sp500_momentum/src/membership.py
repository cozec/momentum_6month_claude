"""S&P 500 membership loading and eligibility filtering."""

from __future__ import annotations

import logging
from pathlib import Path
from io import StringIO

import pandas as pd
import requests

from src.utils import normalize_ticker


LOGGER = logging.getLogger(__name__)
WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Wikipedia split the "Selected changes" table out of the constituents article
# into its own page, so the two tables are fetched separately.
WIKIPEDIA_SP500_CHANGES_URL = (
    "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"
)
MEMBERSHIP_COLUMNS = [
    "ticker",
    "company_name",
    "start_date",
    "end_date",
    "sector",
    "source",
    "notes",
]


def fetch_current_sp500_members() -> pd.DataFrame:
    """Fetch the current S&P 500 member list from Wikipedia.

    Returns
    -------
    pandas.DataFrame
        Membership dataframe using the standard project schema. Dates are left
        open-ended, which means any historical backtest using this file must be
        labeled as survivorship-biased.
    """

    response = requests.get(
        WIKIPEDIA_SP500_URL,
        headers={"User-Agent": "Titan-12 Momentum Rotation research script"},
        timeout=30,
    )
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    members = tables[0].rename(
        columns={
            "Symbol": "ticker",
            "Security": "company_name",
            "GICS Sector": "sector",
            "Date added": "start_date",
        }
    )
    members = members[["ticker", "company_name", "start_date", "sector"]].copy()
    members["ticker"] = members["ticker"].map(normalize_ticker)
    members["start_date"] = pd.to_datetime(members["start_date"], errors="coerce")
    members["end_date"] = pd.NaT
    members["source"] = WIKIPEDIA_SP500_URL
    members["notes"] = (
        "Current constituents only from Wikipedia; survivorship-biased for "
        "historical backtests. start_date is Wikipedia Date added when available."
    )
    return members[MEMBERSHIP_COLUMNS]


def create_current_membership_file(filepath: Path) -> pd.DataFrame:
    """Create a current-constituents S&P 500 membership CSV."""

    filepath.parent.mkdir(parents=True, exist_ok=True)
    membership = fetch_current_sp500_members()
    membership.to_csv(filepath, index=False)
    LOGGER.warning(
        "Created %s with current S&P 500 constituents. Historical runs using "
        "this file are survivorship-biased.",
        filepath,
    )
    return membership


def load_sp500_membership(filepath: Path) -> pd.DataFrame:
    """Load an S&P 500 membership file in the project schema.

    Parameters
    ----------
    filepath
        CSV path with ticker, company_name, start_date, end_date, sector,
        source, and notes columns.

    Returns
    -------
    pandas.DataFrame
        Cleaned membership records with normalized tickers and parsed dates.
    """

    if not filepath.exists():
        raise FileNotFoundError(
            f"Membership file not found: {filepath}. Run with "
            "--membership-mode current_constituents to bootstrap a current "
            "member file, or provide a historical membership CSV."
        )

    membership = pd.read_csv(filepath)
    missing_columns = set(MEMBERSHIP_COLUMNS) - set(membership.columns)
    if missing_columns:
        raise ValueError(
            f"Membership file {filepath} is missing columns: "
            f"{sorted(missing_columns)}"
        )

    membership = membership[MEMBERSHIP_COLUMNS].copy()
    membership["ticker"] = membership["ticker"].map(normalize_ticker)
    membership["start_date"] = pd.to_datetime(membership["start_date"], errors="coerce")
    membership["end_date"] = pd.to_datetime(membership["end_date"], errors="coerce")
    membership["company_name"] = membership["company_name"].fillna("")
    membership["sector"] = membership["sector"].fillna("Unknown")
    membership["source"] = membership["source"].fillna("")
    membership["notes"] = membership["notes"].fillna("")
    return membership


def get_eligible_universe(membership_df: pd.DataFrame, date: object) -> pd.DataFrame:
    """Return members eligible on a rebalance date.

    Rows with missing start dates are treated as eligible from the beginning of
    the test window. Rows with missing end dates are treated as still active.
    """

    rebalance_date = pd.Timestamp(date).normalize()
    starts = membership_df["start_date"].isna() | (
        membership_df["start_date"] <= rebalance_date
    )
    ends = membership_df["end_date"].isna() | (membership_df["end_date"] >= rebalance_date)
    eligible = membership_df.loc[starts & ends].copy()
    return eligible.sort_values("ticker").reset_index(drop=True)


def get_member_metadata(membership_df: pd.DataFrame, date: object) -> pd.DataFrame:
    """Return ticker-indexed company and sector metadata for a rebalance date."""

    eligible = get_eligible_universe(membership_df, date)
    return eligible.drop_duplicates("ticker").set_index("ticker")[
        ["company_name", "sector"]
    ]
