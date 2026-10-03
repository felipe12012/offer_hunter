# tests/test_laikamascotas.py
import json
from pathlib import Path

import pytest

from sources.health import NoResultsError
from sources.laikamascotas import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "laikamascotas_sample.html"

TOPK9_ID = "laikamascotas:21650"
VITALCAN_ID = "laikamascotas:17831"

ZERO_PRICE_JSON = json.dumps({
    "products": [
        {
            "id": 999,
            "name": "Producto Sin Precio",
            "slug": "producto-sin-precio",
            "image": {"url": "https://static.laika.digital/products/zero.jpg"},
            "price": {"sale": 0, "final": 0, "priceForMember": {"final": 0}},
        }
    ]
})


def test_parse_html_extracts_one_deal_per_id_deduping_duplicates():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="shampoo perro")

    assert len(result) == 2  # TopK9 appears twice in the payload; must collapse
    assert {deal.id for deal in result} == {TOPK9_ID, VITALCAN_ID}


def test_parse_html_extracts_title_price_and_absolute_url():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="shampoo perro")

    vitalcan = next(d for d in result if d.id == VITALCAN_ID)
    assert vitalcan.title == "Vitalcan Balanced - Alimento Adulto Natural Recipe Cordero"
    assert vitalcan.price == 55440
    assert vitalcan.url == (
        "https://www.laikamascotas.cl/"
        "vitalcan-balanced-natural-recipe-alimento-perro-adulto-sabor-cordero"
    )
    assert vitalcan.store == "laikamascotas"
    assert vitalcan.category == "shampoo perro"
    assert vitalcan.image_url == (
        "https://static.laika.digital/products-3/"
        "91da9b8603c9649dafdc7d08e516951c_1703690303.jpg"
    )


def test_parse_html_uses_sale_as_crossed_list_price_when_higher():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="shampoo perro")

    topk9 = next(d for d in result if d.id == TOPK9_ID)
    assert topk9.price == 4995  # price.final = what any customer pays
    assert topk9.list_price == 6660  # price.sale = crossed "precio normal"
    assert topk9.discount_pct == 25.0


def test_parse_html_falls_back_to_price_as_list_price_when_no_discount():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="shampoo perro")

    vitalcan = next(d for d in result if d.id == VITALCAN_ID)
    assert vitalcan.list_price == vitalcan.price
    assert vitalcan.discount_pct == 0.0


def test_parse_html_ignores_the_card_member_price():
    payload = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(payload, category="shampoo perro")

    topk9 = next(d for d in result if d.id == TOPK9_ID)
    vitalcan = next(d for d in result if d.id == VITALCAN_ID)
    # priceForMember.final (4662 / 47124) must never win over price.final.
    assert topk9.price == 4995
    assert vitalcan.price == 55440


def test_parse_html_skips_zero_price_products():
    assert parse_html(ZERO_PRICE_JSON, category="alimento") == []


def test_parse_html_treats_empty_products_as_an_empty_query():
    with pytest.raises(NoResultsError):
        parse_html(json.dumps({"products": [], "filters": {}}), category="alimento")


def test_parse_html_raises_on_unparseable_payload():
    with pytest.raises(RuntimeError):
        parse_html("<html>not json</html>", category="alimento")


def test_parse_html_raises_when_products_list_is_missing():
    with pytest.raises(RuntimeError):
        parse_html(json.dumps({"filters": {}}), category="alimento")


def test_a_failing_keyword_does_not_abort_the_other_keywords(monkeypatch):
    import sources.laikamascotas as laika

    good_payload = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search API returned a malformed payload")
        return good_payload

    monkeypatch.setattr(laika, "fetch_html", fake_fetch_html)

    deals = laika.fetch_deals({"keywords": ["bad", "good"]})
    assert deals
    assert {d.id for d in deals} == {TOPK9_ID, VITALCAN_ID}


def test_every_keyword_failing_raises_so_a_dead_store_is_visible(monkeypatch):
    import sources.laikamascotas as laika

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(laika, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        laika.fetch_deals({"keywords": ["bad", "worse"]})


def test_empty_query_is_not_counted_as_a_failure(monkeypatch):
    import sources.laikamascotas as laika

    good_payload = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "empty":
            return json.dumps({"products": [], "filters": {}})
        return good_payload

    monkeypatch.setattr(laika, "fetch_html", fake_fetch_html)

    deals = laika.fetch_deals({"keywords": ["empty", "good"]})
    assert {d.id for d in deals} == {TOPK9_ID, VITALCAN_ID}
