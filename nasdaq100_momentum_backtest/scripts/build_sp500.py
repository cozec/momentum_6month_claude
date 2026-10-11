"""Build the S&P 500 universe: constituents, point-in-time membership, prices.

Writes
  * ``data/sp500_constituents.csv`` — today's members with company name and
    GICS labels (the dashboard's sector column), and
  * ``data/sp500_membership.csv`` — point-in-time spans (``ticker``,
    ``start_date``, ``end_date``) for every stock that was a member at any
    point since 2016, rebuilt from today's list plus the index change log,
and downloads daily price history for every ticker in the membership file
into ``data/raw_prices/`` via the project's cached downloader. Symbols are
normalized to Yahoo form (``BRK.B`` -> ``BRK-B``).

Sources: Wikipedia "List of S&P 500 companies" and "Historical components of
the S&P 500". Removed members that Yahoo no longer serves (most acquisitions
and bankruptcies) get no price file and drop out of the universe, so some
survivorship bias remains.

Run:  python scripts/build_sp500.py
"""

from __future__ import annotations

import io
import os
import sys
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, ".."))
OUT_CSV = os.path.join(PROJ, "data", "sp500_constituents.csv")
MEMBERSHIP_CSV = os.path.join(PROJ, "data", "sp500_membership.csv")

sys.path.insert(0, PROJ)
from src.download_data import download_price_data  # noqa: E402

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
CHANGES_URL = "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

START_DATE = "2016-01-01"


def _first_table(url: str) -> pd.DataFrame:
    """Return the first HTML table on a Wikipedia page."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    return pd.read_html(io.StringIO(html))[0]


def _yahoo(symbols: pd.Series) -> pd.Series:
    """Normalize tickers to Yahoo form, keeping blanks as NaN."""
    norm = symbols.astype(str).str.replace(".", "-", regex=False).str.upper()
    return norm.where(symbols.notna())


def fetch_constituents() -> pd.DataFrame:
    """Return the current constituents with company name, GICS labels and add date.

    Columns: ``Symbol`` (Yahoo form), ``Security``, ``GICS Sector``,
    ``GICS Sub-Industry`` and ``Date added``; the dashboard uses the middle
    three as sector labels.
    """
    df = _first_table(WIKI_URL)
    df["Symbol"] = _yahoo(df["Symbol"])
    cols = ["Symbol", "Security", "GICS Sector", "GICS Sub-Industry", "Date added"]
    return df[cols].drop_duplicates("Symbol").sort_values("Symbol")


def fetch_changes() -> pd.DataFrame:
    """Return the index change log, newest first: ``date``, ``added``, ``removed``."""
    c = _first_table(CHANGES_URL)
    out = pd.DataFrame({
        "date": pd.to_datetime(c[("Effective Date", "Effective Date")], errors="coerce"),
        "added": _yahoo(c[("Added", "Ticker")]),
        "removed": _yahoo(c[("Removed", "Ticker")]),
    })
    return out.dropna(subset=["date"]).sort_values("date", ascending=False, kind="stable")


def build_membership(
    constituents: pd.DataFrame, changes: pd.DataFrame, since: str = START_DATE
) -> pd.DataFrame:
    """Point-in-time spans (``ticker``, ``start_date``, ``end_date``).

    Walks the change log backwards from today's membership: an addition on
    date ``d`` opens the ticker's span at ``d``; a removal on ``d`` means the
    ticker was a member through the day before. A current member's span that
    starts before the log falls back to the constituents table's
    ``Date added``; any other span with no recorded start uses 2000-01-01.
    Spans that ended before ``since`` are dropped; ``end_date`` is empty for
    current members.
    """
    added_on = pd.to_datetime(
        constituents.set_index("Symbol")["Date added"], errors="coerce"
    )
    open_end = {t: pd.NaT for t in constituents["Symbol"]}  # span being traced back
    spans = []
    for ch in changes.itertuples():
        if isinstance(ch.added, str) and ch.added in open_end:
            spans.append((ch.added, ch.date, open_end.pop(ch.added)))
        if isinstance(ch.removed, str) and ch.removed not in open_end:
            open_end[ch.removed] = ch.date - pd.Timedelta(days=1)
    for ticker, end in open_end.items():
        # "Date added" describes the current span only, never an earlier one.
        start = added_on.get(ticker, pd.NaT) if pd.isna(end) else pd.NaT
        spans.append((ticker, start if pd.notna(start) else pd.Timestamp("2000-01-01"), end))
    df = pd.DataFrame(spans, columns=["ticker", "start_date", "end_date"])
    df = df[df["end_date"].isna() | (df["end_date"] >= pd.Timestamp(since))]
    return df.sort_values(["ticker", "start_date"]).reset_index(drop=True)


def main() -> None:
    constituents = fetch_constituents()
    membership = build_membership(constituents, fetch_changes())
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    constituents.to_csv(OUT_CSV, index=False)
    membership.to_csv(MEMBERSHIP_CSV, index=False, date_format="%Y-%m-%d")
    syms = sorted(membership["ticker"].unique())
    print(f"Wrote {OUT_CSV} ({len(constituents)} current members)")
    print(f"Wrote {MEMBERSHIP_CSV} ({len(membership)} spans, {len(syms)} tickers since {START_DATE})")

    end = pd.Timestamp.now().normalize().strftime("%Y-%m-%d")
    panel = download_price_data(syms, START_DATE, end, force_refresh=False)
    print(f"Cached prices for {panel.shape[1]}/{len(syms)} tickers "
          f"({len(panel)} trading days) in data/raw_prices/")


if __name__ == "__main__":
    main()
