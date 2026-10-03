"""Diagnostics collected while the stores are scanned.

Scrapers used to ``print`` their failures to stderr, so after a run nobody could
tell which stores were healthy without reading hundreds of log lines. They now
report here: the orchestrator drains the events once per scan and turns them
into a per-store report (see ``reports.py``).

Three kinds of event:
  * ``warn``   something went wrong with one query (printed and recorded)
  * ``empty``  a query ran fine but matched nothing (recorded only: it is normal
               for a pharmacy to have no "notebook")
"""
import sys
import threading

_lock = threading.Lock()
_events: list[dict] = []


class NoResultsError(RuntimeError):
    """A query returned a valid page with zero products. Not a failure.

    Subclasses RuntimeError so callers that only know the old
    "no product cards found" error keep working."""


def _record(store: str, kind: str, message: str) -> None:
    with _lock:
        _events.append({"store": store, "kind": kind, "message": message})


def warn(store: str, message: str) -> None:
    _record(store, "error", message)
    print(message, file=sys.stderr)


def empty(store: str, query: str) -> None:
    _record(store, "empty", query)


def drain() -> list[dict]:
    """Return every event recorded so far and clear the collector."""
    with _lock:
        events = list(_events)
        _events.clear()
    return events
