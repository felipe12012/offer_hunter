# tests/test_skechers.py
from pathlib import Path

import pytest

import sources.skechers as skechers
from sources.skechers import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "skechers_sample.html"


def _html() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_html_dedupes_repeated_blocks():
    result = parse_html(_html(), category="zapatillas")

    assert len(result) == 3  # 4 blocks, the duplicated one collapses to one Deal
    assert {deal.id for deal in result} == {
        "skechers:women-s-hotshot-kickoff-3",
        "skechers:women-s-hotshot-hi-lifted-luxe-3",
        "skechers:women-s-jade-best-in-class-3",
    }


def test_parse_html_extracts_title_price_url_image_and_id():
    result = parse_html(_html(), category="zapatillas")

    deal = next(d for d in result if d.id == "skechers:women-s-hotshot-kickoff-3")
    assert deal.title == "Zapatillas Mujer Hotshot Kickoff"
    assert deal.price == 59990
    assert deal.url == "https://www.skechers.cl/detalle/women-s-hotshot-kickoff-3"
    assert deal.store == "skechers"
    assert deal.category == "zapatillas"
    assert deal.image_url == (
        "https://skecherscl.b-cdn.net/img/Producto/23638/ith_185232_NTLB.jpg"
    )


def test_lazy_image_falls_back_to_data_src():
    result = parse_html(_html(), category="zapatillas")

    jade = next(d for d in result if d.id == "skechers:women-s-jade-best-in-class-3")
    assert jade.image_url.startswith("https://skecherscl.b-cdn.net/")
    assert not jade.image_url.startswith("data:")


def test_no_crossed_price_uses_price_as_list_price():
    result = parse_html(_html(), category="zapatillas")

    deal = next(d for d in result if d.id == "skechers:women-s-hotshot-kickoff-3")
    assert deal.list_price == 59990
    assert deal.discount_pct == 0.0


def test_crossed_price_becomes_list_price_and_discount():
    result = parse_html(_html(), category="zapatillas")

    hi = next(d for d in result if d.id == "skechers:women-s-hotshot-hi-lifted-luxe-3")
    assert hi.price == 41990
    assert hi.list_price == 69990
    assert hi.discount_pct == 40.0

    jade = next(d for d in result if d.id == "skechers:women-s-jade-best-in-class-3")
    assert jade.price == 37990
    assert jade.list_price == 62990
    assert jade.discount_pct == 39.7


def test_zero_price_is_skipped():
    html = """
    <html><head><title>SKECHERS CHILE</title></head><body>
      <div class="item-producto text-center">
        <a href="/detalle/zapatilla-x"><img src="https://x.cl/x.jpg"></a>
        <a href="/detalle/zapatilla-x"><h2>Zapatilla X</h2></a>
        <h3 class="text-left text-info">$0</h3>
      </div>
    </body></html>
    """
    assert parse_html(html, category="zapatillas") == []


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>SKECHERS CHILE</title></head><body>nada</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="zapatillas")


def test_fetch_deals_isolates_one_keyword_failure(monkeypatch):
    def fake_fetch_html(keyword):
        if keyword == "skechers":
            raise RuntimeError("boom")
        return _html()

    monkeypatch.setattr(skechers, "fetch_html", fake_fetch_html)
    deals = skechers.fetch_deals({"keywords": ["zapatillas", "skechers"]})

    assert deals
    assert all(deal.category == "zapatillas" for deal in deals)


def test_fetch_deals_raises_when_every_keyword_fails(monkeypatch):
    def fake_fetch_html(keyword):
        raise RuntimeError("boom")

    monkeypatch.setattr(skechers, "fetch_html", fake_fetch_html)
    with pytest.raises(RuntimeError):
        skechers.fetch_deals({"keywords": ["zapatillas", "skechers"]})
