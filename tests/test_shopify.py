from sources import shopify
from sources.shopify import StoreConfig

CFG = StoreConfig(store="vans", base_url="https://www.vans.cl", category="zapatillas")


def _product(
    product_id: str = "1",
    handle: str = "zapatilla-old-skool",
    title: str = "Vans Old Skool",
    sku: str = "SKU1",
    price: str = "49990",
    compare_at: str = "69990",
    available: bool = True,
    images=None,
):
    return {
        "id": product_id,
        "title": title,
        "handle": handle,
        "images": images if images is not None else [{"src": "https://cdn.shopify.com/van.jpg"}],
        "variants": [
            {
                "sku": sku,
                "price": price,
                "compare_at_price": compare_at,
                "available": available,
            }
        ],
    }


def test_parse_products_extracts_id_title_price_url_image_and_discount():
    deals = shopify.parse_products([_product()], CFG)

    assert len(deals) == 1
    deal = deals[0]
    assert deal.id == "vans:SKU1"
    assert deal.title == "Vans Old Skool"
    assert deal.price == 49990
    assert deal.list_price == 69990
    assert deal.discount_pct == 28.6
    assert deal.url == "https://www.vans.cl/products/zapatilla-old-skool"
    assert deal.store == "vans"
    assert deal.category == "zapatillas"
    assert deal.image_url == "https://cdn.shopify.com/van.jpg"


def test_parse_products_defaults_list_price_to_price_without_a_crossed_price():
    deals = shopify.parse_products([_product(compare_at="0")], CFG)

    assert deals[0].list_price == 49990
    assert deals[0].discount_pct == 0.0


def test_parse_products_ignores_a_compare_at_price_below_the_sale_price():
    deals = shopify.parse_products([_product(price="49990", compare_at="39990")], CFG)

    assert deals[0].list_price == 49990
    assert deals[0].discount_pct == 0.0


def test_parse_products_drops_products_whose_variants_are_all_sold_out():
    deals = shopify.parse_products([_product(available=False)], CFG)

    assert deals == []


def test_parse_products_picks_the_cheapest_available_variant():
    product = _product()
    product["variants"] = [
        {"sku": "A", "price": "59990", "compare_at_price": "69990", "available": True},
        {"sku": "B", "price": "39990", "compare_at_price": "69990", "available": True},
        {"sku": "C", "price": "1000", "compare_at_price": "0", "available": False},
    ]
    deals = shopify.parse_products([product], CFG)

    assert len(deals) == 1
    assert deals[0].id == "vans:B"
    assert deals[0].price == 39990


def test_fetch_store_deals_paginates_until_a_short_page_and_dedupes():
    calls = []

    def fake_fetch(base_url, page):
        calls.append((base_url, page))
        if page == 1:
            return [_product(product_id=str(i), sku=f"S{i}") for i in range(shopify.PAGE_SIZE)]
        return [_product(product_id="last", sku="LAST")]

    deals = shopify.fetch_store_deals(CFG, {}, fetch=fake_fetch, sleep=lambda s: None)

    ids = {d.id for d in deals}
    assert calls == [("https://www.vans.cl", 1), ("https://www.vans.cl", 2)]
    assert "vans:LAST" in ids
    assert len(deals) == shopify.PAGE_SIZE + 1


def test_fetch_store_deals_respects_the_configured_page_cap():
    calls = []

    def fake_fetch(base_url, page):
        calls.append(page)
        return [_product(product_id=f"{page}-{i}", sku=f"S{page}-{i}") for i in range(shopify.PAGE_SIZE)]

    watchlist = {"scan": {"max_shopify_pages": 2}}
    deals = shopify.fetch_store_deals(CFG, watchlist, fetch=fake_fetch, sleep=lambda s: None)

    assert calls == [1, 2]
    assert len(deals) == 2 * shopify.PAGE_SIZE
