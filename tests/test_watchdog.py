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
