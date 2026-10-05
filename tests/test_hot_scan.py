"""Cyber hot scan: discount-filtered listings, what is worth announcing at once, no double announcements."""
import json
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
import requests

import main_fast
import main_hot
from models import Deal
from sources import httpclient, nextdata
from supabase_sync import SupabaseSync
from tests.test_price_error import deal, history_of
from tests.test_run_reporting import patch_paths
from tests.test_scan_speed import CFG, HOME, WATCHLIST, page_with
from tests.test_workflow import _stub_all_sources


# ---- the discount-filtered listings ----------------------------------------------------------------

def test_the_facet_is_the_one_the_stores_use():
    facet = nextdata.discount_facet(70)
    assert facet.startswith("f.range.derived.variant.discount=")
    assert unquote(facet.split("=", 1)[1]).replace("+", " ") == "70% dcto y más"


def test_with_facet_joins_to_an_existing_query_or_starts_one():
    assert nextdata.with_facet("https://x/search?Ntt=a", "f=1") == "https://x/search?Ntt=a&f=1"
    assert nextdata.with_facet("https://x/category/cat1/slug", "f=1") == "https://x/category/cat1/slug?f=1"


def hot_watchlist(**scan):
    return {**WATCHLIST, "keywords": ["taladro"], "scan": {**WATCHLIST["scan"], "hot_only": True, **scan}}


def test_a_hot_scan_asks_only_for_discounted_listings_over_every_category_and_keyword():
    urls = []

    def fetch(url):
        urls.append(url)
        return page_with([len(urls)])

    nextdata.fetch_store_deals(CFG, hot_watchlist(), fetch=fetch, fetch_home=lambda url: HOME, sleep=lambda s: None)

    assert len(urls) == 5  # 4 categories in the menu + 1 keyword, one page each
    assert all("f.range.derived.variant.discount=70" in url for url in urls)
    assert sum("search" in url for url in urls) == 1


def test_a_hot_scan_does_not_run_the_regular_jobs():
    urls = []
    nextdata.fetch_store_deals(
        CFG, hot_watchlist(max_category_pages=9), fetch=lambda url: urls.append(url) or page_with([1]),
        fetch_home=lambda url: HOME, sleep=lambda s: None,
    )
    assert len(urls) == 5 and not any("page=" in url for url in urls)


def test_the_regular_scan_has_no_facet():
    urls = []
    nextdata.fetch_store_deals(
        CFG, {**WATCHLIST, "keywords": ["taladro"]}, fetch=lambda url: urls.append(url) or page_with([1]),
        fetch_home=lambda url: HOME, sleep=lambda s: None,
    )
    assert urls and not any("discount" in url for url in urls)


# ---- a blocked site is left alone ------------------------------------------------------------------

def test_after_a_few_403_the_site_is_not_asked_again(monkeypatch):
    nextdata.reset_blocks()
    calls = []

    def blocked(url, headers=None, timeout=None):
        calls.append(url)
        response = requests.Response()
        response.status_code = 403
        return response

    monkeypatch.setattr(nextdata.httpclient, "get", blocked)
    monkeypatch.setattr(nextdata.time, "sleep", lambda s: None)

    for _ in range(nextdata.BLOCK_LIMIT):
        with pytest.raises(RuntimeError):
            nextdata.fetch_html("https://www.falabella.com/x")
    asked = len(calls)
    with pytest.raises(nextdata.Blocked):
        nextdata.fetch_html("https://www.falabella.com/y")
    assert len(calls) == asked  # the circuit is open: no new request went out
    nextdata.reset_blocks()


# ---- what is announced ------------------------------------------------------------------------------

WATCH = {"categories": ["x"], "keywords": [], "min_discount_pct": 30, "min_real_discount_pct": 15,
         "verify_advertised_discount": "label"}


def listed(deal_id, price, list_price, **kw):
    base = deal(deal_id, price, list_price)
    return Deal(**{**base.__dict__, "discount_pct": round((list_price - price) / list_price * 100, 1), **kw})


def test_a_confirmed_big_discount_is_announced_at_once():
    history = history_of(("falabella:1", [100_000]))
    [offer] = main_hot.pick_candidates([listed("falabella:1", 30_000, 100_000)], WATCH, history, set())
    assert offer.advertised_confirmed and offer.verified_pct >= 60


def test_an_unconfirmed_claim_waits_for_the_regular_scan():
    # advertised 80 % off but we never saw it at the "normal" price
    assert main_hot.pick_candidates([listed("falabella:2", 20_000, 100_000)], WATCH, {}, set()) == []


def test_a_possible_mistake_is_announced_even_outside_the_watchlist():
    history = history_of(("falabella:3", [100_000]))
    outside = listed("falabella:3", 15_000, 15_000, category="juguetes", title="Cosa rara")
    [offer] = main_hot.pick_candidates([outside], {**WATCH, "categories": ["herramientas"]}, history, set())
    assert offer.price_error


