# sources/ripley.py
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load

SEARCH_URL = "https://simple.ripley.cl/search/{query}"
BASE_URL = "https://simple.ripley.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
# Ripley fronts its listing pages with Cloudflare bot management. A plain
# headless navigation is answered with a 403 "Blocked" page; sending the
# sec-fetch-* navigation headers (and a cross-site referer) yields the real
# server-rendered search HTML.
EXTRA_HTTP_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Upgrade-Insecure-Requests": "1",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "cross-site",
    "sec-fetch-user": "?1",
}
REFERER = "https://www.google.com/"


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _extract_sku(href: str) -> str:
    path = href.split("?", 1)[0].rstrip("/")
    last = path.rsplit("/", 1)[-1]
    match = re.search(r"-([A-Za-z0-9]+?)p?$", last)
    if match:
        return match.group(1)
    return href


def _extract_deal(card, category: str) -> Deal | None:
    href = card.get("href", "")
    title_el = card.select_one(".product-item-horizontal__name") or card.select_one(
        ".product-item--name"
    )
    price_el = card.select_one(".product-price-price")
    if not href or title_el is None or price_el is None:
        return None

    price = _parse_price(price_el.get_text())
    if price <= 0:
        return None

    list_price = price
    old_el = card.select_one(".product-price-old-price")
    if old_el is not None:
        old_price = _parse_price(old_el.get_text())
        if old_price > price:
            list_price = old_price

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = f"{BASE_URL}{href}" if href.startswith("/") else href

    return Deal(
        id=f"ripley:{_extract_sku(href)}",
        title=title_el.get_text(strip=True),
        url=url,
        store="ripley",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=pick_image(card, BASE_URL),
    )


def parse_html(html: str, category: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("a.product-link")
    if not cards:
        title = soup.title.get_text(strip=True) if soup.title else "<no title>"
        raise RuntimeError(
            "No product cards found on Ripley search results page; "
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
            extra_http_headers=EXTRA_HTTP_HEADERS,
        )
        page = context.new_page()
        page.goto(
            url,
            timeout=30000,
            wait_until="domcontentloaded",
            referer=REFERER,
        )
        try:
            page.wait_for_selector('a.product-link, [data-testid="product-list"]', timeout=15000)
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
            print(f"ripley keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Ripley keywords failed")
    return deals
