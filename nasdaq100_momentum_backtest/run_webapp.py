"""Launcher: ``python run_webapp.py`` to start the picks dashboard.

By default it binds to ``127.0.0.1:8765``. Override via env vars:
    MOMENTUM_HOST=0.0.0.0 MOMENTUM_PORT=8000 python run_webapp.py
"""

from __future__ import annotations

import os
import sys

import uvicorn

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def main() -> None:
    host = os.environ.get("MOMENTUM_HOST", "127.0.0.1")
    port = int(os.environ.get("MOMENTUM_PORT", "8765"))
    reload = os.environ.get("MOMENTUM_RELOAD", "0") == "1"
    uvicorn.run(
        "webapp.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
