"""Subscriber filters, the safe-mode switch and the daily digest."""
import json
from datetime import datetime, timezone

import pytest

import digest
import mode
import notifier
import prefs
from models import Deal, ScoredDeal

STORES = {"falabella", "sodimac", "hites"}


def scored(title="Notebook Lenovo 15", store="falabella", pct=50.0, price_error=None):
    deal = Deal("x:1", title, "https://s/1", store, "", 100_000, 200_000, pct, "2026-10-05T00:00:00Z")
    return ScoredDeal(deal, pct, [], verified_pct=pct, price_error=price_error)


# ---- filters -----------------------------------------------------------------------------------------------

def test_no_filters_lets_everything_through():
    assert prefs.matches(scored(), None) and prefs.matches(scored(), {})


def test_category_store_and_minimum_filters():
    tech = scored("Notebook Lenovo 15 pulgadas")
    assert prefs.matches(tech, {"groups": ["tecnologia"]})
    assert not prefs.matches(tech, {"groups": ["mascotas"]})
    assert not prefs.matches(tech, {"stores": ["sodimac"]})
    assert prefs.matches(tech, {"stores": ["falabella", "sodimac"]})
    assert prefs.matches(tech, {"min_pct": 50}) and not prefs.matches(tech, {"min_pct": 60})


def test_a_possible_price_mistake_always_passes():
    assert prefs.matches(scored(price_error="missing digit", pct=30), {"groups": ["mascotas"], "min_pct": 90})


# ---- commands ----------------------------------------------------------------------------------------------

def test_categorias_sets_and_resets():
    new, reply = prefs.apply_command("/categorias", "tecnologia, mascotas", {}, STORES)
    assert new["groups"] == ["tecnologia", "mascotas"] and "Tecnología" in reply
    cleared, _ = prefs.apply_command("/categorias", "todas", new, STORES)
    assert "groups" not in cleared


def test_categorias_unknown_word_changes_nothing():
    new, reply = prefs.apply_command("/categorias", "tecnologia zzz", {"min_pct": 30}, STORES)
    assert new == {"min_pct": 30} and "zzz" in reply


def test_tiendas_and_minimo():
    new, _ = prefs.apply_command("/tiendas", "Falabella sodimac", {}, STORES)
    assert new["stores"] == ["falabella", "sodimac"]
    assert prefs.apply_command("/tiendas", "nada", {}, STORES)[0] == {}
    new, _ = prefs.apply_command("/minimo", "40%", new, STORES)
    assert new["min_pct"] == 40
    assert "min_pct" not in prefs.apply_command("/minimo", "0", new, STORES)[0]
    assert prefs.apply_command("/minimo", "abc", {}, STORES)[0] == {}
    assert prefs.apply_command("/minimo", "150", {}, STORES)[0] == {}


def test_mis_describes_the_filters():
    _, reply = prefs.apply_command("/mis", "", {"groups": ["mascotas"], "min_pct": 40}, STORES)
    assert "Mascotas" in reply and "40%" in reply


# ---- sending -------------------------------------------------------------------------------------------------

def test_each_subscriber_only_gets_what_they_asked_for(monkeypatch):
    sent = []
    monkeypatch.setattr(notifier, "_send_one", lambda s, token, chat, alerts, *a, **k: sent.append((chat, s.deal.title)) or "text")
    monkeypatch.setattr(notifier, "SUBSCRIBER_DELAY_SECONDS", 0)
    deals = [scored("Notebook Lenovo 15 pulgadas"), scored("Alimento perro adulto 15 kg")]
    notifier._send_to_subscribers(
        deals, "tok", ["1", "2"], set(), None, 40.0, {"1": {"groups": ["mascotas"]}}
    )
    by_chat = {chat: [t for c, t in sent if c == chat] for chat in ("1", "2")}
    assert by_chat["1"] == ["Alimento perro adulto 15 kg"]
    assert sorted(by_chat["2"]) == ["Alimento perro adulto 15 kg", "Notebook Lenovo 15 pulgadas"]


# ---- safe mode ---------------------------------------------------------------------------------------------------

def test_mode_reads_the_file_and_the_override(tmp_path, monkeypatch):
    path = tmp_path / "mode.json"
    monkeypatch.delenv("BOT_MODE", raising=False)
    assert mode.current(path) == "normal"                      # missing file
    path.write_text(json.dumps({"mode": "safe"}))
    assert mode.is_safe(path)
    monkeypatch.setenv("BOT_MODE", "normal")
    assert not mode.is_safe(path)                              # the variable wins
    monkeypatch.delenv("BOT_MODE")
    path.write_text("{broken")
    assert mode.current(path) == "normal"
    path.write_text(json.dumps({"mode": "weird"}))
    assert mode.current(path) == "normal"


def test_the_repository_ships_in_normal_mode(monkeypatch):
    monkeypatch.delenv("BOT_MODE", raising=False)
    assert mode.current() == "normal"


# ---- digest -----------------------------------------------------------------------------------------------------

NOON_UTC = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)      # 12:00 in Santiago
EARLY_UTC = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)      # 06:00 in Santiago


def test_the_digest_is_due_once_per_day_after_nine():
    assert digest.is_due(NOON_UTC, None)
    assert digest.is_due(NOON_UTC, "2026-10-04")
    assert not digest.is_due(NOON_UTC, "2026-10-05")
    assert not digest.is_due(EARLY_UTC, None)


def test_digest_text_lists_the_offers():
    rows = [{"title": "Notebook X", "store": "falabella", "price": 199990, "url": "https://s/1", "verified_pct": 61.4, "web_discount_pct": 50}]
    text = digest.build_text(rows, NOON_UTC)
    assert "-61% Notebook X" in text and "$199.990" in text and "https://s/1" in text
    assert digest.build_text([], NOON_UTC) is None


class FakeStore:
    def __init__(self, rows):
        self.rows, self.state = rows, {}

    def get_bot_state(self, key):
        return self.state.get(key)

    def set_bot_state(self, key, value):
        self.state[key] = value

    def _get_rows(self, table, params):
        return self.rows


def test_run_if_due_sends_once_and_remembers(monkeypatch):
    sent = []
    monkeypatch.setattr(digest, "send_alert", lambda text, chat_id=None: sent.append(chat_id) or True)
    monkeypatch.delenv("TELEGRAM_PUBLIC_CHAT_ID", raising=False)
    store = FakeStore([{"title": "A", "store": "s", "price": 1000, "url": "u", "verified_pct": 50, "web_discount_pct": 50}])
    assert digest.run_if_due(store, NOON_UTC) is True
    assert store.state["digest:last"] == "2026-10-05"
    assert digest.run_if_due(store, NOON_UTC) is False and len(sent) == 1


def test_a_failed_send_is_retried_and_errors_never_raise(monkeypatch):
    monkeypatch.setattr(digest, "send_alert", lambda text, chat_id=None: False)
    store = FakeStore([{"title": "A", "store": "s", "price": 1000, "url": "u", "verified_pct": 50, "web_discount_pct": 50}])
    assert digest.run_if_due(store, NOON_UTC) is False and "digest:last" not in store.state

    class Broken(FakeStore):
        def get_bot_state(self, key):
            raise RuntimeError("down")

    assert digest.run_if_due(Broken([]), NOON_UTC) is False
    assert digest.run_if_due(None) is False
