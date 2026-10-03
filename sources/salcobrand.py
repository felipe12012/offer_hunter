# sources/salcobrand.py
"""Salcobrand (salcobrand.cl) browser scraper.

The catalog is an Algolia InstantSearch app: the search results are rendered
client-side into ``li.ais-Hits-item`` cards, so a plain HTTP GET returns the
shell with no products. Patchright (a stealth-patched Playwright drop-in)
renders the results from a datacenter IP without tripping the bot wall, so this
module imports from ``patchright`` instead of ``playwright``.

Card prices come in up to three flavours:

* ``display-offer-price`` — what any customer pays now (used as ``price``).
* ``display-secoundary-price-normal`` — the "precio farmacia" crossed-out
  reference (used as ``list_price`` only when strictly greater).
* ``display-card-price`` — a lower card-only price; **ignored** because not
  everyone pays it.

Full-price products expose a single ``display-price-normal``.
"""
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, urlsplit

from bs4 import BeautifulSoup, Tag
from patchright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load

SEARCH_URL = "https://salcobrand.cl/search_result?query={query}"
BASE_URL = "https://salcobrand.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = "li.ais-Hits-item"


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _product_link(card: Tag) -> Tag | None:
    for anchor in card.select("a[href*='/products/']"):
        if "/preview" not in anchor.get("href", ""):
            return anchor
    return None


def _extract_deal(card: Tag, category: str) -> Deal | None:
    link = _product_link(card)
    title_el = card.select_one("span.product-info") or card.select_one("span.product-name")
    price_el = card.select_one(".display-offer-price") or card.select_one(".display-price-normal")
    if link is None or title_el is None or price_el is None:
        return None

    href = link.get("href", "")
    path = urlsplit(href).path
    default_sku = (parse_qs(urlsplit(href).query).get("default_sku") or [""])[0]
    sku = default_sku or path.rsplit("/", 1)[-1]

    price = _parse_price(price_el.get_text())
    if price <= 0:
        return None

    list_price = price
    list_el = card.select_one(".display-secoundary-price-normal")
    if list_el is not None:
        crossed = _parse_price(list_el.get_text())
        if crossed > price:
            list_price = crossed

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = f"{BASE_URL}{path}"
    if default_sku:
        url = f"{url}?default_sku={default_sku}"

    return Deal(
        id=f"salcobrand:{sku}",
        title=title_el.get_text(strip=True),
        url=url,
        store="salcobrand",
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
            "No product cards found on Salcobrand search results page; "
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
        # One keyword can resolve to a page with no product grid — isolate it
        # instead of letting it abort every other keyword.
        try:
            deals.extend(parse_html(fetch_html(keyword), category=keyword))
        except Exception as exc:
            failures += 1
            print(f"salcobrand keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Salcobrand keywords failed")
    return deals
