import json
from pathlib import Path

from sources import fashionspark
from sources.fashionspark import CONFIG
from sources.shopify import parse_products

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fashionspark_sample.html"


def _fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _product(**overrides) -> dict:
    product = {
        "id": 1,
        "title": "Polera Mujer",
        "handle": "polera-mujer",
        "images": [{"src": "https://cdn.shopify.com/s/files/1/polera.jpg"}],
        "variants": [
            {"sku": "SKU1", "price": "9990", "compare_at_price": "19990", "available": True}
        ],
    }
    product.update(overrides)
    return product


def test_parse_products_maps_id_title_price_url_image_store_and_category():
    deals = {deal.id: deal for deal in parse_products(_fixture(), CONFIG)}

    assert set(deals) == {"fashionspark:67100810103", "fashionspark:85102540101"}
    deal = deals["fashionspark:67100810103"]
    assert deal.title == "Jeans Wide Leg Mujer Azul Indigo"
    assert deal.price == 12490
    assert deal.url == (
        "https://fashionspark.com/products/jeans-mujer-moda-wide-leg-azul-indigo-671008101"
    )
    assert deal.image_url == (
        "https://cdn.shopify.com/s/files/1/0880/1527/4168/files/p-671008101-1.webp?v=1785768297"
    )
    assert deal.store == "fashionspark"
    assert deal.category == "ropa"


def test_parse_products_computes_discount_from_compare_at_price():
    deals = {deal.id: deal for deal in parse_products(_fixture(), CONFIG)}

    deal = deals["fashionspark:85102540101"]
    assert deal.price == 9990
    assert deal.list_price == 19990
    assert deal.discount_pct == 50.0


def test_parse_products_defaults_list_price_to_price_without_a_crossed_price():
    deals = parse_products([_product(variants=[{"sku": "A", "price": "9990", "compare_at_price": None, "available": True}])], CONFIG)

    assert deals[0].list_price == 9990
    assert deals[0].discount_pct == 0.0


def test_parse_products_ignores_a_compare_at_price_below_the_sale_price():
    deals = parse_products([_product(variants=[{"sku": "A", "price": "9990", "compare_at_price": "4990", "available": True}])], CONFIG)

    assert deals[0].list_price == 9990
    assert deals[0].discount_pct == 0.0


def test_parse_products_drops_products_whose_variants_are_all_sold_out():
    deals = parse_products(_fixture(), CONFIG)

    assert "fashionspark:83000520601" not in {deal.id for deal in deals}


def test_fetch_deals_uses_the_shared_shopify_config(monkeypatch):
    captured = {}

    def fake_fetch_store_deals(cfg, watchlist):
        captured["cfg"] = cfg
        captured["watchlist"] = watchlist
        return []

    monkeypatch.setattr(fashionspark, "fetch_store_deals", fake_fetch_store_deals)

    watchlist = {"keywords": []}
    assert fashionspark.fetch_deals(watchlist) == []
    assert captured["cfg"] is CONFIG
    assert captured["cfg"].store == "fashionspark"
    assert captured["cfg"].base_url == "https://fashionspark.com"
    assert captured["cfg"].category == "ropa"
    assert captured["watchlist"] is watchlist
