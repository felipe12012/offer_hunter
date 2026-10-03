import threading

from reports import StoreReport, build_report, format_log, store_transitions, to_json, to_markdown
from sources import health


def ev(kind, message="m", store="falabella"):
    return {"store": store, "kind": kind, "message": message}


# ---- health collector ------------------------------------------------------

def test_health_collects_events_per_store_and_drain_clears_them():
    health.drain()
    health.warn("hites", "hites query 'x' failed: boom")
    health.empty("hites", "kerastase")
    health.warn("ahumada", "ahumada keyword 'y' failed: boom")

    events = health.drain()

    assert [(e["store"], e["kind"]) for e in events] == [("hites", "error"), ("hites", "empty"), ("ahumada", "error")]
    assert health.drain() == []


def test_health_is_safe_to_call_from_several_threads():
    health.drain()
    threads = [threading.Thread(target=lambda i=i: health.warn("s", f"e{i}")) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(health.drain()) == 50


def test_empty_results_are_recorded_but_not_printed(capsys):
    health.drain()
    health.empty("hites", "redken")
    health.warn("hites", "real problem")
    health.drain()
    err = capsys.readouterr().err
    assert "real problem" in err and "redken" not in err


def test_no_results_error_is_a_runtime_error_so_existing_handlers_still_catch_it():
    assert issubclass(health.NoResultsError, RuntimeError)


# ---- classification ---------------------------------------------------------

def test_status_ok_when_there_are_deals_and_no_errors():
    assert build_report("falabella", 100, 5.0, []).status == "ok"


def test_status_partial_when_deals_arrived_but_some_queries_failed():
    report = build_report("hites", 50, 5.0, [ev("error", "q1 failed"), ev("error", "q2 failed")])
    assert report.status == "partial"
    assert report.errors == ["q1 failed", "q2 failed"]


def test_status_failed_when_the_scraper_raised():
    report = build_report("ahumada", 0, 5.0, [], raised=RuntimeError("All Ahumada keywords failed"))
    assert report.status == "failed"
    assert "All Ahumada keywords failed" in report.detail


def test_status_failed_when_no_deals_and_errors_were_logged():
    assert build_report("x", 0, 5.0, [ev("error", "boom")]).status == "failed"


def test_status_timeout_wins_over_everything_else():
    assert build_report("hites", 0, 420.0, [ev("error")], timed_out=True).status == "timeout"


def test_status_empty_when_no_deals_and_no_errors_which_is_suspicious():
    report = build_report("vans", 0, 3.0, [ev("empty", "zapatillas")])
    assert report.status == "empty"
    assert report.empty_queries == 1


def test_empty_queries_alone_do_not_degrade_a_store_that_delivered_deals():
    report = build_report("hites", 3900, 60.0, [ev("empty", "kerastase"), ev("empty", "redken")])
    assert report.status == "ok" and report.empty_queries == 2


def test_disabled_store_report():
    report = StoreReport(store="paris", status="disabled")
    assert report.status == "disabled" and report.deals == 0


# ---- output formats ----------------------------------------------------------

def sample():
    return [
        build_report("falabella", 14926, 41.2, []),
        build_report("hites", 3922, 63.0, [ev("error", "hites query 'fila' failed: x" + "y" * 400, "hites"), ev("empty", "redken", "hites")]),
        build_report("ahumada", 0, 5.0, [], raised=RuntimeError("All Farmacias Ahumada keywords failed")),
        StoreReport(store="paris", status="disabled"),
    ]


def test_to_json_is_compact_and_truncates_long_messages():
    data = to_json(sample())
    assert data["falabella"] == {"status": "ok", "deals": 14926, "seconds": 41.2, "empty_queries": 0, "errors": []}
    assert len(data["hites"]["errors"][0]) <= 200
    assert data["ahumada"]["status"] == "failed"
    assert data["paris"]["status"] == "disabled"


def test_to_json_keeps_at_most_three_errors_per_store():
    reports = [build_report("s", 5, 1.0, [ev("error", f"e{i}", "s") for i in range(10)])]
    assert len(to_json(reports)["s"]["errors"]) == 3


def test_format_log_lists_every_store_with_status_count_and_problems():
    text = format_log(sample())
    assert "falabella" in text and "14926" in text
    assert "hites" in text and "partial" in text.lower()
    assert "ahumada" in text and "FAILED" in text.upper()
    assert "paris" in text and "disabled" in text.lower()


def test_markdown_summary_contains_a_table_and_the_problem_details():
    md = to_markdown(sample())
    assert md.count("|") > 10
    assert "| falabella |" in md
    assert "All Farmacias Ahumada keywords failed" in md


# ---- transitions -------------------------------------------------------------

def test_a_store_is_reported_down_on_its_second_consecutive_bad_run_only():
    cur = {"hites": "failed", "vans": "ok"}
    assert store_transitions(cur, [{"hites": "failed"}, {"hites": "ok"}]) == (["hites"], [])
    assert store_transitions(cur, [{"hites": "ok"}, {"hites": "ok"}]) == ([], [])             # first bad run: wait
    assert store_transitions(cur, [{"hites": "failed"}, {"hites": "failed"}]) == ([], [])     # already alerted


def test_a_store_is_reported_recovered_after_having_been_down():
    cur = {"hites": "ok"}
    assert store_transitions(cur, [{"hites": "failed"}, {"hites": "timeout"}]) == ([], ["hites"])
    assert store_transitions(cur, [{"hites": "failed"}, {"hites": "ok"}]) == ([], [])         # one-run blip: stay quiet


def test_transitions_ignore_unknown_history_and_disabled_stores():
    assert store_transitions({"hites": "failed"}, []) == ([], [])
    assert store_transitions({"paris": "disabled"}, [{"paris": "disabled"}, {"paris": "disabled"}]) == ([], [])
    assert store_transitions({"hites": "failed"}, [None, None]) == ([], [])


def test_partial_counts_as_healthy_for_alerting():
    assert store_transitions({"hites": "partial"}, [{"hites": "failed"}, {"hites": "failed"}]) == ([], ["hites"])
