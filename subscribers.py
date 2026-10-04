"""Telegram bot subscribers: whoever presses /start in a private chat gets the offers.

There is no server listening to the bot. At the start of every run the pipeline asks Telegram
for the messages received since the last run (getUpdates), registers /start and /stop in
Supabase and answers them, so a new subscriber waits at most one scan interval for the welcome.
"""

from __future__ import annotations

import os
import sys

import requests

from supabase_sync import SupabaseError, SupabaseSync

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
OFFSET_KEY = "telegram_update_offset"
# Updates are fetched in one call: a bot that was idle for a day has far fewer than this.
UPDATES_LIMIT = 100
REQUEST_TIMEOUT_SECONDS = 30

WELCOME = (
    "¡Hola{name}! 👋 Quedaste suscrito/a: te enviaré las mejores ofertas de tiendas chilenas, "
    "con el descuento verificado contra el historial de precios.\n\n"
    "/stop — dejar de recibirlas\n"
    "/start — volver a recibirlas\n"
    "/ayuda — cómo funciona"
)
GOODBYE = "Listo, no recibirás más ofertas. Escribe /start cuando quieras volver."
HELP = (
    "Reviso las tiendas cada 15 minutos y te aviso solo de las ofertas que valen la pena: "
    "descuentos confirmados con el historial de precios o de tus categorías de interés. "
    "Un precio \"antes\" inflado por la tienda no cuenta.\n\n"
    "/stop — dejar de recibirlas\n"
    "/start — volver a recibirlas"
)


def _call(token: str, method: str, **payload) -> dict | None:
    try:
        response = requests.post(
            TELEGRAM_API.format(token=token, method=method), json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code >= 400:
            print(f"Telegram {method} failed with HTTP {response.status_code}: {response.text[:200]}", file=sys.stderr)
            return None
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"Telegram {method} request error: {exc}", file=sys.stderr)
        return None


def _command(text: str | None) -> str:
    """"/start@MyBot payload" -> "/start"; anything that is not a command -> ""."""
    if not text or not text.startswith("/"):
        return ""
    return text.split()[0].split("@")[0].lower()


def handle_update(update: dict, store: SupabaseSync, token: str) -> str | None:
    """Apply one update. Returns "subscribed", "unsubscribed" or None (ignored)."""
    member = update.get("my_chat_member")
    if member:
        chat = member.get("chat") or {}
        if chat.get("type") == "private" and (member.get("new_chat_member") or {}).get("status") in ("kicked", "left"):
            store.set_subscribers_active([chat["id"]], False)  # blocked the bot
            return "unsubscribed"
        return None

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return None  # groups and channels are configured with the secrets, not with /start
    chat_id = chat["id"]
    command = _command(message.get("text"))

    if command == "/start":
        sender = message.get("from") or {}
        store.upsert_subscriber(chat_id, sender.get("username"), sender.get("first_name"), True)
        first_name = sender.get("first_name")
        _call(token, "sendMessage", chat_id=chat_id, text=WELCOME.format(name=f" {first_name}" if first_name else ""))
        return "subscribed"
    if command == "/stop":
        store.set_subscribers_active([chat_id], False)
        _call(token, "sendMessage", chat_id=chat_id, text=GOODBYE)
        return "unsubscribed"
    if command in ("/ayuda", "/help"):
        _call(token, "sendMessage", chat_id=chat_id, text=HELP)
    return None


def process_updates(store: SupabaseSync, token: str | None = None) -> dict:
    """Read what the bot received since the last run and register /start and /stop.

    Returns {"subscribed": n, "unsubscribed": n}. Never raises: a Telegram or Supabase
    problem here must not stop the offers from being sent."""
    counts = {"subscribed": 0, "unsubscribed": 0}
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return counts

    try:
        raw_offset = store.get_bot_state(OFFSET_KEY)
        payload: dict = {"limit": UPDATES_LIMIT, "timeout": 0, "allowed_updates": ["message", "my_chat_member"]}
        if raw_offset:
            payload["offset"] = int(raw_offset)
        data = _call(token, "getUpdates", **payload)
        updates = (data or {}).get("result") or []
        last_id = None
        for update in updates:
            try:
                outcome = handle_update(update, store, token)
            except (KeyError, TypeError, AttributeError) as exc:  # malformed update: skip it for good
                print(f"Subscriber update {update.get('update_id')} skipped: {exc!r}", file=sys.stderr)
                outcome = None
            except SupabaseError as exc:  # storage hiccup: stop here, this update is retried next run
                print(f"Subscriber update {update.get('update_id')} not saved, will retry: {exc}", file=sys.stderr)
                break
            if outcome:
                counts[outcome] += 1
            last_id = update["update_id"]
        if last_id is not None:
            store.set_bot_state(OFFSET_KEY, str(last_id + 1))
    except Exception as exc:
        print(f"Subscriber sync failed (offers are unaffected): {exc}", file=sys.stderr)
    return counts
