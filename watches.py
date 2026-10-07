"""Price alerts per product: "tell me when this gets cheaper".

A chat follows a product from the button on the web's product page (a t.me link with ``?start=seguir_<store>_<sku>``) or
with the bot's commands. On every scan ``check`` compares the follow with the product's current price and sends one
message when it dropped:

* at or below the chat's own target (``/precio <n> <monto>``), or
* if there is no target, at least ``DROP_PCT`` % below the price when the chat started following.

No repeats: after an alert the next one needs a lower price; if the price goes back up the alert is armed again.
Pure decision (``decide``) apart from the Supabase reads/writes and the Telegram send, so it is unit tested.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone

from supabase_sync import SupabaseSync, log_failure

DROP_PCT = 5
MAX_WATCHES_PER_CHAT = 30
FRESH_HOURS = 24        # a product not seen for this long is not alerted about (it may be gone)
PAYLOAD_PREFIX = "seguir_"
_PAYLOAD = re.compile(r"^seguir_([a-z0-9]+)_([A-Za-z0-9_-]{1,40})$")


def parse_payload(payload: str | None) -> str | None:
    """"seguir_falabella_12345" -> "falabella:12345" (the /start deep link); None for anything else."""
    match = _PAYLOAD.match((payload or "").strip())
    return f"{match.group(1)}:{match.group(2)}" if match else None


def threshold(watch: dict) -> int:
    """The price at or below which the chat wants to be told."""
    if watch.get("target_price"):
        return int(watch["target_price"])
    return int(watch["baseline_price"] * (100 - DROP_PCT) / 100)


def decide(watch: dict, price: int) -> str:
    """"alert" (send now), "rearm" (price went back up: forget the last alert) or "" (nothing to do)."""
    if price <= threshold(watch):
        last = watch.get("last_notified_price")
        return "alert" if last is None or price < last else ""
    return "rearm" if watch.get("last_notified_price") is not None else ""


def _clp(value) -> str:
    return "$" + f"{int(value):,}".replace(",", ".")


def alert_text(watch: dict, product: dict) -> str:
    price = int(product["price"])
    since = int(watch["baseline_price"])
    lines = [f"📉 Bajó de precio: {product['title'][:90]}", ""]
    lines.append(f"Ahora {_clp(price)} (cuando lo seguiste: {_clp(since)}).")
    if price < since:
        lines.append(f"Es {_clp(since - price)} menos ({round((since - price) / since * 100)}%).")
    lines += ["", product["url"], "", f"/dejar {watch['id']} para dejar de seguirlo."]
    return "\n".join(lines)


def follow(store: SupabaseSync, chat_id: int, product_id: str) -> str:
    """Start following a product. Returns the reply for the chat."""
    product = store.get_product(product_id)
    if product is None:
        return "No encuentro ese producto. Puede que ya no esté en nuestras listas."
    existing = store.chat_watches(chat_id)
    if any(w["product_id"] == product_id for w in existing):
        return f"Ya sigues este producto ({_clp(product['price'])} hoy). /siguiendo para ver tu lista."
    if len(existing) >= MAX_WATCHES_PER_CHAT:
        return f"Ya sigues {MAX_WATCHES_PER_CHAT} productos, el máximo. Quita alguno con /dejar y vuelve a intentarlo."
    store.add_watch(chat_id, product_id, int(product["price"]))
    return (
        f"Listo, sigo este producto: {product['title'][:80]}\n"
        f"Hoy está a {_clp(product['price'])}. Te aviso si baja un {DROP_PCT}% o más.\n"
        "Si quieres otro precio: /siguiendo para ver el número y /precio <número> <monto>."
    )


def list_text(watches: list[dict], products: dict[str, dict]) -> str:
    if not watches:
        return "No sigues ningún producto. Usa el botón «Avísame si baja» de la ficha en la web."
    lines = ["Productos que sigues:", ""]
    for watch in watches:
        product = products.get(watch["product_id"])
        title = product["title"][:55] if product else watch["product_id"]
        now = _clp(product["price"]) if product else "?"
        goal = f"avisa a {_clp(threshold(watch))}" if watch.get("target_price") else f"avisa a {_clp(threshold(watch))} (-{DROP_PCT}%)"
        lines.append(f"{watch['id']}. {title} — hoy {now}, {goal}")
    lines += ["", "/dejar <número> — dejar de seguir", "/precio <número> <monto> — avisar a otro precio"]
    return "\n".join(lines)


def command(store: SupabaseSync, chat_id: int, name: str, args: str) -> str:
    """/siguiendo, /dejar <n>, /precio <n> <monto>. Returns the reply."""
    watches = store.chat_watches(chat_id)
    if name == "/siguiendo":
        products = store.products_by_ids([w["product_id"] for w in watches])
        return list_text(watches, products)

    parts = args.split()
    mine = {str(w["id"]): w for w in watches}
    if name == "/dejar":
        if len(parts) != 1 or parts[0] not in mine:
            return "Escribe /dejar <número> con el número que ves en /siguiendo."
        store.deactivate_watch(int(parts[0]))
        return "Listo, dejé de seguirlo."
    if name == "/precio":
        amount = parts[1].replace(".", "").replace("$", "") if len(parts) == 2 else ""
        if len(parts) != 2 or parts[0] not in mine or not amount.isdigit() or int(amount) <= 0:
            return "Escribe /precio <número> <monto>, por ejemplo /precio 3 49990 (el número está en /siguiendo)."
        store.set_watch_target(int(parts[0]), int(amount))
        return f"Listo, te aviso cuando esté a {_clp(int(amount))} o menos."
    return ""


def check(store: SupabaseSync | None, send, now: datetime | None = None) -> int:
    """Alert the chats whose followed products dropped. ``send(chat_id, text) -> bool``. Never raises. Returns alerts sent."""
    if store is None:
        return 0
    now = now or datetime.now(timezone.utc)
    sent = 0
    try:
        watches = store.active_watches()
        if not watches:
            return 0
        products = store.products_by_ids(sorted({w["product_id"] for w in watches}))
        fresh_after = now - timedelta(hours=FRESH_HOURS)
        for watch in watches:
            product = products.get(watch["product_id"])
            if product is None:
                continue
            seen = datetime.fromisoformat(str(product["last_seen_at"]).replace("Z", "+00:00"))
            if seen < fresh_after:
                continue
            verdict = decide(watch, int(product["price"]))
            if verdict == "rearm":
                store.set_watch_notified(watch["id"], None)
            elif verdict == "alert" and send(int(watch["chat_id"]), alert_text(watch, product)):
                store.set_watch_notified(watch["id"], int(product["price"]))
                sent += 1
    except Exception as exc:
        log_failure("check price alerts", exc)
    if sent:
        print(f"Price alerts: {sent} sent", file=sys.stderr)
    return sent
