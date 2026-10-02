# tests/test_nike.py
from pathlib import Path

import pytest

from sources.nike import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nike_sample.html"

ZERO_PRICE_HTML = """
<html><head><title>Nike Chile | Tienda Oficial</title></head><body>
  <section class="vtex-product-summary-2-x-containerNormal vtex-product-summary-2-x-containerNormal--product-card">
    <a class="vtex-product-summary-2-x-clearLink" href="/xx0000-001-nike-free/p">
      <h3 class="vtex-product-summary-2-x-productNameContainer">Nike Free</h3>
      <span class="vtex-product-price-1-x-sellingPrice">$0</span>
    </a>
  </section>
</body></html>
"""


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    assert len(result) == 2  # not 3 — the duplicated block must collapse
    ids = {deal.id for deal in result}
    assert ids == {"nike:355152-016", "nike:cw2288-111"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    af1 = next(d for d in result if d.id == "nike:cw2288-111")
    assert af1.title == "Nike Air Force 1 '07"
    assert af1.price == 119990
    assert af1.url == "https://www.nike.cl/cw2288-111-nike-air-force-1-07/p"
    assert af1.store == "nike"
    assert af1.category == "zapatillas"


def test_parse_html_computes_discount_when_crossed_price_present():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    big_low = next(d for d in result if d.id == "nike:355152-016")
    assert big_low.price == 44990
    assert big_low.list_price == 96990
    assert big_low.discount_pct == 53.6


def test_parse_html_falls_back_to_price_as_list_price_when_no_crossed_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    af1 = next(d for d in result if d.id == "nike:cw2288-111")
    assert af1.list_price == af1.price
    assert af1.discount_pct == 0.0


def test_parse_html_extracts_real_product_image():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    for deal in result:
        assert deal.image_url.startswith("http"), deal
        assert not deal.image_url.startswith("data:")


def test_parse_html_skips_zero_price_products():
    result = parse_html(ZERO_PRICE_HTML, category="zapatillas")
    assert result == []


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Nike Chile</title></head><body>no products</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="zapatillas")


def test_a_failing_keyword_does_not_abort_the_other_keywords(monkeypatch):
    import sources.nike as nike

    good_html = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(nike, "fetch_html", fake_fetch_html)

    deals = nike.fetch_deals({"keywords": ["bad", "good"]})
    assert deals
    assert {d.id for d in deals} == {"nike:355152-016", "nike:cw2288-111"}


def test_every_keyword_failing_raises_so_a_dead_store_is_visible(monkeypatch):
    import sources.nike as nike

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(nike, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        nike.fetch_deals({"keywords": ["bad", "worse"]})
