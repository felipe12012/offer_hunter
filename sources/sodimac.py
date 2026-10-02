# sources/sodimac.py
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal
from sources.images import pick_image, scroll_to_load

SEARCH_URL = "https://www.sodimac.cl/sodimac-cl/search?Ntt={query}"
BASE_URL = "https://www.sodimac.cl"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one('a.link.link-primary[href*="/product/"]')
    title_el = card.select_one(".product-title")
    price_el = card.select_one(".parsedPrice")
    if link is None or title_el is None or price_el is None:
        return None

    href = link.get("href", "")
    sku_match = re.search(r"/product/([^/]+)/", href)
    sku = sku_match.group(1) if sku_match else href
    price = _parse_price(price_el.get_text())

    list_price = price
    dis_el = card.select_one(".price-dis-grid")
    if dis_el is not None:
        dis_price = _parse_price(dis_el.get_text())
        if dis_price > price:
            list_price = dis_price

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = f"{BASE_URL}{href}" if href.startswith("/") else href

    return Deal(
        id=f"sodimac:{sku}",
        title=title_el.get_text(strip=True),
        url=url,
        store="sodimac",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=pick_image(card, BASE_URL),
    )


def _extract_pod_deal(pod, category: str) -> Deal | None:
    sku = pod.get("data-key")
    internet_el = pod.select_one("li[data-internet-price]")
    if not sku or internet_el is None:
        return None

    price = _parse_price(internet_el.get("data-internet-price", ""))
    normal_el = pod.select_one("li[data-normal-price]")
    list_price = _parse_price(normal_el.get("data-normal-price", "")) if normal_el is not None else price
    if list_price < price:
        list_price = price

    brand_el = pod.select_one(".pod-title")
    subtitle_el = pod.select_one(".pod-subTitle")
    parts = [el.get_text(strip=True) for el in (brand_el, subtitle_el) if el is not None]
    title = " ".join(part for part in parts if part)
    href = pod.get("href", "")
    if not title or not href or price <= 0:
        return None

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = f"{BASE_URL}{href}" if href.startswith("/") else href

    return Deal(
        id=f"sodimac:{sku}",
        title=title,
        url=url,
        store="sodimac",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=pick_image(pod, BASE_URL),
    )


def parse_html(html: str, category: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".product-wrapper")
    pods = soup.select("a.pod-link[data-pod]")
    if not cards and not pods:
        title = soup.title.get_text(strip=True) if soup.title else "<no title>"
        raise RuntimeError(
            "No product cards found on Sodimac search results page; "
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
    for pod in pods:
        deal = _extract_pod_deal(pod, category)
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
            page.wait_for_selector(".product-wrapper, a.pod-link", timeout=15000)
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
            print(f"sodimac keyword {keyword!r} failed: {exc}", file=sys.stderr)
    if keywords and failures == len(keywords):
        raise RuntimeError("All Sodimac keywords failed")
    return deals
