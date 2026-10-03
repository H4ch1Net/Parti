"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

VERSION = "2.0.0"


def _list(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


CORS_ORIGINS = _list("PARTI_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
LOG_LEVEL = os.environ.get("PARTI_LOG_LEVEL", "INFO").upper()
# Directory with a built frontend (``npm run build``). Served at / when present.
STATIC_DIR = Path(os.environ.get("PARTI_STATIC_DIR", Path(__file__).resolve().parents[3] / "frontend" / "dist"))
