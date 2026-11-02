"""Performance metrics for monthly backtest returns."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _max_drawdown(values: pd.Series) -> float:
    """Calculate maximum drawdown from an equity curve."""

    if values.empty:
        return np.nan
    running_max = values.cummax()
    drawdown = values / running_max - 1.0
    return float(drawdown.min())


def calculate_summary_stats(portfolio_returns: pd.DataFrame) -> pd.DataFrame:
    """Calculate common monthly strategy performance statistics."""

    if portfolio_returns.empty:
        return pd.DataFrame()

    returns = pd.to_numeric(
        portfolio_returns["portfolio_return_net"], errors="coerce"
    ).dropna()
    spy_returns = pd.to_numeric(portfolio_returns.get("spy_return"), errors="coerce")
    values = pd.to_numeric(portfolio_returns["portfolio_value"], errors="coerce").dropna()
    if returns.empty or values.empty:
        return pd.DataFrame()

    periods = len(returns)
    years = periods / 12.0
    total_return = float(values.iloc[-1] / values.iloc[0] / (1 + returns.iloc[0]) - 1.0)
    if "portfolio_value" in portfolio_returns:
        initial_equity = values.iloc[0] / (1 + returns.iloc[0])
        total_return = float(values.iloc[-1] / initial_equity - 1.0)
    cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else np.nan
    annualized_volatility = float(returns.std(ddof=1) * np.sqrt(12)) if periods > 1 else np.nan
    sharpe_ratio = (
        float(returns.mean() / returns.std(ddof=1) * np.sqrt(12))
        if periods > 1 and returns.std(ddof=1) != 0
        else np.nan
    )
    downside = returns[returns < 0]
    sortino_ratio = (
        float(returns.mean() / downside.std(ddof=1) * np.sqrt(12))
        if len(downside) > 1 and downside.std(ddof=1) != 0
        else np.nan
    )
    max_drawdown = _max_drawdown(values)
    calmar_ratio = float(cagr / abs(max_drawdown)) if max_drawdown < 0 else np.nan
    monthly_win_rate = float((returns > 0).mean())
    win_rate_vs_spy = (
        float((returns.reset_index(drop=True) > spy_returns.reset_index(drop=True)).mean())
        if spy_returns.notna().any()
        else np.nan
    )
    average_turnover = float(portfolio_returns["turnover"].mean())

    stats = {
        "total_return": total_return,
        "CAGR": cagr,
        "annualized_volatility": annualized_volatility,
        "Sharpe_ratio": sharpe_ratio,
        "Sortino_ratio": sortino_ratio,
        "max_drawdown": max_drawdown,
        "Calmar_ratio": calmar_ratio,
        "monthly_win_rate": monthly_win_rate,
        "win_rate_vs_SPY": win_rate_vs_spy,
        "average_monthly_return": float(returns.mean()),
        "median_monthly_return": float(returns.median()),
        "best_month": float(returns.max()),
        "worst_month": float(returns.min()),
        "number_of_rebalances": int(periods),
        "average_turnover": average_turnover,
        "average_holding_period": "1 month",
    }
    return pd.DataFrame([stats])


def _alpha_beta(
    returns: pd.Series, benchmark_returns: pd.Series
) -> tuple[float, float]:
    """Annualized alpha and beta of monthly returns versus a benchmark.

    Uses an OLS fit of strategy on benchmark monthly returns with a zero
    risk-free rate, matching the Sharpe convention used in this module.
    """

    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 2 or aligned.iloc[:, 1].var(ddof=1) == 0:
        return np.nan, np.nan
    strat, bench = aligned.iloc[:, 0], aligned.iloc[:, 1]
    beta = float(strat.cov(bench) / bench.var(ddof=1))
    alpha = float((strat.mean() - beta * bench.mean()) * 12)
    return alpha, beta


def calculate_strategy_comparison(
    portfolio_returns: pd.DataFrame,
    benchmark_first_price: float,
    benchmark_last_price: float,
    benchmark_label: str = "SPY",
    start_capital: float = 10_000.0,
) -> pd.DataFrame:
    """Compare the strategy with benchmark buy & hold from a fixed capital.

    The strategy row compounds monthly net returns from ``start_capital``. The
    buy & hold row uses ``start_capital * last_price / first_price`` over the
    same first-entry to last-exit window. Max drawdown includes the starting
    capital as the first equity point, so a first-month loss counts. Rows are
    ordered by final equity, highest first.

    Args:
        portfolio_returns: Backtest rows with ``portfolio_return_net`` and
            ``spy_return`` columns.
        benchmark_first_price: Benchmark adjusted close on the first entry
            date.
        benchmark_last_price: Benchmark adjusted close on the last exit date.
        benchmark_label: Display name for the benchmark.
        start_capital: Starting equity for both rows.

    Returns:
        One row per strategy with Final Equity, Return, CAGR, Max DD, Sharpe,
        Alpha and Beta, or an empty frame when there are no returns.
    """

    if portfolio_returns.empty:
        return pd.DataFrame()

    returns = pd.to_numeric(
        portfolio_returns["portfolio_return_net"], errors="coerce"
    )
    spy_returns = pd.to_numeric(
        portfolio_returns["spy_return"], errors="coerce"
    )
    years = len(returns) / 12.0

    def _row(name: str, period_returns: pd.Series, final_equity: float,
             alpha: float, beta: float) -> dict[str, object]:
        """Build one comparison row from monthly returns and final equity."""

        clean = period_returns.dropna()
        equity = start_capital * (1.0 + clean).cumprod()
        equity = pd.concat(
            [pd.Series([start_capital]), equity], ignore_index=True
        )
        total_return = final_equity / start_capital - 1.0
        cagr = (
            (1.0 + total_return) ** (1.0 / years) - 1.0
            if years > 0
            else np.nan
        )
        std = clean.std(ddof=1)
        sharpe = float(clean.mean() / std * np.sqrt(12)) if std else np.nan
        return {
            "Strategy": name,
            "Final Equity": round(final_equity, 2),
            "Return": total_return,
            "CAGR": cagr,
            "Max DD": _max_drawdown(equity),
            "Sharpe": sharpe,
            "Alpha": alpha,
            "Beta": beta,
        }

    alpha, beta = _alpha_beta(returns, spy_returns)
    rows = [
        _row(
            "Titan-12 Momentum",
            returns,
            float(start_capital * (1.0 + returns.dropna()).prod()),
            alpha,
            beta,
        )
    ]
    if pd.notna(benchmark_first_price) and pd.notna(benchmark_last_price):
        rows.append(
            _row(
                f"{benchmark_label} Buy & Hold",
                spy_returns,
                float(
                    start_capital * benchmark_last_price
                    / benchmark_first_price
                ),
                0.0,
                1.0,
            )
        )
    comparison = pd.DataFrame(rows)
    comparison = comparison.sort_values("Final Equity", ascending=False)
    return comparison.reset_index(drop=True)
