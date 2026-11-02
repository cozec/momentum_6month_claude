# Titan-12 Momentum Rotation Summary (Nasdaq-100)

Run timestamp: 2026-10-12T03:04:18.609551+00:00

Data freshness timestamp: 2026-10-01


## Active Configuration

| setting              | value                   |
|:---------------------|:------------------------|
| start_date           | 2016-01-01              |
| end_date             | 2026-10-11              |
| top_n                | 3                       |
| benchmark            | QQQ                     |
| transaction_cost_bps | 5.0                     |
| slippage_bps         | 5.0                     |
| membership_mode      | historical_constituents |

## Strategy Comparison

Start capital $10,000. Buy & hold uses $10,000 x (last_close / first_close) on adjusted closes over the same window. Alpha (annualized) and Beta are versus the benchmark's monthly returns; Sharpe and Alpha assume a 0% risk-free rate.

| Strategy          |   Final Equity |   Return |   CAGR |   Max DD |   Sharpe |   Alpha |   Beta |
|:------------------|---------------:|---------:|-------:|---------:|---------:|--------:|-------:|
| Titan-12 Momentum |     326,830.59 | 3168.31% | 43.43% |  -54.30% |     1.03 |  12.92% |   1.55 |
| QQQ Buy & Hold    |      63,118.70 |  531.19% | 21.00% |  -33.67% |     1.04 |   0.00% |   1.00 |

## Summary Stats

|   total_return |     CAGR |   annualized_volatility |   Sharpe_ratio |   Sortino_ratio |   max_drawdown |   Calmar_ratio |   monthly_win_rate |   win_rate_vs_SPY |   average_monthly_return |   median_monthly_return |   best_month |   worst_month |   number_of_rebalances |   average_turnover | average_holding_period   |
|---------------:|---------:|------------------------:|---------------:|----------------:|---------------:|---------------:|-------------------:|------------------:|-------------------------:|------------------------:|-------------:|--------------:|-----------------------:|-------------------:|:-------------------------|
|        31.6831 | 0.434346 |                0.447686 |        1.02512 |         1.91658 |      -0.542969 |       0.799946 |           0.568966 |          0.551724 |                0.0382445 |               0.0122619 |     0.547129 |     -0.282029 |                    116 |           0.344828 | 1 month                  |

## Latest Completed Rebalance

2026-09-01: SNDK, MU, MRVL

## Final Top 3

2026-10-01: SNDK, MU, INTC

Sister Nasdaq overlap exclusion is not applied to this universe.

## Baseline Open Basket (pre-exclusion)

2026-10-01: SNDK, MU, INTC

## Charts

- outputs/nasdaq100/charts/equity_curve_vs_spy.png
- outputs/nasdaq100/charts/drawdown_curve.png
- outputs/nasdaq100/charts/monthly_return_distribution.png
- outputs/nasdaq100/charts/rolling_6_month_return.png
- outputs/nasdaq100/charts/rolling_12_month_return.png
- outputs/nasdaq100/charts/rolling_sharpe_ratio.png
- outputs/nasdaq100/charts/annual_return_bar_chart.png
- outputs/nasdaq100/charts/top_selected_stocks_frequency.png
- outputs/nasdaq100/charts/sector_exposure_over_time.png
- outputs/nasdaq100/charts/excess_return_vs_spy_over_time.png

## Data Quality Notes

| issue_type                   |   count |
|:-----------------------------|--------:|
| missing_price_history        |    1296 |
| insufficient_history         |    1168 |
| download_failed              |      69 |
| insufficient_selection_count |      13 |

Showing the first 50 of 2,546 issues. Full list: logs/data_quality_report_nasdaq100.csv

| date   | ticker   | issue_type      | message                       |
|:-------|:---------|:----------------|:------------------------------|
|        | AEOS     | download_failed | No rows returned by yfinance. |
|        | ALTR     | download_failed | No rows returned by yfinance. |
|        | ALXN     | download_failed | No rows returned by yfinance. |
|        | AMLN     | download_failed | No rows returned by yfinance. |
|        | ANSS     | download_failed | No rows returned by yfinance. |
|        | APCC     | download_failed | No rows returned by yfinance. |
|        | APOL     | download_failed | No rows returned by yfinance. |
|        | ATVI     | download_failed | No rows returned by yfinance. |
|        | BEAS     | download_failed | No rows returned by yfinance. |
|        | BMET     | download_failed | No rows returned by yfinance. |
|        | BRCM     | download_failed | No rows returned by yfinance. |
|        | CDWC     | download_failed | No rows returned by yfinance. |
|        | CELG     | download_failed | No rows returned by yfinance. |
|        | CEPH     | download_failed | No rows returned by yfinance. |
|        | CERN     | download_failed | No rows returned by yfinance. |
|        | CKFR     | download_failed | No rows returned by yfinance. |
|        | CMVT     | download_failed | No rows returned by yfinance. |
|        | CTRP     | download_failed | No rows returned by yfinance. |
|        | CTRX     | download_failed | No rows returned by yfinance. |
|        | CTXS     | download_failed | No rows returned by yfinance. |
|        | DISCA    | download_failed | No rows returned by yfinance. |
|        | DISH     | download_failed | No rows returned by yfinance. |
|        | DTV      | download_failed | No rows returned by yfinance. |
|        | FI       | download_failed | No rows returned by yfinance. |
|        | FLIR     | download_failed | No rows returned by yfinance. |
|        | FMCN     | download_failed | No rows returned by yfinance. |
|        | FWLT     | download_failed | No rows returned by yfinance. |
|        | GMCR     | download_failed | No rows returned by yfinance. |
|        | HANS     | download_failed | No rows returned by yfinance. |
|        | IACI     | download_failed | No rows returned by yfinance. |
|        | JNPR     | download_failed | No rows returned by yfinance. |
|        | JOYG     | download_failed | No rows returned by yfinance. |
|        | KRFT     | download_failed | No rows returned by yfinance. |
|        | LEAP     | download_failed | No rows returned by yfinance. |
|        | LLTC     | download_failed | No rows returned by yfinance. |
|        | LMCA     | download_failed | No rows returned by yfinance. |
|        | LVLT     | download_failed | No rows returned by yfinance. |
|        | MXIM     | download_failed | No rows returned by yfinance. |
|        | MYL      | download_failed | No rows returned by yfinance. |
|        | NDOI     | download_failed | No rows returned by yfinance. |
|        | NIHD     | download_failed | No rows returned by yfinance. |
|        | NLOK     | download_failed | No rows returned by yfinance. |
|        | NLTI     | download_failed | No rows returned by yfinance. |
|        | NUAN     | download_failed | No rows returned by yfinance. |
|        | PDCO     | download_failed | No rows returned by yfinance. |
|        | PETM     | download_failed | No rows returned by yfinance. |
|        | PPDI     | download_failed | No rows returned by yfinance. |
|        | QRTEA    | download_failed | No rows returned by yfinance. |
|        | RIMM     | download_failed | No rows returned by yfinance. |
|        | SEPR     | download_failed | No rows returned by yfinance. |

## Test Results

`pytest -q`: 17 passed in 0.43s

