"""HTTP for the scrapers that need no browser: one keep-alive session per thread, and numbers.

``requests.get`` opens a new TCP + TLS connection for every page; with ~500 pages per Falabella scan
that handshake was about a third of the time (1.42 s -> 0.98 s per page measured with a session).
A ``requests.Session`` is not guaranteed thread-safe, so every worker thread keeps its own.

Every call is also timed per host, so the run log can say whether a slow scan was the network
(high p95, many errors) or something else (fast requests, still slow).
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlsplit

import requests

# A page that has not answered in this long is not going to: the caller retries instead of
# letting one hung request hold a worker for half a minute.
DEFAULT_TIMEOUT_SECONDS = 15

_local = threading.local()
_lock = threading.Lock()
_stats: dict[str, dict] = {}


def _session() -> requests.Session:
    session = getattr(_local, "session", None)
    if session is None:
        session = requests.Session()
        _local.session = session
    return session


def _record(host: str, seconds: float, failed: bool) -> None:
    with _lock:
        entry = _stats.setdefault(host, {"requests": 0, "errors": 0, "seconds": 0.0, "latencies": []})
        entry["requests"] += 1
        entry["errors"] += failed
        entry["seconds"] += seconds
        entry["latencies"].append(seconds)


def get(url: str, headers: dict | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> requests.Response:
    """GET through this thread's session. Raises like ``requests.get`` (callers keep their own retries)."""
    host = urlsplit(url).netloc
    began = time.perf_counter()
    failed = True
    try:
        response = _session().get(url, headers=headers, timeout=timeout)
        failed = response.status_code >= 400
        return response
    finally:
        _record(host, time.perf_counter() - began, failed)


def reset_stats() -> None:
    with _lock:
        _stats.clear()


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def summary() -> dict[str, dict]:
    """host -> requests, errors, total seconds waiting, median and 95th percentile latency."""
    with _lock:
        return {
            host: {
                "requests": entry["requests"],
                "errors": entry["errors"],
                "seconds": round(entry["seconds"], 1),
                "p50": round(_percentile(entry["latencies"], 0.5), 2),
                "p95": round(_percentile(entry["latencies"], 0.95), 2),
            }
            for host, entry in _stats.items()
            if entry["latencies"]
        }


def format_summary() -> str:
    stats = summary()
    if not stats:
        return ""
    lines = ["HTTP by host (requests, errors, median / p95 latency, time spent waiting):"]
    for host, s in sorted(stats.items(), key=lambda item: -item[1]["seconds"]):
        lines.append(
            f"  {host:<34} {s['requests']:>5} req {s['errors']:>3} err  p50 {s['p50']:.2f}s  p95 {s['p95']:.2f}s  {s['seconds']:.0f}s"
        )
    return "\n".join(lines)


def to_markdown() -> str:
    stats = summary()
    if not stats:
        return ""
    rows = ["| Sitio | Peticiones | Errores | p50 | p95 | Espera total |", "|---|---:|---:|---:|---:|---:|"]
    for host, s in sorted(stats.items(), key=lambda item: -item[1]["seconds"]):
        rows.append(f"| {host} | {s['requests']} | {s['errors']} | {s['p50']:.2f}s | {s['p95']:.2f}s | {s['seconds']:.0f}s |")
    return "\n".join(rows)
