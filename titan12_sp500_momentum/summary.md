# Titan-12 Momentum Rotation Summary (S&P 500)

Run timestamp: 2026-11-01T22:25:00.728586+00:00

Data freshness timestamp: 2026-10-01


## Active Configuration

| setting              | value                   |
|:---------------------|:------------------------|
| start_date           | 2016-01-01              |
| end_date             | 2026-11-01              |
| top_n                | 3                       |
| benchmark            | SPY                     |
| transaction_cost_bps | 5.0                     |
| slippage_bps         | 5.0                     |
| membership_mode      | historical_constituents |

## Strategy Comparison

Start capital $10,000. Buy & hold uses $10,000 x (last_close / first_close) on adjusted closes over the same window. Alpha (annualized) and Beta are versus the benchmark's monthly returns; Sharpe and Alpha assume a 0% risk-free rate.

| Strategy          |   Final Equity |   Return |   CAGR |   Max DD |   Sharpe |   Alpha |   Beta |
|:------------------|---------------:|---------:|-------:|---------:|---------:|--------:|-------:|
| Titan-12 Momentum |     116,951.58 | 1069.52% | 28.97% |  -39.33% |     0.83 |  13.62% |   1.30 |
| SPY Buy & Hold    |      39,072.34 |  290.72% | 15.14% |  -23.79% |     0.95 |   0.00% |   1.00 |

## Summary Stats

|   total_return |     CAGR |   annualized_volatility |   Sharpe_ratio |   Sortino_ratio |   max_drawdown |   Calmar_ratio |   monthly_win_rate |   win_rate_vs_SPY |   average_monthly_return |   median_monthly_return |   best_month |   worst_month |   number_of_rebalances |   average_turnover | average_holding_period   |
|---------------:|---------:|------------------------:|---------------:|----------------:|---------------:|---------------:|-------------------:|------------------:|-------------------------:|------------------------:|-------------:|--------------:|-----------------------:|-------------------:|:-------------------------|
|        10.6952 | 0.289684 |                0.409754 |       0.825915 |         1.45967 |      -0.393272 |       0.736599 |           0.568966 |          0.474138 |                0.0282018 |               0.0246526 |     0.414487 |     -0.304786 |                    116 |           0.428161 | 1 month                  |

## Latest Completed Rebalance

2026-09-01: MRNA, SNDK, MU


## Next Rebalance 2026-11-02 (signal locked 2026-10-30)

Final: MRNA, SNDK, DELL

Baseline (pre-exclusion): MRNA, SNDK, DELL

Excluded sister Nasdaq next picks: CRWD, MU, PANW

Signal uses monthly returns through the last close; the fill is the next open.

## Final Top 3 (Nasdaq-Overlap Excluded)

2026-10-01: MRNA, DELL, MRVL

Excluded sister Nasdaq top picks: MU, INTC, SNDK

## Baseline Open Basket (pre-exclusion)

2026-10-01: MRNA, SNDK, DELL

## Charts

- outputs/charts/equity_curve_vs_spy.png
- outputs/charts/drawdown_curve.png
- outputs/charts/monthly_return_distribution.png
- outputs/charts/rolling_6_month_return.png
- outputs/charts/rolling_12_month_return.png
- outputs/charts/rolling_sharpe_ratio.png
- outputs/charts/annual_return_bar_chart.png
- outputs/charts/top_selected_stocks_frequency.png
- outputs/charts/sector_exposure_over_time.png
- outputs/charts/excess_return_vs_spy_over_time.png

## Data Quality Notes

| issue_type                   |   count |
|:-----------------------------|--------:|
| insufficient_history         |    6243 |
| missing_price_history        |    4290 |
| download_failed              |     176 |
| insufficient_selection_count |      13 |

Showing the first 50 of 10,722 issues. Full list: logs/data_quality_report.csv

| date   | ticker   | issue_type      | message                       |
|:-------|:---------|:----------------|:------------------------------|
|        | ABK      | download_failed | No rows returned by yfinance. |
|        | ABMD     | download_failed | No rows returned by yfinance. |
|        | ACAS     | download_failed | No rows returned by yfinance. |
|        | ACE      | download_failed | No rows returned by yfinance. |
|        | ADS      | download_failed | No rows returned by yfinance. |
|        | AGN      | download_failed | No rows returned by yfinance. |
|        | AKS      | download_failed | No rows returned by yfinance. |
|        | ALTR     | download_failed | No rows returned by yfinance. |
|        | ALXN     | download_failed | No rows returned by yfinance. |
|        | ANR      | download_failed | No rows returned by yfinance. |
|        | ANSS     | download_failed | No rows returned by yfinance. |
|        | APOL     | download_failed | No rows returned by yfinance. |
|        | ARG      | download_failed | No rows returned by yfinance. |
|        | ARNC     | download_failed | No rows returned by yfinance. |
|        | ATVI     | download_failed | No rows returned by yfinance. |
|        | AVP      | download_failed | No rows returned by yfinance. |
|        | AYE      | download_failed | No rows returned by yfinance. |
|        | BCR      | download_failed | No rows returned by yfinance. |
|        | BHI      | download_failed | No rows returned by yfinance. |
|        | BIG      | download_failed | No rows returned by yfinance. |
|        | BJS      | download_failed | No rows returned by yfinance. |
|        | BRCM     | download_failed | No rows returned by yfinance. |
|        | BS       | download_failed | No rows returned by yfinance. |
|        | BXLT     | download_failed | No rows returned by yfinance. |
|        | CDAY     | download_failed | No rows returned by yfinance. |
|        | CELG     | download_failed | No rows returned by yfinance. |
|        | CEPH     | download_failed | No rows returned by yfinance. |
|        | CERN     | download_failed | No rows returned by yfinance. |
|        | CFN      | download_failed | No rows returned by yfinance. |
|        | CHK      | download_failed | No rows returned by yfinance. |
|        | CMA      | download_failed | No rows returned by yfinance. |
|        | CMCSK    | download_failed | No rows returned by yfinance. |
|        | COV      | download_failed | No rows returned by yfinance. |
|        | CPGX     | download_failed | No rows returned by yfinance. |
|        | CSC      | download_failed | No rows returned by yfinance. |
|        | CTLT     | download_failed | No rows returned by yfinance. |
|        | CTX      | download_failed | No rows returned by yfinance. |
|        | CTXS     | download_failed | No rows returned by yfinance. |
|        | CVC      | download_failed | No rows returned by yfinance. |
|        | CVH      | download_failed | No rows returned by yfinance. |
|        | CXO      | download_failed | No rows returned by yfinance. |
|        | DAY      | download_failed | No rows returned by yfinance. |
|        | DF       | download_failed | No rows returned by yfinance. |
|        | DFS      | download_failed | No rows returned by yfinance. |
|        | DISCA    | download_failed | No rows returned by yfinance. |
|        | DISCK    | download_failed | No rows returned by yfinance. |
|        | DISH     | download_failed | No rows returned by yfinance. |
|        | DJ       | download_failed | No rows returned by yfinance. |
|        | DNB      | download_failed | No rows returned by yfinance. |
|        | DNR      | download_failed | No rows returned by yfinance. |

## Test Results

`pytest -q`: 33 passed in 0.62s

