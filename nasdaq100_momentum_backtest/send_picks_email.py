"""Email next month's momentum trades via Resend.

Runs from a daily cron over the last days of each month (see
``.github/workflows/monthly-picks-email.yml``) and only sends on the evening
of the month's last NYSE trading day — the close that locks next month's
picks — so the trades can be placed as market-on-close orders on the next
first trading day, matching the backtest's fill.

The script:
  1. GETs ``/api/dashboard`` (both strategies) from ``MOMENTUM_API_BASE``.
  2. Skips unless Strategy A's next picks are locked as of today's New York
     date (``FORCE_SEND=1`` sends anyway, for smoke tests).
  3. Builds an HTML + text email with each strategy's trade list (sell /
     buy / keep), next picks and current holdings, and POSTs it to Resend.

Env vars:
  RESEND_API_KEY    required — get a key from https://resend.com
  EMAIL_FROM        required — verified Resend sender (e.g. picks@yourdomain.com)
  EMAIL_TO          required — comma-separated recipient(s)
  MOMENTUM_API_BASE optional — defaults to http://127.0.0.1:8765
  REFRESH           optional — "1" forces the backend to re-download prices
  FORCE_SEND        optional — "1" sends even when the signal isn't locked today

Exit codes:
  0  email sent, or nothing to send today
  1  any failure (API down, Resend rejected, missing env, etc.)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


def _env(name: str, default: str = "") -> str:
    """Read an env var and strip whitespace.

    Copy-pasting secrets into the GitHub Actions UI commonly leaves a
    trailing newline. ``urllib`` then rejects the value with
    ``ValueError: Invalid header value`` when it's used in an
    Authorization header, so we sanitize at the boundary.
    """
    return (os.environ.get(name) or default).strip()


API_BASE = _env("MOMENTUM_API_BASE", "http://127.0.0.1:8765").rstrip("/")
RESEND_API_KEY = _env("RESEND_API_KEY")
EMAIL_FROM = _env("EMAIL_FROM")
EMAIL_TO = _env("EMAIL_TO")
FORCE_REFRESH = _env("REFRESH", "0") == "1"
FORCE_SEND = _env("FORCE_SEND", "0") == "1"
HTTP_TIMEOUT = int(_env("HTTP_TIMEOUT", "120"))


def _http_get(url: str) -> bytes:
    """GET ``url`` with a non-default User-Agent and return the body."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "momentum-picks-email/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read()


# 502 / 503 / 504 are the classic wake-up gateway errors on Render's
# Free plan: the proxy answers before the still-cold worker is ready.
# Retrying after a short pause almost always succeeds.
_RETRYABLE_STATUSES = {502, 503, 504}


def _http_get_json(url: str, *, attempts: int = 4, backoff: float = 8.0) -> Dict[str, Any]:
    """GET JSON, retrying gateway errors and timeouts with linear backoff."""
    last_err: Exception | None = None
    for i in range(1, attempts + 1):
        try:
            return json.loads(_http_get(url).decode())
        except urllib.error.HTTPError as e:
            last_err = e
            retryable = e.code in _RETRYABLE_STATUSES
            sys.stderr.write(
                f"[attempt {i}/{attempts}] HTTP {e.code} fetching {url}\n"
            )
            if not retryable or i == attempts:
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            sys.stderr.write(
                f"[attempt {i}/{attempts}] transient error fetching {url}: {e}\n"
            )
            if i == attempts:
                raise
        time.sleep(backoff * i)  # 8s, 16s, 24s...
    raise last_err  # unreachable


def _warm_service() -> None:
    """Pre-warm the web service so the heavy dashboard call doesn't
    hit a cold worker. /health returns instantly when the service is
    live, so we burn the 30-60s wake-up window here instead of in
    the expensive request."""
    url = f"{API_BASE}/health"
    sys.stderr.write(f"Warming {url}…\n")
    try:
        _http_get_json(url, attempts=8, backoff=10.0)
        sys.stderr.write("Service is warm.\n")
    except Exception as e:
        sys.stderr.write(f"Warm-up gave up: {e}; proceeding anyway.\n")


def _fetch_dashboard() -> Dict[str, Any]:
    """Both strategies' payloads from ``/api/dashboard``."""
    qs = "?refresh=1" if FORCE_REFRESH else ""
    return _http_get_json(f"{API_BASE}/api/dashboard{qs}")


