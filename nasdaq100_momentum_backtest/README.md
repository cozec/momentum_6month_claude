# Nasdaq-100 Monthly Momentum Rotation Backtest

A Python backtesting tool that runs a monthly 6-month momentum rotation strategy on the Nasdaq-100 universe, benchmarked against QQQ.

## Reference:
https://www.xiaohongshu.com/explore/69fe40e30000000037037c0d?xsec_token=ABEtUGDxuYs9OY_3Aa3sxyRd1BAlYpUJgOeZagDNpkBIc=&xsec_source=pc_user


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
    charts/                     # generated PNGs (equity curve, drawdown, etc.)
    grid_search/                # grid_results.csv from the param sweep
    monthly_selections.csv
    portfolio_returns.csv
    summary_stats.csv
  src/
    config.py        # BacktestConfig + Nasdaq-100 ticker list
    download_data.py # yfinance downloader with on-disk caching
    membership.py    # constituent loader / template writer
    signals.py       # monthly returns, momentum scores, top-N select
    backtest.py      # core monthly rebalance loop + compute_open_position
    metrics.py       # CAGR, vol, Sharpe, drawdown, win-rate, turnover
    plots.py         # equity curve, drawdown, dist, rolling, grid heatmap, …
    grid_search.py   # (lookback × period) sweep + walk-forward IS/OOS
    utils.py         # logging + filesystem helpers
  webapp/            # FastAPI dashboard (Tailwind-styled SPA)
    server.py        # /api/picks?lookback=&period= + /health
    static/index.html, static/app.js
  tests/
    test_strategy.py # unit tests for signals + portfolio math
  notebooks/
    exploration.ipynb
  main.py            # backtest CLI entry point
  grid_search.py     # grid-search CLI entry point
  run_webapp.py      # launches uvicorn (reads $PORT for Render/Heroku)
  send_picks_email.py# monthly cron → HTML email via Resend
  Procfile           # fallback for platforms that read it
  requirements.txt
  README.md
  summary.md
  config.md          # data + realized window derivation

# repo root (one level up)
render.yaml          # Render Blueprint (web service only; cron lives in GH)
.github/workflows/monthly-picks-email.yml
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

## Grid search + walk-forward

`grid_search.py` sweeps the (lookback × rebalance-period) grid and reports IS/OOS metrics:

```bash
source .venv/bin/activate
cd nasdaq100_momentum_backtest
python grid_search.py \
    --lookbacks 3 6 9 12 \
    --periods 1 2 3 \
    --train-end 2023-01-01
```

Writes `outputs/grid_search/grid_results.csv` and four heatmaps + an IS-vs-OOS scatter under `outputs/charts/`. See the "Grid-search results" section of [`summary.md`](summary.md) for the headline 12-combo table and takeaways.

## Live dashboard

A small FastAPI app at [`webapp/`](webapp/) serves a Tailwind-styled page that shows **two strategies side-by-side**:

- **Strategy A** — `L=6m / P=1m` (the project default / baseline).
- **Strategy B** — `L=3m / P=2m` (the grid-search winner, kept on the page as an apples-to-apples comparison).

Each section shows the current open holdings (with MTD return and "in progress" badge), summary stats (CAGR, Sharpe, max drawdown, win-rate vs QQQ), and a vertical feed of the last 12 completed rebalances. Run locally:

```bash
source .venv/bin/activate
cd nasdaq100_momentum_backtest
python run_webapp.py        # → http://127.0.0.1:8765
```

The page re-runs the backtest pipeline on every load; refresh button forces yfinance to re-download fresh prices. On the first trading day of a new month, Strategy A's open position rolls to a new entry; Strategy B holds for two months so it only rolls every second first-trading-day.

## One-click deploy (Render + GitHub Actions + Resend)

All three pieces have a free tier:

| Piece | Service | Free tier |
|---|---|---|
| Dashboard | [Render](https://render.com) Web Service | 750 hr/mo, sleeps after 15 min idle |
| Monthly email cron | GitHub Actions | 2,000 min/mo (private repo); unlimited for public |
| Email delivery | [Resend](https://resend.com) | 3,000 emails/mo |

Render's Free plan doesn't include cron jobs, which is why the schedule lives in GitHub Actions instead.

**1. Deploy the dashboard on Render:**
- Render dashboard → **New → Blueprint** → connect this repo.
- Render reads [`render.yaml`](../render.yaml) and creates the `momentum-web` service on the Free plan. Note the public URL it gives you (e.g. `https://momentum-web-xyz.onrender.com`).

**2. Set up the monthly email cron in GitHub:**
- In your fork's GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**, add four secrets:
  - `RESEND_API_KEY` — from [resend.com/api-keys](https://resend.com/api-keys)
  - `EMAIL_FROM` — Resend-verified sender (e.g. `picks@yourdomain.com`; for testing you can use `onboarding@resend.dev`)
  - `EMAIL_TO` — recipient(s), comma-separated
  - `MOMENTUM_API_BASE` — the Render URL from step 1
- The workflow at [`.github/workflows/monthly-picks-email.yml`](../.github/workflows/monthly-picks-email.yml) fires automatically at **22:00 UTC on the 1st of each month** (≈ 5–6 pm ET, just after the new month's first-trading-day close).

**3. Smoke-test:**
- GitHub → **Actions → Monthly picks email → Run workflow** → check that you receive the email within ~1 minute (longer if the Render web service is asleep — `send_picks_email.py` pre-warms via `/health` and retries 502s, so wake-ups are absorbed).

The email body shows both strategies' open holdings with rank, MTD return, and entry/last prices — same data the dashboard surfaces.

**Gotchas the script already handles (so you don't have to):**

- **Trailing whitespace in copy-pasted secrets** — env vars are stripped before use; `urllib`'s `Invalid header value` won't fire.
- **Render Free-plan cold-start 502s** — `/health` is hit up to 8× with 10s backoff to warm the worker, and `/api/picks` retries on 502/503/504 with linear backoff.
- **Cloudflare blocking `Python-urllib/*`** — Resend sits behind Cloudflare; the script sends a non-default `User-Agent` so the POST isn't rejected with `error code: 1010`.

## Caveats

- Default universe is the **current** Nasdaq-100 (101 tickers with both Alphabet share classes). Results are survivorship-biased and overstate the strategy's historical edge — winners like NVDA, AVGO, PLTR, MSTR, APP, SNDK, WDC, SHOP, INSM, AXON that were added in the 2020s were already present in the universe back in 2015. The grid-search run quantifies this: dropping post-2018 additions cuts the headline CAGR from ~80% to ~47%.
- The hardcoded universe is a static snapshot of the current Nasdaq-100. Index reconstitutions happen quarterly; refresh `CURRENT_NASDAQ100` in `src/config.py` periodically (or wire up a Wikipedia/Nasdaq fetcher) to keep current.
- Execution assumes you trade at the first-day adjusted close with the configured cost/slippage. Real-world fills, capacity, and tax effects are not modelled.
