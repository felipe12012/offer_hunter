# sources/cruzverde.py
"""Cruz Verde (cruzverde.cl) browser scraper.

The storefront is an Angular SPA: a plain ``requests`` GET only returns the
~2.8 KB application shell, so the product grid has to be rendered. Patchright
(a stealth-patched Playwright drop-in) loads the full-text search route
``/search?query={query}`` with real product cards from a datacenter IP.

Each card is an ``<ml-new-card-product>`` element. The current price is the
green ``<p>`` inside ``<ml-price-tag-v2>``; the crossed-out list price is the
sibling with the ``line-through`` class and only exists when there is a
discount. No card-only / member price is rendered on the search grid.
"""
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load

SEARCH_URL = "https://www.cruzverde.cl/search?query={query}"
BASE_URL = "https://www.cruzverde.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = "ml-new-card-product"
PRODUCT_LINK_RE = re.compile(r"/([^/]+)/(\d+)\.html")
_CURRENT_PRICE_CLASS = "text-green-turquoise"


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _extract_deal(card, category: str) -> Deal | None:
    link = None
    href = ""
    for anchor in card.select("a[href]"):
        candidate = anchor.get("href", "")
        if PRODUCT_LINK_RE.search(candidate):
            link, href = anchor, candidate
            break
    title_el = card.select_one("h2")
    price_tag = card.select_one("ml-price-tag-v2")
    if link is None or title_el is None or price_tag is None:
        return None

    sku_match = PRODUCT_LINK_RE.search(href)
    if sku_match is None:
        return None
    sku = sku_match.group(2)

    list_el = None
    current_el = None
    fallback_el = None
    for price_el in price_tag.select("p"):
        classes = price_el.get("class") or []
        if "line-through" in classes:
            list_el = price_el
        elif _CURRENT_PRICE_CLASS in classes and current_el is None:
            current_el = price_el
        elif fallback_el is None:
            fallback_el = price_el
    if current_el is None:
        current_el = fallback_el or list_el
    if current_el is None:
        return None

    price = _parse_price(current_el.get_text())
    if price <= 0:
        return None

    list_price = price
    if list_el is not None:
        crossed = _parse_price(list_el.get_text())
        if crossed > price:
            list_price = crossed

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = href if href.startswith("http") else f"{BASE_URL}{href}"

    return Deal(
        id=f"cruzverde:{sku}",
        title=title_el.get_text(" ", strip=True),
        url=url,
        store="cruzverde",
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
        raise RuntimeError(
            "No product cards found on Cruz Verde search results page; "
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
    url = SEARCH_URL.format(query=quote(keyword))
    with sync_playwright() as p:
        proxy = os.environ.get("SCRAPER_PROXY")
        browser = p.chromium.launch(
            headless=True, proxy={"server": proxy} if proxy else None
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="es-CL",
            timezone_id="America/Santiago",
        )
        page = context.new_page()
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        try:
            page.wait_for_selector(CARD_SELECTOR, timeout=15000)
        except Exception:
            pass
        scroll_to_load(page)
        html = page.content()
        browser.close()
    return html


def fetch_deals(watchlist: dict) -> list[Deal]:
    deals: list[Deal] = []
    keywords = watchlist.get("keywords", [])
    failures = 0
    for keyword in keywords:
        # One keyword can resolve to a page with no grid — isolate it instead
        # of letting it abort every other keyword.
        try:
            deals.extend(parse_html(fetch_html(keyword), category=keyword))
        except Exception as exc:
            failures += 1
            print(f"cruzverde keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Cruz Verde keywords failed")
    return deals
