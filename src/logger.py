"""Shared logger: console + a dated file in logs/ for every run."""
from __future__ import annotations

import logging
import sys
from datetime import datetime

from src.config import LOGS_DIR

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def get_logger(name: str) -> logging.Logger:
    global _configured
    if not _configured:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):  # Windows consoles default to cp1252
                stream.reconfigure(encoding="utf-8", errors="replace")
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger("codexone")
        root.setLevel(logging.DEBUG)

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter("%(levelname)-7s | %(name)s | %(message)s"))

        logfile = LOGS_DIR / f"run_{datetime.now():%Y-%m-%d}.log"
        file_handler = logging.FileHandler(logfile, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_FORMAT))

        root.addHandler(console)
        root.addHandler(file_handler)
        _configured = True
    return logging.getLogger(f"codexone.{name}")
