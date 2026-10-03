# tests/test_cruzverde.py
from pathlib import Path

import pytest

from sources.cruzverde import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cruzverde_sample.html"

ZERO_PRICE_HTML = """
<html><head><title>Resultados para crema</title></head><body>
  <ml-new-card-product>
    <a href="/crema-sin-precio/12345.html">
      <h2><span>Crema sin precio</span></h2>
    </a>
    <ml-price-tag-v2>
      <p class="font-bold text-green-turquoise"> $ 0 </p>
    </ml-price-tag-v2>
  </ml-new-card-product>
</body></html>
"""


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    assert len(result) == 3  # not 4 — the promoted duplicate must collapse
    ids = {deal.id for deal in result}
    assert ids == {"cruzverde:550670", "cruzverde:276008", "cruzverde:600123"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    deal = next(d for d in result if d.id == "cruzverde:550670")
    assert deal.title == "Refill Crema facial Hydro Boost 50 gr"
    assert deal.price == 7403
    assert deal.url == "https://www.cruzverde.cl/refill-crema-facial-hydro-boost-50-gr/550670.html"
    assert deal.store == "cruzverde"
    assert deal.category == "crema"


def test_parse_html_computes_discount_when_crossed_price_present():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    first = next(d for d in result if d.id == "cruzverde:550670")
    assert first.list_price == 11390
    assert first.discount_pct == 35.0

    second = next(d for d in result if d.id == "cruzverde:276008")
    assert second.price == 8118
    assert second.list_price == 12490
    assert second.discount_pct == 35.0


def test_parse_html_falls_back_to_price_as_list_price_when_no_crossed_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="crema")

    solar = next(d for d in result if d.id == "cruzverde:600123")
    assert solar.price == 8990
    assert solar.list_price == 8990
    assert solar.discount_pct == 0.0


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
    html = "<html><head><title>Cruz Verde</title></head><body>no products</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="crema")


def test_a_failing_keyword_does_not_abort_the_other_keywords(monkeypatch):
    import sources.cruzverde as cruzverde

    good_html = FIXTURE_PATH.read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(cruzverde, "fetch_html", fake_fetch_html)

    deals = cruzverde.fetch_deals({"keywords": ["bad", "good"]})
    assert deals
    assert {d.id for d in deals} == {
        "cruzverde:550670",
        "cruzverde:276008",
        "cruzverde:600123",
    }


def test_every_keyword_failing_raises_so_a_dead_store_is_visible(monkeypatch):
    import sources.cruzverde as cruzverde

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(cruzverde, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        cruzverde.fetch_deals({"keywords": ["bad", "worse"]})
