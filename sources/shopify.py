"""Shared scanner for Shopify stores exposing ``/products.json``.

Shopify stores publish their whole catalogue as JSON, with the variant SKU, the
exact integer price and ``compare_at_price`` (the crossed-out price) already
separated, so no browser is needed. Dedicated brand stores (Vans, Crocs,
Merrell, Salomon, Hush Puppies) sell one category, so their whole catalogue is
tagged with that store's category instead of being filtered by keyword.

Card-only prices do not exist here, but two live traps do: a variant can be sold
out with a discount still attached (measured: 897/1808 products on one store),
and ``compare_at_price`` is sometimes *below* the sale price, which would yield
a negative discount.
"""
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests

from models import Deal

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9",
}
REQUEST_TIMEOUT_SECONDS = 30
FETCH_ATTEMPTS = 3
PAGE_SIZE = 250
DEFAULT_MAX_PAGES = 8
REQUEST_DELAY_SECONDS = 0.3


@dataclass(frozen=True)
class StoreConfig:
    store: str
    base_url: str
    category: str


def _parse_price(text) -> int:
    digits = "".join(ch for ch in str(text or "") if ch.isdigit())
    return int(digits) if digits else 0


def fetch_products(base_url: str, page: int) -> list[dict]:
    url = f"{base_url}/products.json?limit={PAGE_SIZE}&page={page}"
    last_error: Exception | None = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json().get("products", [])
        except Exception as exc:  # noqa: BLE001 - retried, then surfaced
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} failed after {FETCH_ATTEMPTS} attempts: {last_error}")


def _deal_from_product(product: dict, cfg: StoreConfig) -> Deal | None:
    if not isinstance(product, dict):
        return None
    variants = [
        variant
        for variant in (product.get("variants") or [])
        if isinstance(variant, dict)
        and variant.get("available")
        and _parse_price(variant.get("price")) > 0
    ]
    if not variants:
        return None
    # The grid shows the cheapest buyable variant; one Deal per product, not per
    # size, or the same URL would be sent several times under different ids.
    variant = min(variants, key=lambda v: _parse_price(v.get("price")))
    price = _parse_price(variant.get("price"))

    list_price = price
    compare_at = _parse_price(variant.get("compare_at_price"))
    if compare_at > price:
        list_price = compare_at
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    title = (product.get("title") or "").strip()
    handle = product.get("handle") or ""
    if not title or not handle:
        return None

    sku = str(variant.get("sku") or "").strip() or str(product.get("id") or handle)
    images = product.get("images") or []
    image_url = ""
    if images and isinstance(images[0], dict):
        image_url = images[0].get("src") or ""

    return Deal(
        id=f"{cfg.store}:{sku}",
        title=title,
        url=urljoin(cfg.base_url + "/", f"products/{handle}"),
        store=cfg.store,
        category=cfg.category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=image_url,
    )


def parse_products(products: list[dict], cfg: StoreConfig) -> list[Deal]:
    deals: list[Deal] = []
    seen: set[str] = set()
    for product in products:
        deal = _deal_from_product(product, cfg)
        if deal is not None and deal.id not in seen:
            seen.add(deal.id)
            deals.append(deal)
    return deals


def fetch_store_deals(
    cfg: StoreConfig,
    watchlist: dict,
    fetch=fetch_products,
    sleep=time.sleep,
) -> list[Deal]:
    max_pages = watchlist.get("scan", {}).get("max_shopify_pages", DEFAULT_MAX_PAGES)
    deals: dict[str, Deal] = {}
    for page in range(1, max_pages + 1):
        if page > 1:
            sleep(REQUEST_DELAY_SECONDS)
        products = fetch(cfg.base_url, page)
        new = [deal for deal in parse_products(products, cfg) if deal.id not in deals]
        for deal in new:
            deals[deal.id] = deal
        if len(products) < PAGE_SIZE or not new:
            break
    return list(deals.values())
