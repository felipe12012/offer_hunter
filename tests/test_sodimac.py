# tests/test_sodimac.py
from pathlib import Path

import pytest

from sources.sodimac import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sodimac_sample.html"


def test_parse_html_extracts_one_deal_per_sku_deduping_mobile_and_desktop_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="notebook")

    assert len(result) == 2  # not 4 — each SKU's mobile+desktop price blocks must collapse to one Deal
    ids = {deal.id for deal in result}
    assert ids == {"sodimac:6242030", "sodimac:6409121"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="notebook")

    fan = next(d for d in result if d.id == "sodimac:6242030")
    assert fan.title == "Ventilador de notebook"
    assert fan.price == 8990
    assert fan.url == "https://www.sodimac.cl/sodimac-cl/product/6242030/ventilador-de-notebook/6242030/"
    assert fan.store == "sodimac"
    assert fan.category == "notebook"


def test_parse_html_falls_back_to_price_as_list_price_when_no_discount_markup():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="notebook")

    fan = next(d for d in result if d.id == "sodimac:6242030")
    assert fan.list_price == 8990
    assert fan.discount_pct == 0.0


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><body>no products here</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="notebook")