def test_what_was_already_announced_is_not_announced_again():
    history = history_of(("falabella:1", [100_000]))
    offer = listed("falabella:1", 30_000, 100_000)
    assert main_hot.pick_candidates([offer], WATCH, history, {f"{offer.id}:{offer.price}"}) == []


def test_the_hot_scan_covers_the_filtered_stores_and_the_small_http_ones_only():
    watchlist = main_hot.hot_watchlist({"disabled_stores": ["paris"], "scan": {"deep_pages": 10}})
    assert watchlist["scan"]["hot_only"] is True and watchlist["scan"]["deep_pages"] == 10
    enabled = {store for store, _ in main_fast.SOURCE_FETCHERS} - set(watchlist["disabled_stores"])
    assert enabled == set(main_hot.HOT_STORES) | set(main_hot.HOT_FULL_STORES)
    assert not {"skechers", "salcobrand", "paris"} & enabled  # browser and blocked stores stay out


# ---- the whole run ----------------------------------------------------------------------------------

def test_the_run_announces_records_and_does_not_touch_the_state_files(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path, watchlist={"categories": ["x"], "keywords": [], "min_discount_pct": 30,
                                                  "min_real_discount_pct": 15})
    (tmp_path / "price_history.json").write_text(
        json.dumps({"falabella:9": [{"date": "2026-10-04", "price": 100_000}]}), encoding="utf-8"
    )
    cheap = listed("falabella:9", 15_000, 15_000)
    _stub_all_sources(monkeypatch, fetch_falabella_deals=lambda watchlist: [cheap])

    recorded, sent = {}, {}
    monkeypatch.setattr(main_hot, "send_offers", lambda offers, **kw: sent.setdefault("o", list(offers)) and list(offers))

    class FakeStore:
        def active_subscribers(self):
            return [111]

        def record_sent(self, offers):
            recorded["offers"] = list(offers)

        def sync_scan(self, deals):
            recorded["scanned"] = len(deals)

    monkeypatch.setattr(main_hot.SupabaseSync, "from_env", classmethod(lambda cls: FakeStore()))
    monkeypatch.setattr(main_fast, "remote_sent_keys", lambda: set())

    assert main_hot.run() == 0
    assert [o.deal.id for o in sent["o"]] == ["falabella:9"]
    assert [o.deal.id for o in recorded["offers"]] == ["falabella:9"] and recorded["scanned"] == 1
    assert not (tmp_path / "seen_items.json").exists()  # the hot scan never writes the state files


def test_a_failed_hot_scan_is_a_failed_run(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)

    def boom(watchlist):
        raise RuntimeError("down")

    _stub_all_sources(monkeypatch, **{attr: boom for attr in main_fast.SOURCE_NAMES})
    assert main_hot.run() == 1


# ---- reading what the other workflow announced ------------------------------------------------------

def test_recent_sent_keys_pages_through_everything(monkeypatch):
    pages = {0: [{"product_id": f"falabella:{i}", "price": 100 + i} for i in range(3)],
             3: [{"product_id": "sodimac:9", "price": 5}]}
    seen_params = []

    class Response:
        status_code = 200

        def __init__(self, rows):
            self._rows = rows

        def json(self):
            return self._rows

    def fake_get(url, headers=None, params=None, timeout=None):
        seen_params.append(params)
        return Response(pages.get(params["offset"], []))

    monkeypatch.setattr("supabase_sync.requests.get", fake_get)
    keys = SupabaseSync("https://x.supabase.co", "key").recent_sent_keys(page_size=3)

    assert keys == {"falabella:0:100", "falabella:1:101", "falabella:2:102", "sodimac:9:5"}
    assert [p["offset"] for p in seen_params] == [0, 3]
    assert all(p["sent_at"].startswith("gte.") for p in seen_params)


def test_the_regular_scan_skips_what_the_hot_scan_announced(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path, watchlist={"categories": ["x"], "keywords": [], "min_discount_pct": 30,
                                                  "min_real_discount_pct": 15})
    (tmp_path / "price_history.json").write_text(
        json.dumps({"falabella:9": [{"date": "2026-10-04", "price": 100_000}]}), encoding="utf-8"
    )
    cheap = listed("falabella:9", 15_000, 15_000)
    _stub_all_sources(monkeypatch, fetch_falabella_deals=lambda watchlist: [cheap])
    monkeypatch.setattr(main_fast, "remote_sent_keys", lambda: {f"{cheap.id}:{cheap.price}"})
    monkeypatch.setattr(main_fast, "send_offers", lambda offers, **kw: pytest.fail("sent twice"))

    assert main_fast.run() == 0
