# Backtest Summary

## Run configuration

| Parameter | Value |
|-----------|-------|
| Strategy | Top-3 equal-weight, 6-month average monthly return |
| Universe | Nasdaq-100 with **point-in-time membership** (from `scripts/build_membership.py` → 300 spans, 101 currently active). Survivorship bias controlled. |
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
| Tickers with usable history | 101 currently active + historical adds/drops via PIT membership |

## Headline results (point-in-time membership)

| Metric | Strategy | QQQ B&H | TQQQ B&H |
|--------|---------:|--------:|---------:|
| CAGR | **57.70%** | 20.64% | 40.45% |
| Annualized volatility | 39.20% | 20.11% | 62.87% |
| Sharpe ratio | **1.36** | 1.04 | 0.86 |
| Max drawdown | -30.56% | -33.67% | **-80.13%** |
| Total return | +8,390% | +523% | +2,644% |
| Final value (from $100k) | $8,489,656 | $622,983 | $2,743,567 |
| Average monthly return | 4.44% | 1.74% | 4.52% |
| Median monthly return | 2.42% | 2.08% | 5.10% |
| Best month | +54.71% | +16.69% | +52.19% |
| Worst month | -18.15% | -15.58% | -52.31% |
| Win rate vs QQQ (months) | 58.1% | — | — |
| Win rate vs TQQQ (months) | 46.2% | — | — |
| Average turnover | 77.21%/mo | — | — |

## Snapshot vs PIT membership — by strategy

The webapp at [`webapp/`](webapp/) renders both Strategy A and Strategy B; each can be run against either the current-snapshot universe (cheap, survivorship-biased) or the PIT membership CSV. The dashboard was flipped to PIT in commit `202d4f0`. Concretely:

| | Snapshot (was) | **PIT (now)** | Δ |
|---|---:|---:|---:|
| Strategy A CAGR | 83.42% | **57.70%** | −25.7 pp |
| Strategy A Sharpe | 1.43 | **1.36** | −0.07 |
| Strategy B CAGR | 97.84% | **46.86%** | **−51.0 pp** |
| Strategy B Sharpe | 1.58 | **1.24** | −0.34 |

**Why Strategy B's correction is much larger:** its top-3 leaned more heavily on late-2024+ additions (MSTR, PLTR, APP, SNDK) than the L=6m baseline did. The bi-monthly variant was *more* survivorship-inflated, which is consistent with the grid-search caveat: a 0.15-Sharpe edge over 60 observations is well within noise, and most of it was bias to begin with.

**What doesn't change:** the *current* open holdings on both strategies are identical to the snapshot run (`SNDK / WDC / INTC` for A; `INTC / MRVL / SNDK` for B), because all six tickers are current Nasdaq-100 members on the 2026-05-01 entry date. The historical timeline rows in the dashboard's "Past Rebalances" feed do differ — under PIT, late additions are simply not in the eligible universe before their join dates.

## Interpretation

