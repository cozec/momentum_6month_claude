"""Export the local dashboard as static assets or a single shareable file.

Default: a static site directory (``public/``). With ``--report``, one
self-contained ``report.html`` with the data snapshot and script inlined, for
hosting anywhere (e.g. GitHub Pages) or sending as a file.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from run_webapp import build_dashboard_payload  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export dashboard static assets.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "public",
        help="Directory to write static site assets into.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a single self-contained HTML report to this path instead.",
    )
    return parser.parse_args()


def write_report(path: Path) -> None:
    """Write one HTML file with the dashboard snapshot and app.js inlined.

    Args:
        path: Destination HTML file.
    """

    static_dir = PROJECT_ROOT / "webapp" / "static"
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    script = (static_dir / "app.js").read_text(encoding="utf-8")
    # "</" would end the inline <script> early; JSON allows the escaped form.
    data = json.dumps(build_dashboard_payload(), sort_keys=True).replace("</", "<\\/")
    start = html.index('<script src="/app.js')
    end = html.index("</script>", start) + len("</script>")
    inline = (
        f"<script>window.DASHBOARD_DATA = {data};</script>\n"
        f"  <script>\n{script}\n  </script>"
    )
    html = html[:start] + inline + html[end:]
    path.write_text(html, encoding="utf-8")
    print(f"Wrote single-file report to {path}")


def main() -> None:
    args = parse_args()
    if args.report is not None:
        write_report(args.report)
        return
    output_dir = args.output_dir
    static_dir = PROJECT_ROOT / "webapp" / "static"
    chart_dir = PROJECT_ROOT / "outputs" / "charts"

    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(static_dir, output_dir)

    if chart_dir.exists():
        shutil.copytree(chart_dir, output_dir / "charts")

    payload = build_dashboard_payload()
    dashboard_json = json.dumps(payload, indent=2, sort_keys=True)
    (output_dir / "dashboard.json").write_text(dashboard_json + "\n", encoding="utf-8")
    print(f"Wrote static dashboard to {output_dir}")


if __name__ == "__main__":
    main()
