import json
from pathlib import Path

from sources import vtex
from sources.zapatos import CONFIG

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "zapatos_sample.html"


def _products() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_parse_products_extracts_id_title_price_url_image_and_discount():
    deals = vtex.parse_products(_products(), CONFIG, "zapatillas")

    deal = next(d for d in deals if d.id == "zapatos:15187")
    assert deal.title == "Polera de Agua Uv Body"
    assert deal.price == 10794
    assert deal.list_price == 17990
    assert deal.discount_pct == 40.0
    assert deal.url == "https://www.zapatos.cl/hpk-polera-de-agua-nina-body-hk51002168-boh/p"
    assert deal.store == "zapatos"
    assert deal.category == "zapatillas"
    assert deal.image_url.startswith("https://zapatoscl.vteximg.com.br/")


def test_parse_products_defaults_list_price_to_price_without_a_crossed_price():
    deals = vtex.parse_products(_products(), CONFIG, "zapatillas")

    deal = next(d for d in deals if d.id == "zapatos:4606")
    assert deal.price == 29990
    assert deal.list_price == 29990
    assert deal.discount_pct == 0.0


def test_parse_products_drops_sold_out_products():
    sold_out = [p for p in _products() if str(p["productId"]) == "8400"]
    assert sold_out
    assert vtex.parse_products(sold_out, CONFIG, "zapatillas") == []


def test_parse_products_dedupes_repeated_products():
    deals = vtex.parse_products(_products(), CONFIG, "zapatillas")

    ids = [d.id for d in deals]
    # 4 blocks: 1 sold-out (dropped) + a duplicated product -> 2 unique deals.
    assert len(ids) == 2
    assert ids.count("zapatos:15187") == 1
