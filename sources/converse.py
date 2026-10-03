# sources/converse.py
"""Converse Chile (converse.cl) browser scraper.

The store is Adobe Commerce (Magento) behind a bot wall: a plain ``requests``
GET of the search page may be answered with a challenge, so the search page is
rendered with headless Chromium. Products are ``li.product-item`` cards whose
final price lives in ``[data-price-type="finalPrice"]`` and whose crossed-out
price, when present, lives in ``[data-price-type="oldPrice"]``.
"""
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load
from sources import health

SEARCH_URL = "https://www.converse.cl/catalogsearch/result/?q={query}"
BASE_URL = "https://www.converse.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = "li.product-item"
_SKU_RE = re.compile(r"-([a-z0-9]{4,7}-\d{3})-[a-z0-9-]+$", re.IGNORECASE)


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a.product-item-link")
    if link is None:
        link = card.select_one("a.product-item-photo")
    if link is None:
        return None
    title = link.get_text(strip=True)
    price_el = card.select_one('[data-price-type="finalPrice"] .price')
    if price_el is None:
        price_el = card.select_one(".normal-price .price")
    if price_el is None or not title:
        return None

    price = _parse_price(price_el.get_text())
    if price <= 0:
        return None

    list_price = price
    old_el = card.select_one('[data-price-type="oldPrice"] .price')
    if old_el is not None:
        crossed = _parse_price(old_el.get_text())
        if crossed > price:
            list_price = crossed

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    href = link.get("href", "")
    path = urlsplit(href).path or href
    sku_match = _SKU_RE.search(path)
    if sku_match:
        sku = sku_match.group(1)
    else:
        pid_el = card.select_one("[data-product-id]")
        sku = pid_el.get("data-product-id") if pid_el is not None else path
    url = href if href.startswith("http") else f"{BASE_URL}{path}"

    return Deal(
        id=f"converse:{sku}",
        title=title,
        url=url,
        store="converse",
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
            "No product cards found on Converse search results page; "
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
            health.warn("converse", f"converse keyword {keyword!r} failed: {exc}")
    if keywords and failures == len(keywords):
        raise RuntimeError("All Converse keywords failed")
    return deals
