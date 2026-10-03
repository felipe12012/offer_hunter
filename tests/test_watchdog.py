from datetime import datetime, timezone

import watchdog


def test_is_stale_uses_the_age_of_the_last_run():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    assert watchdog.is_stale("2026-01-01T11:00:00Z", now, 40) is True    # 60 min ago
    assert watchdog.is_stale("2026-01-01T11:30:00Z", now, 40) is False   # 30 min ago
    assert watchdog.is_stale("", now, 40) is True                        # unparseable = treat as stalled


def test_dropped_stores_flags_a_store_that_went_to_zero():
    runs = [
        {"per_store": {"a": 5, "b": 0, "c": 2}},   # newest
        {"per_store": {"a": 4, "b": 3, "c": 0}},   # previous
    ]

    assert watchdog.dropped_stores(runs) == ["b"]   # b: 3 -> 0 (c was already 0)


def test_dropped_stores_needs_two_runs_and_ignores_new_stores():
    assert watchdog.dropped_stores([{"per_store": {"a": 0}}]) == []
    # "d" is new this run and zero; it was absent before, so it is not a drop.
    runs = [{"per_store": {"a": 1, "d": 0}}, {"per_store": {"a": 2}}]
    assert watchdog.dropped_stores(runs) == []


def test_supabase_runs_selects_the_real_column_names(monkeypatch):
    """Regression: it asked for `created_at`, which offer_scan_runs does not have
    (the column is `started_at`), so the call failed and the store check never ran."""
    monkeypatch.setenv("SUPABASE_URL", "https://p.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_x")
    seen = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"started_at": "2026-10-03T00:00:00Z", "per_store": {"a": 1}}]

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["params"] = params
        return Response()

    monkeypatch.setattr(watchdog.requests, "get", fake_get)

    assert watchdog._supabase_runs() == [{"started_at": "2026-10-03T00:00:00Z", "per_store": {"a": 1}}]
    assert seen["params"]["select"] == "started_at,per_store"
    assert seen["params"]["order"] == "started_at.desc"
    assert "created_at" not in str(seen["params"])


def test_supabase_runs_is_empty_when_not_configured_and_none_when_the_query_fails(monkeypatch, capsys):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert watchdog._supabase_runs() == []                     # optional check: nothing to do

    monkeypatch.setenv("SUPABASE_URL", "https://p.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_x")

    def boom(*args, **kwargs):
        raise watchdog.requests.ConnectionError("dns")

    monkeypatch.setattr(watchdog.requests, "get", boom)
    assert watchdog._supabase_runs() is None                   # configured but broken: say so
    assert "could not read offer_scan_runs" in capsys.readouterr().err


def test_main_exits_red_without_a_telegram_alert_when_the_store_check_cannot_run(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(watchdog, "_last_run", lambda repo, token: {"created_at": datetime.now(timezone.utc).isoformat()})
    monkeypatch.setattr(watchdog, "_supabase_runs", lambda limit=3: None)
    sent = []
    monkeypatch.setattr(watchdog, "_notify", lambda text: sent.append(text))

    assert watchdog.main() == 1
    assert sent == []
