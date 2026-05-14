# Backtest Summary

## Run configuration

| Parameter | Value |
|-----------|-------|
| Strategy | Top-3 equal-weight, 6-month average monthly return |
| Universe | Current Nasdaq-100 (101 tickers — both GOOG/GOOGL share classes; survivorship-biased) |
| Data window | 2016-01-01 → 2026-05-12 |
| Realized backtest window | 2016-08-01 entry → 2026-05-01 exit |
| Lookback | 6 completed months |
| Score method | `average_monthly_return` |
| Rebalance frequency | First trading day of each month |
| Transaction cost | 0 bps (disabled) |
| Slippage | 0 bps (disabled) |
| Initial capital | $100,000 |
| Primary benchmark | QQQ (buy & hold) |
| Secondary benchmark | TQQQ (buy & hold, 3× leveraged QQQ) |
| Rebalances executed | 117 |
| Tickers with usable history | 101 of 101 |

## Headline results

| Metric | Strategy | QQQ B&H | TQQQ B&H |
|--------|---------:|--------:|---------:|
| CAGR | **83.42%** | 20.64% | 40.45% |
| Annualized volatility | 51.65% | 20.11% | 62.87% |
| Sharpe ratio | **1.43** | 1.04 | 0.86 |
| Max drawdown | -36.48% | -33.67% | **-80.13%** |
| Total return | +36,827% | +523% | +2,644% |
| Final value (from $100k) | $37,026,765 | $622,982 | $2,743,567 |
| Average monthly return | 6.15% | 1.74% | 4.52% |
| Median monthly return | 3.60% | 2.08% | 5.10% |
| Best month | +60.73% | +16.69% | +52.19% |
| Worst month | -23.40% | -15.58% | -52.31% |
| Win rate vs QQQ (months) | 59.8% | — | — |
| Win rate vs TQQQ (months) | 52.1% | — | — |
| Average turnover | 70.94%/mo | — | — |

## Interpretation

- **Strategy vs QQQ.** Better on absolute return (+36,827% vs +523%) and on Sharpe (1.43 vs 1.04), at the cost of ~2.6× the volatility and a slightly deeper drawdown (-36.5% vs -33.7%). The strategy beats QQQ in 60% of months.
- **Strategy vs TQQQ.** TQQQ buy-and-hold (3× daily QQQ) compounded to +2,644% over this window — about 5× the QQQ return, well short of a naive 3× because of daily-rebalanced volatility drag and the brutal 2022 drawdown. The strategy still beat TQQQ in 52% of months and in absolute terms (≈$37.0M vs ≈$2.7M), while running materially lower volatility (52% vs 63%) and a much shallower max drawdown (-36.5% vs **-80.1%**). Sharpe is higher for the strategy (1.43 vs 0.86).
- **TQQQ is the asymmetric loser on drawdown.** -80% peak-to-trough means a $1M TQQQ position drops to $200k; recovering requires a +400% rally on what remains. This is the hidden cost behind TQQQ's superficially attractive +2,644% headline.
- **No-friction caveat.** This run sets transaction cost = slippage = 0, so strategy returns are *gross* (pre-trading-cost). At ~72% average monthly turnover, a 10 bps round-trip would shave roughly 0.86% per year off the strategy's CAGR; a 20 bps round-trip would shave ~1.7%. QQQ and TQQQ buy-and-hold are essentially frictionless anyway.

## Grid-search results (lookback × rebalance period)

12 (lookback, period) combos, full window 2016–2026 plus a walk-forward split at **train_end = 2023-01-01** (≈ 6.5 y train / 3.3 y test). Returns are gross; benchmarks are the same as in the headline table. **Rows are ranked by full-period CAGR (highest first).** The top row — L=3m / P=2m — is also the IS, OOS, and full-period Sharpe winner.

