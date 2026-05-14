"""Email the latest momentum picks via Resend.

Designed to be run as a monthly cron (Render → Cron Job, GitHub Actions,
PythonAnywhere scheduled task, or a plain crontab):

    0 22 1 * *   python send_picks_email.py

The script:
  1. GETs /api/picks for both strategies (L=6m/P=1m and L=3m/P=2m)
     against ``MOMENTUM_API_BASE`` (defaults to the local dev URL).
  2. Builds a clean HTML email summarizing the open holdings for each
     and the equal-weight MTD return.
  3. POSTs to the Resend ``/emails`` endpoint using ``RESEND_API_KEY``.

Env vars (set in Render → Cron Job → Environment, or ``.env``):
  RESEND_API_KEY    required — get a key from https://resend.com
  EMAIL_FROM        required — verified Resend sender (e.g. picks@yourdomain.com)
  EMAIL_TO          required — comma-separated recipient(s)
  MOMENTUM_API_BASE optional — defaults to http://127.0.0.1:8765
  REFRESH           optional — set to "1" to force backend re-download

Exit codes:
  0  email sent
  1  any failure (API down, Resend rejected, missing env, etc.)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict, List


API_BASE = os.environ.get("MOMENTUM_API_BASE", "http://127.0.0.1:8765").rstrip("/")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_TO = os.environ.get("EMAIL_TO")
FORCE_REFRESH = os.environ.get("REFRESH", "0") == "1"
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "120"))

STRATEGIES = [
    {"label": "Strategy A · L=6m / P=1m (baseline)", "lookback": 6, "period": 1},
    {"label": "Strategy B · L=3m / P=2m (grid winner)", "lookback": 3, "period": 2},
]


def _http_get_json(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _fetch_strategy(lookback: int, period: int) -> Dict[str, Any]:
    qs = f"lookback={lookback}&period={period}"
    if FORCE_REFRESH:
        qs += "&refresh=1"
    return _http_get_json(f"{API_BASE}/api/picks?{qs}")


def _fmt_pct(x: Any, digits: int = 1) -> str:
    if x is None:
        return "—"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.{digits}f}%"


def _pick_row(pick: Dict[str, Any]) -> str:
    color = "#047857" if pick.get("stock_return", 0) >= 0 else "#B91C1C"
    return f"""
      <tr>
        <td style="padding:6px 12px;font-weight:600;color:#0F172A;">#{pick['rank']}</td>
        <td style="padding:6px 12px;font-weight:700;color:#0F172A;font-size:16px;">{pick['ticker']}</td>
        <td style="padding:6px 12px;font-weight:600;color:{color};">{_fmt_pct(pick.get('stock_return'))}</td>
        <td style="padding:6px 12px;color:#475569;">${pick.get('entry_price', 0):.2f} → ${pick.get('latest_price', 0):.2f}</td>
      </tr>"""


def _strategy_block(label: str, data: Dict[str, Any]) -> str:
    opens: List[Dict[str, Any]] = data.get("open", []) or []
    meta = data.get("open_meta", {}) or {}
    stats = (data.get("stats", {}) or {}).get("strategy", {}) or {}
    mtd = meta.get("mtd_portfolio_return")
    mtd_str = _fmt_pct(mtd) if mtd is not None else "—"
    rows = "\n".join(_pick_row(p) for p in opens) if opens else (
        "<tr><td colspan='4' style='padding:12px;color:#64748B;font-style:italic'>"
        "No open rebalance.</td></tr>"
    )
    return f"""
      <div style="margin-bottom:32px">
        <div style="font-size:18px;font-weight:700;color:#0F172A;margin-bottom:4px">{label}</div>
        <div style="font-size:12px;color:#64748B;margin-bottom:12px">
          entry {meta.get('entry_date', '—')} · MTD as of {meta.get('as_of', '—')}
        </div>
        <table cellspacing="0" cellpadding="0" style="width:100%;border:1px solid #E2E8F0;border-radius:8px;border-collapse:separate;border-spacing:0;overflow:hidden">
          <thead>
            <tr style="background:#F8FAFC">
              <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:.05em">Rank</th>
              <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:.05em">Ticker</th>
              <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:.05em">Return</th>
              <th style="padding:8px 12px;text-align:left;font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:.05em">Entry → Last</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        <div style="margin-top:10px;font-size:13px;color:#475569">
          Equal-weight portfolio MTD: <b style="color:{'#047857' if (mtd or 0) >= 0 else '#B91C1C'}">{mtd_str}</b>
          &nbsp;·&nbsp; Strategy CAGR: <b>{_fmt_pct(stats.get('cagr'))}</b>
          &nbsp;·&nbsp; Sharpe: <b>{stats.get('sharpe', 0):.2f}</b>
          &nbsp;·&nbsp; Max DD: <b>{_fmt_pct(stats.get('max_drawdown'))}</b>
        </div>
      </div>"""


def _build_email(data_by_strategy: List[Dict[str, Any]]) -> Dict[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    blocks = "\n".join(
        _strategy_block(s["label"], d)
        for s, d in zip(STRATEGIES, data_by_strategy)
    )
    html = f"""<!doctype html>
<html><body style="font-family:'Inter',system-ui,sans-serif;background:#F8FAFC;color:#0F172A;margin:0;padding:24px">
<div style="max-width:640px;margin:0 auto;background:white;border:1px solid #E2E8F0;border-radius:12px;padding:24px">
  <div style="font-size:22px;font-weight:800;margin-bottom:4px">Nasdaq-100 Momentum Picks</div>
  <div style="font-size:12px;color:#64748B;margin-bottom:24px">{today} · {API_BASE}</div>
  {blocks}
  <div style="margin-top:24px;padding-top:16px;border-top:1px solid #E2E8F0;font-size:11px;color:#94A3B8">
    Data: Yahoo Finance (adjusted close). Survivorship-biased universe (current Nasdaq-100).
    Returns are gross of transaction cost &amp; slippage.
  </div>
</div></body></html>"""

    text_lines = [f"Nasdaq-100 Momentum Picks — {today}", ""]
    for strat, data in zip(STRATEGIES, data_by_strategy):
        meta = data.get("open_meta", {}) or {}
        text_lines.append(f"== {strat['label']} ==")
        text_lines.append(
            f"entry {meta.get('entry_date', '—')} · MTD as of {meta.get('as_of', '—')}"
        )
        for p in data.get("open", []) or []:
            text_lines.append(
                f"  #{p['rank']}  {p['ticker']:<6}  {_fmt_pct(p.get('stock_return')):>7}  "
                f"${p.get('entry_price', 0):.2f} → ${p.get('latest_price', 0):.2f}"
            )
        mtd = meta.get("mtd_portfolio_return")
        text_lines.append(f"  portfolio MTD: {_fmt_pct(mtd)}")
        text_lines.append("")

    subject = f"Momentum picks — {today}"
    return {"subject": subject, "html": html, "text": "\n".join(text_lines)}


def _send_via_resend(subject: str, html: str, text: str) -> Dict[str, Any]:
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
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"Resend error {e.code}: {e.read().decode()}\n")
        raise


def main() -> int:
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

    try:
        data = [
            _fetch_strategy(s["lookback"], s["period"]) for s in STRATEGIES
        ]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        sys.stderr.write(f"Failed to fetch /api/picks: {e}\n")
        return 1

    email = _build_email(data)
    result = _send_via_resend(email["subject"], email["html"], email["text"])
    sys.stdout.write(f"Sent: {result.get('id', result)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
