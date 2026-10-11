"""The feed view is rebuilt at most every 45 minutes, and never by the browser tier (disk IO budget)."""
from datetime import datetime, timedelta, timezone

import main_fast
from main_fast import feed_refresh_due, refresh_feed_if_due

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def ago(minutes):
    return (NOW - timedelta(minutes=minutes)).isoformat()


def test_due_rules():
    assert feed_refresh_due(None, NOW, "") is True
    assert feed_refresh_due("basura", NOW, "http") is True
    assert feed_refresh_due(ago(15), NOW, "http") is False
    assert feed_refresh_due(ago(30), NOW, "http") is False
    assert feed_refresh_due(ago(44), NOW, "http") is True      # runs are 15 min apart: 44 min counts as 45
    assert feed_refresh_due(ago(600), NOW, "browser") is False


class Mirror:
    def __init__(self, last=None):
        self.state = {} if last is None else {main_fast.FEED_REFRESH_KEY: last}
        self.refreshed = 0

    def get_bot_state(self, key):
        return self.state.get(key)

    def set_bot_state(self, key, value):
        self.state[key] = value

    def refresh_feed(self):
        self.refreshed += 1


def test_refreshes_when_due_and_remembers(monkeypatch):
    monkeypatch.setenv("SCAN_TIER", "http")
    mirror = Mirror(ago(60))
    assert refresh_feed_if_due(mirror, NOW) is True and mirror.refreshed == 1
    assert mirror.state[main_fast.FEED_REFRESH_KEY] == NOW.isoformat()
    assert refresh_feed_if_due(mirror, NOW + timedelta(minutes=15)) is False and mirror.refreshed == 1


def test_browser_tier_never_refreshes(monkeypatch):
    monkeypatch.setenv("SCAN_TIER", "browser")
    mirror = Mirror()
    assert refresh_feed_if_due(mirror, NOW) is False and mirror.refreshed == 0
