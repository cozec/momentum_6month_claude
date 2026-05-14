"""Performance metrics for the momentum rotation strategy."""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


MONTHS_PER_YEAR = 12


def _series_from(df: pd.DataFrame, col: str) -> pd.Series:
    return df.set_index("rebalance_date")[col].astype(float)


def calculate_summary_stats(
    portfolio_returns: pd.DataFrame,
    periods_per_year: float = MONTHS_PER_YEAR,
) -> pd.DataFrame:
    """Compute summary statistics for the strategy and the benchmark.

    ``periods_per_year`` is how many rebalances fit in a year. For
    monthly rebalances it's 12; for bi-monthly it's 6; for quarterly
    it's 4. The annualization of vol/Sharpe and the years-denominator
    in CAGR both use this value.
    """
    if portfolio_returns.empty:
        return pd.DataFrame()

    df = portfolio_returns.copy()
    df["rebalance_date"] = pd.to_datetime(df["rebalance_date"])
    net_returns = _series_from(df, "portfolio_return_net")
    qqq_returns = _series_from(df, "qqq_return")
    has_tqqq = "tqqq_return" in df.columns and df["tqqq_return"].notna().any()
    tqqq_returns = _series_from(df, "tqqq_return") if has_tqqq else None

    def _stats(returns: pd.Series, equity_col: str) -> Dict[str, float]:
        equity = df.set_index("rebalance_date")[equity_col].astype(float)
        n_periods = len(returns)
        if n_periods == 0:
            return {}
        # equity[-1] is value AFTER the final period; compounding from
        # initial capital over n_periods holding periods gives the true
        # total return. Using equity.iloc[0] here would be off-by-one
        # because that's already post-first-period.
        total_return = float((1.0 + returns).prod()) - 1.0
        years = n_periods / periods_per_year
        cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else np.nan
        vol = returns.std(ddof=1) * np.sqrt(periods_per_year) if n_periods > 1 else np.nan
        sharpe = (
            returns.mean() / returns.std(ddof=1) * np.sqrt(periods_per_year)
            if n_periods > 1 and returns.std(ddof=1) > 0
            else np.nan
        )
        # Build a continuous equity series for drawdown so the first row
        # contributes properly.
        eq = (1.0 + returns).cumprod()
        peak = eq.cummax()
        drawdown = eq / peak - 1.0
        max_dd = float(drawdown.min())
        return {
            "CAGR": cagr,
            "annualized_volatility": vol,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
            "average_monthly_return": float(returns.mean()),
            "median_monthly_return": float(returns.median()),
            "best_month": float(returns.max()),
            "worst_month": float(returns.min()),
            "total_return": total_return,
            "number_of_rebalances": int(n_periods),
        }

    strat = _stats(net_returns, "portfolio_value")
    bench = _stats(qqq_returns, "qqq_value")
    tqqq_stats = (
        _stats(tqqq_returns, "tqqq_value") if has_tqqq else None
    )

    win_rate_qqq = (
        float((net_returns > qqq_returns).mean()) if len(net_returns) else np.nan
    )
    win_rate_tqqq = (
        float((net_returns > tqqq_returns).mean())
        if has_tqqq and len(net_returns)
        else np.nan
    )
    avg_turnover = float(df["turnover"].mean())

    strat["win_rate_vs_qqq"] = win_rate_qqq
    strat["win_rate_vs_tqqq"] = win_rate_tqqq
    strat["average_turnover"] = avg_turnover
    bench["win_rate_vs_qqq"] = np.nan
    bench["win_rate_vs_tqqq"] = np.nan
    bench["average_turnover"] = np.nan

    columns = {"strategy": strat, "benchmark_qqq": bench}
    if tqqq_stats is not None:
        tqqq_stats["win_rate_vs_qqq"] = np.nan
        tqqq_stats["win_rate_vs_tqqq"] = np.nan
        tqqq_stats["average_turnover"] = np.nan
        columns["benchmark_tqqq"] = tqqq_stats
    summary = pd.DataFrame(columns)
    return summary
