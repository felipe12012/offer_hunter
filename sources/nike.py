# sources/nike.py
"""Nike Chile (nike.cl) browser scraper.

The store is VTEX behind a Cloudflare bot wall: a plain ``requests`` GET gets
403, and even stock headless Chromium is answered with "Attention Required!"
from a datacenter IP. Patchright (a stealth-patched Playwright drop-in) renders
the full-text search route ``/_q/{query}?map=ft`` with real product cards, so
this module imports from ``patchright`` instead of ``playwright``. Prices are
CLP in the ``sellingPrice`` element and the crossed-out ``listPrice`` only
exists for discounted products.
"""
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load

SEARCH_URL = "https://www.nike.cl/_q/{query}?map=ft"
BASE_URL = "https://www.nike.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = "section.vtex-product-summary-2-x-containerNormal"
_SKU_RE = re.compile(r"^/?([a-z0-9]+-\d{3})-", re.IGNORECASE)


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a.vtex-product-summary-2-x-clearLink")
    if link is None:
        link = card.select_one("a[href]")
    title_el = card.select_one("h3.vtex-product-summary-2-x-productNameContainer")
    price_el = card.select_one(".vtex-product-price-1-x-sellingPrice")
    if link is None or title_el is None or price_el is None:
        return None

    href = link.get("href", "")
    path = urlsplit(href).path or href.split("?", 1)[0]
    sku_match = _SKU_RE.search(path)
    sku = sku_match.group(1) if sku_match else path
    price = _parse_price(price_el.get_text())
    if price <= 0:
        return None

    list_price = price
    list_el = card.select_one(".vtex-product-price-1-x-listPrice")
    if list_el is not None:
        crossed = _parse_price(list_el.get_text())
        if crossed > price:
            list_price = crossed

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = href if href.startswith("http") else f"{BASE_URL}{path}"

    return Deal(
        id=f"nike:{sku}",
        title=title_el.get_text(strip=True),
        url=url,
        store="nike",
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
            "No product cards found on Nike search results page; "
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
        # One keyword can resolve to a product/category page with no grid —
        # isolate it instead of letting it abort every other keyword.
        try:
            deals.extend(parse_html(fetch_html(keyword), category=keyword))
        except Exception as exc:
            failures += 1
            print(f"nike keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Nike keywords failed")
    return deals
