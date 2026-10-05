"""Shared scanner for VTEX stores exposing the public catalogue search API.

VTEX serves ``/api/catalog_system/pub/products/search`` as JSON with the exact
price (``Price``), the crossed-out price (``ListPrice``) and stock
(``AvailableQuantity``) per seller, so no browser is needed. Used by Asics and
Reebok Chile. The API caps a page at 50 products, and a search term the store
does not carry returns an empty list rather than an error.

Some VTEX IO stores (Sony Chile) keep the classic catalogue API but return an
empty list from it; their search is served by the Intelligent Search API instead
(``/api/io/_v/api/intelligent-search/product_search?query=...``), which returns
the same per-product shape (``items[].sellers[].commertialOffer``). Set
``StoreConfig.use_intelligent_search`` for those stores.
"""
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import requests

from models import Deal
from sources import health
from sources import httpclient

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "es-CL,es;q=0.9",
}
REQUEST_TIMEOUT_SECONDS = 30
FETCH_ATTEMPTS = 3
PAGE_SIZE = 48
DEFAULT_MAX_PAGES = 3
REQUEST_DELAY_SECONDS = 0.3


@dataclass(frozen=True)
class StoreConfig:
    store: str
    base_url: str
    # VTEX IO stores whose classic catalogue API returns an empty array; search via
    # the Intelligent Search endpoint instead (see module docstring).
    use_intelligent_search: bool = False


def _to_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def search_url(base_url: str, keyword: str, start: int) -> str:
    return (
        f"{base_url}/api/catalog_system/pub/products/search"
        f"?ft={quote(keyword)}&_from={start}&_to={start + PAGE_SIZE - 1}"
    )


def intelligent_search_url(base_url: str, keyword: str, start: int) -> str:
    page = start // PAGE_SIZE + 1
    return (
        f"{base_url}/api/io/_v/api/intelligent-search/product_search"
        f"?query={quote(keyword)}&count={PAGE_SIZE}&page={page}"
    )


def _get_json(url: str):
    last_error: Exception | None = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            response = httpclient.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} failed after {FETCH_ATTEMPTS} attempts: {last_error}")


def fetch_page(base_url: str, keyword: str, start: int) -> list[dict]:
    data = _get_json(search_url(base_url, keyword, start))
    return data if isinstance(data, list) else []


def fetch_intelligent_page(base_url: str, keyword: str, start: int) -> list[dict]:
    data = _get_json(intelligent_search_url(base_url, keyword, start))
    if isinstance(data, dict):
        products = data.get("products")
        return products if isinstance(products, list) else []
    return data if isinstance(data, list) else []


def _deal_from_product(product: dict, cfg: StoreConfig, category: str) -> Deal | None:
    if not isinstance(product, dict):
        return None
    items = product.get("items") or []
    if not items:
        return None
    item = items[0]
    sellers = item.get("sellers") or []
    if not sellers:
        return None
    offer = sellers[0].get("commertialOffer") or {}

    price = _to_int(offer.get("Price"))
    # Sold-out products can still carry a crossed-out price; they are not offers.
    if price <= 0 or _to_int(offer.get("AvailableQuantity")) <= 0:
        return None

    list_price = _to_int(offer.get("ListPrice"))
    if list_price <= price:
        list_price = price
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    title = (product.get("productName") or "").strip()
    link = product.get("link") or ""
    if not title or not link:
        return None
    # Classic stores return an absolute link; Intelligent Search returns a
    # root-relative one (``/sel1224g/p``). urljoin leaves an absolute URL intact.
    url = urljoin(cfg.base_url + "/", link)

    images = item.get("images") or []
    image_url = images[0].get("imageUrl", "") if images and isinstance(images[0], dict) else ""

    product_id = product.get("productId") or product.get("productReference") or link
    return Deal(
        id=f"{cfg.store}:{product_id}",
        title=title,
        url=url,
        store=cfg.store,
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=image_url,
    )


def parse_products(products: list[dict], cfg: StoreConfig, category: str) -> list[Deal]:
    deals: list[Deal] = []
    seen: set[str] = set()
    for product in products:
        deal = _deal_from_product(product, cfg, category)
        if deal is not None and deal.id not in seen:
            seen.add(deal.id)
            deals.append(deal)
    return deals


def fetch_store_deals(
    cfg: StoreConfig,
    watchlist: dict,
    fetch=None,
    sleep=time.sleep,
) -> list[Deal]:
    if fetch is None:
        fetch = fetch_intelligent_page if cfg.use_intelligent_search else fetch_page
    max_pages = watchlist.get("scan", {}).get("max_vtex_pages", DEFAULT_MAX_PAGES)
    deals: dict[str, Deal] = {}
    failures = 0
    keywords = watchlist.get("keywords", [])
    for keyword in keywords:
        try:
            for page in range(max_pages):
                if page:
                    sleep(REQUEST_DELAY_SECONDS)
                products = fetch(cfg.base_url, keyword, page * PAGE_SIZE)
                new = [d for d in parse_products(products, cfg, keyword) if d.id not in deals]
                for deal in new:
                    deals[deal.id] = deal
                if len(products) < PAGE_SIZE or not new:
                    break
        except Exception as exc:  # noqa: BLE001 - isolate one bad keyword
            failures += 1
            health.warn(cfg.store, f"{cfg.store} keyword {keyword!r} failed: {exc}")
    if keywords and failures == len(keywords):
        raise RuntimeError(f"All {cfg.store} searches failed")
    return list(deals.values())
