"""Tests for performance metric generation."""

from __future__ import annotations

import pandas as pd
import pytest

from src.metrics import calculate_strategy_comparison, calculate_summary_stats


def test_summary_stats_basic_shape() -> None:
    """Summary stats should include required headline metrics."""

    returns = [0.01, -0.02, 0.03]
    values = [101000.0, 98980.0, 101949.4]
    portfolio_returns = pd.DataFrame(
        {
            "portfolio_return_net": returns,
            "spy_return": [0.0, 0.0, 0.0],
            "portfolio_value": values,
            "turnover": [1.0, 0.5, 0.5],
        }
    )
    stats = calculate_summary_stats(portfolio_returns)
    assert not stats.empty
    assert "Sharpe_ratio" in stats.columns
    assert stats.loc[0, "number_of_rebalances"] == 3


def test_strategy_comparison_buy_and_hold_and_ordering() -> None:
    """B&H uses the simple price ratio and rows sort by final equity."""

    portfolio_returns = pd.DataFrame(
        {
            "portfolio_return_net": [-0.10, 0.20, 0.02, 0.04],
            "spy_return": [-0.05, 0.10, 0.01, 0.02],
        }
    )

    comparison = calculate_strategy_comparison(
        portfolio_returns, 100.0, 125.0, benchmark_label="SPY"
    )

    assert comparison["Strategy"].tolist() == [
        "SPY Buy & Hold",
        "Titan-12 Momentum",
    ]
    spy = comparison.iloc[0]
    assert spy["Final Equity"] == pytest.approx(12_500.0)
    assert spy["Beta"] == 1.0
    strategy = comparison.iloc[1]
    assert strategy["Final Equity"] == pytest.approx(
        10_000 * 0.9 * 1.2 * 1.02 * 1.04, abs=0.01
    )
    # Strategy returns are exactly 2x SPY's, so beta is 2 and alpha is 0.
    assert strategy["Beta"] == pytest.approx(2.0)
    assert strategy["Alpha"] == pytest.approx(0.0, abs=1e-12)
    # The first-month loss counts because start capital is in the curve.
    assert strategy["Max DD"] == pytest.approx(-0.10)
