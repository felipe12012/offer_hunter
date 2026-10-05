import json
from pathlib import Path

from sources import ansaldo
from sources.ansaldo import CONFIG
from sources.shopify import parse_products

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ansaldo_sample.html"


def _fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _product(**overrides) -> dict:
    product = {
        "id": 1,
        "title": "Juguete",
        "handle": "juguete",
        "images": [{"src": "https://cdn.shopify.com/s/files/1/juguete.jpg"}],
        "variants": [
            {"sku": "SKU1", "price": "9990", "compare_at_price": "19990", "available": True}
        ],
    }
    product.update(overrides)
    return product


def test_parse_products_maps_id_title_price_url_image_store_and_category():
    deals = {deal.id: deal for deal in parse_products(_fixture(), CONFIG)}

    assert set(deals) == {"ansaldo:42759", "ansaldo:38703"}
    deal = deals["ansaldo:38703"]
    assert deal.title == "Bluey Peluche Mini Bingo"
    assert deal.price == 7990
    assert deal.url == "https://ansaldo.cl/products/bluey-peluche-mini-bingo"
    assert deal.image_url == (
        "https://cdn.shopify.com/s/files/1/0671/4503/9965/files/38003_05.png?v=1758555296"
    )
    assert deal.store == "ansaldo"
    assert deal.category == "ropa"


def test_parse_products_computes_discount_from_compare_at_price():
    deals = {deal.id: deal for deal in parse_products(_fixture(), CONFIG)}

    deal = deals["ansaldo:42759"]
    assert deal.price == 5593
    assert deal.list_price == 7990
    assert deal.discount_pct == 30.0


def test_parse_products_defaults_list_price_to_price_without_a_crossed_price():
    deals = {deal.id: deal for deal in parse_products(_fixture(), CONFIG)}

    deal = deals["ansaldo:38703"]
    assert deal.list_price == deal.price == 7990
    assert deal.discount_pct == 0.0


def test_parse_products_ignores_a_compare_at_price_below_the_sale_price():
    deals = parse_products([_product(variants=[{"sku": "A", "price": "9990", "compare_at_price": "4990", "available": True}])], CONFIG)

    assert deals[0].list_price == 9990
    assert deals[0].discount_pct == 0.0


def test_parse_products_drops_products_whose_variants_are_all_sold_out():
    deals = parse_products(_fixture(), CONFIG)

    assert "ansaldo:22770" not in {deal.id for deal in deals}


def test_fetch_deals_uses_the_shared_shopify_config(monkeypatch):
    captured = {}

    def fake_fetch_store_deals(cfg, watchlist):
        captured["cfg"] = cfg
        captured["watchlist"] = watchlist
        return []

    monkeypatch.setattr(ansaldo, "fetch_store_deals", fake_fetch_store_deals)

    watchlist = {"keywords": []}
    assert ansaldo.fetch_deals(watchlist) == []
    assert captured["cfg"] is CONFIG
    assert captured["cfg"].store == "ansaldo"
    assert captured["cfg"].base_url == "https://ansaldo.cl"
    assert captured["cfg"].category == "ropa"
    assert captured["watchlist"] is watchlist
