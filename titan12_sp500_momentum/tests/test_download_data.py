"""Tests for price cache refresh behaviour."""

from __future__ import annotations

import pandas as pd

from src import download_data
from src.download_data import PRICE_COLUMNS, download_price_data


def _prices(start: str, periods: int) -> pd.DataFrame:
    """Build a small daily price frame in the cache schema."""

    index = pd.bdate_range(start, periods=periods, name="Date")
    return pd.DataFrame(
        {column: 1.0 for column in PRICE_COLUMNS}, index=index
    )


def _seed_cache(tmp_path, ticker: str) -> pd.DataFrame:
    """Write a 2016-2017 history for ``ticker`` into the cache directory."""

    cached = _prices("2016-01-04", 400)
    cached.to_csv(tmp_path / f"{ticker}.csv")
    return cached


def test_refresh_keeps_cache_when_download_is_truncated(
    tmp_path, monkeypatch
) -> None:
    """A post-merger stub must not overwrite years of cached history."""

    cached = _seed_cache(tmp_path, "QRVO")
    monkeypatch.setattr(
        download_data,
        "_download_ticker_history",
        lambda *args: _prices("2026-07-29", 5),
    )

    prices, issues = download_price_data(
        ["QRVO"], "2016-01-01", "2026-10-09", tmp_path, refresh=True
    )

    assert len(prices["QRVO"]) == len(cached)
    on_disk = pd.read_csv(tmp_path / "QRVO.csv")
    assert len(on_disk) == len(cached)
    assert issues["issue_type"].tolist() == ["refresh_kept_cache"]


def test_refresh_keeps_cache_when_download_is_empty(
    tmp_path, monkeypatch
) -> None:
    """A delisted ticker Yahoo no longer serves still uses its cached prices."""

    cached = _seed_cache(tmp_path, "ANDV")
    monkeypatch.setattr(
        download_data, "_download_ticker_history", lambda *args: pd.DataFrame()
    )

    prices, issues = download_price_data(
        ["ANDV"], "2016-01-01", "2026-10-09", tmp_path, refresh=True
    )

    assert len(prices["ANDV"]) == len(cached)
    assert issues["issue_type"].tolist() == ["refresh_kept_cache"]


def test_refresh_overwrites_cache_with_full_redownload(
    tmp_path, monkeypatch
) -> None:
    """A full-length redownload still replaces the cache (re-adjustment)."""

    _seed_cache(tmp_path, "AAPL")
    fresh = _prices("2016-01-04", 450) * 2.0
    monkeypatch.setattr(
        download_data, "_download_ticker_history", lambda *args: fresh
    )

    prices, issues = download_price_data(
        ["AAPL"], "2016-01-01", "2026-10-09", tmp_path, refresh=True
    )

    assert len(prices["AAPL"]) == 450
    assert prices["AAPL"]["Adj Close"].iloc[0] == 2.0
    assert issues.empty
