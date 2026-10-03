# tests/test_tricot.py
from pathlib import Path

import pytest

from sources.health import NoResultsError

from sources.tricot import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tricot_sample.html"


def _fixture() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_returns_one_deal_per_sku_deduping_duplicate_cards():
    result = parse_html(_fixture(), category="polera")

    ids = [deal.id for deal in result]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert set(ids) == {"tricot:552131", "tricot:552134", "tricot:560590"}


def test_parse_html_extracts_title_price_url_store_category_and_image():
    result = parse_html(_fixture(), category="polera")

    deal = next(d for d in result if d.id == "tricot:552131")
    assert deal.title == "Polera bebé"
    assert deal.price == 3990
    assert deal.url == "https://www.tricot.cl/polera-bebe-552131.html"
    assert deal.store == "tricot"
    assert deal.category == "polera"
    assert deal.image_url.startswith("https://")
    assert "552131" in deal.image_url
    assert not deal.image_url.startswith("data:")


def test_parse_html_computes_discount_when_crossed_price_present():
    result = parse_html(_fixture(), category="polera")

    deal = next(d for d in result if d.id == "tricot:552131")
    assert deal.list_price == 12990
    assert deal.discount_pct == round((12990 - 3990) / 12990 * 100, 1)

    other = next(d for d in result if d.id == "tricot:552134")
    assert other.price == 2990
    assert other.list_price == 8990
    assert other.discount_pct == round((8990 - 2990) / 8990 * 100, 1)


def test_parse_html_without_crossed_price_sets_list_price_to_price():
    result = parse_html(_fixture(), category="polera")

    deal = next(d for d in result if d.id == "tricot:560590")
    assert deal.price == 3990
    assert deal.list_price == 3990
    assert deal.discount_pct == 0.0


def test_parse_html_ignores_a_crossed_price_lower_than_the_current_price():
    html = """
    <html><head><title>x</title></head><body>
      <div class="product-tile" data-pid="111">
        <div class="pdp-link"><a class="link" href="/p-111.html">Good</a></div>
        <div class="price"><span>
          <del><span class="list"><span class="value">$1.000</span></span></del>
          <span class="tri-sales sales"><span class="value">$2.990</span></span>
        </span></div>
        <img data-src="https://www.tricot.cl/dw/image/products/111.jpg" />
      </div>
    </body></html>
    """
    result = parse_html(html, category="x")

    assert [d.id for d in result] == ["tricot:111"]
    assert result[0].price == 2990
    assert result[0].list_price == 2990
    assert result[0].discount_pct == 0.0


def test_parse_html_skips_cards_without_a_positive_price():
    html = """
    <html><head><title>x</title></head><body>
      <div class="product-tile" data-pid="111">
        <div class="pdp-link"><a class="link" href="/p-111.html">Good</a></div>
        <div class="price"><span class="tri-sales sales"><span class="value">$1.990</span></span></div>
        <img data-src="https://www.tricot.cl/dw/image/products/111.jpg" />
      </div>
      <div class="product-tile" data-pid="222">
        <div class="pdp-link"><a class="link" href="/p-222.html">No price</a></div>
        <div class="price"></div>
      </div>
    </body></html>
    """
    result = parse_html(html, category="x")

    assert [d.id for d in result] == ["tricot:111"]


def test_parse_html_reads_the_sku_from_the_product_url_when_no_data_pid():
    html = """
    <html><head><title>x</title></head><body>
      <div class="product-tile">
        <div class="pdp-link"><a class="link" href="/polera-bebe-552999.html">Polera</a></div>
        <div class="price"><span class="tri-sales sales"><span class="value">$4.990</span></span></div>
        <img data-src="https://www.tricot.cl/dw/image/products/552999.jpg" />
      </div>
    </body></html>
    """
    result = parse_html(html, category="x")

    assert [d.id for d in result] == ["tricot:552999"]


def test_parse_html_raises_with_diagnostics_when_a_full_size_page_has_no_cards():
    html = "<html><head><title>Tricot</title></head><body>" + "<p>x</p>" * 2500 + "</body></html>"
    with pytest.raises(RuntimeError) as excinfo:
        parse_html(html, category="polera")

    message = str(excinfo.value)
    assert not isinstance(excinfo.value, NoResultsError)
    assert "Tricot" in message
    assert str(len(html)) in message


def test_parse_html_treats_a_tiny_fragment_as_no_results_not_as_a_failure():
    html = "<html><head><title>Tricot</title></head><body>no products</body></html>"
    with pytest.raises(NoResultsError):
        parse_html(html, category="polera")


def test_fetch_deals_isolates_a_failing_keyword(monkeypatch):
    from sources import tricot

    good_html = _fixture()

    def fake_fetch_html(keyword, start=0):
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(tricot, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(tricot, "PAGE_SIZE", 999)

    deals = tricot.fetch_deals({"keywords": ["bad", "good"]})

    assert {d.id for d in deals} == {"tricot:552131", "tricot:552134", "tricot:560590"}


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    from sources import tricot

    def boom(keyword, start=0):
        raise RuntimeError("site down")

    monkeypatch.setattr(tricot, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        tricot.fetch_deals({"keywords": ["bad", "worse"]})


def test_fetch_deals_dedupes_across_keywords(monkeypatch):
    from sources import tricot

    html = _fixture()
    monkeypatch.setattr(tricot, "fetch_html", lambda keyword, start=0: html)
    monkeypatch.setattr(tricot, "PAGE_SIZE", 999)

    deals = tricot.fetch_deals({"keywords": ["polera", "vestido"]})

    assert len(deals) == 3


def test_fetch_deals_treats_an_empty_grid_as_no_results(monkeypatch):
    from sources import tricot

    empty = "<html><head><title>Tricot</title></head><body>no products</body></html>"

    def fake_fetch_html(keyword, start=0):
        if keyword == "nothing":
            return empty
        return _fixture()

    monkeypatch.setattr(tricot, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(tricot, "PAGE_SIZE", 999)

    deals = tricot.fetch_deals({"keywords": ["nothing", "polera"]})

    assert {d.id for d in deals} == {"tricot:552131", "tricot:552134", "tricot:560590"}
