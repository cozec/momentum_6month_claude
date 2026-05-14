"""Configuration for the Nasdaq-100 monthly momentum rotation backtest.

All tunable parameters live here so the backtest can be reproduced by
adjusting a single source of truth.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import List


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RAW_PRICES_DIR = os.path.join(DATA_DIR, "raw_prices")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")
CHARTS_DIR = os.path.join(OUTPUTS_DIR, "charts")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
MEMBERSHIP_CSV = os.path.join(DATA_DIR, "nasdaq100_membership.csv")


# The current Nasdaq-100 constituents (101 tickers because both share
# classes of Alphabet — GOOG and GOOGL — are listed). This is the
# survivorship-biased universe documented in the README. Tickers
# normalized for Yahoo Finance. Reconciled against the raw_prices
# directory snapshot.
CURRENT_NASDAQ100: List[str] = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "ALNY", "AMAT",
    "AMD", "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO", "AXON", "BKNG",
    "BKR", "CCEP", "CDNS", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD",
    "CSCO", "CSGP", "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA",
    "EXC", "FANG", "FAST", "FER", "FTNT", "GEHC", "GILD", "GOOG", "GOOGL",
    "HON", "IDXX", "INSM", "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC",
    "LIN", "LRCX", "MAR", "MCHP", "MDLZ", "MELI", "META", "MNST", "MPWR",
    "MRVL", "MSFT", "MSTR", "MU", "NFLX", "NVDA", "NXPI", "ODFL", "ORLY",
    "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR", "PYPL", "QCOM", "REGN",
    "ROP", "ROST", "SBUX", "SHOP", "SNDK", "SNPS", "STX", "TMUS", "TRI",
    "TSLA", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "WDC", "WMT",
    "XEL", "ZS",
]


@dataclass
class BacktestConfig:
    """Container for all backtest configuration parameters."""

    start_date: str = "2016-01-01"
    end_date: str = "2026-05-12"
    top_n: int = 3
    lookback_months: int = 6
    rebalance_frequency: str = "monthly"
    rebalance_period_months: int = 1
    benchmark: str = "QQQ"
    secondary_benchmark: str = "TQQQ"
    initial_capital: float = 100_000.0
    transaction_cost_bps: float = 0.0
    slippage_bps: float = 0.0
    min_price_history_months: int = 6
    # "average_monthly_return" or "compound_6m_return"
    score_method: str = "average_monthly_return"
    use_historical_membership: bool = False
    force_refresh: bool = False
    tickers: List[str] = field(default_factory=lambda: list(CURRENT_NASDAQ100))

    def transaction_cost_rate(self) -> float:
        """Per-trade transaction cost as a fraction (e.g. 0.0005)."""
        return self.transaction_cost_bps / 10_000.0

    def slippage_rate(self) -> float:
        """Per-trade slippage as a fraction (e.g. 0.0005)."""
        return self.slippage_bps / 10_000.0
