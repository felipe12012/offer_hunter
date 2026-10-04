"""What a store has found so far, so a scan that runs out of time keeps what it read.

A store scan returns everything at the end; if it overran the run's per-store limit, all of it was
thrown away (Falabella lost ~18,000 products in 4 consecutive scans). Scanners that read many
pages now publish each finished job here, and the orchestrator takes whatever is there when it
gives up. It also raises a stop flag so the abandoned workers wind down instead of finishing a
scan nobody is waiting for.
"""

from __future__ import annotations

import threading
from typing import Callable

from models import Deal

_lock = threading.Lock()
_found: dict[str, dict[str, Deal]] = {}
_stop = threading.Event()


def reset() -> None:
    """Start of a scan: forget the previous one and lower the stop flag."""
    with _lock:
        _found.clear()
    _stop.clear()


def publish(store: str, deals: list[Deal], merge: Callable[[Deal, Deal], Deal] | None = None) -> None:
    with _lock:
        known = _found.setdefault(store, {})
        for deal in deals:
            if deal.id in known and merge is not None:
                known[deal.id] = merge(known[deal.id], deal)
            else:
                known.setdefault(deal.id, deal)


def take(store: str) -> list[Deal]:
    with _lock:
        return list(_found.get(store, {}).values())


def stop() -> None:
    _stop.set()


def stopped() -> bool:
    return _stop.is_set()
