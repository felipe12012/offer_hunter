# tests/test_newbalance.py
from pathlib import Path

import pytest

from sources.newbalance import fetch_deals, parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "newbalance_sample.html"


def _html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    result = parse_html(_html(), category="zapatillas")

    assert len(result) == 2  # 3 cards, one duplicated -> 2 deals
    assert {deal.id for deal in result} == {
        "newbalance:16900000u906044096",
        "newbalance:169000000mr530sg96",
    }


def test_parse_html_extracts_title_price_url_store_category_and_image():
    result = parse_html(_html(), category="zapatillas")

    griegas = next(d for d in result if d.id == "newbalance:16900000u906044096")
    assert griegas.title == "Zapatillas Urbanas Unisex New Balance 9060 Gris"
    assert griegas.price == 100490
    assert griegas.url == (
        "https://newbalance.cl/zapatillas-urbanas-unisex-new-balance-9060-gris-16900000u906044096.html"
    )
    assert griegas.store == "newbalance"
    assert griegas.category == "zapatillas"
    assert griegas.image_url.startswith("https://newbalance.cl/media/catalog/")
    assert not griegas.image_url.startswith("data:")


def test_parse_html_computes_discount_from_crossed_price():
    result = parse_html(_html(), category="zapatillas")

    griegas = next(d for d in result if d.id == "newbalance:16900000u906044096")
    assert griegas.list_price == 154990
    assert griegas.discount_pct == 35.2


def test_parse_html_falls_back_to_price_when_no_crossed_price():
    result = parse_html(_html(), category="zapatillas")

    bicolor = next(d for d in result if d.id == "newbalance:169000000mr530sg96")
    assert bicolor.price == 99990
    assert bicolor.list_price == 99990
    assert bicolor.discount_pct == 0.0
    assert bicolor.image_url.startswith("https://newbalance.cl/media/catalog/")


def test_parse_html_skips_cards_with_zero_price():
    html = _html().replace('data-price-amount="100490"', 'data-price-amount="0"')

    result = parse_html(html, category="zapatillas")

    assert all(deal.id != "newbalance:16900000u906044096" for deal in result)
    assert {deal.id for deal in result} == {"newbalance:169000000mr530sg96"}


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>New Balance Chile</title></head><body>nothing</body></html>"

    with pytest.raises(RuntimeError):
        parse_html(html, category="zapatillas")


def test_fetch_deals_isolates_a_failing_keyword(monkeypatch):
    good_html = _html()

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr("sources.newbalance.fetch_html", fake_fetch_html)

    deals = fetch_deals({"keywords": ["bad", "good"]})

    assert len(deals) == 2


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr("sources.newbalance.fetch_html", boom)

    with pytest.raises(RuntimeError):
        fetch_deals({"keywords": ["bad", "worse"]})
