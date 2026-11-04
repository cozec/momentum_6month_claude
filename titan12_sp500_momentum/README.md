# Titan-12 Momentum Rotation

## Referece:
https://www.xiaohongshu.com/explore/6a01f225000000003700eb1c?app_platform=ios&app_version=9.29&share_from_user_hidden=true&xsec_source=app_share&type=normal&xsec_token=CBUD1EVtTBvYvwum6k6I8QLd6l_uIs6tIanyR4l6dTmd4=&author_share=1&xhsshare=CopyLink&shareRedId=ODZFODc1Rzk2NzUyOTgwNjY0OTc1SD5P&apptime=1778708999&share_id=a512da2b2c7d4303b83d32d6095d0734

Titan-12 Momentum Rotation is a monthly S&P 500 rotation backtest. On the first
trading day of each month, it ranks eligible S&P 500 stocks by a weighted
12-month momentum score, buys the top 3 names at equal weight, and holds them
until the next monthly rebalance.

The score uses only the previous 12 completed monthly returns:

```text
score = 1*r_1 + 2*r_2 + ... + 12*r_12
```

The newest completed month receives the largest weight. The current partial
month is never used for signal calculation.

## Lookback Robustness (why 12 months)

The 12-month lookback is kept as-is, and deliberately not tuned. A grid search
over lookbacks 3M-15M (linear weights `1..N`, all other settings fixed, every
run aligned to the same 110-rebalance window from 2017-05-01) shows the
parameter is not identifiable from this data:

| lookback | CAGR | Sharpe | max DD | turnover |
|---------:|-----:|-------:|-------:|---------:|
| 3M  | 27.8% | 0.80 | -41.9% | 75.8% |
| 6M  | 41.8% | 1.05 | -31.2% | 57.0% |
| 7M  | 31.7% | 0.86 | -33.6% | 56.1% |
| 10M | 44.0% | 1.02 | -34.3% | 46.7% |
| 12M | 34.3% | 0.93 | -39.3% | 42.7% |
| 15M | 26.4% | 0.80 | -43.4% | 35.8% |

Findings:

- **No plateau.** CAGR drops 10.1 points from 6M to 7M, a one-month parameter
  change. Mean adjacent-neighbour swing across the whole grid is 5.1 points.
- **Bimodal.** 6M and 10M are two separate peaks with a trough between them,
  which is the signature of noise rather than structure.
- **No short-lookback edge.** Averaging grid halves: 3-8M CAGR 34.4% vs 9-15M
  34.7%; Sharpe 0.920 vs 0.920.
- **Rankings invert out-of-sample.** Splitting at 2021-12, the Spearman rank
  correlation between first-half and second-half lookback rankings is **-0.52**.
  3M ranked best in 2017-2021 and last in 2022-2026; 10M went worst to first.

What *is* robust: every lookback from 3M to 15M beats SPY by a wide margin
(26-44% CAGR vs 15.2%) with positive alpha, so the momentum signal holds across
the whole parameter range. Only the specific lookback is unidentifiable. 12M is
retained because nothing justifies moving off it and it carries meaningfully
lower turnover (42.7% vs 57.0% at 6M).

Turnover falling monotonically with lookback, and drawdowns of -31% to -45%
across the entire grid, are both structural: the drawdowns come from top-3
concentration, not from the lookback choice.

## Current Research Snapshot

The default run uses approximate point-in-time S&P 500 membership, fills at the
first trading day's open, and excludes the sister Nasdaq basket of each date.

Latest headline results are documented in `summary.md`:

- strategy final value: $43,174 from $10,000
- SPY final value: $38,464 from $10,000
- strategy CAGR: 16.19%
- SPY CAGR: 14.82%
- completed rebalances: 117

The summary also includes:

- run configuration
- headline results
- latest completed basket
- current open basket
- top-3 selections over the past year
- Nasdaq-overlap-excluded top-3 selections

## Setup

Create and activate the project virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running a Backtest

For serious research, provide `data/sp500_membership.csv` with point-in-time
membership history and run:

```bash
python main.py --start-date 2016-01-01 --end-date 2026-05-12
```

