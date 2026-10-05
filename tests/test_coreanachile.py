# tests/test_coreanachile.py
import json
from pathlib import Path

from sources.coreanachile import CONFIG
from sources.shopify import parse_products

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "coreanachile_sample.html"


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
    deal = next(d for d in deals if d.id == "coreanachile:FCXQ030270")
    assert deal.title == "AMPLE:N Mini Sérum Facial Calmante Cica PDRN Hyper Shot 7 ML"
    assert deal.price == 5990
    assert deal.url == (
        "https://coreanachile.cl/products/ample-n-mini-serum-facial-calmante-cica-pdrn-hyper-shot-7-ml"
    )
    assert deal.image_url == (
        "https://cdn.shopify.com/s/files/1/0587/1524/2688/files/a0dfb925-b0fd-4567-9574-b0a557355cb5.jpg?v=1786047395"
    )
    assert deal.store == "coreanachile"
    assert deal.category == "belleza"


def test_compare_at_price_becomes_list_price_and_discount():
    deals = parse_products([_product()], CONFIG)

    assert deals[0].list_price == 20000
    assert deals[0].discount_pct == 50.0


def test_no_crossed_price_falls_back_to_the_sale_price():
    deals = parse_products([_product(variants=[{"sku": "S", "price": "10000", "compare_at_price": "0", "available": True}])], CONFIG)

    assert deals[0].list_price == 10000
    assert deals[0].discount_pct == 0.0


def test_sold_out_products_are_filtered():
    deals = parse_products(
        [_product(variants=[{"sku": "S", "price": "10000", "compare_at_price": "20000", "available": False}])],
        CONFIG,
    )

    assert deals == []
