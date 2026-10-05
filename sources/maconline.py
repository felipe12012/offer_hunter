# sources/maconline.py
"""MacOnline (maconline.com) Spree storefront scraper.

MacOnline is an Apple Premium Partner built on Spree Commerce. Its classic
``/products.json`` API is gone (it answers 500), but the server-rendered search
route ``/products?keywords=`` returns the real product grid over plain HTTP,
paginated with ``page``. No JavaScript is needed, so this mirrors
``sources/hites.py`` (requests + parser) instead of the browser path. It sells
Apple hardware, so every deal is tagged with the ``tecnologia`` category.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import requests
from bs4 import BeautifulSoup

from models import Deal
from sources import health
from sources import httpclient
from sources.images import pick_image

BASE_URL = "https://www.maconline.com"
SEARCH_URL = "https://www.maconline.com/products?keywords={query}"
CARD_SELECTOR = ".product-list-item"
CATEGORY = "tecnologia"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a.info")
    if link is None:
        link = card.select_one(".product-body a[href]")
    if link is None:
        return None

    href = link.get("href", "")
    path = urlsplit(href).path or href.split("?", 1)[0]
    if not path:
        return None

    # The grid shows the cheapest variant, so the selling price already is what
    # any customer pays; the "ANTES" reference price is the crossed-out one.
    price_el = card.select_one(".price.selling")
    price = _parse_price(price_el.get_text()) if price_el is not None else 0
    if price <= 0:
        return None

    list_price = price
    old_el = card.select_one(".reference_price.old-price")
    if old_el is not None:
        crossed = _parse_price(old_el.get_text())
        if crossed > price:
            list_price = crossed

    sku = (card.get("id") or "").replace("product_", "") or path
    title = (link.get("title") or link.get_text(" ", strip=True) or "").strip()
    if not title:
        return None

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    # Scope the image lookup to the product photo container: the card also holds
    # a free-shipping banner whose picture would otherwise be picked first.
    image_card = card.select_one(".product-body") or card

    return Deal(
        id=f"maconline:{sku}",
        title=title,
        url=f"{BASE_URL}{path}",
        store="maconline",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=pick_image(image_card, BASE_URL),
    )


def parse_html(html: str, category: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(CARD_SELECTOR)
    if not cards:
        title = soup.title.get_text(strip=True) if soup.title else "<no title>"
        raise RuntimeError(
            "No product cards found on MacOnline search results page; "
            "the site may be unreachable or its HTML structure may have changed "
            f"(page title={title!r}, html length={len(html)})"
        )

    deals: list[Deal] = []
    seen_ids: set[str] = set()
    for card in cards:
        deal = _extract_deal(card, category)
        if deal is not None and deal.id not in seen_ids:
            seen_ids.add(deal.id)
            deals.append(deal)
    return deals


def fetch_html(keyword: str) -> str:
    """One page of MacOnline's server-rendered search grid; plain HTTP, no browser."""
    url = SEARCH_URL.format(query=quote(keyword))
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpclient.get(url, headers=REQUEST_HEADERS)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} failed: {last_error}")


def fetch_deals(watchlist: dict) -> list[Deal]:
    deals: dict[str, Deal] = {}
    keywords = list(dict.fromkeys(watchlist.get("keywords", [])))
    failures = 0
    for keyword in keywords:
        # A keyword that resolves to a page with no grid must not abort the rest.
        try:
            for deal in parse_html(fetch_html(keyword), category=CATEGORY):
                deals.setdefault(deal.id, deal)
        except Exception as exc:  # noqa: BLE001 - isolate one bad keyword
            failures += 1
            health.warn("maconline", f"maconline keyword {keyword!r} failed: {exc}")
    if keywords and failures == len(keywords):
        raise RuntimeError("All MacOnline keywords failed")
    return list(deals.values())
