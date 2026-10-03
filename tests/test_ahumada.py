# tests/test_ahumada.py
from pathlib import Path

import pytest

from sources.ahumada import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ahumada_sample.html"


def _fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_returns_one_deal_per_sku_deduping_duplicate_cards():
    result = parse_html(_fixture(), category="crema")

    ids = [deal.id for deal in result]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert set(ids) == {"ahumada:88517", "ahumada:68120", "ahumada:96599"}


def test_parse_html_extracts_title_price_url_store_category_and_image():
    result = parse_html(_fixture(), category="crema")

    deal = next(d for d in result if d.id == "ahumada:88517")
    assert deal.title == "Crema De Tratamiento Herbal Essence Argan 300 Ml"
    assert deal.price == 4990
    assert deal.url == (
        "https://www.farmaciasahumada.cl/"
        "crema-de-tratamiento-herbal-essence-argan-300-ml-88517.html"
    )
    assert deal.store == "ahumada"
    assert deal.category == "crema"
    assert deal.image_url.startswith("https://")
    assert "88517" in deal.image_url
    assert not deal.image_url.startswith("data:")


def test_parse_html_computes_discount_when_crossed_price_present():
    result = parse_html(_fixture(), category="crema")

    deal = next(d for d in result if d.id == "ahumada:88517")
    assert deal.list_price == 10649
    assert deal.discount_pct == round((10649 - 4990) / 10649 * 100, 1)

    staple = next(d for d in result if d.id == "ahumada:68120")
    assert staple.price == 5550
    assert staple.list_price == 11099
    assert staple.discount_pct == round((11099 - 5550) / 11099 * 100, 1)


def test_parse_html_without_crossed_price_sets_list_price_to_price():
    result = parse_html(_fixture(), category="crema")

    deal = next(d for d in result if d.id == "ahumada:96599")
    assert deal.price == 6999
    assert deal.list_price == 6999
    assert deal.discount_pct == 0.0


def test_parse_html_skips_cards_without_a_positive_price():
    html = """
    <html><head><title>x</title></head><body>
      <div class="product-tile" data-pid="111">
        <div class="pdp-link"><a class="link" href="/p-111.html">Good</a></div>
        <div class="price"><span class="sales"><div class="promotion-badge-container ml-0">$1.990</div></span></div>
        <img src="https://cdn.example/products/111.jpg" />
      </div>
      <div class="product-tile" data-pid="222">
        <div class="pdp-link"><a class="link" href="/p-222.html">No price</a></div>
        <div class="price"></div>
      </div>
    </body></html>
    """
    result = parse_html(html, category="x")

    assert [d.id for d in result] == ["ahumada:111"]


def test_parse_html_raises_on_zero_cards():
    html = "<html><head><title>Ahumada</title></head><body>no products</body></html>"
    with pytest.raises(RuntimeError) as excinfo:
        parse_html(html, category="crema")

    message = str(excinfo.value)
    assert "Ahumada" in message
    assert str(len(html)) in message


def test_fetch_deals_isolates_a_failing_keyword(monkeypatch):
    from sources import ahumada

    good_html = _fixture()

    def fake_fetch_html(keyword, start=0):
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(ahumada, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(ahumada, "PAGE_SIZE", 999)

    deals = ahumada.fetch_deals({"keywords": ["bad", "good"]})

    assert {d.id for d in deals} == {"ahumada:88517", "ahumada:68120", "ahumada:96599"}


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    from sources import ahumada

    def boom(keyword, start=0):
        raise RuntimeError("site down")

    monkeypatch.setattr(ahumada, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        ahumada.fetch_deals({"keywords": ["bad", "worse"]})


def test_fetch_deals_dedupes_across_keywords(monkeypatch):
    from sources import ahumada

    html = _fixture()
    monkeypatch.setattr(ahumada, "fetch_html", lambda keyword, start=0: html)
    monkeypatch.setattr(ahumada, "PAGE_SIZE", 999)

    deals = ahumada.fetch_deals({"keywords": ["crema", "protector solar"]})

    assert len(deals) == 3
