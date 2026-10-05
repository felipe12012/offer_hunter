# tests/test_kliper.py
from pathlib import Path

import pytest

from sources.kliper import CATEGORY, parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "kliper_sample.html"

ZERO_PRICE_HTML = """
<html><head><title>Resultados de búsqueda para: 'x'</title></head><body>
  <ol class="products">
    <li class="item product product-item">
      <a class="product-item-link" href="https://www.kliper.cl/polera-x-111111-ab">Polera X</a>
      <div class="price-box">
        <span data-price-type="finalPrice" data-price-amount="0"><span class="price">$0</span></span>
      </div>
      <form data-product-sku="111111_AB"></form>
    </li>
  </ol>
</body></html>
"""


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category=CATEGORY)

    assert len(result) == 3  # not 4 — the duplicated block must collapse to one Deal
    ids = {deal.id for deal in result}
    assert ids == {"kliper:586306_GP03", "kliper:795346_GP01", "kliper:723631_GP09"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category=CATEGORY)

    deal = next(d for d in result if d.id == "kliper:586306_GP03")
    assert deal.title == "Polera Gap Polo Manga Corta Hombre Black 013"
    assert deal.price == 24490
    assert deal.url == "https://www.kliper.cl/polera-gap-polo-manga-corta-hombre-black-013-586306-gp03"
    assert deal.store == "kliper"
    assert deal.category == CATEGORY


def test_parse_html_computes_discount_when_crossed_price_present():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category=CATEGORY)

    deal = next(d for d in result if d.id == "kliper:795346_GP01")
    assert deal.price == 11990
    assert deal.list_price == 19990
    assert deal.discount_pct == 40.0


def test_parse_html_falls_back_to_price_as_list_price_when_no_crossed_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category=CATEGORY)

    deal = next(d for d in result if d.id == "kliper:723631_GP09")
    assert deal.price == 14990
    assert deal.list_price == deal.price
    assert deal.discount_pct == 0.0


def test_parse_html_extracts_real_product_image():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category=CATEGORY)

    for deal in result:
        assert deal.image_url.startswith("http"), deal
        assert not deal.image_url.startswith("data:")
        assert "/media/catalog/" in deal.image_url, deal


def test_parse_html_skips_zero_price_products():
    assert parse_html(ZERO_PRICE_HTML, category=CATEGORY) == []


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Kliper Chile</title></head><body>no products here</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category=CATEGORY)


def test_a_failing_keyword_does_not_abort_the_other_keywords(monkeypatch):
    import sources.kliper as kliper

    good_html = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(kliper, "fetch_html", fake_fetch_html)

    deals = kliper.fetch_deals({"keywords": ["bad", "good"]})
    assert deals
    assert {d.id for d in deals} == {"kliper:586306_GP03", "kliper:795346_GP01", "kliper:723631_GP09"}


def test_every_keyword_failing_raises_so_a_dead_store_is_visible(monkeypatch):
    import sources.kliper as kliper

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(kliper, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        kliper.fetch_deals({"keywords": ["bad", "worse"]})
