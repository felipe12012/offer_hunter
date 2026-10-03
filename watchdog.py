"""Service watchdog.

The scan workflow only alerts when a run fails. If the external trigger stops
(cron-job.org token expiry), GitHub stops running the schedule, or every run
silently returns nothing, nobody notices. This checks, from a separate workflow,
that:

  * the fast-tier workflow actually ran recently, and
  * no store that had products last time dropped to zero this time.

It sends one Telegram message only when something is wrong, so a healthy service
stays quiet. Pure helpers (``is_stale``, ``dropped_stores``) are unit tested.
"""
import os
import sys
from datetime import datetime, timezone

import requests

STALE_MINUTES = 40
WORKFLOW = "fast.yml"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def is_stale(created_at: str, now: datetime, max_minutes: int) -> bool:
    moment = _parse_iso(created_at)
    if moment is None:
        return True
    return (now - moment).total_seconds() > max_minutes * 60


def dropped_stores(runs: list[dict]) -> list[str]:
    """Stores with zero products in the newest run but non-zero in the previous
    one. ``runs`` is newest-first, each ``{"per_store": {store: count}}``."""
    if len(runs) < 2:
        return []
    latest = runs[0].get("per_store") or {}
    previous = runs[1].get("per_store") or {}
    return sorted(
        store
        for store, count in previous.items()
        if count and not latest.get(store, 0)
    )


def _last_run(repo: str, token: str) -> dict | None:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW}/runs?per_page=1"
    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    response.raise_for_status()
    runs = response.json().get("workflow_runs", [])
    return runs[0] if runs else None


def _supabase_runs(limit: int = 3) -> list[dict] | None:
    """The per-store counts recorded by each scan, newest first.

    ``[]`` when Supabase is not configured (the check is optional) and ``None``
    when it is configured but the query failed, so the caller can say so instead
    of silently skipping the check. (It used to select a ``created_at`` column
    that does not exist; the error was swallowed and the store check never ran.)"""
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or ""
    if not url or not key:
        return []
    headers = {"apikey": key}
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    try:
        response = requests.get(
            f"{url}/rest/v1/offer_scan_runs",
            headers=headers,
            params={"select": "started_at,per_store", "order": "started_at.desc", "limit": limit},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"watchdog: could not read offer_scan_runs from Supabase: {exc}", file=sys.stderr)
        return None


def _notify(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("Telegram not configured; cannot send the alert", file=sys.stderr)
        return
    requests.post(TELEGRAM_API.format(token=token), json={"chat_id": chat, "text": text}, timeout=30).raise_for_status()


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    problems: list[str] = []

    if not repo or not token:
        print("GITHUB_REPOSITORY / GITHUB_TOKEN are not set", file=sys.stderr)
        return 1

    try:
        latest = _last_run(repo, token)
    except requests.RequestException as exc:
        print(f"watchdog: could not read runs: {exc}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    if latest is None or is_stale(latest.get("created_at", ""), now, STALE_MINUTES):
        when = latest.get("created_at") if latest else "nunca"
        problems.append(f"Sin escaneos en los ultimos {STALE_MINUTES} min (ultimo: {when}).")

    runs = _supabase_runs()
    degraded = runs is None  # configured but unreadable: say so in the Actions run, not on Telegram
    for store in dropped_stores(runs or []):
        problems.append(f"La tienda {store} bajo a 0 productos en el ultimo escaneo.")

    if not problems:
        print(f"watchdog: ok (last run {latest.get('created_at') if latest else 'n/a'})")
        return 1 if degraded else 0

    message = "⚠️ cyberday-hunter vigilancia:\n- " + "\n- ".join(problems)
    try:
        _notify(message)
    except requests.RequestException as exc:
        print(f"watchdog: alert could not be sent: {exc}", file=sys.stderr)
        return 1
    print("\n".join(problems), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