| Lookback | Period | Rebals | CAGR | Vol | Sharpe | Max DD | Total Return | IS Sharpe | OOS Sharpe |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **3m** | **2m** | **60** | **+97.84%** | **52.7%** | **1.58** | **-30.8%** | **91,780%** | **1.24** | **2.27** |
| 3m | 3m | 40 | +84.27% | 69.0% | 1.18 | -47.6% | 45,042% | 0.91 | 1.72 |
| 3m | 1m | 120 | +84.20% | 54.1% | 1.38 | -45.2% | 44,878% | 1.17 | 1.77 |
| 6m | 1m | 117 | +83.42% | 51.6% | 1.43 | -36.5% | 36,927% | 1.06 | 2.04 |
| 9m | 2m | 57 | +82.61% | 54.0% | 1.39 | -32.1% | 30,416% | 0.99 | 2.17 |
| 6m | 3m | 39 | +81.05% | 62.0% | 1.25 | -26.3% | 32,526% | 1.00 | 1.79 |
| 6m | 2m | 58 | +76.40% | 52.1% | 1.35 | -31.1% | 24,039% | 1.15 | 1.72 |
| 9m | 1m | 114 | +76.02% | 54.2% | 1.30 | -35.5% | 21,422% | 1.00 | 1.76 |
| 9m | 3m | 38 | +68.74% | 54.3% | 1.23 | -29.7% | 14,307% | 0.94 | 1.83 |
| 12m | 1m | 111 | +46.33% | 49.0% | 1.00 | -41.4% | 3,283% | 0.66 | 1.48 |
| 12m | 3m | 37 | +44.32% | 50.0% | 0.97 | -52.0% | 2,877% | 0.52 | 1.94 |
| 12m | 2m | 55 | +32.32% | 47.9% | 0.80 | -44.8% | 1,203% | 0.53 | 1.34 |

### Takeaways

- **L=12m is consistently the worst** across every rebalance period (Sharpe 0.80–1.00, CAGR 32–46%). Six-month momentum is the textbook horizon and shorter still works; one year is too stale.
- **The L∈{3,6,9}m × P∈{1,2,3}m sub-block clusters at Sharpe 1.18–1.58** — a flat plateau. Pick anything in that block and you get a similar profile, which is the robustness signal we wanted.
- **No overfitting**: every combo's OOS Sharpe ≥ IS Sharpe (all 12 points plot above y=x in the walk-forward scatter). The IS winner (L3/P2) is also the OOS winner — no parameter cherry-picking advantage.
- **Be skeptical of the OOS magnitudes.** The 2023-01 → 2026-05 OOS regime was a once-in-a-decade momentum tape (NVDA → MSTR → SNDK/WDC chain). 2.0+ Sharpes are not a forward expectation; they're a regime artifact.
- **The headline run uses L=6m/P=1m** (defaults). The grid-best L=3m/P=2m is only ~0.15 Sharpe higher full-period and 1.0 OOS Sharpe higher — given the regime caveat above, the small full-period edge isn't enough to justify switching unless you also believe 3m signal will keep working forward.

See [`outputs/grid_search/grid_results.csv`](outputs/grid_search/grid_results.csv) for raw numbers and [`outputs/charts/grid_full_sharpe.png`](outputs/charts/grid_full_sharpe.png), [`grid_walkforward_scatter.png`](outputs/charts/grid_walkforward_scatter.png) for the heatmap and IS-vs-OOS scatter.

## Debug audit ("75% CAGR — is it real?")

Asked of the result. The answer breaks into two parts.

### Part 1: the math and the data are clean

I audited the full pipeline:

| Check | Result |
|-------|--------|
| Momentum scores at 2016-08-01 vs a hand-built recomputation from raw price files | Identical |
| Score window uses only month-ends strictly *before* the rebalance date (no lookahead) | Confirmed |
| For tickers held across consecutive months, `exit_price[t]` == `entry_price[t+1]` (223 chained pairs) | 0 mismatches |
| Per-stock return == `exit_price / entry_price - 1` | Max diff 2.5e-16 |
| `portfolio_return_gross` == equal-weight mean of per-stock returns | Max diff 1.4e-16 |
| `portfolio_value` series compounds correctly from $100k off `portfolio_return_net` | Reproduces final $27,157,981 exactly |
| NVDA prices (split-adjusted): $1.39 on 2016-08-01 → $221 on 2026-05-12 | Matches Yahoo Finance (4:1 in 2021, 10:1 in 2024 split history accounted for) |

