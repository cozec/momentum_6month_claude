"""Fetch the current S&P 500 constituents and cache their prices.

Writes ``data/sp500_constituents.csv`` (one ``Symbol`` per row) and downloads
daily price history for every constituent into ``data/raw_prices/`` via the
project's cached downloader. Symbols are normalized to Yahoo form (``BRK.B`` ->
``BRK-B``).

Source: Wikipedia "List of S&P 500 companies" (current snapshot only — this is
NOT point-in-time membership, so a backtest over this universe carries some
survivorship bias).

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

sys.path.insert(0, PROJ)
from src.download_data import download_price_data  # noqa: E402

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

START_DATE = "2016-01-01"


def fetch_constituents() -> list[str]:
    req = urllib.request.Request(WIKI_URL, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    df = pd.read_html(io.StringIO(html))[0]
    syms = (
        df["Symbol"].astype(str).str.replace(".", "-", regex=False).str.upper()
    )
    return sorted(set(syms.tolist()))


def main() -> None:
    syms = fetch_constituents()
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    pd.Series(syms, name="Symbol").to_csv(OUT_CSV, index=False)
    print(f"Wrote {OUT_CSV} ({len(syms)} tickers)")

    end = pd.Timestamp.now().normalize().strftime("%Y-%m-%d")
    panel = download_price_data(syms, START_DATE, end, force_refresh=False)
    print(f"Cached prices for {panel.shape[1]}/{len(syms)} tickers "
          f"({len(panel)} trading days) in data/raw_prices/")


if __name__ == "__main__":
    main()
