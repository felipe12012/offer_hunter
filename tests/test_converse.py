# tests/test_converse.py
from pathlib import Path

import pytest

from sources.converse import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "converse_sample.html"

ZERO_PRICE_HTML = """
<html><head><title>Converse Chile</title></head><body>
  <ol class="products list items product-items">
    <li class="item product product-item">
      <a class="product-item-link" href="https://www.converse.cl/chuck-70-a13144c-010-negro">Chuck 70</a>
      <div class="price-box" data-product-id="123">
        <span data-price-type="finalPrice"><span class="price">$0</span></span>
      </div>
    </li>
  </ol>
</body></html>
"""


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    assert len(result) == 2  # not 3 — the duplicated block must collapse
    ids = {deal.id for deal in result}
    assert ids == {"converse:a13144c-010", "converse:a18135c-832"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    boot = next(d for d in result if d.id == "converse:a13144c-010")
    assert boot.title == "Chuck Taylor All Star Malden Street Boot Cuero Infantil"
    assert boot.price == 32990
    assert boot.url == (
        "https://www.converse.cl/chuck-taylor-all-star-malden-street-boot-cuero-infantil-a13144c-010-cafe"
    )
    assert boot.store == "converse"
    assert boot.category == "zapatillas"


def test_parse_html_computes_discount_when_crossed_price_present():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    boot = next(d for d in result if d.id == "converse:a13144c-010")
    assert boot.list_price == 54990
    assert boot.discount_pct == 40.0


def test_parse_html_falls_back_to_price_as_list_price_when_no_crossed_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    seasonal = next(d for d in result if d.id == "converse:a18135c-832")
    assert seasonal.price == 67990
    assert seasonal.list_price == seasonal.price
    assert seasonal.discount_pct == 0.0


def test_parse_html_extracts_real_product_image():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="zapatillas")

    for deal in result:
        assert deal.image_url.startswith("http"), deal
        assert not deal.image_url.startswith("data:")
        assert ".svg" not in deal.image_url.lower()


def test_parse_html_skips_zero_price_products():
    result = parse_html(ZERO_PRICE_HTML, category="zapatillas")
    assert result == []


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Converse Chile</title></head><body>no products</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="zapatillas")


def test_a_failing_keyword_does_not_abort_the_other_keywords(monkeypatch):
    import sources.converse as converse

    good_html = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(converse, "fetch_html", fake_fetch_html)

    deals = converse.fetch_deals({"keywords": ["bad", "good"]})
    assert deals
    assert {d.id for d in deals} == {"converse:a13144c-010", "converse:a18135c-832"}


def test_every_keyword_failing_raises_so_a_dead_store_is_visible(monkeypatch):
    import sources.converse as converse

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(converse, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        converse.fetch_deals({"keywords": ["bad", "worse"]})
