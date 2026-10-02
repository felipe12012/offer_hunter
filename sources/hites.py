# sources/hites.py
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal

SEARCH_URL = "https://www.hites.com/busqueda?q={query}"
BASE_URL = "https://www.hites.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a.goto-product")
    title_el = card.select_one(".product-name--bundle")
    if link is None or title_el is None:
        return None

    href = link.get("href", "")
    sku_match = re.search(r"-(\d+)\.html(?:$|\?)", href)
    sku = sku_match.group(1) if sku_match else href

    sale_el = card.select_one(".price-item.sales .value")
    list_el = card.select_one(".price-item.list.strike-through .value")
    if sale_el is not None:
        price = _parse_price(sale_el.get_text())
    elif list_el is not None:
        price = _parse_price(list_el.get_text())
    else:
        price = 0

    if not href or price <= 0:
        return None

    list_price = price
    if sale_el is not None and list_el is not None:
        crossed = _parse_price(list_el.get_text())
        if crossed > price:
            list_price = crossed

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = f"{BASE_URL}{href}" if href.startswith("/") else href

    return Deal(
        id=f"hites:{sku}",
        title=title_el.get_text(strip=True),
        url=url,
        store="hites",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )


def parse_html(html: str, category: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".product-tile")
    if not cards:
        title = soup.title.get_text(strip=True) if soup.title else "<no title>"
        raise RuntimeError(
            "No product cards found on Hites search results page; "
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
            page.wait_for_selector(".product-tile", timeout=15000)
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
            print(f"hites keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Hites keywords failed")
    return deals
