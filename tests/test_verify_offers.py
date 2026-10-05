"""The verifier: what a product page says, who gets checked, and what is written back."""
import json
from datetime import datetime, timedelta, timezone

import pytest

import verify_offers
from verify_offers import Blocked, classify_page, pick_candidates, verify

NOW = datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)


def page(variants, published=True, out_of_stock=False, include_data=True):
    data = {"isPublished": published, "isOutOfStock": out_of_stock, "variants": variants}
    props = {"productData": data if include_data else None}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps({"props": {"pageProps": props}})}</script></html>'


def variant(sellable=True, hd=True, cc=True, prices=None):
    return {
        "isOnlineSellable": sellable, "isHDAvailable": hd, "isCCAvailable": cc,
        "prices": prices if prices is not None else [
            {"type": "cmrPrice", "price": ["9.990"]},
            {"type": "internetPrice", "price": ["12.990"]},
            {"type": "normalPrice", "price": ["29.990"]},
        ],
    }


# ---- reading a product page --------------------------------------------------------------------------------

def test_a_product_with_a_sellable_variant_is_available_at_the_public_price():
    result = classify_page(page([variant()]))
    assert result["available"] is True
    assert result["price"] == 12_990        # the card-only price (cmr) is not what anyone can pay


def test_the_store_flag_out_of_stock_means_sold_out():
    assert classify_page(page([variant()], out_of_stock=True))["available"] is False


def test_an_unpublished_product_is_not_for_sale():
    assert classify_page(page([variant()], published=False))["available"] is False


def test_no_variant_that_can_be_bought_means_sold_out():
    result = classify_page(page([variant(sellable=False, hd=False, cc=False), variant(sellable=False, hd=False, cc=False)]))
    assert result["available"] is False


def test_one_available_variant_is_enough():
    result = classify_page(page([variant(sellable=False, hd=False, cc=False), variant(sellable=False, hd=True, cc=False)]))
    assert result["available"] is True


def test_the_price_is_the_lowest_of_the_sellable_variants():
    cheap = variant(prices=[{"type": "eventPrice", "price": ["8.490"]}])
    dear = variant(prices=[{"type": "internetPrice", "price": ["12.990"]}])
    sold_out = variant(sellable=False, hd=False, cc=False, prices=[{"type": "internetPrice", "price": ["1.000"]}])
    assert classify_page(page([dear, cheap, sold_out]))["price"] == 8_490


@pytest.mark.parametrize("html", ["<html>Cloudflare</html>", page([variant()], include_data=False), "", '<script id="__NEXT_DATA__">{broken</script>'])
def test_a_page_that_says_nothing_usable_is_unknown_not_sold_out(html):
    assert classify_page(html) is None


# ---- who gets checked --------------------------------------------------------------------------------------