def _fmt_pct(x: Any, digits: int = 1) -> str:
    """Format a fraction as a signed percentage; "—" when missing."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.{digits}f}%"


def _fmt_price(x: Any) -> str:
    """Format a price as ``$1,234.56``; "—" when missing."""
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_num(x: Any, digits: int = 2) -> str:
    """Format a plain number; "—" when missing."""
    try:
        return f"{float(x):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def should_send(bundle: Dict[str, Any], today: str, force: bool = False) -> bool:
    """True when today's close locked the next picks (or ``force``).

    ``today`` is the New York date (YYYY-MM-DD). The lock date is the last
    trading day before the next entry, so a run on any later day of the
    month (a holiday or the weekend) does not send a duplicate.
    """
    if force:
        return True
    strategies = bundle.get("strategies") or []
    if not strategies:
        return False
    first = strategies[0]
    locked_as_of = (first.get("next_meta") or {}).get("signal_locked_as_of")
    return bool(first.get("next")) and locked_as_of == today


def trades(data: Dict[str, Any]) -> Dict[str, List[str]]:
    """Sell / buy / keep lists moving from the open holdings to the next picks."""
    held = [p["ticker"] for p in data.get("open") or []]
    nxt = [p["ticker"] for p in data.get("next") or []]
    return {
        "sell": [t for t in held if t not in nxt],
        "buy": [t for t in nxt if t not in held],
        "keep": [t for t in nxt if t in held],
    }


def _label(data: Dict[str, Any]) -> str:
    """Strategy heading, e.g. "Nasdaq-100 · 6-month momentum, monthly rebalance"."""
    meta = data.get("strategy") or {}
    return f"{meta.get('universe', '')} · {meta.get('label', '')}"


def _trade_line(data: Dict[str, Any]) -> str:
    """One-line trade summary used in the subject and text body."""
    t = trades(data)
    if not data.get("next"):
        return "no new picks yet"
    parts = []
    if t["sell"]:
        parts.append("sell " + ", ".join(t["sell"]))
    if t["buy"]:
        parts.append("buy " + ", ".join(t["buy"]))
    if t["keep"]:
        parts.append("keep " + ", ".join(t["keep"]))
    return "; ".join(parts) or "no change"


_TD = "padding:6px 12px;"
_TH = ("padding:8px 12px;text-align:left;font-size:11px;color:#64748B;"
       "text-transform:uppercase;letter-spacing:.05em")


def _table(headers: List[str], rows: List[List[str]]) -> str:
    """A small bordered HTML table."""
    head = "".join(f'<th style="{_TH}">{h}</th>' for h in headers)
    body = "".join(
        "<tr>" + "".join(f'<td style="{_TD}">{c}</td>' for c in row) + "</tr>"
        for row in rows
    )
    return (
        '<table cellspacing="0" cellpadding="0" style="width:100%;border:1px solid #E2E8F0;'
        'border-radius:8px;border-collapse:separate;border-spacing:0;overflow:hidden">'
        f'<thead><tr style="background:#F8FAFC">{head}</tr></thead><tbody>{body}</tbody></table>'
    )


def _strategy_block(data: Dict[str, Any]) -> str:
    """HTML section for one strategy: trades, next picks, current holdings."""
    t = trades(data)
    nxt = data.get("next") or []
    opens = data.get("open") or []
    next_meta = data.get("next_meta") or {}
    open_meta = data.get("open_meta") or {}
    stats = (data.get("stats") or {}).get("strategy") or {}
    bench = (data.get("stats") or {}).get("benchmark") or {}
    bm = (data.get("strategy") or {}).get("benchmark", "benchmark")

    def chips(names: List[str], color: str) -> str:
        return " ".join(
            f'<span style="display:inline-block;padding:2px 8px;border-radius:9999px;'
            f'background:{color};color:white;font-weight:700;font-size:13px">{n}</span>'
            for n in names
        ) or '<span style="color:#94A3B8">—</span>'

    trade_rows = [
        ["<b>Sell</b>", chips(t["sell"], "#B91C1C")],
        ["<b>Buy</b>", chips(t["buy"], "#047857")],
        ["<b>Keep</b>", chips(t["keep"], "#475569")],
    ]
    next_rows = [
        [f"#{p.get('rank')}", f"<b>{p.get('ticker')}</b>", _fmt_pct(p.get("momentum_score")),
         _fmt_price(p.get("entry_price_estimate"))]
        for p in nxt
    ]
    open_rows = [
        [f"#{p.get('rank')}", f"<b>{p.get('ticker')}</b>", _fmt_pct(p.get("stock_return")),
         f"{_fmt_price(p.get('entry_price'))} → {_fmt_price(p.get('latest_price'))}"]
        for p in opens
    ]
    entry = next_meta.get("planned_entry_date", "—")
    return f"""
      <div style="margin-bottom:32px">
        <div style="font-size:18px;font-weight:700;color:#0F172A;margin-bottom:4px">{_label(data)}</div>
        <div style="font-size:12px;color:#64748B;margin-bottom:12px">
          Trades for the {entry} close · signal locked {next_meta.get('signal_locked_as_of', '—')}
        </div>
        {_table(["Action", "Tickers"], trade_rows)}
        <div style="font-size:13px;font-weight:600;color:#0F172A;margin:16px 0 6px">Next picks (equal weight, ⅓ each)</div>
        {_table(["Rank", "Ticker", "Momentum / mo", "Last close"], next_rows) if next_rows else '<i style="color:#64748B">Not locked yet.</i>'}
        <div style="font-size:13px;font-weight:600;color:#0F172A;margin:16px 0 6px">
          Current holdings · entry {open_meta.get('entry_date', '—')} · month to date {_fmt_pct(open_meta.get('mtd_portfolio_return'))}
        </div>
        {_table(["Rank", "Ticker", "Return", "Entry → last"], open_rows) if open_rows else '<i style="color:#64748B">None.</i>'}
        <div style="margin-top:10px;font-size:12px;color:#475569">
          Backtest: CAGR <b>{_fmt_pct(stats.get('cagr'))}</b> ({bm} {_fmt_pct(bench.get('cagr'))})
          · Sharpe <b>{_fmt_num(stats.get('sharpe'))}</b>
          · Max DD <b>{_fmt_pct(stats.get('max_drawdown'))}</b> ({bm} {_fmt_pct(bench.get('max_drawdown'))})
        </div>
      </div>"""


def build_email(bundle: Dict[str, Any]) -> Dict[str, str]:
    """Subject, HTML and text bodies for the month-end trade email."""
    strategies = bundle.get("strategies") or []
    entry = ((strategies[0].get("next_meta") or {}).get("planned_entry_date", "")
             if strategies else "")
    letters = "ABCDEFGH"
    summary = " | ".join(f"{letters[i]}: {_trade_line(d)}" for i, d in enumerate(strategies))
    subject = f"Momentum trades for {entry or 'next rebalance'} — {summary}"

    blocks = "\n".join(_strategy_block(d) for d in strategies)
    html = f"""<!doctype html>
