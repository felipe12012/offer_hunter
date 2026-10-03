"""Per-store scan report: what each store did in this run, in a form that can be
printed, shown in the GitHub run summary and stored in Supabase.

Pure functions only (no network, no files) so the rules are easy to test.
"""
from dataclasses import dataclass, field

MAX_ERRORS_PER_STORE = 3
MAX_MESSAGE_LENGTH = 200

# A store in one of these states delivered nothing useful this run.
BAD_STATUSES = {"failed", "timeout", "empty"}
# Statuses that count as "the store is working" when deciding recovery.
GOOD_STATUSES = {"ok", "partial"}


@dataclass
class StoreReport:
    store: str
    status: str  # ok | partial | failed | timeout | empty | disabled
    deals: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    empty_queries: int = 0
    detail: str = ""


def build_report(
    store: str,
    deals: int,
    seconds: float,
    events: list[dict],
    raised: Exception | None = None,
    timed_out: bool = False,
) -> StoreReport:
    errors = [e["message"] for e in events if e.get("kind") == "error"]
    empty_queries = sum(1 for e in events if e.get("kind") == "empty")

    if timed_out:
        status = "timeout"
    elif raised is not None:
        status = "failed"
    elif deals > 0:
        status = "partial" if errors else "ok"
    else:
        # Nothing came back. With logged errors the store failed; with none, every
        # query was empty, which usually means a block or a layout change.
        status = "failed" if errors else "empty"

    detail = ""
    if timed_out:
        detail = f"no terminó en {int(seconds)}s"
    elif raised is not None:
        detail = str(raised)
    elif status == "empty":
        detail = "ninguna consulta devolvió productos (¿bloqueo o cambio de estructura?)"
    return StoreReport(
        store=store, status=status, deals=deals, seconds=round(seconds, 1),
        errors=errors, empty_queries=empty_queries, detail=detail,
    )


def _clip(text: str) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= MAX_MESSAGE_LENGTH else text[: MAX_MESSAGE_LENGTH - 1] + "…"


def to_json(reports: list[StoreReport]) -> dict:
    """Compact form stored in offer_scan_runs.store_status."""
    result: dict[str, dict] = {}
    for report in reports:
        errors = [_clip(e) for e in report.errors[:MAX_ERRORS_PER_STORE]]
        if not errors and report.detail:
            errors = [_clip(report.detail)]
        result[report.store] = {
            "status": report.status,
            "deals": report.deals,
            "seconds": report.seconds,
            "empty_queries": report.empty_queries,
            "errors": errors,
        }
    return result


def _problem_text(report: StoreReport) -> str:
    if report.status == "partial":
        return f"{len(report.errors)} consulta(s) con error"
    if report.status in BAD_STATUSES:
        return _clip(report.detail or (report.errors[0] if report.errors else ""))
    return ""


def format_log(reports: list[StoreReport]) -> str:
    lines = ["Store report:"]
    for report in reports:
        label = report.status.upper() if report.status in BAD_STATUSES else report.status
        line = f"  {report.store:<12} {label:<9} {report.deals:>6} deals {report.seconds:>6.1f}s"
        if report.empty_queries:
            line += f"  ({report.empty_queries} empty queries)"
        problem = _problem_text(report)
        if problem:
            line += f"  -> {problem}"
        lines.append(line)
    return "\n".join(lines)


def to_markdown(reports: list[StoreReport]) -> str:
    """Table for the GitHub Actions run summary."""
    icon = {"ok": "✅", "partial": "🟡", "failed": "🔴", "timeout": "🔴", "empty": "🟠", "disabled": "⚪"}
    rows = ["| Tienda | Estado | Productos | Tiempo | Detalle |", "|---|---|---:|---:|---|"]
    for report in reports:
        problem = _problem_text(report).replace("|", "\\|")
        rows.append(
            f"| {report.store} | {icon.get(report.status, '')} {report.status} | {report.deals} "
            f"| {report.seconds:.0f}s | {problem} |"
        )
    return "\n".join(rows)


def store_transitions(
    current: dict[str, str], previous: list[dict | None]
) -> tuple[list[str], list[str]]:
    """Which stores just went down / just recovered.

    ``current`` is store -> status for this run; ``previous`` the statuses of the
    runs before it, newest first (``None`` for runs without data).

    * down:      bad now AND in the previous run, but not in the run before that —
                 so a store is announced once, on its second bad run, not on a blip
    * recovered: healthy now after two bad runs in a row (the ones that were announced)
    """
    prev1 = previous[0] if len(previous) > 0 else None
    prev2 = previous[1] if len(previous) > 1 else None
    if prev1 is None:
        return [], []

    down: list[str] = []
    recovered: list[str] = []
    for store, status in current.items():
        before = prev1.get(store)
        before2 = (prev2 or {}).get(store)
        if status in BAD_STATUSES and before in BAD_STATUSES and before2 not in BAD_STATUSES:
            down.append(store)
        elif status in GOOD_STATUSES and before in BAD_STATUSES and before2 in BAD_STATUSES:
            recovered.append(store)
    return sorted(down), sorted(recovered)
