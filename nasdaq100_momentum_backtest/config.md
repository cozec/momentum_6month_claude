# Backtest Window Configuration

## Data window (price history pulled from Yahoo Finance)

| Field | Value |
|-------|-------|
| `start_date` | **2016-01-01** |
| `end_date` | **2026-05-12** |

This is the *raw data* window: yfinance is asked for daily adjusted-close
prices over this range for every Nasdaq-100 ticker plus the QQQ and TQQQ
benchmarks. The first six months of this window (Jan–Jul 2016) are used
exclusively as the lookback for the momentum signal — no trades are
placed during the warm-up.

## Realized backtest window (actual invested period)

| Field | Value |
|-------|-------|
| First invested rebalance (entry) | **2016-08-01** |
| Last completed holding period ends (exit) | **2026-05-01** |

The strategy holds equal-weight top-3 positions for one month between
each adjacent pair of first-trading-days of the month. The first
invested entry date is the first month-start that has the full six
completed monthly returns available (= `start_date + lookback_months +
1 month` = 2016-01-01 + 7 months = 2016-08-01). The last completed
holding period ends on the last first-trading-day inside the data
window, which is 2026-05-01 (a Friday); the next month-start
(2026-06-01) falls outside `end_date`.

## Derivation

```
start_threshold = start_date + (lookback_months + 1) months
                = 2016-01-01 + 7 months
                = 2016-08-01      # first invested rebalance

last_entry      = penultimate first-trading-day inside data window
                = 2026-04-01

last_exit       = last first-trading-day inside data window
                = 2026-05-01      # last completed holding period ends here
```

The rebalance loop iterates over consecutive `(entry_date, exit_date)`
pairs of the monthly first-trading-day series. Both `2026-04-01` and
`2026-05-01` are real trading days; `2026-06-01` would be the next
month-start but lies outside `end_date = 2026-05-12`, so 2026-05-01 is
the final exit.

## Configured assumptions used for this run

| Parameter | Value |
|-----------|-------|
| `lookback_months` | 6 |
| `top_n` | 3 |
| `score_method` | `average_monthly_return` |
| `rebalance_frequency` | monthly (first trading day) |
| `transaction_cost_bps` | 0.0 (disabled) |
| `slippage_bps` | 0.0 (disabled) |
| `universe_size` | 101 tickers (Nasdaq-100; both GOOG and GOOGL listed) |
| `initial_capital` | $100,000 |
| `benchmark` | QQQ (buy & hold) |
| `secondary_benchmark` | TQQQ (buy & hold) |
| `use_historical_membership` | False (current Nasdaq-100 snapshot) |

## Reproduction

```bash
source .venv/bin/activate
cd nasdaq100_momentum_backtest
python main.py \
    --start-date 2016-01-01 \
    --end-date   2026-05-12 \
    --top-n 3 \
    --lookback-months 6 \
    --benchmark QQQ \
    --secondary-benchmark TQQQ
```
