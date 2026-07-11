"""Download daily price data from Yahoo Finance with local caching.

The downloader saves each ticker's daily OHLCV history to a per-ticker
CSV in ``data/raw_prices``. If a cached file already covers the
requested span it is reused without hitting the network. When the cache
is stale (or ``force_refresh`` is set), only the missing tail of bars is
downloaded and merged onto the existing cache, rather than re-fetching
the full history.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Iterable, List, Optional

import pandas as pd
import yfinance as yf

from .config import RAW_PRICES_DIR
from .utils import ensure_dir, get_logger, to_business_date

LOGGER = get_logger("download_data")

REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# When fetching only the tail of a stale cache, re-request a few extra
# days before the last cached bar. The overlap absorbs any late-arriving
# or revised prints and keeps the merge seam continuous.
INCREMENTAL_OVERLAP_DAYS = 5

# yfinance calls are network-bound, so fetch tickers concurrently. Kept
# modest to stay well under Yahoo's rate limits.
MAX_DOWNLOAD_WORKERS = 8

# Reuse a just-built price panel for the identical (tickers, span, refresh)
# request. The dashboard asks for two strategies in one page refresh, both
# over the same universe — without this the universe downloads twice.
_PANEL_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_PANEL_CACHE_TTL = 60.0
_PANEL_LOCK = Lock()


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
    # Ticker.history() returns a tz-aware index; drop the tz so it merges
    # cleanly with the naive-dated CSV cache and slices against naive bounds.
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
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
    """Download ``ticker``'s daily price history, retrying on failure.

    Uses the instance-based ``Ticker.history`` API rather than
    ``yf.download``: the latter writes module-global state and is not
    safe to call from multiple threads at once, which corrupts frames
    when the universe is fetched concurrently.
    """
    for attempt in range(1, retries + 1):
        try:
            df = yf.Ticker(ticker).history(
                start=start.strftime("%Y-%m-%d"),
                end=(end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=True,
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
    full_refresh: bool = False,
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
        When True, bypass the "cache already covers the range" shortcut
        and check the provider for new bars. The fetch is still
        incremental: only data after the last cached date is downloaded
        and merged, not the full history.
    full_refresh : bool
        When True, ignore the cache completely and re-download the full
        range, overwriting the cached file. Use this to pick up split/
        dividend re-adjustments that an incremental update would miss
        (the provider re-adjusts the whole series, but a tail-only fetch
        leaves older cached bars on their previous adjustment basis).
    """
    ensure_dir(RAW_PRICES_DIR)
    start = to_business_date(start_date)
    end = to_business_date(end_date)
    tickers = list(tickers)

    # Serve an identical request built moments ago (the two dashboard
    # strategies share one universe) instead of re-fetching it.
    cache_key = (
        tuple(sorted({t.upper() for t in tickers})),
        start, end, force_refresh, full_refresh,
    )
    now = time.time()
    with _PANEL_LOCK:
        entry = _PANEL_CACHE.get(cache_key)
    if entry is not None and now - entry[0] < _PANEL_CACHE_TTL:
        LOGGER.info("Reusing in-memory price panel (%.1fs old)", now - entry[0])
        return entry[1].copy()

    # yfinance is network-bound; fetch tickers concurrently.
    closes: dict[str, pd.Series] = {}
    failed: List[str] = []
    workers = max(1, min(MAX_DOWNLOAD_WORKERS, len(tickers)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_ticker_close, t, start, end, force_refresh, full_refresh): t
            for t in tickers
        }
        for fut in as_completed(futures):
            ticker = futures[fut]
            series = fut.result()
            if series is None or series.empty:
                failed.append(ticker)
            else:
                closes[ticker] = series

    if failed:
        LOGGER.warning("Failed to retrieve data for: %s", ", ".join(failed))

    if not closes:
        raise RuntimeError("No price data was successfully downloaded.")

    panel = pd.concat(closes.values(), axis=1).sort_index()
    with _PANEL_LOCK:
        _PANEL_CACHE[cache_key] = (now, panel)
    return panel


def _fetch_ticker_close(
    ticker: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    force_refresh: bool,
    full_refresh: bool,
) -> Optional[pd.Series]:
    """Resolve one ticker's close series over ``[start, end]``.

    Reuses the CSV cache, fetching only the missing tail when stale, and
    writes the merged history back. Returns ``None`` when no usable data
    is available. Safe to run concurrently — each ticker owns its own
    cache file.
    """
    # full_refresh discards the cache so the ticker is re-downloaded
    # from scratch and its file overwritten with re-adjusted bars.
    cached = None if full_refresh else _load_cached(ticker)
    if not force_refresh and cached is not None and _cache_covers(cached, start, end):
        LOGGER.info("Using cached prices for %s", ticker)
        df = cached
    else:
        # Fetch only what's missing. With an existing cache we request
        # just the tail (from a few days before the last cached bar
        # through ``end``); otherwise we pull the full requested range.
        if cached is not None and not cached.empty:
            dl_start = cached.index.max() - pd.Timedelta(days=INCREMENTAL_OVERLAP_DAYS)
            dl_start = min(max(dl_start, start), end)
            LOGGER.info(
                "Updating %s from %s (cache ends %s)",
                ticker,
                dl_start.date(),
                cached.index.max().date(),
            )
        else:
            dl_start = start
            LOGGER.info("Downloading %s (full history)", ticker)

        fresh = _download_one(ticker, dl_start, end)
        if fresh is None:
            # Download failed: fall back to whatever we already have
            # rather than dropping the ticker entirely.
            if cached is not None:
                LOGGER.warning("Update failed for %s; using cached data", ticker)
                df = cached
            else:
                return None
        else:
            # Merge with the existing cache so we keep the broadest range.
            df = pd.concat([cached, fresh]) if cached is not None else fresh
            df = _clean_price_frame(df)
            df.to_csv(_cache_path(ticker), index_label="Date")

    # Restrict to the requested window for the returned panel.
    window = df.loc[(df.index >= start) & (df.index <= end), "Close"]
    if window.empty:
        return None
    return window.rename(ticker)
