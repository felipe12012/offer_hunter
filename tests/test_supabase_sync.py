import json

import pytest
import requests

from models import Deal, ScoredDeal
from supabase_sync import SupabaseError, SupabaseSync

URL = "https://proj.supabase.co"


def make_deal(deal_id="falabella:1", price=1000, list_price=2000, image_url="https://img/x.jpg") -> Deal:
    return Deal(
        id=deal_id, title="Taladro", url=f"https://shop/{deal_id}", store=deal_id.split(":")[0],
        category="herramientas", price=price, list_price=list_price,
        discount_pct=round((list_price - price) / list_price * 100, 1),
        scraped_at="2026-10-02T12:00:00+00:00", image_url=image_url,
    )


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None, text=""):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = text or json.dumps(payload or {})

    def json(self):
        return self._payload


class Recorder:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def __call__(self, url, headers=None, data=None, params=None, timeout=None, **kw):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(data) if data else None, "params": params})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(200, {"received": 0, "new": 0, "updated": 0, "points": 0})


def client(monkeypatch, recorder, key="sb_secret_abc"):
    monkeypatch.setattr("supabase_sync.requests.post", recorder)
    monkeypatch.setattr("supabase_sync.time.sleep", lambda s: None)
    return SupabaseSync(URL, key)


# ---- configuration ---------------------------------------------------------

def test_from_env_is_none_when_not_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert SupabaseSync.from_env() is None


