# sources/lapolar.py
"""La Polar / Abc (abc.cl) HTML-grid scraper.

``lapolar.cl`` now redirects to ``abc.cl`` (same company, same SFCC storefront),
so this module targets ``https://www.abc.cl``. Like Ahumada, the search page is
served by the classic ``Search-UpdateGrid`` endpoint and a plain ``requests``
GET returns the real cards, paginated with ``start``/``sz``.

Price trap: cards may carry a cheaper "La Polar" card price (``.la-polar``,
next to the ``ofex`` icon) alongside the internet price any walk-in customer
pays. ``price`` must always be the ``.internet`` price, never the card price.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import requests
from bs4 import BeautifulSoup

from models import Deal
from sources.images import pick_image
from sources.health import NoResultsError
from sources.sfcc import is_empty_fragment, run_queries

BASE_URL = "https://www.abc.cl"
GRID_URL = (
    "https://www.abc.cl/on/demandware.store/"
    "Sites-Abc-Site/es_CL/Search-UpdateGrid?q={query}&start={start}&sz={size}"
)
CARD_SELECTOR = ".product-tile__wrapper"
PAGE_SIZE = 48
DEFAULT_MAX_PAGES = 3
REQUEST_DELAY_SECONDS = 0.3
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


def _current_price(card) -> int:
    # ``.internet`` is the price every customer pays; the sibling ``.la-polar``
    # badge is the tarjeta price and is deliberately ignored.
    price_el = card.select_one(".prices .internet .price-value")
    return _parse_price(price_el.get_text()) if price_el is not None else 0


def _crossed_price(card, price: int) -> int:
    list_el = card.select_one(".prices .normal .price-value")
    if list_el is None:
        return price
    crossed = _parse_price(list_el.get_text())
    return crossed if crossed > price else price


def _extract_deal(card, category: str) -> "Deal | None":
    link = card.select_one(".pdp-link a.link") or card.select_one(".image-link[href]")
    if link is None:
        return None

    href = link.get("href", "")
    path = urlsplit(href).path or href.split("?", 1)[0]
    sku = card.get("data-pid") or ""
    if not sku:
        sku_match = re.search(r"-(\d+)\.html(?:$|\?)", href)
        sku = sku_match.group(1) if sku_match else path

    price = _current_price(card)
    if not href or price <= 0:
        return None

    list_price = _crossed_price(card, price)
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = href if href.startswith("http") else f"{BASE_URL}{path}"

    return Deal(
        id=f"lapolar:{sku}",
        title=link.get_text(strip=True),
        url=url,
        store="lapolar",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=pick_image(card, BASE_URL),
    )


def parse_html(html: str, category: str) -> list["Deal"]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(CARD_SELECTOR)
    if not cards:
        if is_empty_fragment(html):
            raise NoResultsError("La Polar returned no products for this search")
        title = soup.title.get_text(strip=True) if soup.title else "<no title>"
        raise RuntimeError(
            "No product cards found on La Polar search results page; "
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


def fetch_html(keyword: str, start: int = 0) -> str:
    """One page (up to 48 products) of abc.cl's own grid; plain HTTP, no browser."""
    url = GRID_URL.format(query=quote(keyword), start=start, size=PAGE_SIZE)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} failed: {last_error}")


def _scan_query(query: str, max_pages: int) -> list[Deal]:
    deals: dict[str, Deal] = {}
    for page in range(max_pages):
        if page:
            time.sleep(REQUEST_DELAY_SECONDS)
        try:
            found = parse_html(fetch_html(query, page * PAGE_SIZE), category=query)
        except NoResultsError:
            if page == 0:
                raise  # the query matches nothing at all
            break  # ran off the end: keep what the earlier pages found
        new = [deal for deal in found if deal.id not in deals]
        for deal in new:
            deals[deal.id] = deal
        if len(found) < PAGE_SIZE or not new:
            break
    return list(deals.values())


def fetch_deals(watchlist: dict) -> list[Deal]:
    scan = watchlist.get("scan", {})
    max_pages = scan.get("max_lapolar_pages", DEFAULT_MAX_PAGES)
    keywords = list(dict.fromkeys(watchlist.get("keywords", [])))
    return run_queries("lapolar", keywords, lambda keyword: _scan_query(keyword, max_pages))
