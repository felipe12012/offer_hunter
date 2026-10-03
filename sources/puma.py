# sources/puma.py
"""Browser scraper for PUMA Chile (cl.puma.com).

PUMA runs Magento with a JS-heavy theme. The search page is server-rendered
with product cards, but a plain ``requests`` call is challenged from datacenter
IPs, so the search page is opened with headless Chromium (mirrors
``sources/paris.py``). Cards carry the final and crossed-out price as exact
integers in ``data-price-amount`` attributes.
"""
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load
from sources import health

SEARCH_URL = "https://cl.puma.com/catalogsearch/result/?q={query}"
BASE_URL = "https://cl.puma.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = "div.product-item"


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _price_amount(el) -> int:
    if el is None:
        return 0
    amount = el.get("data-price-amount")
    if amount not in (None, ""):
        try:
            return int(float(amount))
        except (TypeError, ValueError):
            pass
    return _parse_price(el.get_text())


def _sku(card, href: str) -> str:
    # PUMA SKUs look like 026875_02; the URL spells them 026875-02.
    url_sku = re.search(r"-(\d{6}-\d{2})\.html$", href.split("?", 1)[0])
    if url_sku:
        return url_sku.group(1)
    attr_sku = (card.get("data-product-sku") or "").strip()
    if attr_sku:
        return attr_sku.replace("_", "-")
    fallback = re.search(r"-([A-Za-z0-9]+)\.html$", href.split("?", 1)[0])
    return fallback.group(1) if fallback else href


def _extract_deal(card, category: str) -> Deal | None:
    link_el = card.select_one("a.product-item__name") or card.select_one(
        "a.product-item__img-w"
    )
    title_el = card.select_one("a.product-item__name")
    price_el = card.select_one('.product-item__price [data-price-type="finalPrice"]')
    if link_el is None or title_el is None or price_el is None:
        return None

    price = _price_amount(price_el)
    if price <= 0:
        return None

    list_price = price
    old_el = card.select_one('.product-item__price [data-price-type="oldPrice"]')
    old_price = _price_amount(old_el)
    if old_price > price:
        list_price = old_price

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    href = link_el.get("href", "")
    path = href.split("?", 1)[0]
    url = href if href.startswith("http") else f"{BASE_URL}{path}"

    return Deal(
        id=f"puma:{_sku(card, href)}",
        title=title_el.get_text(strip=True),
        url=url,
        store="puma",
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
            "No product cards found on PUMA search results page; "
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
            health.warn("puma", f"puma keyword {keyword!r} failed: {exc}")
    if keywords and failures == len(keywords):
        raise RuntimeError("All PUMA keywords failed")
    return deals
