# tests/test_tusmascotas.py
import json
from pathlib import Path

import pytest

from sources.health import NoResultsError
from sources.tusmascotas import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tusmascotas_sample.html"

HILLS_ID = "tusmascotas:952486"
MAZURI_ID = "tusmascotas:1150201"

HILLS_NAME = "Alimento Humedo Hills C/D Canino 368grs"
MAZURI_NAME = "OUTLET - Fecha Corta (01/09/2026) - Mazuri Mini Bird Diet 0,90kg"

ZERO_PRICE_JSON = json.dumps({
    "products": [
        {
            "id": 999,
            "name": "Producto Sin Precio",
            "sku": "SKU-999",
            "permalink": "https://www.tusmascotas.cl/product/producto-sin-precio/",
            "prices": {
                "price": "0",
                "regular_price": "0",
                "sale_price": "0",
                "currency_code": "CLP",
                "currency_minor_unit": 0,
            },
            "images": [{"id": 1, "src": "https://www.tusmascotas.cl/x.jpg"}],
        }
    ]
})


def test_parse_html_extracts_one_deal_per_id_deduping_duplicates():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="alimento")

    assert len(result) == 2  # Hills appears twice in the payload; must collapse
    assert {deal.id for deal in result} == {HILLS_ID, MAZURI_ID}


def test_parse_html_extracts_title_price_and_absolute_url():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="alimento")

    hills = next(d for d in result if d.id == HILLS_ID)
    assert hills.title == HILLS_NAME
    assert hills.price == 3090
    assert hills.url == (
        "https://www.tusmascotas.cl/product/alimento-humedo-hills-c-d-canino-368grs/"
    )
    assert hills.store == "tusmascotas"
    assert hills.category == "alimento"
    assert hills.image_url == "https://www.tusmascotas.cl/wp-content/uploads/2026/03/isi-41.png"


def test_parse_html_uses_regular_price_as_crossed_list_price():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="alimento")

    hills = next(d for d in result if d.id == HILLS_ID)
    assert hills.price == 3090  # prices.price = what any customer pays
    assert hills.list_price == 5151  # prices.regular_price = crossed list price
    assert hills.discount_pct == 40.0


def test_parse_html_does_not_treat_sale_price_as_list_price():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="alimento")

    hills = next(d for d in result if d.id == HILLS_ID)
    # prices.sale_price == prices.price (3090); it must never be the list price.
    assert hills.list_price != 3090


def test_parse_html_falls_back_to_price_as_list_price_when_no_discount():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="alimento")

    mazuri = next(d for d in result if d.id == MAZURI_ID)
    assert mazuri.title == MAZURI_NAME
    assert mazuri.price == 8470
    assert mazuri.list_price == mazuri.price
    assert mazuri.discount_pct == 0.0


def test_parse_html_skips_zero_price_products():
    assert parse_html(ZERO_PRICE_JSON, category="alimento") == []


def test_parse_html_accepts_the_bare_per_page_array():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["products"][:1]
    result = parse_html(json.dumps(payload), category="alimento")
    assert [d.id for d in result] == [HILLS_ID]


def test_parse_html_treats_empty_products_as_an_empty_query():
    with pytest.raises(NoResultsError):
        parse_html(json.dumps({"products": []}), category="alimento")


def test_parse_html_raises_on_unparseable_payload():
    with pytest.raises(RuntimeError):
        parse_html("<html>not json</html>", category="alimento")


def test_parse_html_raises_when_products_list_is_missing():
    with pytest.raises(RuntimeError):
        parse_html(json.dumps({"results": []}), category="alimento")


def test_a_failing_keyword_does_not_abort_the_other_keywords(monkeypatch):
    import sources.tusmascotas as tus

    good_payload = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("Store API returned a malformed payload")
        return good_payload

    monkeypatch.setattr(tus, "fetch_html", fake_fetch_html)

    deals = tus.fetch_deals({"keywords": ["bad", "good"]})
    assert deals
    assert {d.id for d in deals} == {HILLS_ID, MAZURI_ID}


def test_every_keyword_failing_raises_so_a_dead_store_is_visible(monkeypatch):
    import sources.tusmascotas as tus

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(tus, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        tus.fetch_deals({"keywords": ["bad", "worse"]})


def test_empty_query_is_not_counted_as_a_failure(monkeypatch):
    import sources.tusmascotas as tus

    good_payload = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "empty":
            return json.dumps({"products": []})
        return good_payload

    monkeypatch.setattr(tus, "fetch_html", fake_fetch_html)

    deals = tus.fetch_deals({"keywords": ["empty", "good"]})
    assert {d.id for d in deals} == {HILLS_ID, MAZURI_ID}
