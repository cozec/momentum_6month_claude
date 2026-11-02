"""Market data download, caching, and loading helpers."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yfinance as yf

from src.utils import append_quality_issue, normalize_ticker


LOGGER = logging.getLogger(__name__)
PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
# A refresh whose history starts this much later than the cached file is
# treated as truncated (e.g. a post-merger stub) and the cache is kept.
REFRESH_TRUNCATION_TOLERANCE = pd.Timedelta(days=30)


def price_cache_path(raw_price_dir: Path, ticker: str) -> Path:
    """Return the cache path for a ticker's raw daily price file."""

    safe_ticker = normalize_ticker(ticker).replace("^", "")
    return raw_price_dir / f"{safe_ticker}.csv"


def _clean_downloaded_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Normalize yfinance output into the expected daily price schema."""

    if prices.empty:
        return prices
    prices = prices.copy()
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = prices.columns.get_level_values(0)
    prices.columns.name = None
    prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
    prices.index.name = "Date"
    for column in PRICE_COLUMNS:
        if column not in prices.columns:
            prices[column] = pd.NA
    return prices[PRICE_COLUMNS].dropna(how="all")


def _download_ticker_history(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download and normalize a daily price frame for the inclusive date range."""

    downloaded = yf.download(
        ticker,
        start=start_date,
        end=(pd.Timestamp(end_date) + pd.Timedelta(days=1)).date().isoformat(),
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    return _clean_downloaded_prices(downloaded)


def download_price_data(
    tickers: list[str],
    start_date: str,
    end_date: str,
    raw_price_dir: Path | str = Path("data/raw_prices"),
    refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Download or load cached daily adjusted price data for tickers.

    A cached ticker is topped up incrementally: only the rows after the last
    cached date are fetched and merged into the cache file, so a monthly run
    pulls just the new tail instead of the full history. Passing ``refresh``
    forces a full redownload, which is also what re-adjusts historical adjusted
    closes after splits or dividends (incremental top-up leaves older rows on
    their previously downloaded adjustment basis).

    Parameters
    ----------
    tickers
        Symbols to download from Yahoo Finance.
    start_date, end_date
        Inclusive research date range.
    raw_price_dir
        Directory used for one-CSV-per-ticker cache files.
    refresh
        If true, redownload the full range instead of topping up the cache.
        The cache is kept, and the issue logged, when the redownload comes
        back empty or starts more than ``REFRESH_TRUNCATION_TOLERANCE`` after
        the cached history, since Yahoo drops or stubs delisted tickers.

    Returns
    -------
    tuple[dict[str, pandas.DataFrame], pandas.DataFrame]
        Price frames keyed by normalized ticker and a data quality report.
    """

    raw_price_dir = Path(raw_price_dir)
    raw_price_dir.mkdir(parents=True, exist_ok=True)
    price_data: dict[str, pd.DataFrame] = {}
    issues: list[dict[str, object]] = []
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    for raw_ticker in sorted(set(tickers)):
        ticker = normalize_ticker(raw_ticker)
        cache_path = price_cache_path(raw_price_dir, ticker)
        try:
            cached = None
            if cache_path.exists() and not refresh:
                cached = pd.read_csv(cache_path, parse_dates=["Date"], index_col="Date")
                cached.index = pd.to_datetime(cached.index).tz_localize(None).normalize()

            if cached is not None and not cached.empty:
                last_cached = cached.index.max()
                if last_cached < end:
                    LOGGER.info("Updating %s from %s", ticker, last_cached.date())
                    # Re-fetch from the last cached day (inclusive) so the merge
                    # overwrites that day with its settled values and appends the gap.
                    fresh_tail = _download_ticker_history(
                        ticker, last_cached.date().isoformat(), end_date
                    )
                    if not fresh_tail.empty:
                        combined = pd.concat([cached, fresh_tail])
                        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                        combined.to_csv(cache_path)
                        cached = combined
                prices = cached
            else:
                LOGGER.info("Downloading %s", ticker)
                prices = _download_ticker_history(ticker, start_date, end_date)
                previous = None
                if refresh and cache_path.exists():
                    previous = pd.read_csv(
                        cache_path, parse_dates=["Date"], index_col="Date"
                    )
                    previous.index = (
                        pd.to_datetime(previous.index).tz_localize(None).normalize()
                    )
                if (
                    previous is not None
                    and not previous.empty
                    and (
                        prices.empty
                        or prices.index.min()
                        > previous.index.min() + REFRESH_TRUNCATION_TOLERANCE
                    )
                ):
                    append_quality_issue(
                        issues,
                        ticker,
                        "refresh_kept_cache",
                        "Redownload was empty or truncated; kept cached history "
                        f"from {previous.index.min().date()}.",
                    )
                    prices = previous
                elif prices.empty:
                    append_quality_issue(
                        issues, ticker, "download_failed", "No rows returned by yfinance."
                    )
                    continue
                else:
                    prices.to_csv(cache_path)

            prices = prices.loc[(prices.index >= start) & (prices.index <= end)]

            if prices.empty:
                append_quality_issue(
                    issues, ticker, "empty_range", "No cached rows in requested range."
                )
                continue
            if prices["Adj Close"].isna().all():
                append_quality_issue(
                    issues, ticker, "missing_adj_close", "Adjusted close is unavailable."
                )
                continue
            price_data[ticker] = prices
        except Exception as exc:  # pragma: no cover - defensive download logging
            LOGGER.exception("Failed to load %s", ticker)
            append_quality_issue(issues, ticker, "exception", str(exc))

    return price_data, pd.DataFrame(issues)


def load_cached_price_data(
    tickers: list[str],
    raw_price_dir: Path | str,
    start_date: str,
    end_date: str,
) -> dict[str, pd.DataFrame]:
    """Load cached prices for tickers without attempting network downloads."""

    raw_price_dir = Path(raw_price_dir)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    price_data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        normalized = normalize_ticker(ticker)
        cache_path = price_cache_path(raw_price_dir, normalized)
        if not cache_path.exists():
            continue
        prices = pd.read_csv(cache_path, parse_dates=["Date"], index_col="Date")
        prices.index = pd.to_datetime(prices.index).tz_localize(None).normalize()
        price_data[normalized] = prices.loc[(prices.index >= start) & (prices.index <= end)]
    return price_data
