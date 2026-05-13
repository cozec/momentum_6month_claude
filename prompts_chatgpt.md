Build a Python backtesting tool for a Nasdaq-100 monthly momentum rotation strategy.

Strategy Goal:
Download historical price data for Nasdaq-100 stocks and backtest a monthly momentum strategy.

Momentum Rule:
On the first trading day of each month:
1. For every eligible Nasdaq-100 stock, calculate each of the past 6 monthly returns.
2. Compute the average of those 6 monthly returns.
3. Rank all eligible Nasdaq-100 stocks by this 6-month average monthly return.
4. Select the top 3 stocks.
5. Allocate equally: 1/3 portfolio weight to each selected stock.
6. Hold for one month.
7. Rebalance again on the first trading day of the next month.

Benchmark:
Compare performance against QQQ.

Important:
Avoid lookahead bias. At each rebalance date, use only price data that would have been available before or on that date. Do not use future Nasdaq-100 constituents unless historical membership data is available.

Core Requirements:

1. Data Download for past 10 years
- Use yfinance or another free API.
- Download daily adjusted close prices for:
  - Nasdaq-100 stocks
  - QQQ benchmark
- Store raw prices locally as Parquet or CSV.
- Add caching so repeated runs do not redownload unchanged data.
- Include start_date and end_date in config.py.
- Handle missing data, delisted tickers, renamed tickers, and failed downloads.

2. Nasdaq-100 Constituents
Mode: current_constituents
- Use the current Nasdaq-100 stock list.
- Clearly mark this as survivorship-biased.

3. Monthly Return Calculation
For each stock and each rebalance date:
- Resample daily adjusted close prices to month-end prices.
- Calculate monthly returns.
- For each rebalance date, use the previous 6 completed monthly returns.
- Do NOT include the current partial month.
- If fewer than 6 valid monthly returns exist, exclude the stock for that rebalance.

Momentum Score:
momentum_score = average(previous_6_monthly_returns)

Alternative optional score:
compound_6m_return = product(1 + monthly_returns) - 1

Allow user to choose:
score_method = "average_monthly_return" or "compound_6m_return"

4. Rebalance Logic
On the first trading day of every month:
- Determine eligible Nasdaq-100 stocks.
- Calculate their momentum scores.
- Rank descending.
- Pick top 3.
- Invest equal weight in the top 3.
- Hold until the first trading day of next month.
- Apply transaction costs if configured.

5. Portfolio Accounting
Track:
- selected tickers each month
- entry prices
- exit prices
- monthly stock returns
- portfolio monthly return
- turnover
- transaction costs
- portfolio equity curve

Default assumptions:
- initial capital = $100,000
- equal weight among top 3
- no leverage
- long-only
- transaction cost = 0.05% per trade
- slippage = 0.05% per trade
- dividends included through adjusted close

6. Benchmark
Download QQQ adjusted close.
Calculate:
- QQQ monthly return over same rebalance periods
- strategy excess return vs QQQ
- cumulative strategy return
- cumulative QQQ return

7. Output Files
Save results to outputs/:

outputs/monthly_selections.csv
Columns:
- rebalance_date
- ticker
- rank
- momentum_score
- weight
- entry_price
- exit_date
- exit_price
- stock_return

outputs/portfolio_returns.csv
Columns:
- rebalance_date
- next_rebalance_date
- portfolio_return_gross
- transaction_cost
- slippage_cost
- portfolio_return_net
- qqq_return
- excess_return
- portfolio_value
- qqq_value
- turnover

outputs/summary_stats.csv
Include:
- CAGR
- annualized volatility
- Sharpe ratio
- max drawdown
- win rate vs QQQ
- average monthly return
- median monthly return
- best month
- worst month
- total return
- number of rebalances
- average turnover

8. Charts
Generate charts:
- strategy equity curve vs QQQ
- drawdown curve
- monthly return distribution
- rolling 6-month return
- rolling 12-month return
- top selected stocks frequency
- monthly excess return vs QQQ

Save charts to:
outputs/charts/

9. Project Structure
Create:

nasdaq100_momentum_backtest/
  data/
    raw_prices/
    processed/
    nasdaq100_membership.csv
  outputs/
    charts/
    monthly_selections.csv
    portfolio_returns.csv
    summary_stats.csv
  src/
    config.py
    download_data.py
    membership.py
    signals.py
    backtest.py
    metrics.py
    plots.py
    utils.py
  notebooks/
    exploration.ipynb
  main.py
  requirements.txt
  README.md

10. Functions to Implement

download_price_data(tickers, start_date, end_date)
load_nasdaq100_membership(filepath)
get_eligible_universe(membership_df, date)
get_first_trading_days(price_df)
calculate_monthly_returns(price_df)
calculate_momentum_scores(monthly_returns, rebalance_date, lookback_months=6)
select_top_n(momentum_scores, n=3)
calculate_portfolio_return(selected_tickers, prices, entry_date, exit_date)
run_backtest(config)
calculate_summary_stats(portfolio_returns)
plot_equity_curve(strategy_returns, benchmark_returns)
plot_drawdowns(portfolio_values)

11. Important Bias Controls
Add explicit checks for:
- lookahead bias
- survivorship bias
- missing price data
- insufficient history
- corporate action issues
- delisted stocks
- ticker changes

In README, clearly explain:
- using only current Nasdaq-100 tickers creates survivorship bias
- historical membership data is required for a clean backtest
- signals use only previous completed monthly returns
- adjusted close includes dividends and splits
- first trading day execution is assumed at adjusted close

12. Optional Enhancements
Add config options:
- top_n = 3
- lookback_months = 6
- rebalance_frequency = monthly
- benchmark = QQQ
- transaction_cost_bps
- slippage_bps
- min_price_history_months
- score_method
- start_date
- end_date
- use_historical_membership = True/False

13. CLI
Add command-line usage:

python main.py --start-date 2010-01-01 --end-date 2026-12-31 --top-n 3 --lookback-months 6 --benchmark QQQ

14. Testing
Add simple unit tests for:
- monthly return calculation
- momentum score calculation
- top 3 selection
- rebalance date generation
- portfolio return calculation
- no-lookahead behavior

Deliverables:
- complete runnable Python project
- clean modular code
- README
- requirements.txt
- sample Nasdaq-100 membership CSV template
- output CSV files
- charts