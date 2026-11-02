"""Import the sister project's Nasdaq-100 universe for the Titan-12 backtest.

Copies the point-in-time Nasdaq-100 membership into
``data/nasdaq100_membership.csv`` (project schema) and borrows any price files
this project's cache lacks, including the QQQ benchmark. The sister cache is
downloaded with ``auto_adjust=True``, so its ``Close`` is written as both
``Close`` and ``Adj Close``. Existing local price files are never overwritten.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.download_data import PRICE_COLUMNS  # noqa: E402
from src.membership import MEMBERSHIP_COLUMNS  # noqa: E402
from src.utils import normalize_ticker  # noqa: E402

DEFAULT_SISTER_ROOT = Path(
    "/Users/adam/project/momentum_6m_claude/nasdaq100_momentum_backtest"
)


def build_membership(sister_root: Path) -> pd.DataFrame:
    """Convert the sister membership file to this project's schema.

    Company names and sectors are filled from the local S&P 500 membership
    where a ticker appears there; otherwise the ticker and "Unknown" are used.

    Args:
        sister_root: Root of the sister ``nasdaq100_momentum_backtest`` project.

    Returns:
        Membership rows with ``MEMBERSHIP_COLUMNS``.
    """

    membership = pd.read_csv(sister_root / "data" / "nasdaq100_membership.csv")
    membership["ticker"] = membership["ticker"].map(normalize_ticker)
    sp500 = pd.read_csv(PROJECT_ROOT / "data" / "sp500_membership.csv")
    latest = sp500.drop_duplicates("ticker", keep="last").set_index("ticker")
    sectors = sp500[sp500["sector"].ne("Unknown")].drop_duplicates(
        "ticker", keep="last"
    ).set_index("ticker")["sector"]
    membership["company_name"] = membership["ticker"].map(
        latest["company_name"]
    ).fillna(membership["ticker"])
    membership["sector"] = membership["ticker"].map(sectors).fillna("Unknown")
    membership["source"] = (
        "momentum_6m_claude/nasdaq100_momentum_backtest/data/"
        "nasdaq100_membership.csv"
    )
    membership["notes"] = (
        "Point-in-time Nasdaq-100 span borrowed from the sister project."
    )
    return membership[MEMBERSHIP_COLUMNS]


def borrow_prices(
    tickers: set[str], sister_root: Path, raw_price_dir: Path
) -> list[str]:
    """Copy sister price files for tickers missing from the local cache.

    Args:
        tickers: Tickers the Nasdaq-100 backtest needs.
        sister_root: Root of the sister project.
        raw_price_dir: Local one-CSV-per-ticker price cache.

    Returns:
        The tickers whose files were copied.
    """

    borrowed = []
    for ticker in sorted(tickers):
        local = raw_price_dir / f"{ticker}.csv"
        source = sister_root / "data" / "raw_prices" / f"{ticker}.csv"
        if local.exists() or not source.exists():
            continue
        prices = pd.read_csv(source, parse_dates=["Date"], index_col="Date")
        prices["Adj Close"] = prices["Close"]
        prices[PRICE_COLUMNS].to_csv(local)
        borrowed.append(ticker)
    return borrowed


def main() -> None:
    """Write the Nasdaq-100 membership file and borrow missing prices."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sister-root", type=Path, default=DEFAULT_SISTER_ROOT)
    args = parser.parse_args()

    membership = build_membership(args.sister_root)
    output = PROJECT_ROOT / "data" / "nasdaq100_membership.csv"
    membership.to_csv(output, index=False)
    borrowed = borrow_prices(
        set(membership["ticker"]) | {"QQQ"},
        args.sister_root,
        PROJECT_ROOT / "data" / "raw_prices",
    )
    print(f"Wrote {len(membership):,} membership spans to {output}")
    print(f"Borrowed {len(borrowed)} price files: {', '.join(borrowed) or 'none'}")


if __name__ == "__main__":
    main()
