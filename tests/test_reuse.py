# tests/test_reuse.py
import json
from pathlib import Path

from sources.reuse import CONFIG
from sources.shopify import parse_products

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "reuse_sample.html"


def _fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _product(**overrides) -> dict:
    product = {
        "id": "999",
        "title": "Producto de prueba",
        "handle": "producto-de-prueba",
        "images": [{"src": "https://cdn.shopify.com/s/files/1/0/0/files/x.jpg"}],
        "variants": [
            {"sku": "SYN1", "price": "10000", "compare_at_price": "20000", "available": True}
        ],
    }
    product.update(overrides)
    return product


def test_parse_products_extracts_id_title_price_url_and_image_from_the_fixture():
    deals = parse_products(_fixture(), CONFIG)

    assert len(deals) == 3
    deal = next(d for d in deals if d.id == "reuse:55735142")
    assert deal.title == (
        "Lenovo XT92 TWS Audífonos Bluetooth Inalámbricos + Reloj Inteligente Reacondicionado"
    )
    assert deal.price == 19990
    assert deal.url == (
        "https://www.reuse.cl/products/"
        "lenovo-xt92-tws-audifonos-bluetooth-inalambricos-reloj-inteligente-reacondicionado"
    )
    assert deal.image_url == (
        "https://cdn.shopify.com/s/files/1/0418/4277/0081/files/a-2026-10-02T132519.489.jpg?v=1790969176"
    )
    assert deal.store == "reuse"
    assert deal.category == "tecnologia"


def test_compare_at_price_becomes_list_price_and_discount():
    deals = parse_products(_fixture(), CONFIG)

    lenovo = next(d for d in deals if d.id == "reuse:55735142")
    assert lenovo.list_price == 29990
    assert lenovo.discount_pct == 33.3

    camera = next(d for d in deals if d.id == "reuse:46395308")
    assert camera.list_price == 49990
    assert camera.discount_pct == 20.0


def test_no_crossed_price_falls_back_to_the_sale_price():
    deals = parse_products(_fixture(), CONFIG)

    lp40 = next(d for d in deals if d.id == "reuse:34699078")
    assert lp40.price == 9990
    assert lp40.list_price == 9990
    assert lp40.discount_pct == 0.0


def test_sold_out_products_are_filtered():
    deals = parse_products(
        [_product(variants=[{"sku": "S", "price": "10000", "compare_at_price": "20000", "available": False}])],
        CONFIG,
    )

    assert deals == []
