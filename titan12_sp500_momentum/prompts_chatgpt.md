Build a Python backtesting research system for an S&P 500 monthly rotation
strategy called "Titan-12 Momentum Rotation".

You are a Senior Quantitative Developer and Python Expert. Implement the
project end to end with clean, modular, reproducible Python code.

## Core Strategy

Strategy name: Titan-12 Momentum Rotation

Universe:
- S&P 500 stocks.
- Prefer point-in-time historical S&P 500 membership.
- If only current S&P 500 constituents are used, clearly label every result as
  survivorship-biased.

Rebalance frequency:
- Monthly.
- Rebalance on the first trading day of each month.

Signal:
- 12-step weighted momentum using the past 12 completed monthly returns.
- Do not use the current partial month.
- For a rebalance on the first trading day of a month, calculate scores using
  monthly returns through the previous completed month only.

Momentum formula:

```text
r_1  = oldest completed monthly return
r_12 = most recent completed monthly return

score = 1*r_1 + 2*r_2 + 3*r_3 + ... + 12*r_12
```

The most recent completed month gets weight 12. The oldest completed month gets
weight 1.

Portfolio construction:
- Rank all eligible S&P 500 stocks by weighted momentum score.
- Select the top 3 stocks.
- Equal-weight selected stocks at 33.33% each.
- Optional cross-project Nasdaq exclusion overlay:
  - Read the sister Nasdaq strategy selections from
    `/Users/adam/project/momentum_6m/nasdaq100_momentum_backtest/outputs/monthly_selections.csv`.
  - For each S&P 500 rebalance date, if a ticker appears in the Nasdaq top-3
    selections for the same rebalance date, skip it in the S&P 500 ranking.
  - Backfill from the next-highest S&P 500 Titan-12 ranked stocks until 3 names
    are selected.
  - Clearly label any output that uses this overlay as
    "Nasdaq-overlap-excluded".
- Hold for one month.
- At the next rebalance, sell stocks that fall out of the top 3 and buy new
  top-ranked stocks automatically.
- Long-only.
- No leverage.
- Initial capital: $100,000.
- Default transaction cost: 0.05% per trade.
- Default slippage: 0.05% per trade.
- Use adjusted close prices so dividends and splits are included.

Benchmark:
- Compare against SPY.
- Optionally also compare against ^GSPC.
- Keep benchmark calculations simple and auditable.

## Critical Bias Controls

Avoid lookahead bias:
- At each rebalance, use only information available before that rebalance.
- Use only the previous 12 completed monthly returns.
- Do not use current-month data in signal calculation.

Handle survivorship bias:
- Support historical membership mode.
- Support current-constituents mode.
- If current-constituents mode is used, label output, charts, README, and
  summary as survivorship-biased.

Handle data quality:
- Do not silently drop missing stocks.
- Log failed downloads, missing prices, insufficient history, ticker changes,
  delisted symbols, and excluded symbols.
- Produce a data quality report.

## Required Project Structure

Create this structure:

```text
sp500_titan12_momentum/
  .venv/
  data/
    raw_prices/
    processed/
    sp500_membership.csv
  logs/
    data_quality_report.csv
    backtest.log
  outputs/
    charts/
    monthly_selections.csv
    portfolio_returns.csv
    summary_stats.csv
  plots/
  results/
  src/
    __init__.py
    config.py
    download_data.py
    membership.py
    signals.py
    backtest.py
    metrics.py
    plots.py
    utils.py
  tests/
    test_backtest.py
    test_membership.py
    test_metrics.py
    test_signals.py
  main.py
  requirements.txt
  README.md
  summary.md
```

Use `.venv` as the default Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Always run Python commands through the virtual environment.

Check-in expectations:
- Check in `README.md`, `summary.md`, `src/`, `tests/`, `main.py`, and
  `requirements.txt`.
- Never check in `data/`, `outputs/`, `results/`, `plots/`, `logs/`, or
  `.venv/`.

## Data Requirements

Use `yfinance` for market data.

Download and cache:
- Daily adjusted close prices for all S&P 500 stocks.
- Daily adjusted close prices for SPY.
- Optionally daily adjusted close prices for ^GSPC.

Raw downloaded data:
- Save locally as CSV or Parquet.
- Avoid repeated downloads when cached files exist.
- Each CSV should include: Date, Open, High, Low, Close, Adj Close, Volume.
- Use Date as the index when loading into pandas.

Membership file:

Create `data/sp500_membership.csv` with columns:

```text
ticker
company_name
start_date
end_date
sector
source
notes
```

Support two membership modes:

1. `current_constituents`
   - Use current S&P 500 members.
   - Clearly label results as survivorship-biased.

2. `historical_constituents`
   - At each rebalance date, include only stocks that were actual S&P 500
     members on that date.
   - This is preferred for serious research.

The backtest engine must not hard-code the universe. It should only ask the
membership module which symbols are eligible on each rebalance date.

## Signal Calculation

Implement signal logic separately from portfolio construction.

Required behavior:
- Convert daily adjusted close prices into month-end prices.
- Calculate monthly returns from month-end prices.
- For each rebalance date, find the last completed month before that date.
- Use the previous 12 completed monthly returns only.
- Exclude stocks with fewer than 12 valid monthly returns.
- Log every exclusion and reason.
- Compute the weighted score with weights 1 through 12 from oldest to newest.
- Rank descending.

The signal module should return a ranked table containing at least:
- rebalance_date
- ticker
- company_name
- sector
- weighted_momentum_score
- rank
- enough diagnostics to verify the 12 returns used

