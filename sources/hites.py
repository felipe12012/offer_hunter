# sources/hites.py
import re
import time
import sys
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from models import Deal
from sources.images import pick_image

GRID_URL = (
    "https://www.hites.com/on/demandware.store/Sites-HITES-Site/default/"
    "Search-UpdateGrid?q={query}&start={start}&sz={size}"
)
PAGE_SIZE = 48
DEFAULT_MAX_PAGES = 5
REQUEST_DELAY_SECONDS = 0.3
BASE_URL = "https://www.hites.com"
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
    link = card.select_one("a.goto-product")
    title_el = card.select_one(".product-name--bundle")
    if link is None or title_el is None:
        return None

    href = link.get("href", "")
    sku_match = re.search(r"-(\d+)\.html(?:$|\?)", href)
    sku = sku_match.group(1) if sku_match else href

    sale_el = card.select_one(".price-item.sales .value")
    list_el = card.select_one(".price-item.list.strike-through .value")
    if sale_el is not None:
        price = _parse_price(sale_el.get_text())
    elif list_el is not None:
        price = _parse_price(list_el.get_text())
    else:
        price = 0

    if not href or price <= 0:
        return None

    list_price = price
    if sale_el is not None and list_el is not None:
        crossed = _parse_price(list_el.get_text())
        if crossed > price:
            list_price = crossed

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = f"{BASE_URL}{href}" if href.startswith("/") else href

    return Deal(
        id=f"hites:{sku}",
        title=title_el.get_text(strip=True),
        url=url,
        store="hites",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=pick_image(card, BASE_URL),
    )


def parse_html(html: str, category: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".product-tile")
    if not cards:
        title = soup.title.get_text(strip=True) if soup.title else "<no title>"
        raise RuntimeError(
            "No product cards found on Hites search results page; "
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
    """One page (48 products) of Hites' own grid endpoint; plain HTTP, no browser."""
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
        found = parse_html(fetch_html(query, page * PAGE_SIZE), category=query)
        new = [deal for deal in found if deal.id not in deals]
        for deal in new:
            deals[deal.id] = deal
        if len(found) < PAGE_SIZE or not new:
            break
    return list(deals.values())


def fetch_deals(watchlist: dict) -> list[Deal]:
    scan = watchlist.get("scan", {})
    max_pages = scan.get("max_hites_pages", DEFAULT_MAX_PAGES)
    queries = list(dict.fromkeys([*watchlist.get("keywords", []), *scan.get("hites_queries", [])]))

    deals: dict[str, Deal] = {}
    failures = 0
    for query in queries:
        # One query can resolve to a page with no grid — isolate it instead of
        # letting it abort every other query.
        try:
            for deal in _scan_query(query, max_pages):
                deals.setdefault(deal.id, deal)
        except Exception as exc:
            failures += 1
            print(f"hites query {query!r} failed: {exc}", file=sys.stderr)
    if queries and failures == len(queries):
        raise RuntimeError("All Hites queries failed")
    return list(deals.values())
