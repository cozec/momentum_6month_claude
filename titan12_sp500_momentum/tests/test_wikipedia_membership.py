"""Tests for the Wikipedia S&P 500 membership bootstrap script."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts import build_wikipedia_sp500_membership as wiki
from src.membership import WIKIPEDIA_SP500_CHANGES_URL, WIKIPEDIA_SP500_URL


def test_clean_ticker_strips_trailing_wiki_pipe() -> None:
    """Tickers like 'ITT |' on the changes page should normalize cleanly."""

    assert wiki._clean_ticker("ITT |") == "ITT"
    assert wiki._clean_ticker("ALLE |") == "ALLE"
    assert wiki._clean_ticker("BRK.B") == "BRK-B"
    assert wiki._clean_ticker(None) == ""
    assert wiki._clean_ticker("|") == ""


class _FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        """Pretend the request succeeded."""


def test_read_table_selects_by_header_not_position(monkeypatch) -> None:
    """Skip a navbox above the table, even when the header is split by a link.

    The live constituents page renders ``<a>GICS</a> Sector``, which spans
    two HTML text nodes.
    """

    html = """
    <table><tr><th>Navbox</th></tr><tr><td>x</td></tr></table>
    <table><tr><th>Symbol</th><th><a href="/wiki/GICS">GICS</a> Sector</th></tr>
    <tr><td>AAPL</td><td>Information Technology</td></tr></table>
    """
    monkeypatch.setattr(
        wiki.requests, "get", lambda *args, **kwargs: _FakeResponse(html)
    )

    table = wiki._read_table("https://example.org", "GICS Sector")

    assert list(table.columns) == ["Symbol", "GICS Sector"]
    with pytest.raises(RuntimeError, match="Effective Date"):
        wiki._read_table("https://example.org", "Effective Date")


def test_build_membership_labels_change_rows_with_changes_url(
    monkeypatch,
) -> None:
    """Removal intervals should cite the change-history page as their source."""

    current = pd.DataFrame(
        {
            "Symbol": ["AAA"],
            "Security": ["Alpha"],
            "GICS Sector": ["Industrials"],
            "Date added": ["2010-01-01"],
        }
    )
    changes = pd.DataFrame(
        [["2020-03-02", "AAA", "Alpha", "ITT |", "ITT Inc", "Replaced"]],
        columns=pd.MultiIndex.from_tuples(
            [
                ("Effective Date", "Effective Date"),
                ("Added", "Ticker"),
                ("Added", "Security"),
                ("Removed", "Ticker"),
                ("Removed", "Security"),
                ("Reason", "Reason"),
            ]
        ),
    )
    monkeypatch.setattr(wiki, "_load_wikipedia_tables", lambda: (current, changes))

    membership = wiki.build_membership().set_index("ticker")

    assert membership.loc["ITT", "end_date"] == "2020-03-01"
    assert membership.loc["ITT", "source"] == WIKIPEDIA_SP500_CHANGES_URL
    assert membership.loc["AAA", "start_date"] == "2020-03-02"
    assert membership.loc["AAA", "source"] == WIKIPEDIA_SP500_URL
    assert WIKIPEDIA_SP500_CHANGES_URL in membership.loc["AAA", "notes"]
