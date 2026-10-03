# sources/skechers.py
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load

SEARCH_URL = "https://www.skechers.cl/productos/buscar/{query}"
BASE_URL = "https://www.skechers.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
CARD_SELECTOR = "div.item-producto"


def _parse_price(value) -> int:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


def _slug_from_url(url: str) -> str:
    path = url.split("?", 1)[0].rstrip("/")
    return path.rsplit("/", 1)[-1] or url


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one("a[href*='/detalle/']")
    title_el = card.select_one("h2")
    price_el = card.select_one("h3")
    if link is None or title_el is None or price_el is None:
        return None

    old_el = price_el.find("s")
    if old_el is not None:
        list_price = _parse_price(old_el.get_text())
        without_old = BeautifulSoup(str(price_el), "html.parser")
        for stripped in without_old.select("s"):
            stripped.decompose()
        price = _parse_price(without_old.get_text(" ", strip=True))
    else:
        price = _parse_price(price_el.get_text(" ", strip=True))
        list_price = price
    if price <= 0:
        return None
    if list_price <= price:
        list_price = price
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    href = link.get("href", "")
    url = urljoin(BASE_URL + "/", href.split("?", 1)[0])

    return Deal(
        id=f"skechers:{_slug_from_url(url)}",
        title=title_el.get_text(strip=True),
        url=url,
        store="skechers",
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
            "No product cards found on Skechers search results page; "
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
    last_error: Exception | None = None
    # Skechers is slow to hand over the DOM and intermittently stalls past 30s
    # from CI; retry once with a longer timeout rather than losing the whole
    # store for the run.
    for attempt in range(2):
        try:
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
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector(CARD_SELECTOR, timeout=20000)
                except Exception:
                    pass
                scroll_to_load(page)
                html = page.content()
                browser.close()
            return html
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last_error = exc
            time.sleep(2 + attempt)
    raise RuntimeError(f"GET {url} failed after 2 attempts: {last_error}")


def fetch_deals(watchlist: dict) -> list[Deal]:
    deals: list[Deal] = []
    keywords = watchlist.get("keywords", [])
    failures = 0
    for keyword in keywords:
        # A keyword can return no products; isolate it instead of letting it
        # abort every other keyword.
        try:
            deals.extend(parse_html(fetch_html(keyword), category=keyword))
        except Exception as exc:
            failures += 1
            print(f"skechers keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Skechers keywords failed")
    return deals
