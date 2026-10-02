import pytest

from sources import vtex
from sources.vtex import StoreConfig

CFG = StoreConfig(store="asics", base_url="https://www.asics.cl")


def _product(
    product_id: str = "1",
    name: str = "ASICS Gel Nimbus",
    price="89990",
    list_price="119990",
    available_quantity="10",
    image="https://asics.cl/img.jpg",
    link="https://www.asics.cl/gel-nimbus/p",
):
    return {
        "productId": product_id,
        "productName": name,
        "link": link,
        "items": [
            {
                "images": [{"imageUrl": image}],
                "sellers": [
                    {
                        "commertialOffer": {
                            "Price": price,
                            "ListPrice": list_price,
                            "AvailableQuantity": available_quantity,
                        }
                    }
                ],
            }
        ],
    }


def test_parse_products_extracts_id_title_price_url_image_and_discount():
    deals = vtex.parse_products([_product()], CFG, "zapatillas")

    assert len(deals) == 1
    deal = deals[0]
    assert deal.id == "asics:1"
    assert deal.title == "ASICS Gel Nimbus"
    assert deal.price == 89990
    assert deal.list_price == 119990
    assert deal.discount_pct == 25.0
    assert deal.url == "https://www.asics.cl/gel-nimbus/p"
    assert deal.store == "asics"
    assert deal.category == "zapatillas"
    assert deal.image_url == "https://asics.cl/img.jpg"


def test_parse_products_defaults_list_price_to_price_without_a_crossed_price():
    deals = vtex.parse_products([_product(list_price="89990")], CFG, "zapatillas")

    assert deals[0].list_price == 89990
    assert deals[0].discount_pct == 0.0


def test_parse_products_ignores_list_price_below_the_sale_price():
    deals = vtex.parse_products([_product(price="89990", list_price="79990")], CFG, "zapatillas")

    assert deals[0].list_price == 89990
    assert deals[0].discount_pct == 0.0


def test_parse_products_drops_sold_out_products():
    deals = vtex.parse_products([_product(available_quantity="0")], CFG, "zapatillas")

    assert deals == []


def test_parse_products_skips_products_without_items_or_sellers():
    assert vtex.parse_products([{"productId": "1", "items": []}], CFG, "zapatillas") == []
    assert vtex.parse_products([{"productId": "1", "items": [{"sellers": []}]}], CFG, "zapatillas") == []


def test_fetch_store_deals_scans_each_keyword_and_dedupes():
    def fake_fetch(base_url, keyword, start):
        return [_product(product_id="1"), _product(product_id="2")] if start == 0 else []

    watchlist = {"keywords": ["zapatilla", "adidas"]}
    deals = vtex.fetch_store_deals(CFG, watchlist, fetch=fake_fetch, sleep=lambda s: None)

    assert {d.id for d in deals} == {"asics:1", "asics:2"}


def test_fetch_store_deals_isolates_a_failing_keyword():
    def fake_fetch(base_url, keyword, start):
        if keyword == "bad":
            raise RuntimeError("boom")
        return [_product(product_id="1")] if start == 0 else []

    watchlist = {"keywords": ["bad", "good"]}
    deals = vtex.fetch_store_deals(CFG, watchlist, fetch=fake_fetch, sleep=lambda s: None)

    assert [d.id for d in deals] == ["asics:1"]


def test_fetch_store_deals_raises_when_every_keyword_fails():
    def boom(base_url, keyword, start):
        raise RuntimeError("site down")

    with pytest.raises(RuntimeError):
        vtex.fetch_store_deals(CFG, {"keywords": ["a", "b"]}, fetch=boom, sleep=lambda s: None)
