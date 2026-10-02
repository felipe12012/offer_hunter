# tests/test_puma.py
from pathlib import Path

import pytest

from sources.puma import fetch_deals, parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "puma_sample.html"


def _html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    result = parse_html(_html(), category="zapatillas")

    assert len(result) == 2  # 3 cards, one duplicated -> 2 deals
    assert {deal.id for deal in result} == {"puma:026875-02", "puma:384139-08"}


def test_parse_html_extracts_title_price_url_store_category_and_image():
    result = parse_html(_html(), category="zapatillas")

    gorro = next(d for d in result if d.id == "puma:026875-02")
    assert gorro.title == "Gorro con visera BMW M Motorsport"
    assert gorro.price == 10990
    assert gorro.url == "https://cl.puma.com/gorro-con-visera-bmw-m-motorsport-026875-02.html"
    assert gorro.store == "puma"
    assert gorro.category == "zapatillas"
    assert gorro.image_url.startswith("https://images.puma.com/")
    assert not gorro.image_url.startswith("data:")
    assert "logo" not in gorro.image_url.lower()


def test_parse_html_computes_discount_from_crossed_price():
    result = parse_html(_html(), category="zapatillas")

    gorro = next(d for d in result if d.id == "puma:026875-02")
    assert gorro.list_price == 22990
    assert gorro.discount_pct == 52.2


def test_parse_html_falls_back_to_price_when_crossed_price_not_greater():
    result = parse_html(_html(), category="zapatillas")

    sandalia = next(d for d in result if d.id == "puma:384139-08")
    assert sandalia.price == 19990
    assert sandalia.list_price == 19990
    assert sandalia.discount_pct == 0.0
    assert sandalia.image_url.startswith("https://images.puma.com/")


def test_parse_html_skips_cards_with_zero_price():
    html = _html().replace('data-price-amount="10990"', 'data-price-amount="0"')

    result = parse_html(html, category="zapatillas")

    assert all(deal.id != "puma:026875-02" for deal in result)
    assert {deal.id for deal in result} == {"puma:384139-08"}


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>PUMA.com</title></head><body>no products here</body></html>"

    with pytest.raises(RuntimeError):
        parse_html(html, category="zapatillas")


def test_fetch_deals_isolates_a_failing_keyword(monkeypatch):
    good_html = _html()

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr("sources.puma.fetch_html", fake_fetch_html)

    deals = fetch_deals({"keywords": ["bad", "good"]})

    assert len(deals) == 2


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr("sources.puma.fetch_html", boom)

    with pytest.raises(RuntimeError):
        fetch_deals({"keywords": ["bad", "worse"]})
