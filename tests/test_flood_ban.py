"""A Telegram flood ban (HTTP 429 with hours to wait) must stop the sending, survive between runs and not fail the run."""
from datetime import datetime, timedelta, timezone

import pytest

import main_fast
import notifier
from notifier import send_offers
from tests.test_notifier import FakeResponse, make_scored

NOW = datetime(2026, 10, 5, 17, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(notifier, "RATE_LIMITED", {})
    monkeypatch.setattr("notifier.time.sleep", lambda s: None)


def test_a_long_ban_stops_the_sending_without_hammering_telegram(monkeypatch):
    calls = []

    def post(url, json=None, data=None, files=None, timeout=None):
        calls.append(url)
        return FakeResponse(429, payload={"parameters": {"retry_after": 9000}})

    monkeypatch.setattr("notifier.requests.post", post)
    monkeypatch.setattr("notifier.requests.get", lambda url, **kw: FakeResponse(200))

    offers = [make_scored(f"sodimac:{i}") for i in range(10)]
    assert send_offers(offers, bot_token="tok", chat_id="123") == []
    assert notifier.RATE_LIMITED == {"123": 9000.0}
    assert len(calls) <= 2          # the first refusal ends it: no retries, no other offers tried


def test_a_short_wait_is_still_waited_out_and_retried(monkeypatch):
    answers = [FakeResponse(429, payload={"parameters": {"retry_after": 2}}), FakeResponse(200)]
    monkeypatch.setattr("notifier.requests.post", lambda *a, **k: answers.pop(0))
    monkeypatch.setattr("notifier.requests.get", lambda url, **kw: FakeResponse(200))
    assert len(send_offers([make_scored("sodimac:1")], bot_token="tok", chat_id="123")) == 1
    assert notifier.RATE_LIMITED == {}


def test_a_banned_chat_is_not_contacted_at_all(monkeypatch):
    notifier.RATE_LIMITED["123"] = 500.0
    monkeypatch.setattr("notifier.requests.post", lambda *a, **k: pytest.fail("must not call Telegram"))
    assert notifier.send_alert("hello", bot_token="tok", chat_id="123") is False


class FakeStore:
    def __init__(self, state=None):
        self.state = dict(state or {})

    def get_bot_state(self, key):
        return self.state.get(key)

    def set_bot_state(self, key, value):
        self.state[key] = value


def test_the_ban_is_saved_and_loaded_by_the_next_run(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(main_fast.SupabaseSync, "from_env", classmethod(lambda cls: store))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.delenv("TELEGRAM_ALERT_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_PUBLIC_CHAT_ID", raising=False)

    notifier.RATE_LIMITED["123"] = 9000.0
    main_fast.save_flood_bans(NOW)
    assert store.state["flood_until:123"] == (NOW + timedelta(seconds=9000)).isoformat()

    notifier.RATE_LIMITED.clear()
    main_fast.load_flood_bans(NOW + timedelta(seconds=1000))
    assert 7900 < notifier.RATE_LIMITED["123"] <= 8000

    notifier.RATE_LIMITED.clear()
    main_fast.load_flood_bans(NOW + timedelta(seconds=9500))     # expired
    assert notifier.RATE_LIMITED == {}
