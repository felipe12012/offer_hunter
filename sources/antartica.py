# sources/antartica.py
"""Librería Antártica (antartica.cl) browser scraper.

The storefront is Magento 2 behind a Cloudflare bot wall: the search HTML, the
Storefront GraphQL endpoint (``/graphql``) and ``/rest/V1/products`` all answer
403/401 over plain HTTP from a datacenter IP, and the REST route needs a token.
Patchright (a stealth-patched Playwright drop-in) renders the classic
``/catalogsearch/result/?q=`` grid with real product cards, so this module
mirrors ``sources/nike.py``. It is a bookshop, so every deal is tagged with the
``libros`` category. The final price is in ``data-price-amount`` (already an
integer) and the crossed-out ``oldPrice`` only exists for discounted products.
"""
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright

from models import Deal
from sources import health
from sources.images import pick_image, scroll_to_load

BASE_URL = "https://www.antartica.cl"
SEARCH_URL = "https://www.antartica.cl/catalogsearch/result/?q={query}"
CARD_SELECTOR = ".product-item-info"
CATEGORY = "libros"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _price_amount(box, price_type: str) -> int:
    el = box.select_one(f'.price-wrapper[data-price-type="{price_type}"]')
    if el is None:
        return 0
    raw = el.get("data-price-amount")
    if raw is not None:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            pass
    price_el = el.select_one(".price")
    return _parse_price(price_el.get_text() if price_el is not None else el.get_text())


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a.product-item-link")
    if link is None:
        link = card.select_one("a[data-product-id]")
    if link is None:
        return None

    href = link.get("href", "")
    path = urlsplit(href).path or href.split("?", 1)[0]
    if not path:
        return None

    price_box = card.select_one(".price-box") or card
    price = _price_amount(price_box, "finalPrice")
    if price <= 0:
        return None

    list_price = price
    crossed = _price_amount(price_box, "oldPrice")
    if crossed > price:
        list_price = crossed

    sku = (link.get("data-product-id") or "").strip()
    if not sku:
        sku = (card.get("id") or "").replace("product-item-info_", "") or path
    title = link.get_text(strip=True)
    if not title:
        return None

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = href if href.startswith("http") else f"{BASE_URL}{path}"

    return Deal(
        id=f"antartica:{sku}",
        title=title,
        url=url,
        store="antartica",
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
            "No product cards found on Librería Antártica search results page; "
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
    """Render one search page of Antártica's grid; Cloudflare requires a browser."""
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
    deals: dict[str, Deal] = {}
    keywords = list(dict.fromkeys(watchlist.get("keywords", [])))
    failures = 0
    for keyword in keywords:
        # A keyword that resolves to a page with no grid must not abort the rest.
        try:
            for deal in parse_html(fetch_html(keyword), category=CATEGORY):
                deals.setdefault(deal.id, deal)
        except Exception as exc:  # noqa: BLE001 - isolate one bad keyword
            failures += 1
            health.warn("antartica", f"antartica keyword {keyword!r} failed: {exc}")
    if keywords and failures == len(keywords):
        raise RuntimeError("All Antártica keywords failed")
    return list(deals.values())
