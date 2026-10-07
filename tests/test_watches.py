"""Price alerts per product: the decision, the bot commands and the check on every scan."""
from datetime import datetime, timedelta, timezone

import pytest

import subscribers
import watches
from watches import decide, parse_payload, threshold

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def watch(**overrides):
    base = {"id": 1, "chat_id": 10, "product_id": "falabella:1", "baseline_price": 100_000,
            "target_price": None, "last_notified_price": None}
    return {**base, **overrides}


# ---- the decision ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("payload,expected", [
    ("seguir_falabella_12345", "falabella:12345"),
    ("seguir_hites_10052004071002", "hites:10052004071002"),
    ("seguir_sodimac_a-b_c", "sodimac:a-b_c"),
    ("seguir_", None), ("hola", None), ("", None), (None, None), ("seguir_Falabella_1", None), ("seguir_falabella_1 2", None),
])
def test_deep_link_payloads(payload, expected):
    assert parse_payload(payload) == expected


def test_default_threshold_is_five_percent_below_the_starting_price_and_target_wins():
    assert threshold(watch()) == 95_000
    assert threshold(watch(target_price=80_000)) == 80_000


def test_alerts_only_when_the_price_dropped_enough():
    assert decide(watch(), 96_000) == ""
    assert decide(watch(), 95_000) == "alert"
    assert decide(watch(target_price=80_000), 90_000) == ""
    assert decide(watch(target_price=80_000), 79_990) == "alert"


def test_no_repeat_alerts_until_the_price_drops_further_or_goes_back_up():
    notified = watch(last_notified_price=90_000)
    assert decide(notified, 90_000) == ""            # same price: already told
    assert decide(notified, 85_000) == "alert"       # lower: tell again
    assert decide(notified, 99_000) == "rearm"       # back up: forget, so the next drop alerts
    assert decide(watch(), 99_000) == ""             # never notified and above: nothing


# ---- a fake store -----------------------------------------------------------------------------------------------

class FakeStore:
    def __init__(self, products=(), watch_rows=()):
        self.products = {p["id"]: p for p in products}
        self.watch_rows = [dict(w) for w in watch_rows]
        self.next_id = 100
        self.upserted_subscribers = []

    def get_product(self, product_id):
        return self.products.get(product_id)

    def products_by_ids(self, ids):
        return {i: self.products[i] for i in ids if i in self.products}

    def chat_watches(self, chat_id):
        return [w for w in self.watch_rows if w["chat_id"] == chat_id and w.get("active", True)]

    def active_watches(self):
        return [w for w in self.watch_rows if w.get("active", True)]

    def add_watch(self, chat_id, product_id, price):
        self.next_id += 1
        self.watch_rows.append({"id": self.next_id, "chat_id": chat_id, "product_id": product_id, "baseline_price": price,
                                "target_price": None, "last_notified_price": None, "active": True})

    def _by_id(self, watch_id):
        return next(w for w in self.watch_rows if w["id"] == watch_id)

    def deactivate_watch(self, watch_id):
        self._by_id(watch_id)["active"] = False

    def set_watch_target(self, watch_id, target):
        row = self._by_id(watch_id)
        row["target_price"], row["last_notified_price"] = target, None

    def set_watch_notified(self, watch_id, price):
        self._by_id(watch_id)["last_notified_price"] = price

    def upsert_subscriber(self, *args):
        self.upserted_subscribers.append(args)


def product(price, pid="falabella:1", seen=NOW - timedelta(minutes=10)):
    return {"id": pid, "title": "Notebook X", "url": "https://s/1", "price": price, "last_seen_at": seen.isoformat()}


# ---- following and the commands -------------------------------------------------------------------------------

def test_following_a_product_records_today_s_price():
    store = FakeStore([product(100_000)])
    reply = watches.follow(store, 10, "falabella:1")
    assert "$100.000" in reply and store.watch_rows[0]["baseline_price"] == 100_000


