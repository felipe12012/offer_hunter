# sources/tusmascotas.py
"""Tus Mascotas (tusmascotas.cl) scraper over the WooCommerce Store API.

The storefront is WordPress + WooCommerce. Its Store API serves the product
grid as JSON over plain HTTP (no browser):

    GET /wp-json/wc/store/v1/products?search={query}&per_page=100&page=N

Prices come as integer minor units: ``currency_minor_unit`` is 0 for CLP, so the
values are whole pesos (``"3090"`` is $3.090). ``prices.price`` is what any
customer pays; ``prices.regular_price`` is the crossed list price when it is
strictly greater; ``prices.sale_price`` equals ``price`` and is never the list
price. Pagination stops on the first short/empty page.
"""
import html as html_lib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from models import Deal
from sources import httpclient
from sources.health import NoResultsError
from sources.sfcc import run_queries

BASE_URL = "https://www.tusmascotas.cl"
API_URL = (
    "https://www.tusmascotas.cl/wp-json/wc/store/v1/products"
    "?search={query}&per_page={size}&page={page}"
)
PAGE_SIZE = 100
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


def _parse_price(text) -> int:
    digits = re.sub(r"[^\d]", "", str(text or ""))
    return int(digits) if digits else 0


def _price(value, minor_unit: int) -> int:
    """Store API prices are integer minor units (CLP: minor_unit == 0)."""
    amount = _parse_price(value)
    if minor_unit > 0:
        amount = round(amount / (10**minor_unit))
    return amount


def _extract_deal(product: dict, category: str) -> Deal | None:
    stable_id = product.get("id") or product.get("sku")
    if stable_id is None or stable_id == "":
        return None

    prices = product.get("prices")
    if not isinstance(prices, dict):
        prices = {}
    minor_unit = _to_int(prices.get("currency_minor_unit"))
    price = _price(prices.get("price"), minor_unit)
    regular = _price(prices.get("regular_price"), minor_unit)
    # prices.sale_price equals prices.price; it is never the crossed list price.
    if price <= 0:
        return None

    list_price = regular if regular > price else price
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    images = product.get("images")
    image_url = ""
    if isinstance(images, list) and images and isinstance(images[0], dict):
        image_url = str(images[0].get("src") or "")

    url = str(product.get("permalink") or "").strip() or BASE_URL

    return Deal(
        id=f"tusmascotas:{stable_id}",
        title=html_lib.unescape(str(product.get("name") or "")).strip(),
        url=url,
        store="tusmascotas",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=image_url,
    )


def parse_html(html: str, category: str) -> list[Deal]:
    """Parse the JSON returned by :func:`fetch_html` (pure, no network).

    Accepts the wrapped ``{"products": [...]}`` payload produced by
    :func:`fetch_html` and the bare per-page array the Store API returns. An
    empty ``products`` list is an empty query (``NoResultsError``); a malformed
    payload raises ``RuntimeError`` so a change is loud.
    """
    try:
        payload = json.loads(html)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "Tus Mascotas Store API returned a malformed payload: "
            f"{exc!r} (payload length={len(html)})"
        ) from exc

    if isinstance(payload, list):
        products = payload
    elif isinstance(payload, dict) and "products" in payload:
        products = payload.get("products") or []
    else:
        raise RuntimeError(
            "Tus Mascotas Store API payload has no 'products' list "
            f"(payload length={len(html)})"
        )

    if not products:
        raise NoResultsError("Tus Mascotas Store API returned no products")

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


def _fetch_page(keyword: str, page: int) -> list:
    url = API_URL.format(query=quote(keyword), size=PAGE_SIZE, page=page)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpclient.get(url, headers=REQUEST_HEADERS)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
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
        page_products = _fetch_page(keyword, page)
        if not page_products:
            break
        products.extend(page_products)
        if len(page_products) < PAGE_SIZE:
            break
    return json.dumps({"products": products})


def fetch_deals(watchlist: dict) -> list[Deal]:
    queries = list(dict.fromkeys([*watchlist.get("keywords", []), *watchlist.get("scan", {}).get("tusmascotas_queries", [])]))
    return run_queries(
        "tusmascotas",
        queries,
        lambda keyword: parse_html(fetch_html(keyword), category=keyword),
    )
