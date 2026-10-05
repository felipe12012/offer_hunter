# tests/test_wayu.py
import json
from pathlib import Path

from sources.shopify import parse_products
from sources.wayu import CONFIG

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wayu_sample.html"


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
    deal = next(d for d in deals if d.id == "wayu:16176670703919")
    assert deal.title == "Experiencia Vino Wayu"
    assert deal.price == 19990
    assert deal.url == "https://wayu.cl/products/vino"
    assert deal.image_url == (
        "https://cdn.shopify.com/s/files/1/0818/0406/7119/files/99e9f2c7-5bb0-4926-ae11-70a3781d0acf.png?v=1790783535"
    )
    assert deal.store == "wayu"
    assert deal.category == "muebles"


def test_a_variant_without_sku_falls_back_to_the_product_id():
    deals = parse_products(_fixture(), CONFIG)

    assert {d.id for d in deals} == {
        "wayu:16176670703919",
        "wayu:16176674275631",
        "wayu:6902221563651",
    }


def test_compare_at_price_becomes_list_price_and_discount():
    deals = parse_products(_fixture(), CONFIG)

    wine = next(d for d in deals if d.id == "wayu:16176670703919")
    assert wine.list_price == 32970
    assert wine.discount_pct == 39.4


def test_no_crossed_price_falls_back_to_the_sale_price():
    deals = parse_products(_fixture(), CONFIG)

    solitaire = next(d for d in deals if d.id == "wayu:6902221563651")
    assert solitaire.price == 12990
    assert solitaire.list_price == 12990
    assert solitaire.discount_pct == 0.0


def test_sold_out_products_are_filtered():
    deals = parse_products(
        [_product(variants=[{"sku": "S", "price": "10000", "compare_at_price": "20000", "available": False}])],
        CONFIG,
    )

    assert deals == []
