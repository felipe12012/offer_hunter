# tests/test_salcobrand.py
from pathlib import Path

import pytest

from sources.salcobrand import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "salcobrand_sample.html"

ZERO_PRICE_HTML = """
<html><head><title>Salcobrand</title></head><body>
  <ul class="ais-Hits-list">
    <li class="ais-Hits-item">
      <div class="product-grid-item"><div class="product clickable"><div class="inner-product-box">
        <div class="product-image">
          <a href="/products/crema-sin-precio?default_sku=0000000">
            <img alt="Crema Sin Precio" src="https://static.salcobrand.cl/spree/products/1/small/0000000_1.jpg"/>
          </a>
        </div>
        <div class="info">
          <a href="/products/crema-sin-precio?default_sku=0000000">
            <span class="product-info truncate">Crema Sin Precio</span>
            <div class="product-prices">
              <span class="display-price-normal">$0</span>
            </div>
          </a>
        </div>
      </div></div></div>
    </li>
  </ul>
</body></html>
"""


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    assert len(result) == 2  # duplicated block must collapse
    assert {deal.id for deal in result} == {"salcobrand:7650030", "salcobrand:5970108"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    neutrogena = next(d for d in result if d.id == "salcobrand:7650030")
    assert neutrogena.title == "Hidratante Facial Gel Hydro Boost Neutrogena 50g"
    assert neutrogena.price == 9489
    assert neutrogena.url == (
        "https://salcobrand.cl/products/"
        "hidratante-facial-gel-neutrogena-hydro-boost-50g?default_sku=7650030"
    )
    assert "queryID" not in neutrogena.url
    assert neutrogena.store == "salcobrand"
    assert neutrogena.category == "crema"


def test_parse_html_computes_discount_from_crossed_price_and_ignores_card_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    neutrogena = next(d for d in result if d.id == "salcobrand:7650030")
    assert neutrogena.price == 9489  # offer price, not the card-only 8029
    assert neutrogena.list_price == 14599
    assert neutrogena.discount_pct == 35.0


def test_parse_html_falls_back_to_price_as_list_price_when_no_crossed_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    cerave = next(d for d in result if d.id == "salcobrand:5970108")
    assert cerave.price == 20199
    assert cerave.list_price == cerave.price
    assert cerave.discount_pct == 0.0


def test_parse_html_extracts_real_product_image():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    for deal in result:
        assert deal.image_url.startswith("http"), deal
        assert not deal.image_url.startswith("data:")


def test_parse_html_skips_zero_price_products():
    result = parse_html(ZERO_PRICE_HTML, category="crema")
    assert result == []


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Salcobrand</title></head><body>no products</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="crema")


def test_a_failing_keyword_does_not_abort_the_other_keywords(monkeypatch):
    import sources.salcobrand as salcobrand

    good_html = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(salcobrand, "fetch_html", fake_fetch_html)

    deals = salcobrand.fetch_deals({"keywords": ["bad", "good"]})
    assert deals
    assert {d.id for d in deals} == {"salcobrand:7650030", "salcobrand:5970108"}


def test_every_keyword_failing_raises_so_a_dead_store_is_visible(monkeypatch):
    import sources.salcobrand as salcobrand

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(salcobrand, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        salcobrand.fetch_deals({"keywords": ["bad", "worse"]})
