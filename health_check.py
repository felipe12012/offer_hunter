"""Heartbeats: every scan leaves a mark in Supabase, and the scans watch each other.

GitHub does not fire scheduled workflows reliably (the hot scan and the browser scan stopped running for hours with a
5-minute and a 30-minute schedule), and the external watchdog is itself a scheduled workflow. The scans that do run
(triggered by cron-job.org) are the reliable ones, so they check the others' marks: if the hot scan, the browser scan or
the regular scan has not run for too long, the owner gets one Telegram message saying which and what to do.

Marks live in ``offer_bot_state`` (key ``heartbeat:<name>``); the last alert of each kind in ``alerted:<name>``.
Pure decision (``evaluate``) apart from the Supabase reads and writes, so it is unit tested.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from notifier import send_alert
from supabase_sync import SupabaseSync, log_failure

# Minutes without a mark before it is a problem. The hot scan is dispatched every 5-10 minutes, the browser scan
# every 30 and the regular scan every 15.
LIMIT_MINUTES = {"fast": 40, "hot": 25, "browser": 75}
# One alert per component per this many hours (the problem is still there; saying it again every run is noise).
REALERT_HOURS = 3

WHAT_TO_DO = {
    "fast": "El escaneo normal lleva {minutes} min sin ejecutarse. Revisa el trabajo de cron-job.org (token vencido o pausado) "
            "y que GitHub Actions funcione.",
    "hot": "El escaneo caliente (errores de precio y descuentos fuertes) lleva {minutes} min sin ejecutarse. GitHub no dispara "
           "bien sus horarios: crea en cron-job.org un trabajo POST a .../workflows/hot.yml/dispatches cada 5 min.",
    "browser": "El escaneo de las tiendas con navegador (Skechers, Salcobrand, Cruz Verde, Fila...) lleva {minutes} min sin "
               "ejecutarse. Crea en cron-job.org un trabajo POST a .../workflows/browser.yml/dispatches cada 30 min.",
}


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def evaluate(
    beats: dict[str, str | None],
    alerted: dict[str, str | None],
    now: datetime,
    watcher: str,
) -> tuple[list[tuple[str, str]], list[str]]:
    """(alerts as (component, text), components with no mark yet). A component without any mark gets a grace period
    (its mark is initialised to ``now``) instead of an immediate alert. ``watcher`` does not check itself."""
    alerts: list[tuple[str, str]] = []
    unseen: list[str] = []
    for name, limit in LIMIT_MINUTES.items():
        if name == watcher:
            continue
        beat = _parse(beats.get(name))
        if beat is None:
            unseen.append(name)
            continue
        minutes = int((now - beat).total_seconds() // 60)
        if minutes <= limit:
            continue
        last_alert = _parse(alerted.get(name))
        if last_alert is not None and now - last_alert < timedelta(hours=REALERT_HOURS):
            continue
        alerts.append((name, "⚠️ " + WHAT_TO_DO[name].format(minutes=minutes)))
    return alerts, unseen


def beat(store: SupabaseSync | None, name: str, now: datetime | None = None) -> None:
    if store is None:
        return
    try:
        store.set_bot_state(f"heartbeat:{name}", (now or datetime.now(timezone.utc)).isoformat())
    except Exception as exc:
        log_failure(f"write the {name} heartbeat", exc)


def check(store: SupabaseSync | None, watcher: str, now: datetime | None = None) -> list[str]:
    """Look at the other scans' marks and alert the owner about the ones that stopped. Returns the alert texts."""
    if store is None:
        return []
    now = now or datetime.now(timezone.utc)
    try:
        names = [n for n in LIMIT_MINUTES if n != watcher]
        beats = {n: store.get_bot_state(f"heartbeat:{n}") for n in names}
        alerted = {n: store.get_bot_state(f"alerted:{n}") for n in names}
        alerts, unseen = evaluate(beats, alerted, now, watcher)
        for name in unseen:  # first time we look: start the clock instead of crying wolf
            store.set_bot_state(f"heartbeat:{name}", now.isoformat())
        texts = []
        for name, text in alerts:
            if send_alert(text):
                store.set_bot_state(f"alerted:{name}", now.isoformat())
            texts.append(text)
            print(text, file=sys.stderr)
        return texts
    except Exception as exc:
        log_failure("check the heartbeats", exc)
        return []
