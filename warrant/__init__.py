"""Warrant — intent conformance for agent purchases.

Loads `.env` on import so every entry point (eval scripts, tests, the API, the
UI) sees the same configuration without each one remembering to do it.
Environment variables already set always win, so CI and shell overrides are
never clobbered by a stale local file.
"""

from __future__ import annotations

from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

try:
    from dotenv import load_dotenv

    load_dotenv(_ENV_PATH, override=False)
except ImportError:  # python-dotenv is optional; env vars still work
    pass