## Backtest Execution

Execution assumptions:
- Entry price: adjusted close on rebalance date.
- Exit price: adjusted close on the next month's first trading day.
- Selected stocks are equal-weighted.
- Transaction costs and slippage are deducted from returns.
- Turnover is calculated from previous holdings to current holdings.

Required outputs:

`outputs/monthly_selections.csv`

```text
rebalance_date
ticker
company_name
sector
rank
weighted_momentum_score
weight
entry_price
exit_date
exit_price
stock_return
```

`outputs/portfolio_returns.csv`

```text
rebalance_date
next_rebalance_date
selected_tickers
portfolio_return_gross
transaction_cost
slippage_cost
portfolio_return_net
spy_return
excess_return_vs_spy
portfolio_value
spy_value
turnover
```

`outputs/summary_stats.csv`

Include:
- total return
- CAGR
- annualized volatility
- Sharpe ratio
- Sortino ratio
- max drawdown
- Calmar ratio
- monthly win rate
- win rate vs SPY
- average monthly return
- median monthly return
- best month
- worst month
- number of rebalances
- average turnover
- average holding period

If a strategy run has fewer than 30 completed trades, log the trade details in
`summary.md`.

## Charts

Save charts to `outputs/charts/`:
- equity curve vs SPY
- drawdown curve
- monthly return distribution
- rolling 6-month return
- rolling 12-month return
- rolling Sharpe ratio
- annual return bar chart
- top selected stocks frequency
- sector exposure over time
- excess return vs SPY over time

Also create human-readable tables in `summary.md` for:
- latest completed rebalance
- current open basket, if available
- recent selection history
- data freshness timestamp
- active configuration
- data quality warnings

## Required Functions

Implement these functions with comprehensive docstrings:

```python
download_price_data(tickers, start_date, end_date)
load_sp500_membership(filepath)
get_eligible_universe(membership_df, date)
get_first_trading_days(price_df)
calculate_month_end_prices(price_df)
calculate_monthly_returns(month_end_prices)
calculate_titan12_score(monthly_returns, rebalance_date)
rank_stocks_by_score(scores)
select_top_n(scores, n=3)
calculate_portfolio_return(selected_tickers, prices, entry_date, exit_date)
calculate_turnover(previous_holdings, current_holdings)
run_backtest(config)
calculate_summary_stats(portfolio_returns)
plot_equity_curve(strategy_returns, benchmark_returns)
plot_drawdowns(portfolio_values)
plot_sector_exposure(monthly_selections)
```

## Configuration

Create `src/config.py` with configurable defaults:

```python
start_date = "2016-01-01"
end_date = "2026-05-12"
universe = "sp500"
benchmark = "SPY"
top_n = 3
lookback_months = 12
weights = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
rebalance_frequency = "monthly"
initial_capital = 100000
transaction_cost_bps = 5
slippage_bps = 5
use_historical_membership = True
min_price_history_months = 12
```

Treat configuration as the contract between code, outputs, README, summary,
charts, and tests.

## CLI

Add command-line support:

```bash
python main.py --start-date 2010-01-01 --end-date 2026-12-31 --top-n 3 --benchmark SPY
```

The CLI should support:
- start date
- end date
- top N
- benchmark
- transaction cost bps
- slippage bps
- membership mode
- refresh data flag

## Validation and Research Extensions

Keep the core implementation focused on Titan-12, but design modules so future
research can test:
- different lookback windows
- different top-N values
- different rebalance intervals
- equal-weight versus volatility-scaled portfolios
- transaction cost sensitivity
- slippage sensitivity
- delayed execution by one day
- regime robustness
- walk-forward validation

Do not overfit to the best CAGR. When adding parameter searches, rank candidates
by multiple views:
- CAGR
- Sharpe ratio
- max drawdown
- return stability across regimes
- turnover
- transaction cost sensitivity
- number of independent rebalances
- out-of-sample performance

## Tests

Add unit tests for:
- monthly return calculation
- 12-month weighted momentum score
- no-lookahead signal calculation
- top 3 stock selection
- first trading day rebalance generation
- portfolio return calculation
- turnover calculation
- historical membership filtering
- missing data handling
- benchmark return calculation

Tests should protect the research assumptions, not just code mechanics.

## README

Create a clear `README.md` explaining:
- what Titan-12 Momentum Rotation does
- how to create and activate `.venv`
- how to install dependencies
- how to run the backtest
- how to refresh price data
- how to update S&P 500 membership data
- how to interpret results
- why historical membership matters
- how survivorship bias affects current-constituents mode
- limitations such as delisted stocks, ticker changes, taxes, liquidity,
  execution assumptions, transaction costs, and slippage

## summary.md

Create and update `summary.md` after each run.

Include:
- active configuration
- run timestamp
- data freshness timestamp
- membership mode
- bias warnings
- summary stats
- chart list
- data quality notes
- latest completed rebalance
- current open basket, if available
- trade details if fewer than 30 trades
- test results

## Code Style

Follow PEP 8.

All functions must have comprehensive docstrings.

Prefer clear, auditable code over clever shortcuts. Use pandas/numpy idioms
where appropriate, but keep the research logic easy to inspect.

## Final Requirement

Build a research system that answers:
- What exactly was tradable at the time?
- What information was available at the time?
- Why were these stocks selected?
- How sensitive are results to transaction costs and slippage?
- How does the strategy compare with SPY?
- Are the results point-in-time or survivorship-biased?
- Can the same code produce both historical results and current live picks?