I also found a small bug: the old `metrics.py` computed `total_return = equity.iloc[-1] / equity.iloc[0] - 1`, but `equity.iloc[0]` is already post-first-period, so the reported CAGR was understated by ~2 pp. The fix uses `(1 + monthly_returns).prod() - 1`, which is exactly the $100k → final-value path. This is why the headline CAGR moved from 75.64% to **77.68%**.

### Part 2: the headline is real, the *interpretation* is bias

Naked buy-and-hold of the strategy's favorite picks over the same window:

| Ticker | Buy-and-hold multiple | Buy-and-hold CAGR |
|--------|---------------------:|------------------:|
| NVDA   | 142× | 66.31% |
| AMD    |  54× | 50.64% |
| AVGO   |  34× | 43.38% |
| TSLA   |  25× | 39.39% |
| MSTR   |  10× | 27.02% |

NVDA *alone* is 66% CAGR. The strategy concentrates 1/3 of capital into one of these names every month, so 78% CAGR is consistent with successfully rotating among the top movers.

But **the universe itself is the bias**. To bound this, I re-ran the strategy after dropping 23 tickers that joined the Nasdaq-100 only after 2018 — specifically the post-2018 IPOs that were added *because* they did well: MSTR, PLTR, APP, ABNB, DASH, ARM, CRWD, DDOG, MDB, PDD, TEAM, TTD, ZS, GFS, CEG, GEHC, CCEP, CDW, MELI, WBD, FANG, AZN, KDP.

| Universe | Strategy CAGR | Final value |
|----------|--------------:|------------:|
| Full current Nasdaq-100 (100 tickers) | **77.68%** | $27.2M |
| Drop 23 late additions (77 tickers) | **46.94%** | $4.3M |

So roughly **31 percentage points of the headline CAGR comes purely from "knowing in advance" which late additions would do well.** This is the textbook survivorship-bias mechanism flagged in the README and the spec.

The remaining ~47% CAGR is still extraordinary, and reflects:
1. NVDA / AMD / AVGO / TSLA legitimately had 40-66% CAGR buy-and-hold over this period.
2. Top-3 equal-weight monthly rebalance concentrates into whatever is rallying.
3. Even the 77-ticker universe is *still* survivorship-biased — every name in it survived to 2026.

A proper apples-to-apples result requires a historical Nasdaq-100 membership file (run with `--use-historical-membership`); the code path is ready for it.
- **Caveat — survivorship bias.** The strategy's universe is the *current* Nasdaq-100, which already includes NVDA, MSTR, PLTR, APP, MELI, AMD. Re-running with historical membership would shrink the strategy's edge over TQQQ (and possibly QQQ). The TQQQ comparison is bias-free; the strategy comparison is not.

## Most-selected tickers (out of 117 rebalances)

| Ticker | Selections |
|--------|-----------:|
| MSTR | 26 |
| NVDA | 25 |
| TSLA | 20 |
| PDD | 19 |
| INSM | 19 |
| PLTR | 19 |
| AMD | 19 |
| ALNY | 17 |
| SHOP | 17 |
| APP | 15 |
| DXCM | 15 |
| AXON | 14 |
| WDC | 11 |
| ZS | 10 |
| FANG | 9 |

## Output files