def iso(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


def test_never_checked_products_go_first_in_priority_order_then_the_oldest_checks():
    checks = {
        "a": {"available": True, "checked_at": iso(90)},
        "b": {"available": True, "checked_at": iso(30)},
        "c": {"available": True, "checked_at": iso(5)},     # checked a moment ago: left alone
    }
    assert pick_candidates(["x", "a", "y", "b", "c"], checks, NOW) == ["x", "y", "a", "b"]


def test_a_sold_out_product_is_rechecked_less_often():
    checks = {"gone": {"available": False, "checked_at": iso(30)}, "old": {"available": False, "checked_at": iso(90)}}
    assert pick_candidates(["gone", "old"], checks, NOW) == ["old"]


def test_the_limit_and_duplicates():
    assert pick_candidates(["a", "a", "b", "c", "d"], {}, NOW, limit=3) == ["a", "b", "c"]


# ---- the run -----------------------------------------------------------------------------------------------

class FakeStore:
    def __init__(self, feed, sent=(), checks=(), extra_products=()):
        self.tables = {
            "offer_feed": [{"id": i, "url": f"https://shop/{i}"} for i in feed],
            "offer_sent": [{"product_id": i} for i in sent],
            "offer_availability": list(checks),
            "offer_products": [{"id": i, "url": f"https://shop/{i}"} for i in extra_products],
        }
        self.written = []
        self.last_seen = []
        self.refreshed = False

    def _get_rows(self, table, params):
        rows = self.tables[table]
        key = {"offer_availability": "product_id", "offer_products": "id"}.get(table)
        if key and key in params:
            wanted = params[key][4:-1].split(",")
            rows = [r for r in rows if r[key] in wanted]
        return rows

    def _post(self, table, rows, prefer=None, params=None):
        self.written.extend(rows)

    def set_last_seen(self, ids, when):
        self.last_seen.append((list(ids), when))

    def refresh_feed(self):
        self.refreshed = True


def fetcher(answers):
    def fetch(url):
        answer = answers[url.rsplit("/", 1)[-1]]
        if isinstance(answer, Exception):
            raise answer
        return answer
    return fetch


AVAILABLE = {"available": True, "price": 1000, "detail": "ok"}
SOLD_OUT = {"available": False, "price": None, "detail": "outOfStock=True"}


def test_a_sold_out_product_is_recorded_and_moved_back_so_the_web_hides_it():
    store = FakeStore(["falabella:1", "falabella:2"])
    counters = verify(store, NOW, fetch=fetcher({"falabella:1": AVAILABLE, "falabella:2": SOLD_OUT}))

    assert counters["checked"] == 2 and counters["sold_out"] == 1
    assert {r["product_id"]: r["available"] for r in store.written} == {"falabella:1": True, "falabella:2": False}
    [(ids, when)] = store.last_seen
    assert ids == ["falabella:2"] and datetime.fromisoformat(when) == NOW - timedelta(hours=7)


def test_a_product_the_store_sells_again_is_brought_back():
    store = FakeStore(["falabella:1"], checks=[{"product_id": "falabella:1", "available": False, "checked_at": iso(120)}])
    counters = verify(store, NOW, fetch=fetcher({"falabella:1": AVAILABLE}))
    assert counters["restocked"] == 1
    assert store.last_seen == [(["falabella:1"], NOW.isoformat())]


def test_what_was_announced_is_checked_before_the_rest_even_if_it_left_the_top():
    store = FakeStore(["falabella:1", "falabella:2"], sent=["sodimac:9", "hites:5"], extra_products=["sodimac:9"])
    checked = []

    def fetch(url):
        checked.append(url.rsplit("/", 1)[-1])
        return AVAILABLE

    verify(store, NOW, fetch=fetch, per_run=10)
    assert checked[0] == "sodimac:9"                 # announced first
    assert "hites:5" not in checked                  # only the stores whose pages we can read
    assert set(checked) == {"sodimac:9", "falabella:1", "falabella:2"}


def test_unknown_answers_change_nothing():
    store = FakeStore(["falabella:1", "falabella:2"])
    counters = verify(store, NOW, fetch=fetcher({"falabella:1": None, "falabella:2": requests_error()}))
    assert counters["checked"] == 0 and store.written == [] and store.last_seen == []


def requests_error():
    import requests

    return requests.ConnectionError("down")


def test_a_store_that_blocks_us_stops_the_run(monkeypatch):
    monkeypatch.setattr(verify_offers, "WORKERS", 1)
    ids = [f"falabella:{i}" for i in range(30)]
    store = FakeStore(ids)
    calls = []

    def fetch(url):
        calls.append(url)
        raise Blocked("HTTP 403")

    counters = verify(store, NOW, fetch=fetch)
    assert counters["blocked"] == verify_offers.BLOCK_LIMIT and len(calls) == verify_offers.BLOCK_LIMIT
    assert store.written == []          # nothing is concluded from a refusal


def test_the_run_refreshes_the_feed_only_when_something_changed(monkeypatch, capsys):
    store = FakeStore(["falabella:1"])
    monkeypatch.setattr(verify_offers.SupabaseSync, "from_env", classmethod(lambda cls: store))
    monkeypatch.setattr(verify_offers, "fetch_status", fetcher({"falabella:1": SOLD_OUT}))
    assert verify_offers.run() == 0 and store.refreshed
    assert "1 sold out" in capsys.readouterr().err

    quiet = FakeStore(["falabella:1"])
    monkeypatch.setattr(verify_offers.SupabaseSync, "from_env", classmethod(lambda cls: quiet))
    monkeypatch.setattr(verify_offers, "fetch_status", fetcher({"falabella:1": AVAILABLE}))
    assert verify_offers.run() == 0 and not quiet.refreshed


def test_without_supabase_the_run_fails_loudly(monkeypatch):
    monkeypatch.setattr(verify_offers.SupabaseSync, "from_env", classmethod(lambda cls: None))
    assert verify_offers.run() == 1
