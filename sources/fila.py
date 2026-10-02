# sources/fila.py
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load

SEARCH_URL = "https://fila.cl/catalogsearch/result/?q={query}"
BASE_URL = "https://fila.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = "li.item.product.product-item"


def _parse_price(value) -> int:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


def _amount(el) -> int:
    if el is None:
        return 0
    raw = el.get("data-price-amount")
    if raw is not None:
        return _parse_price(raw)
    return _parse_price(el.get_text())


def _sku_from_url(url: str) -> str:
    path = url.split("?", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1] or url


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a.product-item-photo") or card.select_one("a[href]")
    title_el = card.select_one("strong.product-item-name")
    price_el = card.select_one('[data-price-type="finalPrice"]')
    if link is None or title_el is None or price_el is None:
        return None

    price = _amount(price_el)
    if price <= 0:
        return None

    href = link.get("href", "")
    url = urljoin(BASE_URL + "/", href.split("?", 1)[0])
    sku_el = card.select_one("[data-product-sku]")
    sku = (sku_el.get("data-product-sku") if sku_el else "") or _sku_from_url(href)

    list_price = price
    old_price = _amount(card.select_one('[data-price-type="oldPrice"]'))
    if old_price > price:
        list_price = old_price
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    return Deal(
        id=f"fila:{sku}",
        title=title_el.get_text(strip=True),
        url=url,
        store="fila",
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
            "No product cards found on Fila search results page; "
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
        # A keyword can rewrite to a category (or the home page) with no grid —
        # isolate it instead of letting it abort every other keyword.
        try:
            deals.extend(parse_html(fetch_html(keyword), category=keyword))
        except Exception as exc:
            failures += 1
            print(f"fila keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Fila keywords failed")
    return deals
