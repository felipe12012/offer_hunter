import json
from pathlib import Path

from sources import vtex
from sources.hm import CONFIG

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hm_sample.html"


def _products() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_products_extracts_id_title_price_url_image_and_discount():
    deals = vtex.parse_products(_products(), CONFIG, "ropa")

    deal = next(d for d in deals if d.id == "hm:18302")
    assert deal.title == "Polera"
    assert deal.price == 9090
    assert deal.list_price == 12990
    assert deal.discount_pct == 30.0
    assert deal.url == "https://cl.hm.com/1308438001/p"
    assert deal.store == "hm"
    assert deal.category == "ropa"
    assert deal.image_url.startswith("https://hmchile.vteximg.com.br/")


def test_parse_products_defaults_list_price_to_price_without_a_crossed_price():
    deals = vtex.parse_products(_products(), CONFIG, "ropa")

    deal = next(d for d in deals if d.id == "hm:73426")
    assert deal.price == 46990
    assert deal.list_price == 46990
    assert deal.discount_pct == 0.0


def test_parse_products_drops_sold_out_products():
    sold_out = [p for p in _products() if str(p["productId"]) == "13605"]
    assert sold_out
    assert vtex.parse_products(sold_out, CONFIG, "ropa") == []


def test_parse_products_dedupes_repeated_products():
    deals = vtex.parse_products(_products(), CONFIG, "ropa")

    ids = [d.id for d in deals]
    # 4 blocks: 1 sold-out (dropped) + a duplicated product -> 2 unique deals.
    assert len(ids) == 2
    assert ids.count("hm:18302") == 1
