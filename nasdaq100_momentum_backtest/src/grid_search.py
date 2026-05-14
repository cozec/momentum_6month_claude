"""Grid search over (lookback × rebalance period) with walk-forward
validation.

The goal here is *robustness*, not optimization. A grid that shows a
flat Sharpe plateau across reasonable parameter choices is reassuring;
a sharp peak at one combo is a red flag for overfitting.

Walk-forward design
-------------------
For a chosen ``train_end`` date, every combo is evaluated twice:
  * in-sample (IS): rebalance returns whose entry date is < train_end
  * out-of-sample (OOS): the remaining tail
The combo that maxes IS Sharpe is reported alongside its OOS Sharpe so
you can see how badly the "winner" degrades on data it didn't pick on.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .backtest import (
    _build_membership,
    calculate_portfolio_return,
)
from .config import BacktestConfig
from .download_data import download_price_data
from .membership import get_eligible_universe
from .signals import (
    calculate_momentum_scores,
    calculate_monthly_returns,
    get_first_trading_days,
    select_top_n,
)
from .utils import get_logger, to_business_date

LOGGER = get_logger("grid_search")


def _filter_rebalance_days(
    first_days: List[pd.Timestamp], period_months: int
) -> List[pd.Timestamp]:
    """Take every ``period_months``-th first trading day."""
    if period_months <= 1:
        return list(first_days)
    return [d for i, d in enumerate(first_days) if i % period_months == 0]


def _strategy_returns(
    prices: pd.DataFrame,
    monthly_returns: pd.DataFrame,
    membership_df: pd.DataFrame,
    rebalance_days: List[pd.Timestamp],
    lookback_months: int,
    top_n: int,
    score_method: str,
    excluded_tickers: set,
) -> pd.Series:
    """Return the per-rebalance gross strategy returns as a Series
    indexed by entry date.
    """
    available = [t for t in prices.columns if t not in excluded_tickers]
    pairs = []
    for i in range(len(rebalance_days) - 1):
        entry = rebalance_days[i]
        exit_ = rebalance_days[i + 1]
        eligible = get_eligible_universe(
            membership_df, entry, available_tickers=available
        )
        scores = calculate_momentum_scores(
            monthly_returns[eligible] if eligible else monthly_returns.iloc[:, :0],
            entry,
            lookback_months=lookback_months,
            score_method=score_method,
        )
        selected = select_top_n(scores, n=top_n)
        if not selected:
            ret = 0.0
        else:
            ret, _, _, _ = calculate_portfolio_return(
                selected, prices, entry, exit_
            )
        pairs.append((entry, ret))
    return pd.Series(dict(pairs), dtype=float)


def _metrics(returns: pd.Series, periods_per_year: float) -> Dict[str, float]:
    """Compute CAGR / Sharpe / vol / drawdown for a return series.

    Annualization uses ``periods_per_year`` (12/period_months) so combos
    with different rebalance frequencies are comparable.
    """
    n = len(returns)
    if n == 0:
        return {
            "cagr": float("nan"),
            "sharpe": float("nan"),
            "vol": float("nan"),
            "total_return": float("nan"),
            "max_drawdown": float("nan"),
        }
    years = n / periods_per_year
    total_return = float((1.0 + returns).prod() - 1.0)
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else float("nan")
    if n > 1:
        std = float(returns.std(ddof=1))
        sharpe = (
            float(returns.mean()) / std * np.sqrt(periods_per_year)
            if std > 0
            else float("nan")
        )
        vol = std * np.sqrt(periods_per_year)
    else:
        sharpe, vol = float("nan"), float("nan")
    eq = (1.0 + returns).cumprod()
    drawdown = float((eq / eq.cummax() - 1.0).min())
    return {
        "cagr": cagr,
        "sharpe": sharpe,
        "vol": vol,
        "total_return": total_return,
        "max_drawdown": drawdown,
    }


def run_grid(
    config: BacktestConfig,
    lookbacks: List[int],
    periods: List[int],
    train_end: Optional[str] = None,
) -> pd.DataFrame:
    """Sweep the (lookback × rebalance-period) grid.

    Parameters
    ----------
    config : BacktestConfig
        Source of universe / date window / score method / top_n.
    lookbacks : list[int]
        Lookback windows in months, e.g. ``[3, 6, 9, 12]``.
    periods : list[int]
        Rebalance periods in months, e.g. ``[1, 2, 3]``.
    train_end : Optional[str]
        ISO date splitting in-sample (entry < train_end) from
        out-of-sample (entry >= train_end). If None, only full-period
        metrics are reported.
    """
    universe = sorted(set(t.upper() for t in config.tickers))
    excluded = {config.benchmark.upper()}
    if config.secondary_benchmark:
        excluded.add(config.secondary_benchmark.upper())
    all_tickers = sorted(set(universe) | excluded)

    LOGGER.info(
        "Downloading prices for grid: %d tickers, %s → %s",
        len(all_tickers), config.start_date, config.end_date,
    )
    prices = download_price_data(
        all_tickers, config.start_date, config.end_date,
        force_refresh=config.force_refresh,
    )
    monthly_returns = calculate_monthly_returns(prices)
    first_days = get_first_trading_days(prices)
    membership_df = _build_membership(config)

    train_end_ts = pd.Timestamp(train_end) if train_end else None
    rows: List[Dict] = []

    for lb in lookbacks:
        # We need ``lb`` completed monthly returns before the first
        # rebalance — that determines the warm-up boundary.
        warmup = to_business_date(config.start_date) + pd.DateOffset(months=lb + 1)
        usable_first = [d for d in first_days if d >= warmup]

        for period in periods:
            rebalance_days = _filter_rebalance_days(usable_first, period)
            if len(rebalance_days) < 4:
                LOGGER.warning(
                    "Skipping lookback=%d period=%d (only %d rebalances)",
                    lb, period, len(rebalance_days),
                )
                continue

            rets = _strategy_returns(
                prices, monthly_returns, membership_df, rebalance_days,
                lookback_months=lb,
                top_n=config.top_n,
                score_method=config.score_method,
                excluded_tickers=excluded,
            )
            ppy = 12.0 / period
            row = {
                "lookback": lb,
                "period": period,
                "n_rebalances": int(len(rets)),
            }
            row.update({f"full_{k}": v for k, v in _metrics(rets, ppy).items()})

            if train_end_ts is not None:
                is_rets = rets[rets.index < train_end_ts]
                oos_rets = rets[rets.index >= train_end_ts]
                row["is_n"] = int(len(is_rets))
                row["oos_n"] = int(len(oos_rets))
                row.update({f"is_{k}": v for k, v in _metrics(is_rets, ppy).items()})
                row.update({f"oos_{k}": v for k, v in _metrics(oos_rets, ppy).items()})

            rows.append(row)
            LOGGER.info(
                "  lookback=%2d period=%d  full_sharpe=%.2f  cagr=%.2f%%",
                lb, period,
                row.get("full_sharpe", float("nan")),
                100 * row.get("full_cagr", float("nan")),
            )

    return pd.DataFrame(rows).sort_values(["lookback", "period"]).reset_index(drop=True)


def summarize_walkforward(grid: pd.DataFrame) -> Dict:
    """Pick the IS-best combo and report its OOS performance."""
    if "is_sharpe" not in grid.columns:
        return {}
    valid = grid.dropna(subset=["is_sharpe", "oos_sharpe"])
    if valid.empty:
        return {}
    is_winner = valid.loc[valid["is_sharpe"].idxmax()]
    oos_winner = valid.loc[valid["oos_sharpe"].idxmax()]
    return {
        "is_winner": {
            "lookback": int(is_winner["lookback"]),
            "period": int(is_winner["period"]),
            "is_sharpe": float(is_winner["is_sharpe"]),
            "oos_sharpe": float(is_winner["oos_sharpe"]),
            "is_cagr": float(is_winner["is_cagr"]),
            "oos_cagr": float(is_winner["oos_cagr"]),
        },
        "oos_winner": {
            "lookback": int(oos_winner["lookback"]),
            "period": int(oos_winner["period"]),
            "is_sharpe": float(oos_winner["is_sharpe"]),
            "oos_sharpe": float(oos_winner["oos_sharpe"]),
        },
        # Honest measure of overfitting bias: how much does the IS-best
        # combo's Sharpe drop in OOS compared to the OOS-best combo?
        "is_to_oos_sharpe_degradation": float(is_winner["is_sharpe"]) - float(is_winner["oos_sharpe"]),
        "mean_is_sharpe": float(valid["is_sharpe"].mean()),
        "mean_oos_sharpe": float(valid["oos_sharpe"].mean()),
    }
