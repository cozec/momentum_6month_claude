"""Utility helpers for logging and filesystem operations."""

from __future__ import annotations

import logging
import os
from typing import Optional

import pandas as pd

from .config import LOGS_DIR


def ensure_dir(path: str) -> None:
    """Create the directory at ``path`` if it does not already exist."""
    os.makedirs(path, exist_ok=True)


def get_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """Return a configured logger that writes to both stdout and a file.

    Parameters
    ----------
    name : str
        Logger name.
    log_file : Optional[str]
        Path to the log file. Defaults to ``logs/<name>.log``.
    """
    ensure_dir(LOGS_DIR)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s - %(message)s"
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    if log_file is None:
        log_file = os.path.join(LOGS_DIR, f"{name}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.propagate = False
    return logger


def to_business_date(value) -> pd.Timestamp:
    """Convert ``value`` to a ``pd.Timestamp`` (date-only, tz-naive)."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()