def test_from_env_treats_empty_secrets_as_unset(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")
    assert SupabaseSync.from_env() is None


def test_from_env_builds_a_client(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", URL + "/")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sb_secret_abc")
    assert SupabaseSync.from_env().url == URL           # trailing slash stripped


def test_new_style_secret_key_is_sent_only_as_apikey(monkeypatch):
    rec = Recorder()
    client(monkeypatch, rec, key="sb_secret_abc").sync_scan([make_deal()])
    headers = rec.calls[0]["headers"]
    assert headers["apikey"] == "sb_secret_abc"
    assert "Authorization" not in headers


def test_legacy_jwt_service_key_is_also_sent_as_bearer(monkeypatch):
    rec = Recorder()
    client(monkeypatch, rec, key="eyJhbGciOi.payload.sig").sync_scan([make_deal()])
    assert rec.calls[0]["headers"]["Authorization"] == "Bearer eyJhbGciOi.payload.sig"


# ---- scan sync -------------------------------------------------------------

def test_sync_scan_sends_deals_to_the_rpc_in_batches_and_sums_the_results(monkeypatch):
    rec = Recorder([
        FakeResponse(200, {"received": 2, "new": 1, "updated": 2, "points": 1}),
        FakeResponse(200, {"received": 1, "new": 1, "updated": 1, "points": 1}),
    ])
    sync = client(monkeypatch, rec)
    sync.batch_size = 2
    deals = [make_deal(f"falabella:{i}") for i in range(3)]

    totals = sync.sync_scan(deals)

    assert [c["url"] for c in rec.calls] == [f"{URL}/rest/v1/rpc/offer_sync_scan"] * 2
    assert [len(c["body"]["deals"]) for c in rec.calls] == [2, 1]
    assert totals == {"received": 3, "new": 2, "updated": 3, "points": 2}


def test_sync_scan_payload_carries_every_field_the_sql_function_reads(monkeypatch):
    rec = Recorder()
    client(monkeypatch, rec).sync_scan([make_deal("sodimac:9", price=500, list_price=1000)])
    row = rec.calls[0]["body"]["deals"][0]
    assert row == {
        "id": "sodimac:9", "store": "sodimac", "title": "Taladro", "url": "https://shop/sodimac:9",
        "image_url": "https://img/x.jpg", "category": "herramientas",
        "price": 500, "list_price": 1000, "discount_pct": 50.0,
        "grp": "herramientas", "subcat": "electricas",
    }


def test_http_errors_raise_with_the_status_and_a_body_excerpt(monkeypatch):
    rec = Recorder([FakeResponse(401, text='{"message":"Invalid API key"}')])
    with pytest.raises(SupabaseError) as err:
        client(monkeypatch, rec).sync_scan([make_deal()])
    assert "401" in str(err.value) and "Invalid API key" in str(err.value)


def test_server_errors_are_retried_then_succeed(monkeypatch):
    rec = Recorder([FakeResponse(503, text="busy"), FakeResponse(200, {"received": 1, "new": 0, "updated": 0, "points": 0})])
    totals = client(monkeypatch, rec).sync_scan([make_deal()])
    assert len(rec.calls) == 2 and totals["received"] == 1


def test_client_errors_are_not_retried(monkeypatch):
    rec = Recorder([FakeResponse(400, text="bad request")])
    with pytest.raises(SupabaseError):
        client(monkeypatch, rec).sync_scan([make_deal()])
    assert len(rec.calls) == 1


def test_network_failures_become_supabase_errors(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.ConnectionError("dns")
    monkeypatch.setattr("supabase_sync.requests.post", boom)
    monkeypatch.setattr("supabase_sync.time.sleep", lambda s: None)
    with pytest.raises(SupabaseError):
        SupabaseSync(URL, "k").sync_scan([make_deal()])


# ---- delivered offers and runs ----------------------------------------------

def test_record_sent_stores_one_row_per_offer_ignoring_duplicates(monkeypatch):
    rec = Recorder()
    deal = make_deal("falabella:7", price=300, list_price=1000)
    offer = ScoredDeal(deal=deal, real_discount_pct=40.0, reasons=["-40% vs minimo"], verified_pct=40.0)

    client(monkeypatch, rec).record_sent([offer])

    call = rec.calls[0]
    assert call["url"] == f"{URL}/rest/v1/offer_sent"
    assert call["params"] == {"on_conflict": "product_id,price"}
    assert "ignore-duplicates" in call["headers"]["Prefer"]
    assert call["body"] == [{
        "product_id": "falabella:7", "price": 300, "store": "falabella", "title": "Taladro",
        "url": "https://shop/falabella:7", "verified_pct": 40.0, "advertised_pct": 70.0,
        "real_pct": 40.0, "reasons": ["-40% vs minimo"], "price_error": None, "source": "live",
    }]


def test_record_sent_with_nothing_makes_no_request(monkeypatch):
    rec = Recorder()
    client(monkeypatch, rec).record_sent([])
    assert rec.calls == []


def test_record_run_posts_the_scan_statistics(monkeypatch):
    rec = Recorder()
    stats = {"scanned": 10, "new_deals": 3, "qualifying": 2, "delivered": 2, "unverified": 5,
             "per_store": {"falabella": 10}, "duration_seconds": 12.3, "github_run_id": "99"}
    client(monkeypatch, rec).record_run(stats)
    assert rec.calls[0]["url"] == f"{URL}/rest/v1/offer_scan_runs"
    assert rec.calls[0]["body"] == [stats]


# ---- one-time import of the JSON state --------------------------------------

def test_import_history_creates_products_first_then_dated_price_points(monkeypatch):
    rec = Recorder()
    history = {
        "falabella:1": [{"date": "2026-10-01", "price": 900}, {"date": "2026-10-02", "price": 700}],
        "hites:2": [{"date": "2026-10-02", "price": 50}],
    }

    totals = client(monkeypatch, rec).import_history(history)

    products_call, points_call = rec.calls
    assert products_call["url"].endswith("/rest/v1/offer_products")
    assert products_call["params"] == {"on_conflict": "id"}
    by_id = {row["id"]: row for row in products_call["body"]}
    assert by_id["falabella:1"] == {"id": "falabella:1", "store": "falabella", "price": 700, "list_price": 700}
    assert by_id["hites:2"]["store"] == "hites"

    assert points_call["url"].endswith("/rest/v1/offer_price_points")
    assert points_call["params"] == {"on_conflict": "product_id,observed_at,price"}
    assert {"product_id": "falabella:1", "observed_at": "2026-10-01T12:00:00Z", "price": 900, "source": "migrated"} in points_call["body"]
    assert len(points_call["body"]) == 3
    assert totals == {"products": 2, "points": 3}


def test_import_history_batches_large_histories(monkeypatch):
    rec = Recorder()
    history = {f"falabella:{i}": [{"date": "2026-10-02", "price": 10}] for i in range(2500)}
    client(monkeypatch, rec).import_history(history)
    product_calls = [c for c in rec.calls if c["url"].endswith("/offer_products")]
    assert [len(c["body"]) for c in product_calls] == [1000, 1000, 500]


def test_import_seen_converts_keys_into_sent_rows(monkeypatch):
    rec = Recorder()
    total = client(monkeypatch, rec).import_seen(["falabella:80726514:339990", "sodimac:prod:7:100"])
    assert total == 2
    rows = rec.calls[0]["body"]
    assert {"product_id": "falabella:80726514", "price": 339990, "source": "migrated"} in rows
    assert {"product_id": "sodimac:prod:7", "price": 100, "source": "migrated"} in rows   # price is after the LAST colon
    assert rec.calls[0]["params"] == {"on_conflict": "product_id,price"}


def test_count_reads_the_exact_row_count_from_content_range(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        assert "count=exact" in headers["Prefer"]
        return FakeResponse(200, [], headers={"Content-Range": "0-0/43039"})
    monkeypatch.setattr("supabase_sync.requests.get", fake_get)
    assert SupabaseSync(URL, "k").count("offer_products") == 43039


def test_import_history_counts_a_repeated_day_and_price_once(monkeypatch):
    rec = Recorder()
    history = {"falabella:1": [
        {"date": "2026-10-02", "price": 100},
        {"date": "2026-10-02", "price": 90},
        {"date": "2026-10-02", "price": 100},   # back to 100 the same day: same row as the first
    ]}

    totals = client(monkeypatch, rec).import_history(history)

    points_call = rec.calls[1]
    assert len(points_call["body"]) == 2
    assert totals == {"products": 1, "points": 2}


def test_recent_store_status_returns_newest_first_with_none_for_runs_without_data(monkeypatch):
    def fake_get(url, headers=None, params=None, timeout=None):
        assert url == f"{URL}/rest/v1/offer_scan_runs"
        assert params["order"] == "started_at.desc" and params["limit"] == 2
        return FakeResponse(200, [
            {"store_status": {"hites": {"status": "failed", "deals": 0}, "vans": {"status": "ok", "deals": 5}}},
            {"store_status": None},
        ])
    monkeypatch.setattr("supabase_sync.requests.get", fake_get)

    result = SupabaseSync(URL, "k").recent_store_status(2)

    assert result == [{"hites": "failed", "vans": "ok"}, None]


def test_recent_store_status_raises_a_supabase_error_on_http_errors(monkeypatch):
    monkeypatch.setattr("supabase_sync.requests.get", lambda *a, **k: FakeResponse(400, text="column does not exist"))
    with pytest.raises(SupabaseError):
        SupabaseSync(URL, "k").recent_store_status(2)


def test_refresh_feed_calls_the_rpc_with_an_empty_body(monkeypatch):
    rec = Recorder()

    client(monkeypatch, rec).refresh_feed()

    assert rec.calls[0]["url"] == f"{URL}/rest/v1/rpc/offer_refresh_feed"
    assert rec.calls[0]["body"] == {}
