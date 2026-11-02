# Lessons Learned

This project started as a Nasdaq-100 six-month momentum backtest, but the most useful outcome is a reusable pattern for testing any stock universe with any momentum definition. The main lesson is to keep the research pipeline modular: universe, data, signal, portfolio construction, execution, metrics, validation, and presentation should be separate parts.

## 1. Treat the Universe as a First-Class Input

The current project uses a Nasdaq-100 membership file. That made the system easy to run, but it also exposed an important research risk: using current constituents for a long historical backtest creates survivorship bias.

For future universes, the membership file should be explicit and versioned. A good universe file should answer:

- Which tickers were eligible on each rebalance date?
- When did each ticker enter or leave the universe?
- Are ticker changes, mergers, delistings, and dual share classes handled?
- Is the universe survivorship-biased or point-in-time?

The backtest engine should not know that the universe is Nasdaq-100. It should only ask, "Which symbols are tradable for this rebalance date?"

## 2. Separate Signal Calculation From Portfolio Rules

The first signal was six completed months of average monthly return. Later, the project tested three-month, six-month, nine-month, and twelve-month lookbacks, plus different rebalance intervals.

That showed why signal logic should be isolated from the rest of the system. Future momentum variants may include:

- average monthly return
- compound lookback return
- risk-adjusted momentum
- volatility-scaled momentum
- skip-month momentum
- trend filters such as price above moving average
- earnings or fundamental overlays
- sector-neutral ranking

The signal module should produce a ranked table with scores. The portfolio module should decide how many names to buy, how to weight them, and when to rebalance.

## 3. Use Completed Historical Data Only

A major rule is that momentum should be calculated using completed lookback periods only. For a rebalance on the first trading day of a month, the signal should use data through the previous completed month.

This avoids lookahead bias. It also makes live trading behavior match backtest behavior. If the strategy rebalances on 2026-05-01, the scores should be based on data available before that rebalance, not prices later in May.

For open/current holdings, label them separately from completed historical holds. The dashboard now distinguishes closed months from the current open basket, which is the right pattern.

## 4. Benchmark Calculation Should Be Simple and Auditable

The QQQ buy-and-hold benchmark was changed to use direct start and end adjusted prices. That was the right choice because it is easy to explain:

```text
QQQ return = ending adjusted price / starting adjusted price - 1
```

For benchmarks, prefer the simplest method that matches the research question. Portfolio returns can be monthly because the strategy rebalances monthly, but buy-and-hold comparisons should be directly auditable from price data.

## 5. Grid Search Is Useful, But It Can Seduce You

The grid search found that `3m / top 3 / 2m` had much higher CAGR than the original `6m / top 3 / 1m` configuration. That is interesting, but not automatically tradeable.

Grid search is good for discovering families of behavior. It is dangerous if the final decision is based only on the highest CAGR. A single best row may be overfit to one market regime, one data sample, one universe definition, or one lucky sequence of winners.

Future grid searches should rank by multiple views:

- CAGR
- Sharpe ratio
- max drawdown
- return stability across regimes
- turnover
- transaction cost sensitivity
- number of independent rebalances
- out-of-sample performance

The best production candidate is often not the highest CAGR. It is usually a robust area of the parameter grid.

## 6. Walk-Forward Testing Is More Useful Than One Big Backtest

The walk-forward validation was added because the grid-search winner needed a reality check. The process was:

1. Train on history up to a cutoff date.
2. Select the best parameter set from that training period.
3. Test only on the next unseen period.
4. Repeat through time.

This is closer to how a real trader would have made decisions. It showed that short lookback configurations kept reappearing, which supports the idea that they are not purely random. But it also showed weakness in 2022, which is a warning.

Future projects should make walk-forward validation a default step, not an afterthought.

## 7. Regime Robustness Matters More Than Headline CAGR

The regime analysis separated performance into different market environments:

- early sample
- pre-COVID
- COVID rebound
- 2022 rate bear market
- AI/semi bull period

This made the strategy easier to understand. The short-lookback strategy did very well in momentum-heavy bull markets, but it was not immune to bear markets.

