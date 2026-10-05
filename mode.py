"""Safe-mode switch: one setting that makes the bot send less and risk less when something is wrong.

``config/mode.json`` is ``{"mode": "normal"}`` or ``{"mode": "safe"}``; the BOT_MODE environment variable (a repository
variable in GitHub) overrides it without a commit. In safe mode the scans keep running and the state keeps being
recorded, but only what is surest goes out: verified offers and possible price mistakes (no unconfirmed discounts,
no priority interests without confirmation) and nothing is fanned out to subscribers.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MODE_PATH = Path(__file__).parent / "config" / "mode.json"
NORMAL = "normal"
SAFE = "safe"


def current(path: Path = MODE_PATH) -> str:
    override = (os.environ.get("BOT_MODE") or "").strip().lower()
    if override in (NORMAL, SAFE):
        return override
    try:
        value = str(json.loads(path.read_text(encoding="utf-8")).get("mode", NORMAL)).strip().lower()
    except (OSError, ValueError, AttributeError):
        return NORMAL
    if value not in (NORMAL, SAFE):
        print(f"Unknown mode {value!r} in {path.name}; using {NORMAL}", file=sys.stderr)
        return NORMAL
    return value


def is_safe(path: Path = MODE_PATH) -> bool:
    return current(path) == SAFE