- **Strategy vs QQQ.** Still meaningfully better on absolute return (+8,390% vs +523%) and on Sharpe (1.36 vs 1.04), at the cost of ~2× the volatility (39% vs 20%). Strikingly, with PIT membership the max drawdown is now *shallower* than QQQ's (-30.6% vs -33.7%) — the strategy rotates out of the worst names before they bottom. Beats QQQ in 58% of months.
- **Strategy vs TQQQ.** TQQQ buy-and-hold (3× daily QQQ) compounded to +2,644% — about 5× the QQQ return, well short of a naive 3× because of daily-rebalanced volatility drag and the brutal 2022 drawdown. The strategy beats TQQQ in absolute terms (≈$8.5M vs ≈$2.7M) and on Sharpe (1.36 vs 0.86), with much lower volatility (39% vs 63%) and a far shallower max drawdown (-30.6% vs **-80.1%**). It loses on monthly win rate (46% — TQQQ's monthly returns are amplified). The right comparison isn't *which beats more months* but *which is worth holding*: TQQQ-style leverage spends its CAGR on volatility, while the strategy turns it into Sharpe.
- **TQQQ is the asymmetric loser on drawdown.** -80% peak-to-trough means a $1M TQQQ position drops to $200k; recovering requires a +400% rally on what remains. This is the hidden cost behind TQQQ's superficially attractive +2,644% headline.
- **No-friction caveat.** This run sets transaction cost = slippage = 0, so strategy returns are *gross* (pre-trading-cost). At ~77% average monthly turnover, a 10 bps round-trip would shave roughly 0.92% per year off the strategy's CAGR; a 20 bps round-trip would shave ~1.8%. QQQ and TQQQ buy-and-hold are essentially frictionless anyway.

## Current holdings and last 12 rebalances

**Open position** (entry 2026-05-01, MTD through 2026-05-12; from the PIT run):

| Rank | Ticker | Momentum score | Entry $ | Latest $ | MTD return |
|---:|:---:|---:|---:|---:|---:|
| 1 | SNDK | 0.407 | $1,187.00 | $1,452.02 | **+22.3%** |
| 2 | WDC  | 0.215 |   $431.52 |   $488.74 | **+13.3%** |
| 3 | INTC | 0.212 |    $99.62 |   $120.61 | **+21.1%** |

Equal-weight portfolio MTD: **+18.9%**.

**Last 12 completed rebalances** (newest first; each cell shows the per-stock return over the holding period; final column is the equal-weight portfolio's gross return for that month):

| Entry | Exit | #1 | #2 | #3 | Portfolio |
|---|---|---|---|---|---:|
| Apr 2026 | May 2026 | WDC (+44.9%) | MU (+47.4%) | STX (+71.8%) | **+54.7%** |
| Mar 2026 | Apr 2026 | WDC (+10.3%) | MU (−10.8%) | WBD (−3.5%) | −1.4% |
| Feb 2026 | Mar 2026 | MU (−5.7%) | WDC (−0.1%) | STX (−12.3%) | −6.0% |
| Jan 2026 | Feb 2026 | WDC (+44.0%) | WBD (−3.5%) | MU (+38.8%) | **+26.4%** |
| Dec 2025 | Jan 2026 | MU (+31.2%) | WBD (+19.4%) | AMD (+1.7%) | +17.5% |
| Nov 2025 | Dec 2025 | MU (+2.5%) | AMD (−15.4%) | WBD (+7.1%) | −1.9% |
| Oct 2025 | Nov 2025 | APP (−10.2%) | PLTR (+12.0%) | WBD (+15.2%) | +5.7% |
| Sep 2025 | Oct 2025 | PLTR (+17.7%) | AMD (+1.0%) | APP (+46.2%) | +21.6% |
| Aug 2025 | Sep 2025 | PLTR (+1.8%) | AMD (−5.5%) | NVDA (−1.7%) | −1.8% |
| Jul 2025 | Aug 2025 | PLTR (+18.1%) | ZS (−8.8%) | CEG (+10.7%) | +6.6% |
| Jun 2025 | Jul 2025 | PLTR (−1.0%) | AVGO (+6.7%) | CRWD (+2.7%) | +2.8% |
| May 2025 | Jun 2025 | PLTR (+13.6%) | APP (+43.8%) | MSTR (−2.4%) | +18.3% |

Trailing 12-month compounded returns: **Strategy +241.9% · QQQ +40.6% · TQQQ +131.7%**. The window captured the late-2025 → early-2026 storage/memory rally (SNDK, WDC, MU, STX) plus the PLTR run earlier in 2025, which drove the strategy's outsized year.

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

## Most-selected tickers (out of 117 rebalances, PIT membership)

| Ticker | Selections |
|--------|-----------:|
| NVDA | 43 |
| TSLA | 31 |
| MU | 23 |
| AMD | 22 |
| MELI | 18 |
| PDD | 17 |
| STX | 11 |
| NFLX | 11 |
| PLTR | 10 |
| CEG | 10 |
| VRTX | 9 |
| APP | 8 |
| META | 8 |
| AMAT | 8 |
| CRWD | 7 |

PIT-vs-snapshot diff: under PIT, names always-in-the-index (NVDA, TSLA, MU, AMD, MELI) get many more selections because they're the only eligible momentum candidates for most of the early window. Late additions (MSTR, SHOP, SNDK, WDC, INSM, ALNY, AXON) drop sharply since they aren't eligible until their actual join date.

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

### Dashboard UX & refresh performance

- **Strategy A explainer** — a "How this strategy works" panel sits directly under the Strategy A header (with the summary-stats row — CAGR, Sharpe, max DD, win-rate vs QQQ — moved to just beneath it), so the page is self-describing without the README.
- **Forced-refresh speedup** — the header **Refresh** button (`refresh=1`) re-downloads fresh prices and bypasses the 5-min result cache. It used to make ~200 sequential yfinance calls (two strategies × ~100 tickers) and took tens of seconds. Now:
  - the universe is fetched **concurrently** (8-worker thread pool) in `download_price_data`, and
  - a 60 s in-memory **price-panel cache** lets the second strategy in the same page load reuse the first's download instead of re-fetching it.
  - Switched the per-ticker fetch from `yf.download` to the thread-safe `Ticker.history` API (`yf.download` writes module-global state and corrupts frames under concurrency), stripping its tz so it still merges with the naive-dated CSV cache.
  - **Result:** a full forced refresh of 103 tickers now completes in **~2.4 s** end-to-end (first strategy ~2.3 s of parallel download, second strategy ~0.07 s from the panel cache); a normal cached reload is ~1.5 ms. All 23 unit tests still pass.

## Caveats

1. **Survivorship bias** — current-constituents universe overstates strategy returns. The grid-search experiment first estimated this at ~31 pp (dropping post-2018 index additions cut CAGR from ~78% to ~47%). With a Wikipedia-sourced PIT membership CSV (`python scripts/build_membership.py` then `--use-historical-membership`), the measured delta is ~25 pp: **CAGR 83.4% → 57.7%, Sharpe 1.43 → 1.36, max DD -36.5% → -30.6%** over the same 117-rebalance window. Sharpe and DD barely move — the strategy *quality* is intact; the excess return is what shrinks. QQQ and TQQQ buy-and-hold figures are unaffected.
2. **Leverage decay** — TQQQ resets exposure daily, so over multi-month windows the return is path-dependent and typically less than 3× the QQQ return. The realized -80% drawdown is the worst-case manifestation of that path dependence.
3. **Concentration risk** — top-3 equal-weight is highly concentrated; the realized volatility reflects that.
4. **Execution** — fills assumed at the first-day adjusted close with 0 bps friction. Real capacity, market impact, and tax effects are not modelled; at ~72%/mo turnover, a 10 bps round-trip would shave ~0.86 pp/yr off the CAGR.
5. **Universe is a static hardcoded snapshot.** It was reconciled to 101 tickers (the universe correction section above) but Nasdaq-100 reconstitutions happen quarterly; refresh `CURRENT_NASDAQ100` in `src/config.py` periodically.


