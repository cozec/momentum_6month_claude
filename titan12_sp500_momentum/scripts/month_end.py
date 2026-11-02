"""Month-end automation: refresh, rebuild report.html, publish, email the trades.

Borrowed from the sister Nasdaq project's month-end workflow, but run locally
by launchd (``scripts/com.adam.titan12.monthend.plist``) instead of GitHub
Actions, because the price cache is not in git and the S&P 500 overlap
exclusion needs the sister dashboard's live ``/api/picks`` on port 8765.

launchd starts it daily at 4:30 pm Pacific, after the sister's own month-end
workflow (22:30 UTC = 2:30 pm PST / 3:30 pm PDT) has run. It does real work only from the close of the
month's last NYSE trading day until the next rebalance (so a run missed while
the Mac slept fires on wake), and only once per lock date. It then:

  1. starts the sister dashboard if it is down and refreshes its prices,
  2. re-runs the S&P 500 backtest through today (prices topped up),
  3. rebuilds ``report.html``, commits it and pushes (GitHub Pages redeploys),
  4. emails the trades (sell / buy / keep) with a link to the report.

Usage::

    .venv/bin/python scripts/month_end.py                 # scheduled run
    .venv/bin/python scripts/month_end.py --dry-run --force
    .venv/bin/python scripts/month_end.py --force --skip-refresh --no-publish

Env vars (read from the untracked ``.env`` at the project root if present):
  RESEND_API_KEY  required to send — https://resend.com
  EMAIL_FROM      required to send — Resend-verified sender
  EMAIL_TO        required to send — comma-separated recipient(s)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.nyse_calendar import NYSE_SESSION  # noqa: E402

PYTHON = sys.executable
SISTER_ROOT = Path("/Users/adam/project/momentum_6m_claude/nasdaq100_momentum_backtest")
SISTER_PYTHON = SISTER_ROOT.parent / ".venv" / "bin" / "python"
SISTER_URL = "http://127.0.0.1:8765"
REPORT_PATH = PROJECT_ROOT / "report.html"
REPORT_URL = "https://cozec.github.io/titan_12_sp500_momentum/report.html"
STATE_PATH = PROJECT_ROOT / "logs" / "month_end_state.json"
PREVIEW_PATH = PROJECT_ROOT / "logs" / "month_end_email.html"
NEW_YORK = ZoneInfo("America/New_York")


def log(message: str) -> None:
    """Print a timestamped progress line (launchd captures stdout)."""

    print(f"{datetime.now(NEW_YORK):%Y-%m-%d %H:%M:%S %Z} {message}", flush=True)


def load_env(path: Path = PROJECT_ROOT / ".env") -> None:
    """Load ``KEY=VALUE`` lines from ``path`` into ``os.environ`` if unset."""

    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def lock_date(today: pd.Timestamp) -> pd.Timestamp:
    """Return the close that locks the next rebalance after ``today``.

    That is the last NYSE session before the first session of the next
    rebalance month. On days of a new month before its first session (e.g. a
    weekend 1st), the pending rebalance is this month's, so its lock is the
    prior month's last session.
    """

    today = pd.Timestamp(today).normalize()
    entry = pd.Timestamp(today.replace(day=1)) - pd.Timedelta(days=1) + NYSE_SESSION
    if today >= entry:
        entry = today + pd.offsets.MonthBegin(1) - pd.Timedelta(days=1) + NYSE_SESSION
    return entry - NYSE_SESSION


def in_window(today: pd.Timestamp) -> bool:
    """True from the locking close until the next rebalance session."""

    return pd.Timestamp(today).normalize() >= lock_date(today)


def read_state() -> dict[str, str]:
    """Return the last-sent state, or an empty dict."""

    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return {}


def http_get_json(url: str, timeout: float) -> dict[str, object]:
    """GET ``url`` and decode its JSON body."""

    req = urllib.request.Request(url, headers={"User-Agent": "titan12-month-end/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def ensure_sister() -> None:
    """Start the sister dashboard on port 8765 if it is not answering."""

    try:
        http_get_json(f"{SISTER_URL}/health", timeout=5)
        return
    except (urllib.error.URLError, OSError, ValueError):
        pass
    log("Sister dashboard down; starting it.")
    with open(SISTER_ROOT / "logs" / "webapp.month_end.log", "a") as out:
        subprocess.Popen(  # noqa: S603 - fixed local command
            [str(SISTER_PYTHON), "run_webapp.py"],
            cwd=SISTER_ROOT, stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
        )
    for _ in range(60):
        time.sleep(2)
        try:
            http_get_json(f"{SISTER_URL}/health", timeout=5)
            return
        except (urllib.error.URLError, OSError, ValueError):
            continue
    raise RuntimeError("sister dashboard did not start")


def sister_picks(refresh: bool = False) -> dict[str, object]:
    """Fetch the sister's baskets, which also warms its 5-minute cache.

    The S&P backtest reads ``/api/picks`` with a 4 s timeout, shorter than an
    uncached sister compute, so callers warm it right before the backtest.
    """

    qs = "?refresh=true" if refresh else ""
    return http_get_json(f"{SISTER_URL}/api/picks{qs}", timeout=900)


def run(cmd: list[str]) -> None:
    """Run ``cmd`` in the project root, raising on failure."""

    log("$ " + " ".join(cmd))
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)  # noqa: S603


def refresh_outputs(end_date: str) -> None:
    """Refresh sister + own prices and re-run the S&P 500 backtest."""

    ensure_sister()
    sister_picks(refresh=True)
    backtest = [PYTHON, "main.py", "--end-date", end_date]
    # First pass tops up ~700 price files, which can outlast the sister cache;
    # the second pass reuses the prices with the sister cache freshly warm.
    run(backtest)
    sister_picks()
    run(backtest)


def check_overlap(payload: dict[str, object]) -> None:
    """Fail if the next basket shares a ticker with the sister's next basket."""

    sister_next = {p["ticker"] for p in sister_picks().get("next") or []}
    ours = {p["ticker"] for p in payload["next"]["picks"]}
    if sister_next & ours:
        raise RuntimeError(f"next picks overlap the sister basket: {sorted(sister_next & ours)}")


