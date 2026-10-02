# tests/test_paris.py
from pathlib import Path

import pytest

from sources.paris import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "paris_sample.html"


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    assert len(result) == 3  # not 4 — the duplicated block must collapse to one Deal
    ids = {deal.id for deal in result}
    assert ids == {"paris:870486999", "paris:320477999", "paris:MKODCEUUTU"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    buds = next(d for d in result if d.id == "paris:870486999")
    assert buds.title == "Audífonos Bluetooth Redmi Buds 6 Play Black"
    assert buds.price == 12990
    assert buds.url == "https://www.paris.cl/audifonos-bluetooth-redmi-buds-6-play-black-870486999.html"
    assert buds.store == "paris"
    assert buds.category == "audifonos"


def test_parse_html_falls_back_to_price_as_list_price_when_no_discount_markup():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    hoco = next(d for d in result if d.id == "paris:MKODCEUUTU")
    assert hoco.price == 19990
    assert hoco.list_price == 19990
    assert hoco.discount_pct == 0.0


def test_parse_html_computes_discount_when_crossed_price_present():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    buds = next(d for d in result if d.id == "paris:870486999")
    assert buds.list_price == 19990
    assert buds.discount_pct == 35.0

    air = next(d for d in result if d.id == "paris:320477999")
    assert air.price == 8990
    assert air.list_price == 14990
    assert air.discount_pct == 40.0


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Paris.cl</title></head><body>no products here</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="audifonos")
