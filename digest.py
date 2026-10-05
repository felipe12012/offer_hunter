"""Daily digest: once a day, the best offers of the last 24 hours in a single message.

Sent to the owner and the public channel (not to every subscriber: they already receive offers all day). Due once per
Chile calendar day, from the first scan after 09:00; the day it was sent is kept in ``offer_bot_state``.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

from notifier import send_alert
from supabase_sync import SupabaseSync, log_failure

SEND_HOUR = 9
TOP = 10
STATE_KEY = "digest:last"
SITE = "https://offerhunter-mu.vercel.app"


def chile_now(now: datetime) -> datetime:
    try:
        from zoneinfo import ZoneInfo

        return now.astimezone(ZoneInfo("America/Santiago"))
    except Exception:  # no tz database (Windows without tzdata)
        return now.astimezone(timezone(timedelta(hours=-3)))


def is_due(now: datetime, last_sent: str | None) -> bool:
    local = chile_now(now)
    return local.hour >= SEND_HOUR and last_sent != local.date().isoformat()


def _clp(value) -> str:
    return "$" + f"{int(value):,}".replace(",", ".")


def build_text(rows: list[dict], now: datetime) -> str | None:
    if not rows:
        return None
    local = chile_now(now)
    lines = [f"☀️ Mejores ofertas de las últimas 24 h ({local.day:02d}/{local.month:02d})", ""]
    for index, row in enumerate(rows, 1):
        pct = round(row.get("verified_pct") or row.get("web_discount_pct") or 0)
        lines.append(f"{index}. -{pct}% {str(row['title'])[:70]} — {_clp(row['price'])} ({row['store']})")
        lines.append(f"   {row['url']}")
    lines += ["", f"Todas las ofertas en {SITE}"]
    return "\n".join(lines)


def top_rows(store: SupabaseSync, now: datetime) -> list[dict]:
    return store._get_rows(
        "offer_feed",
        {
            "select": "title,store,price,url,verified_pct,web_discount_pct",
            "dup_rank": "eq.1",
            "last_seen_at": f"gte.{(now - timedelta(hours=6)).isoformat()}",
            "web_confirmed": "eq.true",
            "order": "verified_pct.desc,id.asc",
            "limit": TOP,
        },
    )


def run_if_due(store: SupabaseSync | None, now: datetime | None = None) -> bool:
    """Send the digest if today's is pending. Never raises. True when it was sent."""
    if store is None:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        if not is_due(now, store.get_bot_state(STATE_KEY)):
            return False
        rows = top_rows(store, now)
        text = build_text(rows, now)
        if text is None:
            return False
        sent = send_alert(text)
        public = os.environ.get("TELEGRAM_PUBLIC_CHAT_ID") or None
        if public:
            send_alert(text, chat_id=public)
        if sent:
            store.set_bot_state(STATE_KEY, chile_now(now).date().isoformat())
        return sent
    except Exception as exc:
        log_failure("send the daily digest", exc)
        return False

