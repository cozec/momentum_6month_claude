"""Generate a detailed MU (Micron Technology) PDF report.

Combines:
  * Quarterly revenue history since FY2021 (sourced from Micron press releases /
    stockanalysis.com / the referenced Yahoo Finance article).
  * MU's price path from the project's own price dataset.
  * Every time MU appeared in our 6-month momentum top-3 picks, with the
    momentum score and realized one-month forward return at each appearance.

Output: outputs/MU_report.pdf
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
PRICE_CSV = os.path.join(ROOT, "data", "raw_prices", "MU.csv")
PICKS_CSV = os.path.join(ROOT, "outputs", "monthly_selections.csv")
OPEN_CSV = os.path.join(ROOT, "outputs", "open_rebalance_picks.csv")
OUT_PDF = os.path.join(ROOT, "outputs", "MU_report.pdf")

# Report focuses on the 2024-to-present AI/HBM super-cycle window.
START = "2024-01-01"

ACCENT = "#1f4e79"
GREEN = "#2e7d32"
RED = "#c62828"
GREY = "#666666"

# ---------------------------------------------------------------------------
# Quarterly revenue ($B). Fiscal quarters (Micron FY ends late Aug/early Sep).
# Sources: Micron 8-K press releases (SEC EDGAR), stockanalysis.com quarterly
# financials, and the referenced Yahoo Finance article (Q3 FY2026).
# ---------------------------------------------------------------------------
REVENUE = [
    ("Q1'21", "2020-12-03", 5.77, None),
    ("Q2'21", "2021-03-04", 6.24, None),
    ("Q3'21", "2021-06-03", 7.42, None),
    ("Q4'21", "2021-09-02", 8.27, 36.6),
    ("Q1'22", "2021-12-02", 7.69, 33.2),
    ("Q2'22", "2022-03-03", 7.79, 24.9),
    ("Q3'22", "2022-06-02", 8.64, 16.4),
    ("Q4'22", "2022-09-01", 6.64, -19.7),
    ("Q1'23", "2022-12-01", 4.09, -46.9),
    ("Q2'23", "2023-03-02", 3.69, -52.6),
    ("Q3'23", "2023-06-01", 3.75, -56.6),
    ("Q4'23", "2023-08-31", 4.01, -39.6),
    ("Q1'24", "2023-11-30", 4.73, 15.7),
    ("Q2'24", "2024-02-29", 5.82, 57.7),
    ("Q3'24", "2024-05-30", 6.81, 81.5),
    ("Q4'24", "2024-08-29", 7.75, 93.3),
    ("Q1'25", "2024-11-28", 8.71, 84.3),
    ("Q2'25", "2025-02-27", 8.05, 38.3),
    ("Q3'25", "2025-05-29", 9.30, 36.6),
    ("Q4'25", "2025-08-28", 11.32, 46.0),
    ("Q1'26", "2025-11-27", 13.64, 56.7),
    ("Q2'26", "2026-02-26", 23.86, 196.3),
    ("Q3'26", "2026-05-28", 41.46, 345.7),
]
REV_DF = pd.DataFrame(REVENUE, columns=["fq", "end", "rev", "yoy"])
REV_DF["end"] = pd.to_datetime(REV_DF["end"])
# Quarters whose period end falls in the 2024-present window.
REV_WIN = REV_DF[REV_DF["end"] >= START].reset_index(drop=True)


def load_data():
    px = pd.read_csv(PRICE_CSV, parse_dates=["Date"]).sort_values("Date")
    picks = pd.read_csv(PICKS_CSV, parse_dates=["rebalance_date", "exit_date"])
    mu = picks[(picks["ticker"] == "MU") &
               (picks["rebalance_date"] >= START)].copy()
    mu["is_open"] = False

    # Append the current open (uncompleted) rebalance if MU is a live pick.
    if os.path.exists(OPEN_CSV):
        op = pd.read_csv(OPEN_CSV, parse_dates=["rebalance_date", "exit_date"])
        op = op[(op["ticker"] == "MU") & (op["rebalance_date"] >= START)].copy()
        if not op.empty:
            op["is_open"] = True
            mu = pd.concat([mu, op[mu.columns]], ignore_index=True)

    mu = mu.sort_values("rebalance_date").reset_index(drop=True)
    return px, mu


def fmt_pct(x):
    return f"{x*100:+.1f}%"


# ---------------------------------------------------------------------------
# Page 1 — title + key facts + revenue table
# ---------------------------------------------------------------------------
def page_title(pdf, px, mu):
    last = px.iloc[-1]
    p2024 = px[px["Date"] >= START].iloc[0]
    chg_since_24 = last["Close"] / p2024["Close"] - 1
    first_pick = mu["rebalance_date"].min().date()
    last_pick = mu["rebalance_date"].max().date()
    avg_score = mu["momentum_score"].mean()
    hit = (mu["stock_return"] > 0).mean()

    fig = plt.figure(figsize=(11, 8.5))
    fig.suptitle("")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")

    ax.text(0.5, 0.94, "Micron Technology (MU)", ha="center", fontsize=26,
            fontweight="bold", color=ACCENT)
    ax.text(0.5, 0.895, "Momentum-Strategy Deep Dive  ·  2024-to-Present AI/HBM Super-Cycle",
            ha="center", fontsize=12.5, color=GREY)
    ax.text(0.5, 0.862, "Generated 2026-06-24  ·  Nasdaq-100 6-month momentum rotation backtest",
            ha="center", fontsize=9, color=GREY, style="italic")

    # Key-fact boxes
    facts = [
        (f"${last['Close']:,.0f}", f"Last close ({last['Date'].date()})"),
        (fmt_pct(chg_since_24), "Price change since Jan-2024"),
        (f"{len(mu)}", "Top-3 picks since 2024"),
        ("$41.46B", "Latest qtr revenue (Q3 FY26)"),
        ("+345.7%", "Revenue YoY (Q3 FY26)"),
        (f"{avg_score:.3f}", "Avg momentum score (picks)"),
    ]
    x0, y0, w, h = 0.06, 0.70, 0.288, 0.085
    for i, (big, small) in enumerate(facts):
        cx = x0 + (i % 3) * 0.31
        cy = y0 - (i // 3) * 0.115
        ax.add_patch(plt.Rectangle((cx, cy), w, h, transform=ax.transAxes,
                                   facecolor="#eef3f8", edgecolor=ACCENT, lw=1.2))
        ax.text(cx + w / 2, cy + h * 0.60, big, ha="center", va="center",
                fontsize=17, fontweight="bold", color=ACCENT)
        ax.text(cx + w / 2, cy + h * 0.22, small, ha="center", va="center",
                fontsize=8.5, color=GREY)

    # Narrative (escape $ so matplotlib does not parse it as math)
    txt = (
        "This report zooms in on Micron's 2024-to-present run — the AI/HBM super-cycle. Entering\n"
        f"2024 near \\${p2024['Close']:,.0f}, MU rode surging high-bandwidth-memory demand for AI accelerators:\n"
        "quarterly revenue climbed from \\$5.82B (Q2 FY24) to \\$41.46B (Q3 FY26) — +345.7% YoY in\n"
        "the latest print, beating estimates by 14% with adjusted EPS of \\$25.11. Management guided\n"
        f"next-quarter revenue to ~\\$50B and the stock last closed at \\${last['Close']:,.0f} (+{chg_since_24*100:.0f}% since Jan-2024).\n"
        f"Across this window MU hit our 6-month momentum top-3 {len(mu)} times — a brief 2024 cameo, then\n"
        "persistently from late 2025 at its highest-ever scores, including the current June 2026 basket (#2, open)."
    )
    fig.text(0.06, 0.515, "Overview", fontsize=13, fontweight="bold", color=ACCENT)
    ax.text(0.06, 0.49, txt, ha="left", va="top", fontsize=9.2, color="#222222",
            linespacing=1.28)

    # Revenue table (2024-present quarters, compact two-column layout)
    fig.text(0.06, 0.335, "Quarterly Revenue, 2024 – Present  (\\$ billions, fiscal quarters)",
             fontsize=13, fontweight="bold", color=ACCENT)
    half = (len(REV_WIN) + 1) // 2
    left = REV_WIN.iloc[:half].reset_index(drop=True)
    right = REV_WIN.iloc[half:].reset_index(drop=True)

    def block(df, x):
        rows = [["Fiscal Q", "Period end", "Rev $B", "YoY"]]
        for _, r in df.iterrows():
            yoy = "" if pd.isna(r["yoy"]) else f"{r['yoy']:+.1f}%"
            rows.append([r["fq"], r["end"].strftime("%b-%Y"), f"{r['rev']:.2f}", yoy])
        tb = ax.table(cellText=rows[1:], colLabels=rows[0],
                      bbox=[x, 0.04, 0.40, 0.27])
        tb.auto_set_font_size(False)
        tb.set_fontsize(8.2)
        for (ri, ci), cell in tb.get_celld().items():
            cell.set_edgecolor("#cccccc")
            if ri == 0:
                cell.set_facecolor(ACCENT)
                cell.set_text_props(color="white", fontweight="bold")
            elif ri % 2 == 0:
                cell.set_facecolor("#f4f7fb")
        return tb

    block(left, 0.06)
    block(right, 0.54)
    pdf.savefig(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 2 — revenue bar chart + YoY line
# ---------------------------------------------------------------------------
def page_revenue(pdf):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8.5),
                                   gridspec_kw={"height_ratios": [3, 2]})
    fig.suptitle("Micron Quarterly Revenue & Growth (2024 – Q3 FY2026)",
                 fontsize=16, fontweight="bold", color=ACCENT, y=0.97)

    x = np.arange(len(REV_WIN))
    colors = [RED if r < 5 else (ACCENT if r < 15 else GREEN) for r in REV_WIN["rev"]]
    ax1.bar(x, REV_WIN["rev"], color=colors)
    for xi, r in zip(x, REV_WIN["rev"]):
        ax1.text(xi, r + 0.5, f"{r:.1f}", ha="center", fontsize=7.5, color="#333")
    ax1.set_xticks(x)
    ax1.set_xticklabels(REV_WIN["fq"], rotation=45, fontsize=8)
    ax1.set_ylabel("Revenue ($B)")
    ax1.set_title("AI/HBM super-cycle: revenue up ~7x in nine fiscal quarters",
                  fontsize=10, color=GREY)
    ax1.grid(axis="y", alpha=0.3)
    peak_i = int(REV_WIN["rev"].idxmax())
    ax1.annotate("$41.46B\n+346% YoY", xy=(peak_i, 41.46), xytext=(peak_i - 4.5, 33),
                 fontsize=8.5, color=GREEN, fontweight="bold",
                 arrowprops=dict(arrowstyle="->", color=GREEN))

    yoy = REV_WIN.dropna(subset=["yoy"])
    xy = np.arange(len(REV_WIN))[REV_WIN["yoy"].notna().values]
    ax2.plot(xy, yoy["yoy"], marker="o", color=ACCENT, lw=1.6)
    ax2.axhline(0, color=GREY, lw=0.8)
    ax2.fill_between(xy, yoy["yoy"], 0, where=(yoy["yoy"] >= 0), color=GREEN, alpha=0.15)
    ax2.fill_between(xy, yoy["yoy"], 0, where=(yoy["yoy"] < 0), color=RED, alpha=0.15)
    ax2.set_xticks(xy)
    ax2.set_xticklabels(yoy["fq"], rotation=45, fontsize=8)
    ax2.set_ylabel("YoY revenue growth")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax2.grid(axis="y", alpha=0.3)

    fig.text(0.5, 0.02,
             "Sources: Micron 8-K press releases (SEC EDGAR) · stockanalysis.com · "
             "Yahoo Finance (Q3 FY2026 article).",
             ha="center", fontsize=7.5, color=GREY, style="italic")
    fig.tight_layout(rect=[0, 0.04, 1, 0.94])
    pdf.savefig(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 3 — price chart with pick markers
# ---------------------------------------------------------------------------
GOLD = "#e8a300"


def _close_on(px, date):
    """First available close on or after `date` → (timestamp, price)."""
    row = px[px["Date"] >= date].iloc[0]
    return row["Date"], row["Close"]


def _price_panel(ax, px, mu, start, title, minor_months, major="year",
                 trade=None):
    p = px[px["Date"] >= start]
    ax.plot(p["Date"], p["Close"], color=ACCENT, lw=1.3, label="MU close")
    ax.set_yscale("log")
    ax.set_ylabel("Close (log scale, $)")
    ax.set_title(title, fontsize=11, color=GREY)

    # Golden star on the price whenever MU was in our top-3 that month.
    picks = mu[mu["rebalance_date"] >= start]
    done = picks[~picks["is_open"]]
    live = picks[picks["is_open"]]
    ax.scatter(done["rebalance_date"], done["entry_price"], marker="*", s=300,
               color=GOLD, zorder=6, edgecolor="#7a5800", linewidth=0.6,
               label="MU in top-3")
    if not live.empty:
        ax.scatter(live["rebalance_date"], live["entry_price"], marker="*", s=420,
                   color=GOLD, zorder=7, edgecolor=RED, linewidth=1.6,
                   label="MU in top-3 (open / current)")
    for _, r in picks.iterrows():
        lbl = f"#{int(r['rank'])}" + (" open" if r["is_open"] else "")
        ax.annotate(lbl, (r["rebalance_date"], r["entry_price"]),
                    textcoords="offset points", xytext=(0, 13), ha="center",
                    fontsize=7, color=(RED if r["is_open"] else "#333"))

    # Entry / exit annotation for a held trade over this time frame.
    if trade is not None:
        ed, ep = _close_on(px, trade[0])
        xd, xp = _close_on(px, trade[1])
        gain = xp / ep - 1
        box = dict(boxstyle="round,pad=0.4", fc="white", ec=ACCENT, lw=1.2)
        arr = dict(arrowstyle="->", color=ACCENT, lw=1.4)
        ax.annotate(f"Entry  {ed.strftime('%b %-d, %Y')}\n${ep:,.0f}",
                    xy=(ed, ep), xytext=(-4, -68), textcoords="offset points",
                    ha="center", fontsize=8.5, color=ACCENT, fontweight="bold",
                    bbox=box, arrowprops=arr)
        ax.annotate(f"Exit  {xd.strftime('%b %-d, %Y')}\n${xp:,.0f}",
                    xy=(xd, xp), xytext=(-70, 18), textcoords="offset points",
                    ha="center", fontsize=8.5, color=ACCENT, fontweight="bold",
                    bbox=box, arrowprops=arr)
        ax.text(0.015, 0.95,
                f"Hold {ed.strftime('%b %Y')} → {xd.strftime('%b %Y')}:  "
                f"total gain {gain*100:+.0f}%  (${ep:,.0f} → ${xp:,.0f})",
                transform=ax.transAxes, ha="left", va="top", fontsize=10.5,
                fontweight="bold", color=GREEN,
                bbox=dict(boxstyle="round,pad=0.45", fc="#eaf5ea", ec=GREEN, lw=1.2))

    if major == "month":
        ax.xaxis.set_major_locator(mdates.MonthLocator(minor_months))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    else:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.xaxis.set_minor_locator(mdates.MonthLocator(minor_months))
    ax.grid(alpha=0.3, which="both")
    loc = "lower right" if trade is not None else "upper left"
    ax.legend(loc=loc, fontsize=9)


def page_price(pdf, px, mu):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8.5))
    fig.suptitle("MU Price & Strategy Top-3 Pick Timing",
                 fontsize=16, fontweight="bold", color=ACCENT, y=0.97)

    _price_panel(ax1, px, mu, START, "Full window: 2024 – present", (1, 7))
    _price_panel(ax2, px, mu, "2025-09-01", "Zoom: Sep 2025 – present",
                 range(1, 13), major="month",
                 trade=("2025-11-01", "2026-05-01"))

    fig.text(0.99, 0.01,
             "Gold star = month MU entered our top-3 momentum basket; label = rank that month.",
             ha="right", fontsize=8, color=GREY, style="italic")
    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    pdf.savefig(fig)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Page 4 — momentum score over time + picks table
# ---------------------------------------------------------------------------
def page_picks(pdf, mu):
    fig = plt.figure(figsize=(11, 8.5))
    fig.suptitle("MU as a Momentum Pick — Score History & Trade Log",
                 fontsize=16, fontweight="bold", color=ACCENT, y=0.97)

    ax = fig.add_axes([0.08, 0.62, 0.86, 0.28])
    colors = [GOLD if o else (GREEN if r > 0 else RED)
              for r, o in zip(mu["stock_return"], mu["is_open"])]
    ax.bar(mu["rebalance_date"], mu["momentum_score"], width=20, color=colors)
    ax.set_ylabel("Momentum score\n(6m avg monthly return)")
    ax.set_title("Bar height = momentum score at selection · color = realized next-month return "
                 "(green up / red down · gold = open)", fontsize=9.5, color=GREY)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(mu["momentum_score"].mean(), color=GREY, ls="--", lw=1,
               label=f"mean {mu['momentum_score'].mean():.3f}")
    ax.legend(fontsize=8, loc="upper left")

    # Trade-log table
    ax2 = fig.add_axes([0.04, 0.03, 0.92, 0.52])
    ax2.axis("off")
    rows = [["Rebalance", "Rank", "Mom. score", "Entry $", "Exit $", "1-mo return"]]
    for _, r in mu.iterrows():
        open_pick = bool(r["is_open"])
        rebal = r["rebalance_date"].strftime("%Y-%m-%d") + (" (open)" if open_pick else "")
        ret = fmt_pct(r["stock_return"]) + (" MTD" if open_pick else "")
        rows.append([
            rebal,
            f"{int(r['rank'])}",
            f"{r['momentum_score']:.4f}",
            f"{r['entry_price']:,.2f}",
            f"{r['exit_price']:,.2f}",
            ret,
        ])
    tb = ax2.table(cellText=rows[1:], colLabels=rows[0], cellLoc="center",
                   bbox=[0, 0, 1, 1])
    tb.auto_set_font_size(False)
    tb.set_fontsize(8.0)
    for (ri, ci), cell in tb.get_celld().items():
        cell.set_edgecolor("#cccccc")
        if ri == 0:
            cell.set_facecolor(ACCENT)
            cell.set_text_props(color="white", fontweight="bold")
            continue
        row = mu.iloc[ri - 1]
        if row["is_open"]:
            cell.set_facecolor("#fff6e0")
        elif ri % 2 == 0:
            cell.set_facecolor("#f4f7fb")
        if ci == 5:  # return column color
            val = row["stock_return"]
            cell.set_text_props(color=GREEN if val > 0 else RED, fontweight="bold")
    pdf.savefig(fig)
    plt.close(fig)


def main():
    px, mu = load_data()
    with PdfPages(OUT_PDF) as pdf:
        page_title(pdf, px, mu)
        page_revenue(pdf)
        page_price(pdf, px, mu)
        page_picks(pdf, mu)
    done = mu[~mu["is_open"]]
    print(f"Wrote {OUT_PDF}")
    print(f"MU appeared in top-3 picks {len(mu)} times "
          f"({int(mu['is_open'].sum())} open); "
          f"avg momentum score {mu['momentum_score'].mean():.4f}; "
          f"hit rate {(done['stock_return']>0).mean()*100:.0f}% on {len(done)} completed")


if __name__ == "__main__":
    main()
