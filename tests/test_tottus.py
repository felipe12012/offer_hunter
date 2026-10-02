# tests/test_tottus.py
from pathlib import Path

import pytest

from sources.tottus import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "tottus_sample.html"


def test_parse_html_extracts_one_deal_per_sku_deduping_repeated_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="leche")

    assert len(result) == 2  # not 3 — the repeated pod for the same SKU must collapse to one Deal
    ids = {deal.id for deal in result}
    assert ids == {"tottus:113152870", "tottus:112737942"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="leche")

    milk = next(d for d in result if d.id == "tottus:113152870")
    assert milk.title == "TOTTUS Leche Entera Natural"
    assert milk.price == 990
    assert milk.url == "https://www.tottus.cl/tottus-cl/articulo/113152870/leche-tottus-entera-1lt/113152872"
    assert milk.store == "tottus"
    assert milk.category == "leche"


def test_parse_html_computes_discount_from_crossed_out_normal_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="leche")

    milk = next(d for d in result if d.id == "tottus:113152870")
    assert milk.list_price == 1150
    assert milk.discount_pct == 13.9


def test_parse_html_falls_back_to_price_as_list_price_when_no_crossed_price():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="leche")

    plain = next(d for d in result if d.id == "tottus:112737942")
    assert plain.title == "SOPROLE Leche Entera Natural Soprole 1 lt"
    assert plain.price == 1350
    assert plain.list_price == 1350
    assert plain.discount_pct == 0.0


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><title>un momento</title><body>no products here</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="leche")
