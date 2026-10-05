# tests/test_maconline.py
from pathlib import Path

import pytest

from sources.maconline import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "maconline_sample.html"

ZERO_PRICE_HTML = """
<html><head><title>MacOnline</title></head><body>
  <div class="product-list-item" id="product_9">
    <div class="panel-body product-body">
      <a href="/products/x"><img class="lazyload" data-src="https://cdn.example/x.jpg"></a>
    </div>
    <div class="panel-footer">
      <a class="info" href="/products/x" title="X">
        <span>X</span>
        <span><span class="price selling lead">$0</span></span>
      </a>
    </div>
  </div>
</body></html>
"""


def _fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_returns_one_deal_per_sku_deduping_duplicate_cards():
    result = parse_html(_fixture(), category="tecnologia")

    ids = [deal.id for deal in result]
    assert len(ids) == 3  # not 4 — the duplicated block must collapse
    assert len(set(ids)) == 3
    assert set(ids) == {"maconline:4324", "maconline:4325", "maconline:4923"}


def test_parse_html_extracts_title_price_url_store_category_and_image():
    result = parse_html(_fixture(), category="tecnologia")

    deal = next(d for d in result if d.id == "maconline:4324")
    assert deal.title == "AirPods 4"
    assert deal.price == 129990
    assert deal.url == "https://www.maconline.com/products/airpods-4"
    assert deal.store == "maconline"
    assert deal.category == "tecnologia"
    assert deal.image_url.startswith("https://")
    assert "Apple_AirPods_4_1" in deal.image_url
    assert "free-shipping" not in deal.image_url
    assert not deal.image_url.startswith("data:")


def test_parse_html_computes_discount_when_crossed_price_present():
    result = parse_html(_fixture(), category="tecnologia")

    airpods4 = next(d for d in result if d.id == "maconline:4324")
    assert airpods4.list_price == 159990
    assert airpods4.discount_pct == round((159990 - 129990) / 159990 * 100, 1)

    anc = next(d for d in result if d.id == "maconline:4325")
    assert anc.price == 169990
    assert anc.list_price == 219990
    assert anc.discount_pct == round((219990 - 169990) / 219990 * 100, 1)


def test_parse_html_without_crossed_price_sets_list_price_to_price():
    result = parse_html(_fixture(), category="tecnologia")

    airpods5 = next(d for d in result if d.id == "maconline:4923")
    assert airpods5.price == 159990
    assert airpods5.list_price == 159990
    assert airpods5.discount_pct == 0.0


def test_parse_html_skips_cards_without_a_positive_price():
    assert parse_html(ZERO_PRICE_HTML, category="tecnologia") == []


def test_parse_html_raises_with_diagnostics_when_no_product_cards():
    html = "<html><head><title>MacOnline | Tienda</title></head><body>no products here</body></html>"
    with pytest.raises(RuntimeError) as excinfo:
        parse_html(html, category="tecnologia")

    message = str(excinfo.value)
    assert "MacOnline" in message
    assert str(len(html)) in message


def test_fetch_deals_isolates_a_failing_keyword(monkeypatch):
    from sources import maconline

    good_html = _fixture()

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(maconline, "fetch_html", fake_fetch_html)

    deals = maconline.fetch_deals({"keywords": ["bad", "good"]})

    assert {d.id for d in deals} == {"maconline:4324", "maconline:4325", "maconline:4923"}
    assert {d.category for d in deals} == {"tecnologia"}


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    from sources import maconline

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(maconline, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        maconline.fetch_deals({"keywords": ["bad", "worse"]})


def test_fetch_deals_dedupes_across_keywords(monkeypatch):
    from sources import maconline

    html = _fixture()
    monkeypatch.setattr(maconline, "fetch_html", lambda keyword: html)

    deals = maconline.fetch_deals({"keywords": ["airpods", "audifonos"]})

    assert len(deals) == 3
