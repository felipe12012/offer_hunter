# sources/laikamascotas.py
"""Laika Mascotas (laikamascotas.cl) scraper over the store's JSON search API.

The storefront is a custom Next.js + Tailwind SPA: a plain GET of
``/listados?q=`` returns only the app shell, so the grid needs a browser. The
same grid is served by a plain JSON endpoint though, which is what this module
uses (no browser, no Playwright):

    GET /api/proxy/v1/products/search?search={query}&page=1&pageSize=48

Each product carries ``price.final`` (the price any customer pays, including a
running promotion), ``price.sale`` (the regular "precio normal", higher than
``final`` only while a promotion runs) and ``price.priceForMember`` (card-only,
always ignored). The featured price shown on the site against ``sale`` is what
becomes ``list_price``/``discount_pct``.
"""
import json
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from models import Deal
from sources import httpclient
from sources.health import NoResultsError
from sources.sfcc import run_queries

BASE_URL = "https://www.laikamascotas.cl"
API_URL = (
    "https://www.laikamascotas.cl/api/proxy/v1/products/search"
    "?search={query}&page={page}&pageSize={size}"
)
PAGE_SIZE = 48
MAX_PAGES = 50
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _extract_deal(product: dict, category: str) -> Deal | None:
    product_id = product.get("id")
    price_obj = product.get("price")
    if not isinstance(price_obj, dict):
        price_obj = {}
    final = _to_int(price_obj.get("final"))
    sale = _to_int(price_obj.get("sale"))
    # "final" is what any customer pays; fall back to "sale" if it is missing.
    # priceForMember (the card-only "precio con Laika Member") is never read.
    price = final if final > 0 else sale
    if product_id is None or price <= 0:
        return None

    list_price = sale if sale > price else price
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    slug = str(product.get("slug") or "").strip()
    url = f"{BASE_URL}/{slug}" if slug else BASE_URL
    image_obj = product.get("image")
    image = ""
    if isinstance(image_obj, dict):
        image = str(image_obj.get("url") or "")

    return Deal(
        id=f"laikamascotas:{product_id}",
        title=str(product.get("name") or "").strip(),
        url=url,
        store="laikamascotas",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=image,
    )


def parse_html(html: str, category: str) -> list[Deal]:
    """Parse the JSON payload returned by :func:`fetch_html` (pure, no network).

    A payload with an empty ``products`` list is an empty query, not a failure;
    a malformed/unparseable payload raises ``RuntimeError`` so a change is loud.
    """
    try:
        payload = json.loads(html)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"Laika Mascotas search API returned a malformed payload: {exc!r} "
            f"(payload length={len(html)})"
        ) from exc

    if not isinstance(payload, dict) or "products" not in payload:
        raise RuntimeError(
            "Laika Mascotas search API payload has no 'products' list "
            f"(payload length={len(html)})"
        )

    products = payload.get("products") or []
    if not products:
        raise NoResultsError("Laika Mascotas search API returned no products")

    deals: list[Deal] = []
    seen_ids: set[str] = set()
    for product in products:
        if not isinstance(product, dict):
            continue
        deal = _extract_deal(product, category)
        if deal is not None and deal.id not in seen_ids:
            seen_ids.add(deal.id)
            deals.append(deal)
    return deals


def _fetch_page(keyword: str, page: int) -> dict:
    url = API_URL.format(query=quote(keyword), page=page, size=PAGE_SIZE)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpclient.get(url, headers=REQUEST_HEADERS)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or "products" not in payload:
                raise RuntimeError(f"unexpected payload from {url}")
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} failed: {last_error}")


def fetch_html(keyword: str) -> str:
    """Fetch every result page and return one combined JSON payload as text."""
    products: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        payload = _fetch_page(keyword, page)
        page_products = payload.get("products") or []
        if not page_products:
            break
        products.extend(page_products)
        if len(page_products) < PAGE_SIZE:
            break
    return json.dumps({"products": products})


def fetch_deals(watchlist: dict) -> list[Deal]:
    keywords = watchlist.get("keywords", [])
    return run_queries(
        "laikamascotas",
        keywords,
        lambda keyword: parse_html(fetch_html(keyword), category=keyword),
    )
