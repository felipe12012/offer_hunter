# tests/test_ripley.py
from pathlib import Path

import pytest

from sources.ripley import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ripley_sample.html"


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    assert len(result) == 2  # duplicate Samsung block must collapse to one Deal
    ids = {deal.id for deal in result}
    assert ids == {"ripley:2000382046113", "ripley:2000347231318"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    samsung = next(d for d in result if d.id == "ripley:2000382046113")
    assert samsung.title == "AUDÍFONOS SAMSUNG TIPO-C"
    assert samsung.price == 12990
    assert samsung.url == (
        "https://simple.ripley.cl/audifonos-samsung-tipo-c-2000382046113p"
        "?color_80=negro&s=mdco&searchTerm=audifonos"
    )
    assert samsung.store == "ripley"
    assert samsung.category == "audifonos"


def test_parse_html_falls_back_to_price_as_list_price_when_no_discount_markup():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    sony = next(d for d in result if d.id == "ripley:2000347231318")
    assert sony.price == 6990
    assert sony.list_price == 6990
    assert sony.discount_pct == 0.0


def test_parse_html_computes_discount_when_crossed_price_exists():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="audifonos")

    samsung = next(d for d in result if d.id == "ripley:2000382046113")
    assert samsung.list_price == 19990
    assert samsung.discount_pct == 35.0


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Ripley</title></head><body>no products here</body></html>"
    with pytest.raises(RuntimeError) as excinfo:
        parse_html(html, category="audifonos")

    message = str(excinfo.value)
    assert "Ripley" in message
    assert str(len(html)) in message
