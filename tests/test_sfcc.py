import pytest

from models import Deal
from sources import health, sfcc
from sources.health import NoResultsError


def deal(deal_id: str) -> Deal:
    return Deal(
        id=deal_id, title="t", url="https://x/" + deal_id, store="s", category="c", price=10,
        list_price=10, discount_pct=0.0, scraped_at="2026-10-01T00:00:00+00:00",
    )


@pytest.fixture(autouse=True)
def clean_health():
    health.drain()
    yield
    health.drain()


def test_run_queries_merges_results_and_deduplicates_across_queries():
    results = {"a": [deal("s:1"), deal("s:2")], "b": [deal("s:2"), deal("s:3")]}
    found = sfcc.run_queries("s", ["a", "b"], lambda q: results[q])
    assert sorted(d.id for d in found) == ["s:1", "s:2", "s:3"]


def test_an_empty_query_is_recorded_as_empty_not_as_an_error(capsys):
    def scan(query):
        if query == "redken":
            raise NoResultsError("no results")
        return [deal("s:1")]

    found = sfcc.run_queries("s", ["notebook", "redken"], scan)

    assert [d.id for d in found] == ["s:1"]
    events = health.drain()
    assert [(e["kind"], e["message"]) for e in events] == [("empty", "redken")]
    assert "redken" not in capsys.readouterr().err


def test_real_failures_are_warned_and_do_not_stop_the_other_queries():
    def scan(query):
        if query == "bad":
            raise RuntimeError("HTTP 500")
        return [deal("s:1")]

    found = sfcc.run_queries("s", ["bad", "good"], scan)

    assert len(found) == 1
    events = health.drain()
    assert events[0]["kind"] == "error" and "bad" in events[0]["message"] and "HTTP 500" in events[0]["message"]


def test_raises_only_when_every_query_failed():
    def scan(query):
        raise RuntimeError("down")

    with pytest.raises(RuntimeError, match="All s queries failed"):
        sfcc.run_queries("s", ["a", "b"], scan)


def test_all_queries_empty_returns_nothing_without_raising_so_the_report_can_flag_it():
    def scan(query):
        raise NoResultsError("none")

    assert sfcc.run_queries("s", ["a", "b"], scan) == []
    assert [e["kind"] for e in health.drain()] == ["empty", "empty"]


def test_queries_run_concurrently():
    import threading
    import time

    active = {"now": 0, "max": 0}
    lock = threading.Lock()

    def scan(query):
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.05)
        with lock:
            active["now"] -= 1
        return [deal("s:" + query)]

    sfcc.run_queries("s", [str(i) for i in range(8)], scan, workers=4)
    assert active["max"] > 1


def test_no_queries_returns_empty():
    assert sfcc.run_queries("s", [], lambda q: []) == []