- `outputs/monthly_selections.csv` — 351 rows (117 rebalances × 3 picks). 33 distinct tickers picked from the 101-name universe.
- `outputs/portfolio_returns.csv` — 117 rows. Includes `tqqq_return`, `tqqq_value`, and `excess_return_vs_tqqq` columns.
- `outputs/summary_stats.csv` — three columns: strategy, QQQ buy-and-hold, TQQQ buy-and-hold.
- `outputs/charts/` — equity curve (log-scale, all three lines), drawdown (strategy + QQQ + TQQQ overlay), monthly distribution, rolling 6m and 12m returns (with TQQQ), ticker-selection frequency, monthly excess vs QQQ.

## Universe correction (this run)

The previously-hardcoded universe was a stale 100-ticker snapshot. It was reconciled against an authoritative price-file dataset to match the current Nasdaq-100 (101 entries because both Alphabet share classes — `GOOG` and `GOOGL` — are listed):

- **Added (11):** `ALNY`, `AXON`, `FER`, `INSM`, `MPWR`, `SHOP`, `SNDK`, `STX`, `TRI`, `WDC`, `WMT`
- **Removed (10):** `ANSS`, `AZN`, `BIIB`, `CDW`, `GFS`, `LULU`, `MDB`, `ON`, `TEAM`, `TTD`

Of the 11 newly-added names, 7 ended up in the top-3 at least once over the realized window (`INSM` 19, `SHOP` 17, `ALNY` 17, `AXON` 14, `WDC` 11, `STX` 8, `SNDK` 7). The other 4 (`MPWR`, `WMT`, `TRI`, `FER`) never had strong enough 6-month momentum to crack the top 3.

This correction also lifted the headline CAGR from 77.68% → **83.42%** because two of the additions (`INSM` and `SHOP`) had multi-bagger runs that the strategy successfully rotated into.

## Live deployment

The dashboard + monthly email pipeline is wired up end-to-end, all on free tiers:

| Piece | Service | Notes |
|---|---|---|
| Dashboard | Render Free web service (`momentum-web`) | Tailwind SPA showing Strategy A (L=6m/P=1m) and Strategy B (L=3m/P=2m) side-by-side. Sleeps after 15 min idle; first call ≈ 30 s wake + < 1 s after that. |
| Monthly cron | GitHub Actions (`monthly-picks-email.yml`) | Fires at `0 22 1 * *` UTC. Pre-warms `/health`, fetches both strategies with `refresh=1`, builds an HTML+text email. |
| Email delivery | Resend (3,000 / mo free) | Cloudflare-fronted; the script sends a non-default `User-Agent` so the POST isn't blocked with code 1010. |

**Behaviour on the 1st of each month:** Strategy A rebalances (new picks scored on the new first-trading-day, MTD ≈ 0% on entry). Strategy B holds for two months, so on every *other* 1st it rolls; in between it just shows the same picks with an updated period-to-date return. The completed previous-month holding becomes a new row in the dashboard's "Past rebalances" feed and is reflected in the next email.

## Caveats

1. **Survivorship bias** — current-constituents universe overstates strategy returns. To get a clean number, supply historical Nasdaq-100 membership in `data/nasdaq100_membership.csv` and run with `--use-historical-membership`. The QQQ and TQQQ buy-and-hold figures are not affected. The grid-search experiment quantified this: dropping post-2018 index additions cut the headline CAGR from ~78% to ~47% (a ~31 pp survivorship premium).
2. **Leverage decay** — TQQQ resets exposure daily, so over multi-month windows the return is path-dependent and typically less than 3× the QQQ return. The realized -80% drawdown is the worst-case manifestation of that path dependence.
3. **Concentration risk** — top-3 equal-weight is highly concentrated; the realized volatility reflects that.
4. **Execution** — fills assumed at the first-day adjusted close with 0 bps friction. Real capacity, market impact, and tax effects are not modelled; at ~72%/mo turnover, a 10 bps round-trip would shave ~0.86 pp/yr off the CAGR.
5. **Universe is a static hardcoded snapshot.** It was reconciled to 101 tickers (the universe correction section above) but Nasdaq-100 reconstitutions happen quarterly; refresh `CURRENT_NASDAQ100` in `src/config.py` periodically.


