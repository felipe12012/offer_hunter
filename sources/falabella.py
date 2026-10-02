# sources/falabella.py
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal

SEARCH_URL = "https://www.falabella.com/falabella-cl/search?Ntt={query}"
BASE_URL = "https://www.falabella.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = '[data-testid="ssr-pod"], [data-testid="csr-pod"]'


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _attr_price(card, attr: str) -> int:
    el = card.select_one(f"[{attr}]")
    if el is None:
        return 0
    raw = (el.get(attr) or "").split(",")[0]
    return _parse_price(raw)


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a.pod-link[href]")
    title_el = card.select_one(".pod-subTitle") or card.select_one(".pod-title")
    if link is None or title_el is None:
        return None

    internet = _attr_price(card, "data-internet-price")
    event = _attr_price(card, "data-event-price")
    cmr = _attr_price(card, "data-cmr-price")
    normal = _attr_price(card, "data-normal-price")
    price = internet or event or cmr or normal
    if price <= 0:
        return None

    href = link.get("href", "")
    sku_match = re.search(r"/product/([^/]+)", href)
    sku = sku_match.group(1) if sku_match else href
    list_price = normal if normal > price else price

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = href.split("?")[0]
    if url.startswith("/"):
        url = f"{BASE_URL}{url}"

    return Deal(
        id=f"falabella:{sku}",
        title=title_el.get_text(strip=True),
        url=url,
        store="falabella",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )


def parse_html(html: str, category: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(CARD_SELECTOR)
    if not cards:
        title = soup.title.get_text(strip=True) if soup.title else "<no title>"
        raise RuntimeError(
            "No product cards found on Falabella search results page; "
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
        browser = p.chromium.launch(headless=True)
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
            print(f"falabella keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Falabella keywords failed")
    return deals
