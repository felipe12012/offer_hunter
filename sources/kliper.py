# sources/kliper.py
"""Kliper Chile (kliper.cl) HTTP scraper.

The storefront is Magento (the same Luma-derived theme as Surprice): a browser
User-Agent gets the server-rendered ``/catalogsearch/result/?q=`` grid over
plain HTTP. Some queries 302-redirect to a ``/marcas?cat=`` category page and
``requests`` follows it transparently, so the same parser handles both. Cards
carry ``data-price-amount`` on the final and old price wrappers and the product
SKU on the add-to-cart form.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from models import Deal
from sources.images import pick_image
from sources import health
from sources import httpclient

BASE_URL = "https://www.kliper.cl"
SEARCH_URL = "https://www.kliper.cl/catalogsearch/result/?q={query}"
CARD_SELECTOR = "li.item.product.product-item"
CATEGORY = "ropa"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}
_SKU_PATH_RE = re.compile(r"-(\d+)-([a-z0-9]+)/?$", re.IGNORECASE)


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _price_amount(card, price_type: str) -> int:
    el = card.select_one(f'[data-price-type="{price_type}"]')
    if el is None:
        return 0
    amount = el.get("data-price-amount")
    if amount not in (None, ""):
        try:
            return int(float(amount))
        except (TypeError, ValueError):
            pass
    return _parse_price(el.get_text())


def _sku(card, path: str) -> str:
    form = card.select_one("form[data-product-sku]")
    if form is not None and form.get("data-product-sku"):
        return form["data-product-sku"]
    product = card.select_one("[data-product-id]")
    if product is not None and product.get("data-product-id"):
        return product["data-product-id"]
    match = _SKU_PATH_RE.search(path)
    if match:
        return f"{match.group(1)}_{match.group(2)}"
    return path


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a.product-item-link")
    if link is None:
        return None

    href = link.get("href", "")
    price = _price_amount(card, "finalPrice")
    if not href or price <= 0:
        return None

    path = href.split("?", 1)[0]
    list_price = price
    crossed = _price_amount(card, "oldPrice")
    if crossed > price:
        list_price = crossed

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = href if href.startswith("http") else f"{BASE_URL}{path}"

    return Deal(
        id=f"kliper:{_sku(card, path)}",
        title=link.get_text(strip=True),
        url=url,
        store="kliper",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=pick_image(card, BASE_URL),
    )


def parse_html(html: str, category: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(CARD_SELECTOR)
    if not cards:
        title = soup.title.get_text(strip=True) if soup.title else "<no title>"
        raise health.NoResultsError(
            "No product cards found on Kliper search results page; "
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
    """One page of Kliper's search grid; plain HTTP, no browser.

    ``requests`` follows the store's search-to-category redirect, so the
    returned HTML is whatever grid the keyword resolved to."""
    url = SEARCH_URL.format(query=quote(keyword))
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpclient.get(url, headers=REQUEST_HEADERS)
            httpclient.raise_if_blocked(response)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} failed: {last_error}")


def fetch_deals(watchlist: dict) -> list[Deal]:
    deals: list[Deal] = []
    keywords = watchlist.get("keywords", [])
    failures = 0
    for keyword in keywords:
        # One keyword can resolve to a page with no grid (a store that does not
        # carry it) — isolate it instead of letting it abort every other keyword.
        try:
            deals.extend(parse_html(fetch_html(keyword), category=CATEGORY))
        except health.NoResultsError:
            health.empty("kliper", keyword)  # the store does not carry it: not an error
        except httpclient.Blocked as exc:
            raise RuntimeError(f"Kliper is refusing us ({exc}); not asking again this run") from exc
        except Exception as exc:  # noqa: BLE001 - isolate one bad keyword
            failures += 1
            health.warn("kliper", f"kliper keyword {keyword!r} failed: {exc}")
    if keywords and failures == len(keywords):
        raise RuntimeError("All Kliper keywords failed")
    return deals
