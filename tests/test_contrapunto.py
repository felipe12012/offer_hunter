import json
from pathlib import Path

from sources import contrapunto
from sources.contrapunto import CONFIG
from sources.shopify import parse_products

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "contrapunto_sample.html"


def _fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _product(**overrides) -> dict:
    product = {
        "id": 1,
        "title": "Libro",
        "handle": "libro",
        "images": [{"src": "https://cdn.shopify.com/s/files/1/libro.jpg"}],
        "variants": [
            {"sku": "SKU1", "price": "9990", "compare_at_price": "19990", "available": True}
        ],
    }
    product.update(overrides)
    return product


def test_parse_products_maps_id_title_price_url_image_store_and_category():
    deals = {deal.id: deal for deal in parse_products(_fixture(), CONFIG)}

    assert set(deals) == {"contrapunto:978-84-19094-63-6", "contrapunto:979-8-89019-052-9"}
    deal = deals["contrapunto:978-84-19094-63-6"]
    assert deal.title == "El último árbol"
    assert deal.price == 16080
    assert deal.url == "https://contrapunto.cl/products/el-ultimo-arbol"
    assert deal.image_url == (
        "https://cdn.shopify.com/s/files/1/0572/1486/1387/files/27945.jpg?v=1725308980"
    )
    assert deal.store == "contrapunto"
    assert deal.category == "libros"


def test_parse_products_computes_discount_from_compare_at_price():
    deals = {deal.id: deal for deal in parse_products(_fixture(), CONFIG)}

    deal = deals["contrapunto:979-8-89019-052-9"]
    assert deal.price == 4960
    assert deal.list_price == 6200
    assert deal.discount_pct == 20.0


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

    assert "contrapunto:9788491054566" not in {deal.id for deal in deals}


def test_fetch_deals_uses_the_shared_shopify_config(monkeypatch):
    captured = {}

    def fake_fetch_store_deals(cfg, watchlist):
        captured["cfg"] = cfg
        captured["watchlist"] = watchlist
        return []

    monkeypatch.setattr(contrapunto, "fetch_store_deals", fake_fetch_store_deals)

    watchlist = {"keywords": []}
    assert contrapunto.fetch_deals(watchlist) == []
    assert captured["cfg"] is CONFIG
    assert captured["cfg"].store == "contrapunto"
    assert captured["cfg"].base_url == "https://contrapunto.cl"
    assert captured["cfg"].category == "libros"
    assert captured["watchlist"] is watchlist