def publish(today: str) -> None:
    """Commit ``report.html`` (only that path) and push to origin."""

    if subprocess.run(["git", "diff", "--quiet", "--", "report.html"], cwd=PROJECT_ROOT).returncode:
        run(["git", "commit", "-m", f"Month-end report snapshot {today}", "--", "report.html"])
    run(["git", "push", "origin", "HEAD:main"])


def trades(held: list[str], nxt: list[str]) -> dict[str, list[str]]:
    """Sell / buy / keep lists moving from the held basket to the next picks."""

    return {
        "sell": [t for t in held if t not in nxt],
        "buy": [t for t in nxt if t not in held],
        "keep": [t for t in nxt if t in held],
    }


def _pct(x: object) -> str:
    """Format a fraction as a signed percentage; "—" when missing."""

    return "—" if x is None else f"{float(x) * 100:+.1f}%"


def _price(x: object) -> str:
    """Format a price as ``$1,234.56``; "—" when missing."""

    return "—" if x is None else f"${float(x):,.2f}"


_TD = "padding:6px 12px;"
_TH = ("padding:8px 12px;text-align:left;font-size:11px;color:#64748B;"
       "text-transform:uppercase;letter-spacing:.05em")


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """A small bordered HTML table."""

    head = "".join(f'<th style="{_TH}">{h}</th>' for h in headers)
    body = "".join(
        "<tr>" + "".join(f'<td style="{_TD}">{c}</td>' for c in row) + "</tr>" for row in rows
    )
    return (
        '<table cellspacing="0" cellpadding="0" style="width:100%;border:1px solid #E2E8F0;'
        'border-radius:8px;border-collapse:separate;border-spacing:0;overflow:hidden">'
        f'<thead><tr style="background:#F8FAFC">{head}</tr></thead><tbody>{body}</tbody></table>'
    )


def _chips(names: list[str], color: str) -> str:
    """Ticker pills, or a dash when empty."""

    return " ".join(
        f'<span style="display:inline-block;padding:2px 8px;border-radius:9999px;'
        f'background:{color};color:white;font-weight:700;font-size:13px">{n}</span>'
        for n in names
    ) or '<span style="color:#94A3B8">—</span>'


