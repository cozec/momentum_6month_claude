"""Snapshot the running dashboard into a static report.html.

Usage (dashboard already running, e.g. ``python run_webapp.py``)::

    python scripts/build_report.py ../report.html

Loads the dashboard in headless Chromium (Playwright) and evaluates
``snapshot_report.js``, which swaps the charts for PNG images and keeps the
view tabs working without the app scripts.
"""

from __future__ import annotations

import argparse
import os

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))


def build_report(url: str, out_path: str) -> int:
    """Render ``url`` and write the static snapshot to ``out_path``.

    Returns the number of bytes written.
    """
    with open(os.path.join(HERE, "snapshot_report.js")) as f:
        snapshot_js = f.read()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}, device_scale_factor=2
        )
        page.goto(url, wait_until="networkidle", timeout=600_000)
        html = page.evaluate(snapshot_js)
        browser.close()
    if html.count("data:image/png") < 2:
        raise RuntimeError("snapshot is missing chart images")
    with open(out_path, "w") as f:
        f.write(html)
    return len(html)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", help="output path, e.g. ../report.html")
    parser.add_argument("--url", default="http://127.0.0.1:8765/#a-top3")
    args = parser.parse_args()
    size = build_report(args.url, args.out)
    print(f"Wrote {args.out} ({size:,} bytes)")


if __name__ == "__main__":
    main()