To bootstrap from the current S&P 500 list, run:

```bash
python main.py --membership-mode current_constituents
```

That mode is survivorship-biased for historical testing because it uses today's
index members for the full past period.

## Nasdaq-100 Universe

The same Titan-12 rules (12-month weighted momentum, top 3, monthly, 10 bps
costs) can run on the point-in-time Nasdaq-100, benchmarked against QQQ. The
universe is borrowed from the sister project
(`momentum_6m_claude/nasdaq100_momentum_backtest`):

```bash
.venv/bin/python scripts/import_sister_nasdaq100.py   # membership + missing prices
.venv/bin/python main.py --universe nasdaq100 --end-date 2026-10-11
```

The import writes `data/nasdaq100_membership.csv` and copies any price files the
local cache lacks (QQQ and Nasdaq-only names such as ASML, MELI, MSTR). The run
writes to `outputs/nasdaq100/` and `summary_nasdaq100.md`, so it never touches
the S&P 500 results. It does not apply the sister-overlap exclusion, since it is
itself a Nasdaq strategy. About 29 former Nasdaq-100 members that Yahoo no
longer prices (CELG, XLNX, ATVI, ...) are missing, so some survivorship bias
remains.

## Nasdaq-Overlap Exclusion Overlay

For cross-project diversification against the sister Nasdaq strategy, the
S&P basket excludes the sister's top picks **of the same rebalance date**, in the
historical backtest as well as the current basket, so the headline stats describe
the basket actually held:

1. Read the sister's dated baskets: a snapshot named by `NASDAQ_PICKS_FILE` when
   set (`scripts/month_end.py` takes one per run), else its live dashboard
   (`http://127.0.0.1:8765/api/picks?history=240`, override with
   `NASDAQ_PICKS_URL`), merged over its on-disk `outputs/` CSVs. Each basket is
   decided on the same prior close as the S&P basket, so this adds no lookahead.
   A run with no sister basket dated like the open rebalance stops with an error;
   older dates without one are logged as `missing_sister_basket`.
2. Drop any of those sister tickers from the S&P 500 Titan-12 ranking.
3. Backfill from the next-highest S&P 500 Titan-12 ranked names until 3 names
   are selected.

The result is written to `outputs/final_rebalance_picks.csv` and reported as
`Final Top 3 (Nasdaq-Overlap Excluded)` in `summary.md`, alongside the
pre-exclusion `Baseline Open Basket`. This final basket is the intended
tradeable set; the dashboard's headline "Current Basket" shows it too.

## Local Dashboard

Start the local dashboard from the project virtual environment:

```bash
.venv/bin/python run_webapp.py
```

Then open:

```text
http://127.0.0.1:8766/
```

By default the dashboard binds to `127.0.0.1` on port `8766`. Override the host
or port with environment variables:

```bash
TITAN12_HOST=0.0.0.0 TITAN12_PORT=8767 .venv/bin/python run_webapp.py
```

The dashboard has two tabs, S&P 500 and Nasdaq-100 (`/#sp500`, `/#nasdaq100`;
the API is `/api/dashboard?universe=nasdaq100`). The S&P 500 tab reads
`outputs/` and shows headline stats, the Nasdaq-overlap-excluded current basket,
and the last 12 Nasdaq-overlap-excluded rebalance baskets. The Nasdaq-100 tab
reads `outputs/nasdaq100/` and shows the plain Titan-12 basket and history
versus QQQ. The S&P 500 exclusions come from the sister dashboard on port 8765;
if it is offline, recent months fall back to its older CSV.

## Month-End Report and Trades Email

This project now lives inside the `momentum_6m_claude` repo next to the sister
Nasdaq-100 project (`../nasdaq100_momentum_backtest`). One GitHub Action
(`../.github/workflows/monthly-picks-email.yml`) handles month-end for both: on
the month's last NYSE trading day it starts the Nasdaq-100 dashboard, then runs
`scripts/month_end.py --email-json …`, which refreshes prices, re-runs the S&P 500
Titan-12 backtest, checks the next basket doesn't overlap the sister's, and
rebuilds `report.html`. The Action publishes it at
<https://cozec.github.io/momentum_6month_claude/titan12/report.html> and sends
one email covering both strategies, and still sends the Nasdaq-100 part if this
step fails. A seed price cache (`data/raw_prices/`) and the membership CSVs are
tracked; each run tops the cache up from the seed and does not commit it back.