For future universes, define regimes that fit the asset class. For example:

- small caps: high-rate vs low-rate periods
- commodities: inflationary vs disinflationary periods
- international equities: strong-dollar vs weak-dollar periods
- crypto: risk-on vs liquidity-crunch periods

A strategy that only works in one regime can still be useful, but it should be traded with that limitation in mind.

## 8. Turnover and Trading Friction Cannot Stay at Zero Forever

The current run uses zero transaction cost and zero slippage. That is acceptable for early research, but not for a trading decision.

Momentum strategies can rotate aggressively, especially with short lookbacks and concentrated baskets. Before using a strategy live, test:

- 5 bps, 10 bps, and 25 bps transaction cost
- slippage assumptions
- delayed execution by one day
- missing price data
- failed trades
- liquidity limits
- tax impact, if relevant

If a strategy only wins with zero friction, it is probably too fragile.

## 9. Keep Outputs Human-Readable

The most useful outputs were not just raw CSV files. The project became easier to reason about after adding:

- recent picks table
- pick rotation color block plot
- equity and drawdown charts
- grid-search table
- walk-forward table
- regime robustness table
- local dashboard

For future strategies, keep both machine-readable and human-readable outputs. CSV files are good for analysis. Markdown tables and dashboard views are good for decision-making.

## 10. The Dashboard Should Refresh Research, Not Hide It

The dashboard is useful because it can refresh data and show current picks. But it should remain connected to the same backtest logic used by the CLI. A dashboard that uses different logic from the research engine will eventually create confusion.

Future dashboards should show:

- current open basket
- latest completed rebalance
- next rebalance preview
- recent selection history
- performance vs benchmark
- parameter settings used for the run
- data freshness timestamp

The page should make the strategy inspectable, not just attractive.

## 11. Use Configuration as the Contract

`run_config.md` became the standard reference for what the current backtest means. This was important because small choices change results:

- start date
- end date
- realized backtest window
- lookback months
- score method
- rebalance date
- benchmark method
- transaction cost
- universe definition

For future projects, create a config file first. Treat it as the contract between research, code, summary, dashboard, and live use.

## 12. Tests Should Protect the Research Assumptions

The tests are not just code hygiene. They protect the meaning of the backtest.

Important behaviors to test:

- no lookahead in signal dates
- correct use of completed months
- correct rebalance timing
- correct equal-weight return calculation
- correct transaction cost handling
- correct benchmark return calculation
- correct period filtering for validation
- correct behavior when a ticker has missing data

When changing the universe or momentum formula, add tests for the new assumptions.

## 13. Best Reusable Architecture

For the next stock universe or signal, keep this structure:

```text
data source
  -> universe membership by date
  -> adjusted price cache
  -> signal/ranking function
  -> portfolio construction
  -> rebalance execution
  -> monthly returns
  -> metrics
  -> validation
  -> summary/dashboard
```

Each layer should be replaceable. For example, changing from Nasdaq-100 to S&P 500 should mostly change the universe file. Changing from six-month average return to volatility-adjusted momentum should mostly change the signal function.

## 14. Practical Research Checklist for Future Strategies

Before trusting a new universe or momentum calculation:

1. Define the universe and whether it is point-in-time.
2. Define the signal using only data available at rebalance time.
3. Define rebalance timing and execution price.
4. Compare against a simple benchmark.
5. Run baseline metrics.
6. Run grid search over a small, sensible parameter range.
7. Check whether good results cluster or come from one isolated parameter.
8. Run walk-forward validation.
9. Run regime robustness.
10. Add transaction cost and slippage sensitivity.
11. Inspect recent picks manually.
12. Document the exact run configuration.

## 15. Main Takeaway

The most important lesson is this:

Do not build a backtest that only answers, "How much money would this have made?"

Build a research system that answers:

- What exactly was tradable at the time?
- What information was available at the time?
- Why were these stocks selected?
- How sensitive is the result to parameters?
- Does it survive different market regimes?
- Does it still work after realistic trading friction?
- Can the same code produce both historical results and current live picks?

That is the foundation for adapting this project to a new universe and a new momentum calculation without starting over.
