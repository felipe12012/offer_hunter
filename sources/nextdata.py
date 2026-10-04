"""Shared scanner for stores whose listing pages embed their catalogue as JSON.

Falabella and Sodimac run on the same platform: every search/category page
ships the full result set in ``<script id="__NEXT_DATA__">`` (48 products per
page, with prices already split into internet / event / card / crossed-out
normal price). Reading that JSON needs no browser, so a request takes about a
second and a whole category can be paged through cheaply.
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import requests

from models import Deal
from sources import health, httpclient, progress

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
}
REQUEST_DELAY_SECONDS = 0.3
REQUEST_TIMEOUT_SECONDS = httpclient.DEFAULT_TIMEOUT_SECONDS
FETCH_ATTEMPTS = 3
DEFAULT_MAX_SEARCH_PAGES = 3
DEFAULT_MAX_CATEGORY_PAGES = 4
DEFAULT_MAX_CATEGORIES = 40
WORKERS = 4
MAX_WORKERS = 12  # a cap on what the watchlist may ask for: more is a way to get blocked

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


@dataclass(frozen=True)
class StoreConfig:
    store: str
    base_url: str
    home_url: str
    search_url: str        # with {query}
    category_url: str      # with {id} and {slug}
    category_href_re: str  # two groups: category id, slug


def _parse_price(text) -> int:
    digits = re.sub(r"[^\d]", "", str(text or ""))
    return int(digits) if digits else 0


def fetch_html(url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            response = httpclient.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"GET {url} failed after {FETCH_ATTEMPTS} attempts: {last_error}")


def fetch_page_props(url: str) -> dict:
    html = fetch_html(url)
    match = _NEXT_DATA.search(html)
    if match is None:
        title = re.search(r"<title>(.*?)</title>", html, re.S)
        raise RuntimeError(
            f"No __NEXT_DATA__ in {url} (page title={title.group(1).strip()[:60]!r}, length={len(html)})"
        )
    return json.loads(match.group(1))["props"]["pageProps"]


def _price_values(result: dict) -> dict[str, int]:
    """Map price type -> its first (representative) value as an int."""
    values: dict[str, int] = {}
    for entry in result.get("prices", []):
        amounts = entry.get("price") or []
        if amounts:
            values[entry.get("type", "")] = _parse_price(amounts[0])
    return values


def _deal_from_result(result: dict, cfg: StoreConfig, category: str, hint: str = "") -> Deal | None:
    product_id = result.get("productId")
    if not product_id:
        return None

    prices = _price_values(result)
    # Card-only (CMR) prices need the store's credit card, so the price anyone
    # can pay is the lowest of the internet and event prices.
    public = [prices[kind] for kind in ("internetPrice", "eventPrice") if prices.get(kind, 0) > 0]
    price = min(public) if public else (prices.get("cmrPrice") or prices.get("normalPrice") or 0)
    if price <= 0:
        return None

    normal = prices.get("normalPrice", 0)
    list_price = normal if normal > price else price
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0

    brand = (result.get("brand") or "").strip()
    name = (result.get("displayName") or "").strip()
    title = name if not brand or name.lower().startswith(brand.lower()) else f"{brand} {name}"
    if not title:
        return None

    media = result.get("mediaUrls") or []
    return Deal(
        id=f"{cfg.store}:{product_id}",
        title=title,
        url=urljoin(cfg.base_url, (result.get("url") or "").split("?")[0]),
        store=cfg.store,
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
        image_url=media[0] if media else "",
        hint=hint,
    )


def parse_results(page_props: dict, cfg: StoreConfig, category: str, hint: str = "") -> list[Deal]:
    deals: list[Deal] = []
    seen: set[str] = set()
    for result in page_props.get("results", []):
        deal = _deal_from_result(result, cfg, category, hint)
        if deal is not None and deal.id not in seen:
            seen.add(deal.id)
            deals.append(deal)
    return deals


def with_page(url: str, page: int) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
    query.append(("page", str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def scan_listing(
    start_url: str,
    cfg: StoreConfig,
    category: str,
    max_pages: int,
    fetch=fetch_page_props,
    sleep=time.sleep,
    hint: str = "",
) -> list[Deal]:
    """Read a search/category listing page by page, up to ``max_pages``."""
    deals: dict[str, Deal] = {}
    page_url = start_url
    for page in range(1, max_pages + 1):
        if progress.stopped():
            break  # the run gave up on this store: do not keep reading pages nobody is waiting for
        if page > 1:
            sleep(REQUEST_DELAY_SECONDS)
        props = fetch(page_url if page == 1 else with_page(page_url, page))
        new = [d for d in parse_results(props, cfg, category, hint) if d.id not in deals]
        for deal in new:
            deals[deal.id] = deal
        if page == 1 and props.get("currentUrl"):
            # A search such as "taladro" is rewritten by the site to a category
            # page; only that rewritten URL honours the page parameter.
            page_url = urljoin(cfg.base_url, props["currentUrl"])

        pagination = props.get("pagination") or {}
        per_page = pagination.get("perPage") or 0
        total = pagination.get("count") or 0
        last_page = -(-total // per_page) if per_page else page
        if not new or page >= last_page:
            break
    return list(deals.values())


def discover_categories(
    home_html: str,
    cfg: StoreConfig,
    patterns: dict[str, list[str]],
    limit: int = DEFAULT_MAX_CATEGORIES,
) -> list[tuple[str, str, str]]:
    """(group, category id, slug) for menu categories matching a group's patterns."""
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(cfg.category_href_re, home_html):
        category_id, slug = match.group(1), match.group(2)
        if category_id in seen:
            continue
        lowered = slug.lower()
        for group, group_patterns in patterns.items():
            if any(pattern.lower() in lowered for pattern in group_patterns):
                seen.add(category_id)
                found.append((group, category_id, slug))
                break
    return found[:limit]