<html><body style="font-family:'Inter',system-ui,sans-serif;background:#F8FAFC;color:#0F172A;margin:0;padding:24px">
<div style="max-width:680px;margin:0 auto;background:white;border:1px solid #E2E8F0;border-radius:12px;padding:24px">
  <div style="font-size:22px;font-weight:800;margin-bottom:4px">Momentum rotation · next month's trades</div>
  <div style="font-size:13px;color:#475569;margin-bottom:24px">
    Place <b>market-on-close</b> orders on <b>{entry or '—'}</b> (the first trading day) to match the backtest's fill.
    Dashboard: <a href="{API_BASE}">{API_BASE}</a>
  </div>
  {blocks}
  <div style="margin-top:24px;padding-top:16px;border-top:1px solid #E2E8F0;font-size:11px;color:#94A3B8">
    Data: Yahoo Finance (adjusted close). Point-in-time index membership; delisted former members without
    Yahoo data are missing, so some survivorship bias remains. Backtest returns are gross of transaction
    cost &amp; slippage. Not investment advice.
  </div>
</div></body></html>"""

    lines = [f"Momentum trades for {entry} (market-on-close on the first trading day)", ""]
    for d in strategies:
        lines.append(f"== {_label(d)} ==")
        lines.append(f"  {_trade_line(d)}")
        for p in d.get("next") or []:
            lines.append(f"  next #{p.get('rank')} {p.get('ticker', ''):<6} last close {_fmt_price(p.get('entry_price_estimate'))}")
        mtd = (d.get("open_meta") or {}).get("mtd_portfolio_return")
        lines.append(f"  current holdings month to date: {_fmt_pct(mtd)}")
        lines.append("")
    lines.append(API_BASE)
    return {"subject": subject, "html": html, "text": "\n".join(lines)}


def _send_via_resend(subject: str, html: str, text: str) -> Dict[str, Any]:
    """POST the email to Resend and return its JSON response."""
    payload = {
        "from": EMAIL_FROM,
        "to": [t.strip() for t in EMAIL_TO.split(",") if t.strip()],
        "subject": subject,
        "html": html,
        "text": text,
    }
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {RESEND_API_KEY}",
            # Resend sits behind Cloudflare. The default urllib UA
            # (Python-urllib/x.y) trips Cloudflare's bot mitigation and
            # returns 403 with error code 1010 before the request ever
            # reaches Resend. Any non-default UA works.
            "User-Agent": "momentum-picks-email/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"Resend error {e.code}: {e.read().decode()}\n")
        raise


def main(today: Optional[str] = None) -> int:
    """Send the month-end trade email when today's close locked the picks."""
    missing = [
        name for name, val in (
            ("RESEND_API_KEY", RESEND_API_KEY),
            ("EMAIL_FROM", EMAIL_FROM),
            ("EMAIL_TO", EMAIL_TO),
        ) if not val
    ]
    if missing:
        sys.stderr.write(f"Missing env vars: {', '.join(missing)}\n")
        return 1

    today = today or datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    _warm_service()
    try:
        bundle = _fetch_dashboard()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        sys.stderr.write(f"Failed to fetch /api/dashboard: {e}\n")
        return 1

    if not should_send(bundle, today, FORCE_SEND):
        sys.stdout.write(f"{today}: next picks not locked today; nothing to send.\n")
        return 0

    email = build_email(bundle)
    result = _send_via_resend(email["subject"], email["html"], email["text"])
    sys.stdout.write(f"Sent: {result.get('id', result)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
