# sources/newbalance.py
"""Browser scraper for New Balance Chile (newbalance.cl).

New Balance Chile runs Magento. A search resolves to a category page
(``/catalogsearch/result/?q=zapatillas`` -> ``/zapatillas.html``) whose product
cards are server-rendered, but a plain ``requests`` call is challenged from
datacenter IPs, so the page is opened with headless Chromium (mirrors
``sources/paris.py``). Use the apex domain: ``www.newbalance.cl`` redirects the
search to the homepage. Cards carry the final price and, when discounted, the
crossed-out price as exact integers in ``data-price-amount`` attributes.
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

SEARCH_URL = "https://newbalance.cl/catalogsearch/result/?q={query}"
BASE_URL = "https://newbalance.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = "li.product-item"


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
    # The SKU usually ends the product URL (169000000mr530sg96.html), but some
    # slugs drop it; the add-to-cart form keeps the authoritative SKU.
    path = href.split("?", 1)[0].rsplit("/", 1)[-1]
    stem = re.sub(r"\.html$", "", path)
    match = re.search(r"-([A-Za-z0-9]+)$", stem)
    url_sku = match.group(1) if match else stem
    form = card.select_one("form[data-product-sku]")
    form_sku = (form.get("data-product-sku") if form else "") or ""
    if form_sku and (len(url_sku) < 8 or not re.search(r"\d", url_sku)):
        return form_sku.lower()
    return url_sku


def _extract_deal(card, category: str) -> Deal | None:
    link_el = card.select_one("a.product-item-link")
    price_el = card.select_one('[data-price-type="finalPrice"]')
    if link_el is None or price_el is None:
        return None

    price = _price_amount(price_el)
    if price <= 0:
        return None

    list_price = price
    old_el = card.select_one('[data-price-type="oldPrice"]')
    old_price = _price_amount(old_el)
    if old_price > price:
        list_price = old_price

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    href = link_el.get("href", "")
    path = href.split("?", 1)[0]
    url = href if href.startswith("http") else f"{BASE_URL}{path}"

    return Deal(
        id=f"newbalance:{_sku(card, href)}",
        title=link_el.get_text(strip=True),
        url=url,
        store="newbalance",
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
            "No product cards found on New Balance search results page; "
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
            print(f"newbalance keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All New Balance keywords failed")
    return deals