def _merge_hint(existing: Deal, other: Deal) -> Deal:
    """The same product often turns up in several scans. The first one is kept, but the
    store's own department names from the others are remembered, so priority matching
    sees every department the store listed it in. (Search terms are not remembered:
    a search returns loosely related products.)"""
    extra = other.hint.strip()
    if extra and extra not in existing.hint:
        return replace(existing, hint=f"{existing.hint} {extra}".strip())
    return existing


def fetch_store_deals(
    cfg: StoreConfig,
    watchlist: dict,
    fetch=fetch_page_props,
    fetch_home=fetch_html,
    sleep=time.sleep,
) -> list[Deal]:
    scan = watchlist.get("scan", {})
    max_search = scan.get("max_search_pages", DEFAULT_MAX_SEARCH_PAGES)
    max_category = scan.get("max_category_pages", DEFAULT_MAX_CATEGORY_PAGES)

    deep_slugs = {slug.lower() for slug in scan.get("deep_slugs", [])}
    deep_pages = scan.get("deep_pages", max_category)
    jobs: list[tuple[str, str, int, str]] = []  # (category label, start url, max pages, hint)
    patterns = scan.get("category_patterns", {})
    if patterns:
        try:
            categories = discover_categories(
                fetch_home(cfg.home_url), cfg, patterns, scan.get("max_categories", DEFAULT_MAX_CATEGORIES)
            )
        except Exception as exc:
            health.warn(cfg.store, f"{cfg.store} category discovery failed: {exc}")
            categories = []
        # Priority (deep) categories go first: if the run runs out of time, the partial result
        # holds what matters most. sorted() is stable, so the menu order is kept inside each class.
        for group, category_id, slug in sorted(categories, key=lambda c: c[2].lower() not in deep_slugs):
            # Priority categories are read deeper; the slug travels as a hint so a
            # "Moda Mujer" product is recognised as women's clothing even when its
            # title never says so.
            pages = deep_pages if slug.lower() in deep_slugs else max_category
            hint = slug.replace("-", " ").replace("_", " ")
            jobs.append((group, cfg.category_url.format(id=category_id, slug=slug), pages, hint))
    for keyword in watchlist.get("keywords", []):
        jobs.append((keyword, cfg.search_url.format(query=quote(keyword)), max_search, ""))

    def run(job):
        label, url, pages, hint = job
        try:
            found = scan_listing(url, cfg, label, pages, fetch=fetch, sleep=sleep, hint=hint)
        except Exception as exc:
            return [], f"{cfg.store} scan of {url} failed: {exc}"
        # Publish as each job finishes: if the store overruns its time, these survive.
        progress.publish(cfg.store, found, merge=_merge_hint)
        return found, None

    # Requests are mostly waiting on the network (measured: 503 pages, 1,040 s of waiting, ~260 s wall time
    # with 4 workers), so more workers shorten the scan; the watchlist sets how many (scan.nextdata_workers).
    workers = max(1, min(int(scan.get("nextdata_workers", WORKERS)), MAX_WORKERS))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(run, jobs))

    deals: dict[str, Deal] = {}
    failures = 0
    for found, error in outcomes:  # jobs are ordered: categories first, so their label wins
        if error:
            failures += 1
            health.warn(cfg.store, error)
        for deal in found:
            if deal.id in deals:
                deals[deal.id] = _merge_hint(deals[deal.id], deal)
            else:
                deals[deal.id] = deal

    if jobs and failures == len(jobs):
        raise RuntimeError(f"All {cfg.store} scans failed")
    return list(deals.values())
