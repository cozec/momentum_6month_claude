"""Generate rebalance_example.html — strategy "success story" case studies.

Shows how the momentum rotation actually traded a couple of signature names
(MU and PLTR), month by month: when it bought, held, sold, and (for MU) bought
again. Each case study has a price chart with buy/sell markers and shaded hold
periods, headline stat tiles, and a monthly trade log — all baked into one
self-contained HTML file (charts embedded as PNG data URIs).

Run:  python scripts/rebalance_example.py
Out:  repo-root/rebalance_example.html
"""

from __future__ import annotations

import base64
import io
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, ".."))
REPO_ROOT = os.path.abspath(os.path.join(PROJ, ".."))
RAW = os.path.join(PROJ, "data", "raw_prices")
OUT_HTML = os.path.join(REPO_ROOT, "rebalance_example.html")

sys.path.insert(0, PROJ)
from src.backtest import run_backtest  # noqa: E402
from src.config import BacktestConfig  # noqa: E402

ACCENT = "#1f4e79"
GREEN = "#2e7d32"
RED = "#c62828"
GOLD = "#e8a300"
INK = "#0f172a"
MUTED = "#64748b"

TODAY = pd.Timestamp.now().normalize()

# Each case study is one ticker over a date window; continuous monthly holds
# (and the gaps between them) are detected automatically from the pick chain.
CAMPAIGNS = [
    {
        "ticker": "TSLA",
        "name": "Tesla",
        "subtitle": "The pandemic-era moonshot — a top pick every month of 2020",
        "window": ("2020-01-01", "2021-01-01"),
    },
    {
        "ticker": "TSLA",
        "name": "Tesla",
        "subtitle": "The flip side of momentum — a choppy, range-bound 2021 of whipsaws",
        "window": ("2021-01-01", "2022-01-01"),
    },
    {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "subtitle": "The AI awakening — the strategy caught the 2023 breakout and held it",
        "window": ("2023-03-01", "2023-12-10"),
    },
    {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "subtitle": "AI leadership continues — held through 2024, re-entered in November",
        "window": ("2024-03-01", "2024-12-10"),
    },
    {
        "ticker": "PLTR",
        "name": "Palantir",
        "subtitle": "A momentum leader the strategy rode through the summer of 2025",
        "window": ("2025-07-01", "2025-11-10"),
    },
    {
        "ticker": "MU",
        "name": "Micron Technology",
        "subtitle": "Riding the AI-memory super-cycle — bought, sold near the top, bought back",
        "window": ("2025-11-01", "2026-12-31"),
    },
]


def load_trades():
    """Run the backtest to today and return all top-3 picks (completed + open)."""
    cfg = BacktestConfig(
        start_date="2016-01-01",
        end_date=TODAY.strftime("%Y-%m-%d"),
        use_historical_membership=True,
    )
    res = run_backtest(cfg)
    sel = res["selections"].copy()
    sel["is_open"] = False
    op = res.get("open_position")
    if op is not None and not op.empty:
        op = op.copy()
        op["is_open"] = True
        sel = pd.concat([sel, op[sel.columns]], ignore_index=True)
    sel["rebalance_date"] = pd.to_datetime(sel["rebalance_date"])
    sel["exit_date"] = pd.to_datetime(sel["exit_date"])
    return sel


