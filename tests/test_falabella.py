# tests/test_falabella.py
from pathlib import Path

import pytest

from sources.falabella import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "falabella_sample.html"


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    assert len(result) == 3  # not 4 — the same SKU rendered in two blocks must collapse to one Deal
    ids = {deal.id for deal in result}
    assert ids == {
        "falabella:142403285",
        "falabella:80717556",
        "falabella:80762054",
    }


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    lenovo = next(d for d in result if d.id == "falabella:142403285")
    assert lenovo.title == "Audífonos Clip TA140 TWS Bluetooth 5.4"
    assert lenovo.price == 18990
    assert lenovo.url == (
        "https://www.falabella.com/falabella-cl/product/142403285/"
        "audifonos-lenovo-clip-ta140-tws-bluetooth-5-4/151118201"
    )
    assert lenovo.store == "falabella"
    assert lenovo.category == "audifonos"


def test_parse_html_computes_discount_from_crossed_normal_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    lenovo = next(d for d in result if d.id == "falabella:142403285")
    assert lenovo.price == 18990
    assert lenovo.list_price == 28988
    assert lenovo.discount_pct == 34.5


def test_parse_html_extracts_discount_when_only_internet_and_normal_prices():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    buds = next(d for d in result if d.id == "falabella:80717556")
    assert buds.title == "Galaxy Buds4 Pro Black"
    assert buds.price == 219990
    assert buds.list_price == 274990
    assert buds.discount_pct == 20.0


def test_parse_html_falls_back_to_price_as_list_price_when_no_normal_markup():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    tune = next(d for d in result if d.id == "falabella:80762054")
    assert tune.price == 49990
    assert tune.list_price == 49990
    assert tune.discount_pct == 0.0


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Sin resultados</title></head><body>no products here</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="audifonos")