def build_email(payload: dict[str, object], test: bool = False) -> dict[str, str]:
    """Subject, HTML and text bodies for the month-end trade email.

    Args:
        payload: S&P 500 dashboard payload from ``build_dashboard_payload``.
        test: Prefix the subject with ``[TEST]``.
    """

    held_rows = payload["nasdaq_overlay"]["adjusted"]
    nxt = payload["next"]
    held = [p["ticker"] for p in held_rows]
    t = trades(held, [p["ticker"] for p in nxt["picks"]])
    entry = nxt["date"] or "—"
    line = "; ".join(f"{k} {', '.join(v)}" for k, v in t.items() if v) or "no change"
    subject = f"{'[TEST] ' if test else ''}Titan-12 S&P 500 trades for {entry} — {line}"
    rets = [p["stock_return"] for p in held_rows if p.get("stock_return") is not None]
    mtd = sum(rets) / len(rets) if rets else None
    stats = payload["stats"]
    excluded = ", ".join(nxt.get("excluded") or []) or "—"

    trade_rows = [
        ["<b>Sell</b>", _chips(t["sell"], "#B91C1C")],
        ["<b>Buy</b>", _chips(t["buy"], "#047857")],
        ["<b>Keep</b>", _chips(t["keep"], "#475569")],
    ]
    next_rows = [
        [f"#{p['rank']}", f"<b>{p['ticker']}</b>", p.get("sector", ""),
         f"{p['score']:.2f}" if p.get("score") is not None else "—",
         _price(p.get("entry_price_estimate"))]
        for p in nxt["picks"]
    ]
    open_rows = [[f"<b>{p['ticker']}</b>", _pct(p.get("stock_return"))] for p in held_rows]
    html = f"""<!doctype html>
<html><body style="font-family:'Inter',system-ui,sans-serif;background:#F8FAFC;color:#0F172A;margin:0;padding:24px">
<div style="max-width:680px;margin:0 auto;background:white;border:1px solid #E2E8F0;border-radius:12px;padding:24px">
  <div style="font-size:22px;font-weight:800;margin-bottom:4px">Titan-12 S&amp;P 500 · next month's trades</div>
  <div style="font-size:13px;color:#475569;margin-bottom:24px">
    Rebalance at the <b>open</b> on <b>{entry}</b> (the first trading day) to match the backtest's fill.
    Signal locked {nxt['as_of'] or '—'}.<br>
    Full report: <a href="{REPORT_URL}" style="font-weight:600">{REPORT_URL}</a>
  </div>
  {_table(["Action", "Tickers"], trade_rows)}
  <div style="font-size:13px;font-weight:600;margin:16px 0 6px">Next picks (equal weight, ⅓ each)</div>
  {_table(["Rank", "Ticker", "Sector", "Score", "Last close"], next_rows) if next_rows else '<i style="color:#64748B">Not locked yet.</i>'}
  <div style="font-size:12px;color:#64748B;margin-top:6px">Excluded sister Nasdaq next picks: {excluded}</div>
  <div style="font-size:13px;font-weight:600;margin:16px 0 6px">
    Current holdings · entry {payload['open']['date'] or '—'} · month to date {_pct(mtd)}
  </div>
  {_table(["Ticker", "Return"], open_rows) if open_rows else '<i style="color:#64748B">None.</i>'}
  <div style="margin-top:10px;font-size:12px;color:#475569">
    Backtest: CAGR <b>{_pct(stats['cagr'])}</b> · Sharpe <b>{stats['sharpe']:.2f}</b>
    · Max DD <b>{_pct(stats['max_drawdown'])}</b>
  </div>
  <div style="margin-top:24px;padding-top:16px;border-top:1px solid #E2E8F0;font-size:11px;color:#94A3B8">
    {payload['bias_warning']} Not investment advice.
  </div>
</div></body></html>"""

    lines = [f"Titan-12 S&P 500 trades for {entry} (rebalance at the open)", "", f"  {line}"]
    for p in nxt["picks"]:
        lines.append(f"  next #{p['rank']} {p['ticker']:<6} last close {_price(p.get('entry_price_estimate'))}")
    lines += [f"  excluded sister Nasdaq picks: {excluded}",
              f"  current holdings month to date: {_pct(mtd)}", "", f"Full report: {REPORT_URL}"]
    return {"subject": subject, "html": html, "text": "\n".join(lines)}


def send_via_resend(email: dict[str, str]) -> dict[str, object]:
    """POST the email to Resend and return its JSON response."""

    body = json.dumps({
        "from": os.environ["EMAIL_FROM"],
        "to": [t.strip() for t in os.environ["EMAIL_TO"].split(",") if t.strip()],
        **email,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            # Cloudflare in front of Resend rejects the default urllib UA (1010).
            "User-Agent": "titan12-month-end/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Resend error {exc.code}: {exc.read().decode()}") from exc


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true",
                        help="Run outside the month-end window and ignore the sent state.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Rebuild report.html and write the email preview; no push, no email.")
    parser.add_argument("--skip-refresh", action="store_true",
                        help="Reuse the current outputs instead of re-running the backtest.")
    parser.add_argument("--no-publish", action="store_true",
                        help="Do not commit or push report.html.")
    return parser.parse_args()


def main() -> int:
    """Run the month-end pipeline when today is in the window."""

    args = parse_args()
    load_env()
    today = pd.Timestamp(datetime.now(NEW_YORK).date())
    lock = lock_date(today).date().isoformat()
    if not args.force:
        if not in_window(today):
            log(f"Not in month-end window (next lock {lock}); nothing to do.")
            return 0
        if read_state().get("sent_lock_date") == lock:
            log(f"Already sent for lock date {lock}.")
            return 0

    missing = [k for k in ("RESEND_API_KEY", "EMAIL_FROM", "EMAIL_TO") if not os.environ.get(k)]
    if missing and not args.dry_run:
        raise RuntimeError(f"missing env vars: {', '.join(missing)} (set them in .env)")
    if not args.skip_refresh:
        refresh_outputs(today.date().isoformat())

    from run_webapp import build_dashboard_payload  # after the backtest rewrote outputs

    payload = build_dashboard_payload()
    if not args.force and payload["next"]["as_of"] != lock:
        raise RuntimeError(f"next picks locked {payload['next']['as_of']}, expected {lock}")
    if not args.skip_refresh:
        check_overlap(payload)

    run([PYTHON, "scripts/export_static_dashboard.py", "--report", str(REPORT_PATH)])
    email = build_email(payload, test=args.force)
    PREVIEW_PATH.write_text(email["html"])
    log(f"Subject: {email['subject']}")
    log(f"Preview: {PREVIEW_PATH}")
    if args.dry_run:
        log("Dry run: not publishing or sending.")
        return 0

    if not args.no_publish:
        publish(today.date().isoformat())
    result = send_via_resend(email)
    log(f"Sent: {result.get('id', result)}")
    if not args.force:
        STATE_PATH.write_text(json.dumps({"sent_lock_date": lock}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
