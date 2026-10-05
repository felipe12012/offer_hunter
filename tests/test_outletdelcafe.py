import json
from pathlib import Path

from sources import shopify
from sources.outletdelcafe import CONFIG

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "outletdelcafe_sample.html"


def _products() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_products_extracts_id_title_price_url_image_and_discount():
    deals = shopify.parse_products(_products(), CONFIG)

    deal = next(d for d in deals if d.id == "outletdelcafe:46087742488799")
    assert deal.title == "Té Negro - Cinnamon Dream - 150 g"
    assert deal.price == 5990
    assert deal.list_price == 13000
    assert deal.discount_pct == 53.9
    assert deal.url == "https://www.outletdelcafe.cl/products/te-negro-cinnamon-dream-150-g"
    assert deal.store == "outletdelcafe"
    assert deal.category == "alimentos"
    assert deal.image_url.startswith("https://cdn.shopify.com/")


def test_no_compare_at_price_uses_price_as_list_price():
    deals = shopify.parse_products(_products(), CONFIG)

    deal = next(d for d in deals if d.id == "outletdelcafe:9499355283679")
    assert deal.price == 30990
    assert deal.list_price == 30990
    assert deal.discount_pct == 0.0


def test_missing_sku_falls_back_to_the_product_id():
    deals = shopify.parse_products(_products(), CONFIG)

    assert any(d.id == "outletdelcafe:9499355283679" for d in deals)


def test_sold_out_products_are_filtered():
    sold_out = [
        p for p in _products() if p["variants"][0]["available"] is False
    ]
    assert sold_out
    assert shopify.parse_products(sold_out, CONFIG) == []


def test_parse_products_dedupes_repeated_products():
    deals = shopify.parse_products(_products(), CONFIG)

    ids = [d.id for d in deals]
    # 4 blocks: 1 sold-out (dropped) + a duplicated product -> 2 unique deals.
    assert len(ids) == 2
    assert ids.count("outletdelcafe:46087742488799") == 1
