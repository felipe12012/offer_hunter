# tests/test_fila.py
from pathlib import Path

import pytest

import sources.fila as fila
from sources.fila import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fila_sample.html"


def _html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_dedupes_repeated_blocks():
    result = parse_html(_html(), category="zapatillas")

    assert len(result) == 3  # 4 blocks, the duplicated one collapses to one Deal
    assert {deal.id for deal in result} == {
        "fila:105215-100",
        "fila:1BM00624-332",
        "fila:1FM00139-125",
    }


def test_parse_html_extracts_title_price_url_image_and_id():
    result = parse_html(_html(), category="zapatillas")

    deal = next(d for d in result if d.id == "fila:105215-100")
    assert deal.title == "Zapatillas Fila New Retro RN Hombre"
    assert deal.price == 59990
    assert deal.url == "https://fila.cl/zapatillas-fila-new-retro-rn-hombre-105215-100-blanco"
    assert deal.store == "fila"
    assert deal.category == "zapatillas"
    assert deal.image_url.startswith("https://fila.cl/media/")
    assert not deal.image_url.startswith("data:")


def test_no_crossed_price_uses_price_as_list_price():
    result = parse_html(_html(), category="zapatillas")

    deal = next(d for d in result if d.id == "fila:105215-100")
    assert deal.list_price == 59990
    assert deal.discount_pct == 0.0


def test_crossed_price_becomes_list_price_and_discount():
    result = parse_html(_html(), category="zapatillas")

    uproot = next(d for d in result if d.id == "fila:1BM00624-332")
    assert uproot.price == 55990
    assert uproot.list_price == 69990
    assert uproot.discount_pct == 20.0

    disruptor = next(d for d in result if d.id == "fila:1FM00139-125")
    assert disruptor.price == 48990
    assert disruptor.list_price == 69990
    assert disruptor.discount_pct == 30.0


def test_zero_price_is_skipped():
    html = """
    <html><head><title>Fila</title></head><body>
      <ul class="products list items product-items">
        <li class="item product product-item">
          <a class="product-item-photo" href="https://fila.cl/zapatilla-x">
            <img class="product-image-photo" src="https://fila.cl/media/x.jpg">
          </a>
          <strong class="product name product-item-name">
            <a class="product-item-link" href="https://fila.cl/zapatilla-x">Zapatilla X</a>
          </strong>
          <form data-product-sku="X-1"></form>
          <span data-price-amount="0" data-price-type="finalPrice" class="price-wrapper"></span>
        </li>
      </ul>
    </body></html>
    """
    assert parse_html(html, category="zapatillas") == []


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Fila Chile</title></head><body>nada</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="zapatillas")


def test_fetch_deals_isolates_one_keyword_failure(monkeypatch):
    def fake_fetch_html(keyword):
        if keyword == "fila":
            raise RuntimeError("boom")
        return _html()

    monkeypatch.setattr(fila, "fetch_html", fake_fetch_html)
    deals = fila.fetch_deals({"keywords": ["zapatillas", "fila"]})

    assert deals
    assert all(deal.category == "zapatillas" for deal in deals)


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    def fake_fetch_html(keyword):
        raise RuntimeError("boom")

    monkeypatch.setattr(fila, "fetch_html", fake_fetch_html)
    with pytest.raises(RuntimeError):
        fila.fetch_deals({"keywords": ["zapatillas", "fila"]})