def test_following_twice_or_an_unknown_product_or_too_many():
    store = FakeStore([product(100_000)])
    watches.follow(store, 10, "falabella:1")
    assert "Ya sigues" in watches.follow(store, 10, "falabella:1") and len(store.watch_rows) == 1
    assert "No encuentro" in watches.follow(store, 10, "falabella:999")
    full = FakeStore([product(1, f"falabella:{i}") for i in range(31)])
    for i in range(watches.MAX_WATCHES_PER_CHAT):
        watches.follow(full, 10, f"falabella:{i}")
    assert "máximo" in watches.follow(full, 10, "falabella:30")


def test_siguiendo_dejar_and_precio():
    store = FakeStore([product(100_000)])
    watches.follow(store, 10, "falabella:1")
    watch_id = store.watch_rows[0]["id"]

    assert "Notebook X" in watches.command(store, 10, "/siguiendo", "")
    assert "$49.990" in watches.command(store, 10, "/precio", f"{watch_id} 49.990")
    assert store.watch_rows[0]["target_price"] == 49_990
    assert "Escribe /precio" in watches.command(store, 10, "/precio", f"{watch_id} abc")
    assert "Escribe /dejar" in watches.command(store, 99, "/dejar", str(watch_id))      # someone else's watch
    assert "dejé de seguirlo" in watches.command(store, 10, "/dejar", str(watch_id))
    assert "No sigues ningún" in watches.command(store, 10, "/siguiendo", "")


# ---- the bot ------------------------------------------------------------------------------------------------------

def start_message(text, chat_id=10):
    return {"update_id": 1, "message": {"chat": {"id": chat_id, "type": "private"}, "text": text, "from": {"first_name": "Ana"}}}


def test_the_deep_link_follows_the_product_without_subscribing(monkeypatch):
    sent = []
    monkeypatch.setattr(subscribers, "_call", lambda token, method, **kw: sent.append(kw["text"]))
    store = FakeStore([product(100_000)])
    assert subscribers.handle_update(start_message("/start seguir_falabella_1"), store, "tok") is None
    assert store.upserted_subscribers == []                      # not signed up to every offer
    assert store.watch_rows and "Hoy está a $100.000" in sent[0]


def test_a_plain_start_still_subscribes(monkeypatch):
    monkeypatch.setattr(subscribers, "_call", lambda *a, **k: None)
    store = FakeStore()
    assert subscribers.handle_update(start_message("/start"), store, "tok") == "subscribed"


# ---- the check on every scan ----------------------------------------------------------------------------------------

def run_check(store):
    sent = []
    count = watches.check(store, lambda chat, text: sent.append((chat, text)) or True, NOW)
    return count, sent


def test_a_drop_sends_one_alert_and_is_not_repeated():
    store = FakeStore([product(90_000)], [watch()])
    count, sent = run_check(store)
    assert count == 1 and sent[0][0] == 10 and "$90.000" in sent[0][1] and "$100.000" in sent[0][1]
    assert store.watch_rows[0]["last_notified_price"] == 90_000
    assert run_check(store)[0] == 0


def test_a_price_that_went_back_up_rearms_the_alert():
    store = FakeStore([product(99_000)], [watch(last_notified_price=90_000)])
    assert run_check(store)[0] == 0 and store.watch_rows[0]["last_notified_price"] is None
    store.products["falabella:1"] = product(92_000)
    assert run_check(store)[0] == 1


def test_a_product_not_seen_for_a_day_gets_no_alert():
    store = FakeStore([product(50_000, seen=NOW - timedelta(hours=30))], [watch()])
    assert run_check(store)[0] == 0


def test_a_failed_send_is_retried_next_scan():
    store = FakeStore([product(90_000)], [watch()])
    assert watches.check(store, lambda chat, text: False, NOW) == 0
    assert store.watch_rows[0]["last_notified_price"] is None
    assert run_check(store)[0] == 1


def test_check_never_raises_and_does_nothing_without_supabase():
    class Broken(FakeStore):
        def active_watches(self):
            raise RuntimeError("down")

    assert watches.check(Broken(), lambda c, t: True, NOW) == 0
    assert watches.check(None, lambda c, t: True, NOW) == 0
