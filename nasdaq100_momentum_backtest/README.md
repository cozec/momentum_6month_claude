# Nasdaq-100 Monthly Momentum Rotation Backtest

A Python backtesting tool that runs a monthly 6-month momentum rotation strategy on the Nasdaq-100 universe, benchmarked against QQQ.

## Strategy

On the first trading day of each month:

1. For every eligible Nasdaq-100 stock, compute the previous **six completed monthly returns** (the current partial month is excluded).
2. Score each stock with either:
   - `average_monthly_return` — mean of those six returns (default), or
   - `compound_6m_return` — `prod(1 + r) - 1` of those six returns.
3. Rank descending and select the top 3.
4. Buy equal-weight (1/3 each) and hold until the first trading day of the next month.
5. Apply transaction cost + slippage on each trade based on portfolio turnover.

## Project layout

```
nasdaq100_momentum_backtest/
  data/
    raw_prices/                 # per-ticker daily-OHLCV CSV cache
    processed/
    nasdaq100_membership.csv    # current-snapshot membership (template)
  outputs/
    charts/                     # generated PNGs
    monthly_selections.csv
    portfolio_returns.csv
    summary_stats.csv
  src/
    config.py        # BacktestConfig + Nasdaq-100 ticker list
    download_data.py # yfinance downloader with on-disk caching
    membership.py    # constituent loader / template writer
    signals.py       # monthly returns, momentum scores, top-N select
    backtest.py      # core monthly rebalance loop
    metrics.py       # CAGR, vol, Sharpe, drawdown, win-rate, turnover
    plots.py         # equity curve, drawdown, distribution, rolling, etc.
    utils.py         # logging + filesystem helpers
  tests/
    test_strategy.py # unit tests for signals + portfolio math
  notebooks/
    exploration.ipynb
  main.py            # CLI entry point
  requirements.txt
  README.md
  summary.md
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r nasdaq100_momentum_backtest/requirements.txt
```

## Running the backtest

```bash
cd nasdaq100_momentum_backtest
python main.py \
    --start-date 2015-05-01 \
    --end-date 2025-05-01 \
    --top-n 3 \
    --lookback-months 6 \
    --benchmark QQQ
```

CLI flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--start-date`             | `2015-05-01` | Inclusive start of the data window. |
| `--end-date`               | `2025-05-01` | Inclusive end of the data window. |
| `--top-n`                  | `3` | Number of stocks held each month. |
| `--lookback-months`        | `6` | Completed months of returns to score. |
| `--benchmark`              | `QQQ` | Primary benchmark ticker. |
| `--secondary-benchmark`    | `TQQQ` | Extra buy-and-hold benchmark (set to empty string to disable). |
| `--score-method`           | `average_monthly_return` | `average_monthly_return` or `compound_6m_return`. |
| `--transaction-cost-bps`   | `0.0` | Per-trade transaction cost. Default disables it; pass `5.0` for 0.05%. |
| `--slippage-bps`           | `0.0` | Per-trade slippage. Default disables it; pass `5.0` for 0.05%. |
| `--initial-capital`        | `100000` | Starting portfolio value. |
| `--use-historical-membership` | off | Read `data/nasdaq100_membership.csv` instead of the current snapshot. |

## Outputs

After a run you will find:

- `outputs/monthly_selections.csv` — one row per (rebalance, ticker) with rank, score, weight, entry/exit prices, and per-stock holding return.
- `outputs/portfolio_returns.csv` — one row per rebalance period with gross / net / QQQ / TQQQ returns, transaction cost, slippage, turnover, and cumulative values for the strategy, QQQ buy-and-hold, and TQQQ buy-and-hold.
- `outputs/summary_stats.csv` — CAGR, vol, Sharpe, max drawdown, win-rate vs QQQ, best/worst month, total return, rebalances, average turnover.
- `outputs/charts/` — equity curve, drawdown, monthly distribution, rolling 6m/12m return, ticker-frequency, monthly excess return.

## Bias controls

The code addresses each potential source of bias explicitly:

- **Lookahead bias** — momentum scores use only monthly returns whose month-end strictly precedes the rebalance date. The current partial month is never used. A unit test (`test_momentum_score_no_lookahead`) pins this behavior.
- **Survivorship bias** — by default the universe is the *current* Nasdaq-100 list, which is biased toward present-day winners. The README, summary, and config flag (`use_historical_membership`) all surface this fact. To run a survivorship-free backtest, supply a historical `data/nasdaq100_membership.csv` and pass `--use-historical-membership`.
- **Missing price data / delisted / renamed tickers** — the downloader retries with backoff, logs failures, and skips tickers that come back empty. The eligible universe is intersected with the tickers we have prices for.
- **Insufficient history** — stocks with fewer than `lookback_months` valid completed returns are excluded from the rank.
- **Corporate actions** — adjusted close (`auto_adjust=True` in yfinance) is used throughout, which folds in dividends and splits.
- **Execution assumption** — the first trading day's adjusted close is used as both the exit price for the prior month and the entry price for the new month.

## Membership template

A current-snapshot membership CSV is written automatically the first time the backtest runs. To replace it with historical data, edit `data/nasdaq100_membership.csv` with rows of `ticker,start_date,end_date` (empty `end_date` = still a constituent) and run with `--use-historical-membership`.

## Tests

```bash
cd nasdaq100_momentum_backtest
python -m unittest discover tests
```

Covered: monthly return calculation, momentum score correctness with both methods, the no-lookahead invariant, insufficient-history rejection, first-trading-day extraction, top-N selection, and equal-weight portfolio return arithmetic.

## Caveats

- Default universe is the **current** Nasdaq-100. Results are survivorship-biased and overstate the strategy's historical edge — winners like NVDA, AVGO, PLTR, MSTR, APP that were added in the 2020s were already present in the universe back in 2015.
- One ticker (`ANSS`) may fail to download because Yahoo Finance dropped history after the 2025 acquisition; the run continues with the remaining 99 stocks.
- Execution assumes you trade at the first-day adjusted close with the configured cost/slippage. Real-world fills, capacity, and tax effects are not modelled.
