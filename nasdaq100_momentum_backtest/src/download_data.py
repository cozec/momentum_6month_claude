"""Download daily price data from Yahoo Finance with local caching.

The downloader saves each ticker's daily OHLCV history to a per-ticker
CSV in ``data/raw_prices``. The cache is keyed by the requested date
range; if a cached file already covers the requested span it is reused.
"""

from __future__ import annotations

import os
import time
from typing import Iterable, List, Optional

import pandas as pd
import yfinance as yf

from .config import RAW_PRICES_DIR
from .utils import ensure_dir, get_logger, to_business_date

LOGGER = get_logger("download_data")

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _cache_path(ticker: str) -> str:
    """Return the on-disk CSV path for ``ticker``."""
    return os.path.join(RAW_PRICES_DIR, f"{ticker.upper()}.csv")


def _clean_price_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a price DataFrame.

    yfinance's newer versions sometimes return a column ``MultiIndex``
    where the second level is the ticker symbol. When concatenated with
    a cached single-level frame, the ticker labels can leak into a data
    row (e.g. ``,AAPL,AAPL,AAPL,AAPL,AAPL``), poisoning the cache. This
    helper guarantees:

      * single-level columns
      * ``DatetimeIndex`` named "Date" with no ``NaT`` rows
      * required OHLCV columns coerced to numeric (junk rows dropped)
      * deduped, sorted index
    """
    if df is None or df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    df = df.rename_axis("Date")
    df.index = pd.to_datetime(df.index, errors="coerce")
    df = df[~df.index.isna()]
    keep = [c for c in REQUIRED_COLUMNS if c in df.columns]
    df = df[keep].copy()
    for col in keep:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Close"]) if "Close" in df.columns else df.dropna(how="all")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _load_cached(ticker: str) -> Optional[pd.DataFrame]:
    """Load a cached price history for ``ticker`` if present."""
    path = _cache_path(ticker)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, index_col="Date", parse_dates=["Date"])
    except (ValueError, KeyError):
        return None
    df = _clean_price_frame(df)
    if df is None or df.empty:
        return None
    return df


def _cache_covers(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    """Return True when ``df`` extends through (roughly) ``end``.

    We only enforce the end boundary: yfinance hands back at most the
    earliest available print for each ticker, so re-downloading a
    post-IPO name doesn't yield more history. The 3-day calendar
    tolerance covers weekends/holidays so a cache produced on Friday
    is still valid over the weekend.
    """
    if df.empty:
        return False
    cached_end = df.index.max()
    end_tolerance = end - pd.Timedelta(days=3)
    return cached_end >= end_tolerance


def _download_one(
    ticker: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    retries: int = 3,
) -> Optional[pd.DataFrame]:
    """Download ``ticker``'s daily price history, retrying on failure."""
    for attempt in range(1, retries + 1):
        try:
            df = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Download attempt %s for %s failed: %s", attempt, ticker, exc
            )
            time.sleep(1.5 * attempt)
            continue

        if df is None or df.empty:
            LOGGER.warning("Empty data for %s on attempt %s", ticker, attempt)
            time.sleep(1.0 * attempt)
            continue

        return _clean_price_frame(df)

    LOGGER.error("All download attempts failed for %s", ticker)
    return None


def download_price_data(
    tickers: Iterable[str],
    start_date: str,
    end_date: str,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Download adjusted price data for ``tickers``.

    Returns a wide DataFrame whose columns are tickers and whose index
    is the trading-day date. The "Close" column from yfinance with
    ``auto_adjust=True`` represents the dividend- and split-adjusted
    close which is suitable for return calculations.

    Parameters
    ----------
    tickers : Iterable[str]
        Tickers to download.
    start_date, end_date : str
        Inclusive date range in YYYY-MM-DD form.
    force_refresh : bool
        When True, re-download even if a cached file already covers the
        requested range.
    """
    ensure_dir(RAW_PRICES_DIR)
    start = to_business_date(start_date)
    end = to_business_date(end_date)

    closes: dict[str, pd.Series] = {}
    failed: List[str] = []

    for ticker in tickers:
        cached = None if force_refresh else _load_cached(ticker)
        if cached is not None and _cache_covers(cached, start, end):
            LOGGER.info("Using cached prices for %s", ticker)
            df = cached
        else:
            LOGGER.info("Downloading %s", ticker)
            df = _download_one(ticker, start, end)
            if df is None:
                failed.append(ticker)
                continue
            # Merge with any existing cache so we keep the broadest range.
            if cached is not None:
                df = pd.concat([cached, df])
            df = _clean_price_frame(df)
            df.to_csv(_cache_path(ticker), index_label="Date")

        # Restrict to the requested window for the returned panel.
        window = df.loc[(df.index >= start) & (df.index <= end), "Close"]
        if window.empty:
            failed.append(ticker)
            continue
        closes[ticker] = window.rename(ticker)

    if failed:
        LOGGER.warning("Failed to retrieve data for: %s", ", ".join(failed))

    if not closes:
        raise RuntimeError("No price data was successfully downloaded.")

    panel = pd.concat(closes.values(), axis=1).sort_index()
    return panel
