"""Image extraction against real storefront markup captured from each store.

Each fixture holds two product cards exactly as the live page rendered them
(after scrolling), including the noise a naive ``img`` lookup would pick up:
lazy-load placeholders, warranty ribbons, payment-card icons.
"""
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from sources import hites, paris, ripley, tottus
from sources.images import pick_image

FIXTURES = Path(__file__).parent / "fixtures"

PARSERS = {
    "hites": (hites.parse_html, "hites_images_sample.html"),
    "paris": (paris.parse_html, "paris_images_sample.html"),
    "ripley": (ripley.parse_html, "ripley_images_sample.html"),
    "tottus": (tottus.parse_html, "tottus_images_sample.html"),
}


@pytest.mark.parametrize("name", sorted(PARSERS))
def test_every_deal_has_a_real_product_image(name):
    parse, fixture = PARSERS[name]
    deals = parse((FIXTURES / fixture).read_text(encoding="utf-8"), category="x")

    assert len(deals) == 2
    for deal in deals:
        assert deal.image_url.startswith("http"), deal
        assert not deal.image_url.startswith("data:")
        lowered = deal.image_url.lower()
        for noise in ("ribbon", "tag_icons", "tarjeta", ".svg", "logo"):
            assert noise not in lowered, (name, deal.image_url)


def test_pick_image_skips_lazy_placeholders_and_icons():
    html = """
    <div>
      <img src="data:image/svg+xml;charset=utf-8,&lt;svg/&gt;" alt="">
      <img src="/static/ribbon-proteccion-hites.svg" alt="Protección Hites">
      <img src="/_next/image?url=https%3A%2F%2Fx%2Ftag_icons%2Ftarjeta_credito.png&w=32" alt="Ripley Card">
      <img src="https://cdn.example/products/123_1.jpg" alt="Notebook">
    </div>
    """
    card = BeautifulSoup(html, "html.parser")
    assert pick_image(card, "https://shop.example") == "https://cdn.example/products/123_1.jpg"


def test_pick_image_prefers_lazy_data_src_over_placeholder_src():
    html = '<div><img src="data:image/gif;base64,R0lG" data-src="https://cdn.example/p.jpg"></div>'
    assert pick_image(BeautifulSoup(html, "html.parser")) == "https://cdn.example/p.jpg"


def test_pick_image_makes_relative_urls_absolute():
    html = '<div><img src="/images/p.jpg"></div>'
    assert pick_image(BeautifulSoup(html, "html.parser"), "https://shop.example") == "https://shop.example/images/p.jpg"


def test_pick_image_returns_empty_string_when_card_has_no_usable_image():
    html = '<div><img src="data:image/gif;base64,R0lG"><img src="/static/logo.png"></div>'
    assert pick_image(BeautifulSoup(html, "html.parser"), "https://shop.example") == ""