To run it by hand (publishes and sends its own email):

```bash
# untracked .env at the project root
RESEND_API_KEY=re_...
EMAIL_FROM=onboarding@resend.dev
EMAIL_TO=you@example.com

.venv/bin/python scripts/month_end.py --dry-run --force          # no push, no email
.venv/bin/python scripts/month_end.py --force --skip-refresh --no-publish  # [TEST] email
```

The email preview goes to `logs/month_end_email.html`.

## Cloudflare Pages Static Deployment

The local dashboard can be exported as static files for Cloudflare Pages:

```bash
.venv/bin/python scripts/export_static_dashboard.py --output-dir public
```

The static export writes:

```text
public/index.html
public/app.js
public/dashboard.json
public/charts/*.png
```

Useful CLI options:

```bash
python main.py \
  --start-date 2010-01-01 \
  --end-date 2026-12-31 \
  --top-n 3 \
  --benchmark SPY \
  --transaction-cost-bps 5 \
  --slippage-bps 5 \
  --membership-mode historical_constituents \
  --refresh-data
```

## Membership Data

The membership file must be:

```text
data/sp500_membership.csv
```

Required columns:

```text
ticker,company_name,start_date,end_date,sector,source,notes
```

Rows with missing `start_date` are treated as eligible from the beginning of the
backtest. Rows with missing `end_date` are treated as active.

Historical membership matters because the current S&P 500 excludes companies
that were removed, acquired, or failed. Using only current constituents usually
overstates historical performance.

### Wikipedia History Bootstrap

For a good-enough research bootstrap, build an approximate point-in-time file
from Wikipedia's current S&P 500 table plus the add/remove history on the separate
[Historical components of the S&P 500](https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500)
page:

```bash
.venv/bin/python scripts/build_wikipedia_sp500_membership.py
```

This writes:

```text
data/sp500_membership_wikipedia_history.csv
```

Review the generated file before promoting it:

```bash
cp data/sp500_membership.csv data/sp500_membership.current_constituents.csv
cp data/sp500_membership_wikipedia_history.csv data/sp500_membership.csv
.venv/bin/python main.py --membership-mode historical_constituents --refresh-data
```

This Wikipedia-derived file is still approximate. It is better than using only
today's constituents, but it can have unknown start dates, missing sectors for
removed companies, ticker-history gaps, and omissions from Wikipedia's selected
changes table. For production-grade research, use a paid point-in-time index
constituent source such as CRSP, Compustat/Capital IQ, Bloomberg, Refinitiv,
Norgate, or another licensed dataset.

## Outputs

The backtest writes:

- `outputs/monthly_selections.csv`
- `outputs/portfolio_returns.csv`
- `outputs/summary_stats.csv`
- `outputs/charts/*.png`
- `logs/data_quality_report.csv`
- `logs/backtest.log`
- `summary.md`

The data quality report logs failed downloads, missing adjusted closes,
insufficient history, missing prices, and incomplete selections.

Key charts include the equity curve, drawdown curve, rolling returns, selection
frequency, sector exposure, excess return vs SPY, and a recent-rebalances card
chart showing the latest 12 completed top-3 baskets plus the current open MTD
basket.

## Tests

Run:

```bash
source .venv/bin/activate
pytest
```

The tests cover monthly return calculation, no-lookahead scoring, top-N
selection, first trading day generation, portfolio returns, turnover,
membership filtering, and summary metrics.

## Limitations

This is a research tool, not trading advice. Important limitations include:

- survivorship bias if current constituents are used
- imperfect historical ticker and delisting support
- Yahoo Finance data quality constraints
- taxes are not modeled
- liquidity constraints are not modeled
- execution uses the adjusted open on rebalance dates (decided on the prior close)
- transaction cost and slippage assumptions are simplified
- concentrated top-3 portfolios can have high idiosyncratic risk
