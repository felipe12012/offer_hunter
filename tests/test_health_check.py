"""Heartbeats: the scans leave a mark and watch each other, because GitHub's schedules cannot be trusted."""
from datetime import datetime, timedelta, timezone

import pytest

import health_check
import main_fast
import main_hot
from health_check import evaluate

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def ago(minutes):
    return (NOW - timedelta(minutes=minutes)).isoformat()


def test_a_component_that_ran_recently_is_fine():
    alerts, unseen = evaluate({"hot": ago(10), "browser": ago(40)}, {}, NOW, "fast")
    assert alerts == [] and unseen == []


def test_a_component_silent_for_too_long_is_reported_with_what_to_do():
    alerts, _ = evaluate({"hot": ago(90), "browser": ago(10)}, {}, NOW, "fast")
    assert [name for name, _ in alerts] == ["hot"]
    text = alerts[0][1]
    assert "90 min" in text and "cron-job.org" in text and "hot.yml" in text


def test_the_browser_scan_has_a_longer_limit_than_the_hot_scan():
    alerts, _ = evaluate({"hot": ago(30), "browser": ago(60)}, {}, NOW, "fast")
    assert [name for name, _ in alerts] == ["hot"]       # 30 min is too long for hot; 60 is fine for browser


def test_nothing_is_said_twice_within_the_realert_window():
    beats = {"hot": ago(90), "browser": ago(10)}
    alerts, _ = evaluate(beats, {"hot": ago(60)}, NOW, "fast")
    assert alerts == []
    alerts, _ = evaluate(beats, {"hot": ago(health_check.REALERT_HOURS * 60 + 5)}, NOW, "fast")
    assert len(alerts) == 1


def test_a_component_never_seen_gets_a_grace_period_not_an_alert():
    alerts, unseen = evaluate({}, {}, NOW, "fast")
    assert alerts == [] and set(unseen) == {"hot", "browser"}


def test_a_watcher_does_not_check_itself():
    alerts, unseen = evaluate({"fast": ago(500)}, {}, NOW, "fast")
    assert all(name != "fast" for name, _ in alerts) and "fast" not in unseen


def test_the_hot_scan_watches_the_regular_scan():
    alerts, _ = evaluate({"fast": ago(120), "browser": ago(10)}, {}, NOW, "hot")
    assert [name for name, _ in alerts] == ["fast"]


# ---- reading and writing the marks ------------------------------------------------------------------------------

class FakeStore:
    def __init__(self, state=None):
        self.state = dict(state or {})

    def get_bot_state(self, key):
        return self.state.get(key)

    def set_bot_state(self, key, value):
        self.state[key] = value


def test_beat_writes_the_mark():
    store = FakeStore()
    health_check.beat(store, "hot", NOW)
    assert store.state == {"heartbeat:hot": NOW.isoformat()}


def test_check_sends_one_alert_and_remembers_it(monkeypatch):
    sent = []
    monkeypatch.setattr(health_check, "send_alert", lambda text: sent.append(text) or True)
    store = FakeStore({"heartbeat:hot": ago(90), "heartbeat:browser": ago(5)})

    assert len(health_check.check(store, "fast", NOW)) == 1
    assert len(sent) == 1 and store.state["alerted:hot"] == NOW.isoformat()
    assert health_check.check(store, "fast", NOW + timedelta(minutes=15)) == health_check.check(store, "fast", NOW + timedelta(minutes=15))
    assert len(sent) == 1       # the second look, 15 minutes later, stays quiet


def test_an_alert_that_could_not_be_sent_is_tried_again_next_time(monkeypatch):
    monkeypatch.setattr(health_check, "send_alert", lambda text: False)
    store = FakeStore({"heartbeat:hot": ago(90), "heartbeat:browser": ago(5)})
    health_check.check(store, "fast", NOW)
    assert "alerted:hot" not in store.state


def test_the_first_look_starts_the_clock(monkeypatch):
    monkeypatch.setattr(health_check, "send_alert", lambda text: pytest.fail("no alert on the first look"))
    store = FakeStore()
    assert health_check.check(store, "fast", NOW) == []
    assert store.state["heartbeat:hot"] == NOW.isoformat() and store.state["heartbeat:browser"] == NOW.isoformat()


def test_without_supabase_nothing_happens():
    health_check.beat(None, "hot")
    assert health_check.check(None, "fast") == []


def test_supabase_errors_never_break_the_run(monkeypatch):
    class Broken:
        def get_bot_state(self, key):
            raise RuntimeError("down")

        def set_bot_state(self, key, value):
            raise RuntimeError("down")

    health_check.beat(Broken(), "hot")
    assert health_check.check(Broken(), "fast") == []


# ---- the scans use it ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("tier,expected_beat,checks", [("", "fast", True), ("http", "fast", True), ("browser", "browser", False)])
def test_each_tier_leaves_its_own_mark_and_only_the_http_tier_checks(monkeypatch, tier, expected_beat, checks):
    calls = {"beats": [], "checks": []}
    monkeypatch.setenv("SCAN_TIER", tier)
    monkeypatch.setattr(main_fast.SupabaseSync, "from_env", classmethod(lambda cls: "STORE"))
    monkeypatch.setattr(main_fast.health_check, "beat", lambda store, name, now=None: calls["beats"].append(name))
    monkeypatch.setattr(main_fast.health_check, "check", lambda store, watcher, now=None: calls["checks"].append(watcher))

    main_fast.record_heartbeat()

    assert calls["beats"] == [expected_beat]
    assert calls["checks"] == (["fast"] if checks else [])
