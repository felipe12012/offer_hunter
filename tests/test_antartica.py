# tests/test_antartica.py
from pathlib import Path

import pytest

from sources.antartica import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "antartica_sample.html"

ZERO_PRICE_HTML = """
<html><head><title>Librería Antártica</title></head><body>
  <div class="product-item-info" id="product-item-info_9">
    <a class="product-item-link" data-product-id="9" href="https://www.antartica.cl/x.html">X</a>
    <div class="price-box price-final_price">
      <span class="normal-price">
        <span class="price-wrapper" data-price-type="finalPrice" data-price-amount="0">
          <span class="price">$0</span>
        </span>
      </span>
    </div>
    <img class="product-image-photo" src="https://www.antartica.cl/media/x.jpg">
  </div>
</body></html>
"""


def _fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_returns_one_deal_per_sku_deduping_duplicate_cards():
    result = parse_html(_fixture(), category="libros")

    ids = [deal.id for deal in result]
    assert len(ids) == 3  # not 4 — the duplicated block must collapse
    assert len(set(ids)) == 3
    assert set(ids) == {"antartica:781501", "antartica:710721", "antartica:761399"}


def test_parse_html_extracts_title_price_url_store_category_and_image():
    result = parse_html(_fixture(), category="libros")

    deal = next(d for d in result if d.id == "antartica:781501")
    assert deal.title == "Estuche Harry Potter (7 Tomos)"
    assert deal.price == 76300
    assert deal.url == "https://www.antartica.cl/estuche-harry-potter-7-tomos-9786287744134.html"
    assert deal.store == "antartica"
    assert deal.category == "libros"
    assert deal.image_url.startswith("https://")
    assert "9786287744134_1" in deal.image_url
    assert not deal.image_url.startswith("data:")
    assert "logo" not in deal.image_url.lower()


def test_parse_html_computes_discount_when_crossed_price_present():
    result = parse_html(_fixture(), category="libros")

    deal = next(d for d in result if d.id == "antartica:781501")
    assert deal.list_price == 109000
    assert deal.discount_pct == round((109000 - 76300) / 109000 * 100, 1)


def test_parse_html_without_crossed_price_sets_list_price_to_price():
    result = parse_html(_fixture(), category="libros")

    deal = next(d for d in result if d.id == "antartica:761399")
    assert deal.price == 24900
    assert deal.list_price == 24900
    assert deal.discount_pct == 0.0


def test_parse_html_skips_cards_without_a_positive_price():
    assert parse_html(ZERO_PRICE_HTML, category="libros") == []


def test_parse_html_raises_with_diagnostics_when_no_product_cards():
    html = (
        "<html><head><title>Librería Antártica</title></head><body>"
        + "<p>x</p>" * 2500
        + "</body></html>"
    )
    with pytest.raises(RuntimeError) as excinfo:
        parse_html(html, category="libros")

    message = str(excinfo.value)
    assert "Antártica" in message or "Ant" in message
    assert str(len(html)) in message


def test_fetch_deals_isolates_a_failing_keyword(monkeypatch):
    from sources import antartica

    good_html = _fixture()

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(antartica, "fetch_html", fake_fetch_html)

    deals = antartica.fetch_deals({"keywords": ["bad", "good"]})

    assert {d.id for d in deals} == {"antartica:781501", "antartica:710721", "antartica:761399"}
    assert {d.category for d in deals} == {"libros"}


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    from sources import antartica

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(antartica, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        antartica.fetch_deals({"keywords": ["bad", "worse"]})


def test_fetch_deals_dedupes_across_keywords(monkeypatch):
    from sources import antartica

    html = _fixture()
    monkeypatch.setattr(antartica, "fetch_html", lambda keyword: html)

    deals = antartica.fetch_deals({"keywords": ["harry potter", "libros"]})

    assert len(deals) == 3
