"""Faster scans and scans that survive running out of time: keep-alive sessions, HTTP numbers,
partial results on timeout and priority categories read first."""
import threading
import time

import pytest
import requests

import main_fast
from models import Deal
from reports import build_report
from sources import httpclient, nextdata, progress
from tests.test_run_reporting import make_deal, patch_paths
from tests.test_workflow import _stub_all_sources


# ---- httpclient ----------------------------------------------------------------------------------

class FakeSession:
    instances: list = []

    def __init__(self):
        self.calls = []
        FakeSession.instances.append(self)

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, timeout))
        response = requests.Response()
        response.status_code = 503 if "fail" in url else 200
        response._content = b"ok"
        return response


@pytest.fixture
def fake_session(monkeypatch):
    FakeSession.instances = []
    monkeypatch.setattr(httpclient.requests, "Session", FakeSession)
    monkeypatch.setattr(httpclient, "_local", threading.local())
    return FakeSession


def test_a_thread_reuses_its_session_across_requests(fake_session):
    httpclient.get("https://shop.example/a")
    httpclient.get("https://shop.example/b")
    assert len(fake_session.instances) == 1
    assert [url for url, _ in fake_session.instances[0].calls] == ["https://shop.example/a", "https://shop.example/b"]


def test_each_thread_gets_its_own_session(fake_session):
    sessions = []

    def work():
        httpclient.get("https://shop.example/x")
        sessions.append(httpclient._local.session)

    threads = [threading.Thread(target=work) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len({id(s) for s in sessions}) == 3


def test_default_timeout_is_short(fake_session):
    httpclient.get("https://shop.example/a")
    assert fake_session.instances[0].calls[0][1] == httpclient.DEFAULT_TIMEOUT_SECONDS == 15


def test_stats_count_requests_errors_and_latency_per_host(fake_session):
    httpclient.get("https://www.falabella.com/a")
    httpclient.get("https://www.falabella.com/fail")
    httpclient.get("https://www.sodimac.cl/a")
    stats = httpclient.summary()
    assert stats["www.falabella.com"]["requests"] == 2 and stats["www.falabella.com"]["errors"] == 1
    assert stats["www.sodimac.cl"]["requests"] == 1
    assert {"p50", "p95", "seconds"} <= set(stats["www.falabella.com"])
    assert "www.falabella.com" in httpclient.format_summary()
    assert "| www.sodimac.cl |" in httpclient.to_markdown()


def test_a_connection_error_is_counted_and_still_raised(monkeypatch):
    class Boom(FakeSession):
        def get(self, url, headers=None, timeout=None):
            raise requests.ConnectionError("down")

    monkeypatch.setattr(httpclient.requests, "Session", Boom)
    monkeypatch.setattr(httpclient, "_local", threading.local())
    with pytest.raises(requests.ConnectionError):
        httpclient.get("https://shop.example/a")
    assert httpclient.summary()["shop.example"]["errors"] == 1


def test_no_stats_means_no_log_line():
    assert httpclient.format_summary() == "" and httpclient.to_markdown() == ""


# ---- progress ------------------------------------------------------------------------------------

def test_progress_collects_per_store_without_duplicates():
    progress.publish("falabella", [make_deal("falabella:1"), make_deal("falabella:2")])
    progress.publish("falabella", [make_deal("falabella:2"), make_deal("falabella:3")])
    assert sorted(d.id for d in progress.take("falabella")) == ["falabella:1", "falabella:2", "falabella:3"]
    assert progress.take("sodimac") == []


def test_progress_reset_clears_deals_and_the_stop_flag():
    progress.publish("falabella", [make_deal("falabella:1")])
    progress.stop()
    assert progress.stopped()
    progress.reset()
    assert progress.take("falabella") == [] and not progress.stopped()


# ---- scan_stores keeps what a store had read when it ran out of time ------------------------------

def test_a_store_that_overruns_keeps_the_products_it_already_read(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(main_fast, "SOURCE_TIMEOUT_SECONDS", 0.3)

    def slow_but_productive(watchlist):
        progress.publish("falabella", [make_deal("falabella:1"), make_deal("falabella:2")])
        time.sleep(1.5)
        return []

    _stub_all_sources(
        monkeypatch,
        fetch_falabella_deals=slow_but_productive,
        fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")],
    )

    deals, reports = main_fast.scan_stores({})

    by_store = {r.store: r for r in reports}
    assert by_store["falabella"].status == "partial"
    assert by_store["falabella"].deals == 2
    assert "no terminó en" in by_store["falabella"].detail and "2 productos" in by_store["falabella"].detail
    assert sorted(d.id for d in deals) == ["falabella:1", "falabella:2", "sodimac:1"]
    assert progress.stopped()  # the abandoned workers were told to wind down


def test_a_store_that_overruns_with_nothing_is_still_a_timeout(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(main_fast, "SOURCE_TIMEOUT_SECONDS", 0.2)

    def hang(watchlist):
        time.sleep(1.0)
        return []

    _stub_all_sources(monkeypatch, fetch_hites_deals=hang, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")])
    _, reports = main_fast.scan_stores({})
    assert {r.store: r.status for r in reports}["hites"] == "timeout"


def test_report_rules_for_timeouts():
    assert build_report("falabella", 0, 420.0, [], timed_out=True).status == "timeout"
    partial = build_report("falabella", 1500, 420.0, [], timed_out=True)
    assert partial.status == "partial" and "1500" in partial.detail


# ---- nextdata: priority first, publishes as it goes, stops when told ------------------------------

CFG = nextdata.StoreConfig(
    store="falabella",
    base_url="https://www.falabella.com",
    home_url="https://www.falabella.com/falabella-cl",
    search_url="https://www.falabella.com/falabella-cl/search?Ntt={query}",
    category_url="https://www.falabella.com/falabella-cl/category/{id}/{slug}",
    category_href_re=r"/category/(cat\d+)/([a-z\-]+)",
)
HOME = (
    '<a href="/category/cat1/hogar-y-jardin"></a><a href="/category/cat2/zapatillas-mujer"></a>'
    '<a href="/category/cat3/ferreteria"></a><a href="/category/cat4/tablets"></a>'
)
WATCHLIST = {
    "keywords": [],
    "scan": {
        "category_patterns": {"todo": ["hogar", "zapatillas", "ferreteria", "tablets"]},
        "deep_slugs": ["zapatillas-mujer", "tablets"],
        "max_category_pages": 1,
        "deep_pages": 1,
    },
}


def page_with(ids):
    return {
        "results": [
            {"productId": i, "displayName": f"Producto {i}", "url": f"/p/{i}",
             "prices": [{"type": "internetPrice", "price": ["1.000"]}, {"type": "normalPrice", "price": ["2.000"]}]}
            for i in ids
        ],
        "pagination": {"perPage": 48, "count": 1},
    }


def test_priority_categories_are_read_first(monkeypatch):
    monkeypatch.setattr(nextdata, "WORKERS", 1)  # one worker: the order of the requests is the order of the jobs
    order = []

    def fetch(url):
        order.append(url.rsplit("/", 1)[-1])
        return page_with([len(order)])

    nextdata.fetch_store_deals(CFG, WATCHLIST, fetch=fetch, fetch_home=lambda url: HOME, sleep=lambda s: None)

    assert order == ["zapatillas-mujer", "tablets", "hogar-y-jardin", "ferreteria"]


def test_each_finished_job_is_published_for_a_partial_result(monkeypatch):
    nextdata.fetch_store_deals(
        CFG, WATCHLIST, fetch=lambda url: page_with([url.rsplit("/", 1)[-1]]), fetch_home=lambda url: HOME,
        sleep=lambda s: None,
    )
    assert len(progress.take("falabella")) == 4


def test_a_stopped_scan_reads_no_more_pages():
    progress.stop()
    calls = []

    def fetch(url):
        calls.append(url)
        return page_with([1])

    deals = nextdata.scan_listing("https://www.falabella.com/x", CFG, "cat", 5, fetch=fetch, sleep=lambda s: None)
    assert calls == [] and deals == []
