import json
from pathlib import Path

from sources import vtex
from sources.sony import CONFIG

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sony_sample.html"


def _products() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_products_extracts_id_title_price_url_image_and_discount():
    deals = vtex.parse_products(_products(), CONFIG, "tecnologia")

    deal = next(d for d in deals if d.id == "sony:1007")
    assert deal.title == "FE 12-24mm F4 G"
    assert deal.price == 1859990
    assert deal.list_price == 1969990
    assert deal.discount_pct == 5.6
    # Intelligent Search returns a root-relative link; it must be made absolute.
    assert deal.url == "https://store.sony.cl/sel1224g/p"
    assert deal.store == "sony"
    assert deal.category == "tecnologia"
    assert deal.image_url.startswith("https://clsonyb2c.vtexassets.com/")


def test_parse_products_defaults_list_price_to_price_without_a_crossed_price():
    deals = vtex.parse_products(_products(), CONFIG, "tecnologia")

    deal = next(d for d in deals if d.id == "sony:2574")
    assert deal.price == 4619991
    assert deal.list_price == 4619991
    assert deal.discount_pct == 0.0


def test_parse_products_drops_sold_out_products():
    sold_out = [p for p in _products() if str(p["productId"]) == "198"]
    assert sold_out
    assert vtex.parse_products(sold_out, CONFIG, "tecnologia") == []


def test_parse_products_dedupes_repeated_products():
    deals = vtex.parse_products(_products(), CONFIG, "tecnologia")

    ids = [d.id for d in deals]
    # 4 blocks: 1 sold-out (dropped) + a duplicated product -> 2 unique deals.
    assert len(ids) == 2
    assert ids.count("sony:1007") == 1