def load_prices(ticker):
    df = pd.read_csv(os.path.join(RAW, f"{ticker}.csv"), parse_dates=["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def split_holds(rows):
    """Split a ticker's picks into continuous holds.

    Consecutive monthly rolls chain (each pick's entry is the prior pick's
    exit), so a break appears whenever a pick's rebalance date doesn't equal
    the previous pick's exit date — i.e. the stock left the basket for a
    month or more, then came back.
    """
    holds, cur = [], None
    for _, r in rows.iterrows():
        if cur is not None and r["rebalance_date"] != cur[-1]["exit_date"]:
            holds.append(cur)
            cur = None
        if cur is None:
            cur = []
        cur.append(r)
    if cur:
        holds.append(cur)
    return [pd.DataFrame(h).reset_index(drop=True) for h in holds]


def fmt_price(x):
    return f"${x:,.2f}"


def fmt_pct(x):
    return f"{x*100:+.1f}%"


def make_chart(ticker, name, segments_rows, px):
    """Price line with shaded holds, buy/sell markers, monthly-repick stars."""
    starts = [r.iloc[0]["rebalance_date"] for r in segments_rows if len(r)]
    last = segments_rows[-1]
    end_anchor = last.iloc[-1]["exit_date"] if len(last) else TODAY
    first_entry = min(starts)
    # Show the 7 months of price history before the first buy — the strategy
    # scores on the prior 6 months, so this is the run-up it "saw".
    x0 = first_entry - pd.DateOffset(months=7)
    x1 = min(end_anchor + pd.Timedelta(days=14), TODAY)
    p = px[(px["Date"] >= x0) & (px["Date"] <= x1)]

    fig, ax = plt.subplots(figsize=(11, 4.3))
    ax.plot(p["Date"], p["Close"], color=ACCENT, lw=1.8, zorder=3)
    ax.fill_between(p["Date"], p["Close"], p["Close"].min(),
                    color=ACCENT, alpha=0.06, zorder=1)

    # Shade the 6-month momentum lookback window that drove the first pick.
    lb_start = first_entry - pd.DateOffset(months=6)
    ax.axvspan(lb_start, first_entry, color="#94a3b8", alpha=0.12, zorder=0)
    ax.annotate("6-mo momentum\nlookback",
                xy=(lb_start + (first_entry - lb_start) / 2, ax.get_ylim()[1]),
                xytext=(0, -3), textcoords="offset points",
                ha="center", va="top", fontsize=7.5, color=MUTED)

    for rows in segments_rows:
        if not len(rows):
            continue
        entry_d = rows.iloc[0]["rebalance_date"]
        entry_p = rows.iloc[0]["entry_price"]
        exit_d = rows.iloc[-1]["exit_date"]
        exit_p = rows.iloc[-1]["exit_price"]
        is_open = bool(rows.iloc[-1]["is_open"])

        ax.axvspan(entry_d, exit_d, color=GREEN, alpha=0.10, zorder=0)
        # monthly re-pick stars
        ax.scatter(rows["rebalance_date"], rows["entry_price"], marker="*",
                   s=150, color=GOLD, edgecolor="#7a5800", lw=0.5, zorder=5)
        # BUY marker
        ax.scatter([entry_d], [entry_p], marker="^", s=190, color=GREEN,
                   edgecolor="white", lw=1.3, zorder=6)
        ax.annotate(f"BUY\n{fmt_price(entry_p)}", (entry_d, entry_p),
                    textcoords="offset points", xytext=(-2, -40), ha="center",
                    fontsize=8.5, fontweight="bold", color=GREEN)
        # SELL / current marker
        if is_open:
            ax.scatter([exit_d], [exit_p], marker="o", s=120, color=GOLD,
                       edgecolor="white", lw=1.3, zorder=6)
            ax.annotate(f"HOLDING\n{fmt_price(exit_p)}", (exit_d, exit_p),
                        textcoords="offset points", xytext=(6, 14), ha="left",
                        fontsize=8.5, fontweight="bold", color="#8a6d00")
        else:
            ax.scatter([exit_d], [exit_p], marker="v", s=190, color=RED,
                       edgecolor="white", lw=1.3, zorder=6)
            ax.annotate(f"SELL\n{fmt_price(exit_p)}", (exit_d, exit_p),
                        textcoords="offset points", xytext=(2, 16), ha="center",
                        fontsize=8.5, fontweight="bold", color=RED)

    ax.set_ylabel("Price ($)", fontsize=9, color=MUTED)
    span_months = max(1, (x1 - x0).days / 30.4)
    iv = 1 if span_months <= 9 else (2 if span_months <= 18 else 3)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=iv))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.tick_params(labelsize=8, colors=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#cbd5e1")
    ax.grid(axis="y", alpha=0.25)
    ax.margins(x=0.01)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def campaign_data(cfg, picks):
    ticker = cfg["ticker"]
    px = load_prices(ticker)
    lo, hi = cfg["window"]
    m = ((picks["ticker"] == ticker)
         & (picks["rebalance_date"] >= lo)
         & (picks["rebalance_date"] < hi))
    rows_all = picks[m].sort_values("rebalance_date").reset_index(drop=True)
    seg_rows_list, seg_meta = split_holds(rows_all), []
    for rows in seg_rows_list:
        entry_p = rows.iloc[0]["entry_price"]
        exit_p = rows.iloc[-1]["exit_price"]
        seg_meta.append({
            "entry_date": rows.iloc[0]["rebalance_date"],
            "exit_date": rows.iloc[-1]["exit_date"],
            "entry_price": entry_p,
            "exit_price": exit_p,
            "ret": exit_p / entry_p - 1.0,      # chained monthly rolls => exit/entry
            "months": len(rows),
            "is_open": bool(rows.iloc[-1]["is_open"]),
            "rows": rows,
        })
    img = make_chart(ticker, cfg["name"], seg_rows_list, px)
    # buy & hold over the whole campaign span (first entry -> last exit/latest)
    first_entry = seg_meta[0]["entry_price"]
    last_exit = seg_meta[-1]["exit_price"]
    bh = last_exit / first_entry - 1.0
    return {"cfg": cfg, "img": img, "segments": seg_meta, "buyhold": bh,
            "span_start": seg_meta[0]["entry_date"], "span_end": seg_meta[-1]["exit_date"]}


# --------------------------------------------------------------------------- HTML

def tile(label, value, sub="", color=INK):
    sub_html = f'<div class="tile-sub">{sub}</div>' if sub else ""
    return (f'<div class="tile"><div class="tile-label">{label}</div>'
            f'<div class="tile-val" style="color:{color}">{value}</div>{sub_html}</div>')


def trade_table(rows):
    body = []
    for _, r in rows.iterrows():
        ret = r["stock_return"]
        c = GREEN if ret > 0 else RED
        tag = ' <span class="open-tag">open · MTD</span>' if r["is_open"] else ""
        exit_lbl = ("now " if r["is_open"] else "") + r["exit_date"].strftime("%b %-d, %Y")
        body.append(
            f"<tr><td>{r['rebalance_date'].strftime('%b %-d, %Y')}</td>"
            f"<td class='center'>#{int(r['rank'])}</td>"
            f"<td class='num'>{fmt_price(r['entry_price'])}</td>"
            f"<td>{exit_lbl}</td>"
            f"<td class='num'>{fmt_price(r['exit_price'])}</td>"
            f"<td class='num' style='color:{c};font-weight:700'>{fmt_pct(ret)}{tag}</td></tr>"
        )
    return (
        "<table class='log'><thead><tr>"
        "<th>Bought (1st of month)</th><th class='center'>Rank</th><th class='num'>Entry</th>"
        "<th>Sold / rolled</th><th class='num'>Exit</th><th class='num'>1-mo return</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )


def campaign_html(d):
    cfg = d["cfg"]
    segs = d["segments"]
    total_months = sum(s["months"] for s in segs)
    hero_seg = max(segs, key=lambda s: s["ret"])   # headline = best segment

    tiles = []
    tiles.append(tile("First bought", segs[0]["entry_date"].strftime("%b %-d, %Y"),
                      fmt_price(segs[0]["entry_price"])))
    last = segs[-1]
    if last["is_open"]:
        tiles.append(tile("Currently holding", fmt_price(last["exit_price"]),
                          "since " + last["entry_date"].strftime("%b %Y"), GOLD))
    else:
        tiles.append(tile("Last sold", last["exit_date"].strftime("%b %-d, %Y"),
                          fmt_price(last["exit_price"])))
    tiles.append(tile("Months held", str(total_months),
                      f"{len(segs)} hold" + ("s" if len(segs) > 1 else "")))
    tiles.append(tile("Best hold return", fmt_pct(hero_seg["ret"]),
                      hero_seg["entry_date"].strftime("%b") + " → "
                      + hero_seg["exit_date"].strftime("%b %Y"),
                      GREEN if hero_seg["ret"] >= 0 else RED))
    tiles.append(tile("Buy &amp; hold (same span)", fmt_pct(d["buyhold"]),
                      d["span_start"].strftime("%b %Y") + " → "
                      + d["span_end"].strftime("%b %Y"),
                      GREEN if d["buyhold"] >= 0 else RED))

    # per-segment narrative + trade tables
    blocks = []
    for i, s in enumerate(segs):
        label = (f"Hold {i+1}: {s['entry_date'].strftime('%b %Y')} → "
                 + ("present (open)" if s["is_open"]
                    else s["exit_date"].strftime("%b %Y")))
        ret_c = GREEN if s["ret"] >= 0 else RED
        badge = (f"<span class='seg-ret' style='color:{ret_c}'>{fmt_pct(s['ret'])}"
                 f" over {s['months']} month" + ("s" if s["months"] > 1 else "") + "</span>")
        blocks.append(f"<div class='seg'><div class='seg-head'>{label} {badge}</div>"
                      + trade_table(s["rows"]) + "</div>")

    return f"""
    <section class="case">
      <div class="case-head">
        <div class="tk">{cfg['ticker']}</div>
        <div>
          <h2>{cfg['name']}</h2>
          <p class="sub">{cfg['subtitle']}</p>
        </div>
      </div>
      <div class="tiles">{''.join(tiles)}</div>
      <img class="chart" alt="{cfg['ticker']} price with buy/sell markers"
           src="data:image/png;base64,{d['img']}" />
      <div class="legend">
        <span><i class="sw buy"></i> Bought (entered basket)</span>
        <span><i class="sw star">★</i> Re-picked that month</span>
        <span><i class="sw sell"></i> Sold (left basket)</span>
        <span><i class="sw hold"></i> Still holding</span>
        <span><i class="sw band"></i> Strategy held here</span>
      </div>
      {''.join(blocks)}
    </section>
    """


def build_html(cards):
    gen = TODAY.strftime("%B %-d, %Y")
    css = """
    :root{--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--bg:#f8fafc;--accent:#1f4e79;}
    *{box-sizing:border-box;} body{margin:0;background:var(--bg);color:var(--ink);
      font-family:'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.5;}
    .wrap{max-width:960px;margin:0 auto;padding:40px 22px 64px;}
    header.top h1{font-size:30px;font-weight:800;letter-spacing:-.02em;margin:0 0 6px;}
    header.top p{color:var(--muted);margin:0;font-size:15px;}
    .note{margin:18px 0 30px;padding:12px 15px;border:1px solid var(--line);border-radius:10px;
      background:#fff;color:#475569;font-size:13px;}
    .case{background:#fff;border:1px solid var(--line);border-radius:16px;padding:24px;margin:26px 0;
      box-shadow:0 1px 2px rgba(15,23,42,.04);}
    .case-head{display:flex;gap:16px;align-items:center;margin-bottom:18px;}
    .tk{font-size:15px;font-weight:800;color:#fff;background:var(--accent);border-radius:10px;
      padding:10px 12px;letter-spacing:.03em;}
    .case-head h2{margin:0;font-size:21px;font-weight:800;}
    .case-head .sub{margin:2px 0 0;color:var(--muted);font-size:13.5px;}
    .tiles{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:18px;}
    .tile{border:1px solid var(--line);border-radius:12px;padding:12px 13px;background:#fbfdff;}
    .tile-label{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);}
    .tile-val{font-size:19px;font-weight:800;margin-top:4px;}
    .tile-sub{font-size:11px;color:var(--muted);margin-top:2px;}
    img.chart{width:100%;height:auto;border:1px solid var(--line);border-radius:12px;margin:4px 0 10px;}
    .legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:#475569;margin:6px 2px 18px;}
    .legend .sw{display:inline-block;width:12px;height:12px;margin-right:5px;vertical-align:-1px;border-radius:3px;}
    .sw.buy{background:#2e7d32;} .sw.sell{background:#c62828;} .sw.hold{background:#e8a300;border-radius:50%;}
    .sw.band{background:rgba(46,125,50,.18);} .sw.star{background:none;color:#e8a300;width:auto;}
    .seg{margin-top:14px;} .seg-head{font-size:13.5px;font-weight:700;margin-bottom:8px;}
    .seg-ret{font-weight:800;margin-left:6px;}
    table.log{width:100%;border-collapse:collapse;font-size:12.5px;}
    table.log th{background:var(--accent);color:#fff;text-align:left;padding:7px 9px;font-weight:600;}
    table.log th.num,table.log td.num{text-align:right;} table.log th.center,table.log td.center{text-align:center;}
    table.log td{padding:7px 9px;border-bottom:1px solid var(--line);}
    table.log tbody tr:nth-child(even){background:#f6f9fc;}
    .open-tag{font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:#8a6d00;
      background:#fff7e6;border:1px solid #f2d38a;border-radius:4px;padding:1px 4px;margin-left:4px;}
    footer{color:var(--muted);font-size:12px;margin-top:30px;border-top:1px solid var(--line);padding-top:16px;}
    @media(max-width:720px){.tiles{grid-template-columns:repeat(2,1fr);}
      table.log{display:block;overflow-x:auto;white-space:nowrap;}}
    """
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Momentum Strategy · Rebalance Case Studies</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{css}</style></head>
<body><div class="wrap">
  <header class="top">
    <h1>Strategy in Action — Rebalance Case Studies</h1>
    <p>How the Nasdaq-100 6-month momentum rotation actually traded some of its biggest winners
       across 2020–2026 — month by month, with the whipsaws too.</p>
  </header>
  <div class="note">
    Each case study follows one stock through the strategy's <b>monthly top-3 rebalances</b>: it enters on the
    first trading day of a month, is re-scored and rolled each month it stays in the top 3, and is sold the month
    it drops out. Returns are the strategy's realized entry→exit prices (gross of costs). Prices are adjusted
    daily closes. Illustrative single-name walk-throughs, not the full portfolio — generated {gen}.
  </div>
  {''.join(cards)}
  <footer>
    Nasdaq-100 6-month momentum rotation · point-in-time membership · data: Yahoo Finance (adjusted close).
    Past performance of a backtest does not indicate future results.
  </footer>
</div></body></html>"""


def main():
    picks = load_trades()
    cards = [campaign_html(campaign_data(c, picks)) for c in CAMPAIGNS]
    with open(OUT_HTML, "w") as f:
        f.write(build_html(cards))
    print("Wrote", OUT_HTML)


if __name__ == "__main__":
    main()
