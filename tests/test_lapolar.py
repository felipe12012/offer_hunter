# tests/test_lapolar.py
from pathlib import Path

import pytest

from sources.health import NoResultsError

from sources.lapolar import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lapolar_sample.html"


def _fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_returns_one_deal_per_sku_deduping_duplicate_cards():
    result = parse_html(_fixture(), category="zapatillas")

    ids = [deal.id for deal in result]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert set(ids) == {"lapolar:653730", "lapolar:631187", "lapolar:653073"}


def test_parse_html_extracts_title_price_url_store_category_and_image():
    result = parse_html(_fixture(), category="zapatillas")

    deal = next(d for d in result if d.id == "lapolar:653730")
    assert deal.title == "Zapatilla Urbana Mujer Puma"
    assert deal.price == 29990
    assert deal.url == "https://www.abc.cl/zapatilla-urbana-mujer-puma/653730.html"
    assert deal.store == "lapolar"
    assert deal.category == "zapatillas"
    assert deal.image_url.startswith("https://")
    assert "653730" in deal.image_url
    assert not deal.image_url.startswith("data:")


def test_parse_html_uses_internet_price_not_the_la_polar_card_price():
    # The card carries a cheaper "la-polar" (tarjeta) price ($27.990) and the
    # internet price any customer pays ($29.990): the internet price must win.
    result = parse_html(_fixture(), category="zapatillas")

    deal = next(d for d in result if d.id == "lapolar:653730")
    assert deal.price == 29990
    assert deal.list_price == 59990
    assert deal.discount_pct == round((59990 - 29990) / 59990 * 100, 1)


def test_parse_html_computes_discount_when_crossed_price_present():
    result = parse_html(_fixture(), category="zapatillas")

    deal = next(d for d in result if d.id == "lapolar:653073")
    assert deal.price == 4990
    assert deal.list_price == 12990
    assert deal.discount_pct == round((12990 - 4990) / 12990 * 100, 1)


def test_parse_html_without_crossed_price_sets_list_price_to_price():
    result = parse_html(_fixture(), category="zapatillas")

    deal = next(d for d in result if d.id == "lapolar:631187")
    assert deal.price == 19990
    assert deal.list_price == 19990
    assert deal.discount_pct == 0.0


def test_parse_html_skips_cards_without_a_positive_price():
    html = """
    <html><head><title>x</title></head><body>
      <div class="product-tile__wrapper" data-pid="111">
        <div class="pdp-link"><a class="link" href="/p/111.html">Good</a></div>
        <div class="prices"><p class="internet price"><span class="price-value">$1.990</span></p></div>
        <img src="https://cdn.example/products/111.jpg" />
      </div>
      <div class="product-tile__wrapper" data-pid="222">
        <div class="pdp-link"><a class="link" href="/p/222.html">No price</a></div>
        <div class="prices"></div>
      </div>
    </body></html>
    """
    result = parse_html(html, category="x")

    assert [d.id for d in result] == ["lapolar:111"]


def test_parse_html_raises_with_diagnostics_when_a_full_size_page_has_no_cards():
    # A real-sized page without product cards means the layout changed (or a block page).
    html = "<html><head><title>Abc</title></head><body>" + "<p>x</p>" * 2500 + "</body></html>"
    with pytest.raises(RuntimeError) as excinfo:
        parse_html(html, category="zapatillas")

    message = str(excinfo.value)
    assert not isinstance(excinfo.value, NoResultsError)
    assert "La Polar" in message
    assert str(len(html)) in message


def test_parse_html_treats_a_tiny_fragment_as_no_results_not_as_a_failure():
    html = "<html><head><title>Abc</title></head><body>no products</body></html>"
    with pytest.raises(NoResultsError):
        parse_html(html, category="zapatillas")


def test_fetch_deals_isolates_a_failing_keyword(monkeypatch):
    from sources import lapolar

    good_html = _fixture()

    def fake_fetch_html(keyword, start=0):
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(lapolar, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(lapolar, "PAGE_SIZE", 999)

    deals = lapolar.fetch_deals({"keywords": ["bad", "good"]})

    assert {d.id for d in deals} == {"lapolar:653730", "lapolar:631187", "lapolar:653073"}


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    from sources import lapolar

    def boom(keyword, start=0):
        raise RuntimeError("site down")

    monkeypatch.setattr(lapolar, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        lapolar.fetch_deals({"keywords": ["bad", "worse"]})


def test_fetch_deals_dedupes_across_keywords(monkeypatch):
    from sources import lapolar

    html = _fixture()
    monkeypatch.setattr(lapolar, "fetch_html", lambda keyword, start=0: html)
    monkeypatch.setattr(lapolar, "PAGE_SIZE", 999)

    deals = lapolar.fetch_deals({"keywords": ["zapatillas", "polera"]})

    assert len(deals) == 3
