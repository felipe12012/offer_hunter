"""Verifier: opens the product page of the offers people see and checks whether the store still sells them.

Not being in our scans does not mean sold out (we read the first pages of each listing and the order changes: of the
Falabella/Sodimac products unseen for 75 min to 24 h, 92-97 % were still on sale) and being in them does not mean on
sale (about 2 % of the products seen minutes ago were already out of stock). Only the product page knows:
``productData`` carries ``isPublished``, ``isOutOfStock`` and, per variant, ``isOnlineSellable`` / ``isHDAvailable`` /
``isCCAvailable``. Falabella and Sodimac share that page (a product page answers 200 from GitHub's servers in ~0.2 s).

What it does with the answer:

* writes it to ``offer_availability`` (the product page of the web reads it: "Agotado, según la tienda");
* a sold-out product gets its ``last_seen_at`` moved back so the lists hide it and its page shows it as ended at once
  (the next scan that really sees it revives it); a product the store sells again is brought back the same way.

Priority: the best offers (the web's default order) and what was announced in the last hours; those never checked first,
then the ones checked longest ago. A few hundred a run, every few minutes.
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from sources import httpclient
from sources.nextdata import HEADERS
from supabase_sync import SupabaseSync, log_failure

VERIFIED_STORES = ("falabella", "sodimac")
TOP_OFFERS = 800            # the web's best offers (default order) are always candidates
ANNOUNCED_HOURS = 12        # ... and what was sent to Telegram in the last hours
ANNOUNCED_LIMIT = 600
PER_RUN = 300               # pages opened per run
RECHECK_AVAILABLE_MINUTES = 20
RECHECK_SOLD_OUT_MINUTES = 60   # a sold-out product may be restocked
WORKERS = 8
RUN_BUDGET_SECONDS = 240
BLOCK_LIMIT = 8             # 403/429 answers in one run before it stops asking
SOLD_OUT_BACK_HOURS = 7     # last_seen_at of a sold-out product goes this far back (the web hides after 6 h)
CHUNK = 100

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


# ---- reading a product page -----------------------------------------------------------------------------------

def _parse_price(text) -> int:
    digits = re.sub(r"[^\d]", "", str(text or ""))
    return int(digits) if digits else 0


def _variant_price(variant: dict) -> int:
    """What anyone can pay: the lowest of the internet and event prices (the card-only price needs the store's card)."""
    amounts = []
    for entry in variant.get("prices") or []:
        if entry.get("type") in ("internetPrice", "eventPrice"):
            values = entry.get("price") or []
            if values and _parse_price(values[0]) > 0:
                amounts.append(_parse_price(values[0]))
    return min(amounts) if amounts else 0


def classify_page(html: str) -> dict | None:
    """{'available': bool, 'price': int | None, 'detail': str} or None when the page says nothing usable."""
    match = _NEXT_DATA.search(html)
    if match is None:
        return None
    try:
        data = json.loads(match.group(1))["props"]["pageProps"].get("productData") or {}
    except (ValueError, KeyError, AttributeError):
        return None
    if not data:
        return None
    variants = data.get("variants") or []
    sellable = [v for v in variants if v.get("isOnlineSellable") or v.get("isHDAvailable") or v.get("isCCAvailable")]
    prices = [p for p in (_variant_price(v) for v in sellable) if p > 0]
    price = min(prices) if prices else None
    detail = f"published={data.get('isPublished')} outOfStock={data.get('isOutOfStock')} sellable={len(sellable)}/{len(variants)}"
    if data.get("isPublished") is False or data.get("isOutOfStock") or not sellable:
        return {"available": False, "price": price, "detail": detail}
    return {"available": True, "price": price, "detail": detail}


class Blocked(RuntimeError):
    pass


def fetch_status(url: str) -> dict | None:
    """The page's verdict; {'available': False, 'detail': 'gone'} for a page that no longer exists; None when the
    answer proves nothing (error, odd page). Raises Blocked on 403/429 (the caller counts those)."""
    response = httpclient.get(url, headers=HEADERS, timeout=25)
    if response.status_code in (404, 410):
        return {"available": False, "price": None, "detail": f"gone (HTTP {response.status_code})"}
    if response.status_code in (403, 429):
        raise Blocked(f"HTTP {response.status_code}")
    if response.status_code != 200:
        return None
    return classify_page(response.text)


# ---- who to check ---------------------------------------------------------------------------------------------

def _chunks(items: list, size: int = CHUNK):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def pick_candidates(
    ranked_ids: list[str],
    checks: dict[str, dict],
    now: datetime,
    limit: int = PER_RUN,
) -> list[str]:
    """Ids to open now. ``ranked_ids`` is in priority order (best offers and announced ones first). Never checked first, in
    that order; then those checked longest ago. Recently checked ones are left alone."""
    fresh_available = now - timedelta(minutes=RECHECK_AVAILABLE_MINUTES)
    fresh_sold_out = now - timedelta(minutes=RECHECK_SOLD_OUT_MINUTES)
    never: list[str] = []
    stale: list[tuple[datetime, str]] = []
    seen: set[str] = set()
    for product_id in ranked_ids:
        if product_id in seen:
            continue
        seen.add(product_id)
        check = checks.get(product_id)
        if check is None:
            never.append(product_id)
            continue
        checked = datetime.fromisoformat(check["checked_at"].replace("Z", "+00:00"))
        if checked < (fresh_available if check["available"] else fresh_sold_out):
            stale.append((checked, product_id))
    stale.sort()
    return (never + [product_id for _checked, product_id in stale])[:limit]


# ---- the run --------------------------------------------------------------------------------------------------

def _load_ranked(store: SupabaseSync, now: datetime) -> tuple[list[str], dict[str, str]]:
    """(ids by priority, id -> url). Announced offers first (people already acted on them), then the web's best."""
    since = (now - timedelta(hours=6)).isoformat()
    top = store._get_rows(
        "offer_feed",
        {
            "select": "id,url",
            "store": f"in.({','.join(VERIFIED_STORES)})",
            "dup_rank": "eq.1",
            "last_seen_at": f"gte.{since}",
            "order": "verified_pct.desc,web_discount_pct.desc,id.asc",
            "limit": TOP_OFFERS,
        },
    )
    sent = store._get_rows(
        "offer_sent",
        {
            "select": "product_id",
            "sent_at": f"gte.{(now - timedelta(hours=ANNOUNCED_HOURS)).isoformat()}",
            "order": "sent_at.desc",
            "limit": ANNOUNCED_LIMIT,
        },
    )
    urls = {row["id"]: row["url"] for row in top}
    announced = [row["product_id"] for row in sent if row["product_id"].split(":", 1)[0] in VERIFIED_STORES]
    missing = [pid for pid in announced if pid not in urls]
    for chunk in _chunks(missing):
        for row in store._get_rows("offer_products", {"select": "id,url", "id": f"in.({','.join(chunk)})"}):
            urls[row["id"]] = row["url"]
    ranked = [pid for pid in announced if pid in urls] + [row["id"] for row in top]
    return ranked, urls


def _load_checks(store: SupabaseSync, ids: list[str]) -> dict[str, dict]:
    checks: dict[str, dict] = {}
    for chunk in _chunks(ids):
        for row in store._get_rows(
            "offer_availability", {"select": "product_id,available,checked_at", "product_id": f"in.({','.join(chunk)})"}
        ):
            checks[row["product_id"]] = row
    return checks


def apply_results(store: SupabaseSync, results: dict[str, dict], previous: dict[str, dict], now: datetime) -> dict:
    """Write what the stores said. Returns counters."""
    stamp = now.isoformat()
    rows = [
        {"product_id": pid, "available": r["available"], "price": r.get("price"), "detail": r.get("detail"), "checked_at": stamp}
        for pid, r in results.items()
    ]
    for chunk in _chunks(rows, 500):
        store._post(
            "offer_availability", chunk,
            prefer="resolution=merge-duplicates,return=minimal", params={"on_conflict": "product_id"},
        )
    sold_out = [pid for pid, r in results.items() if not r["available"]]
    restocked = [pid for pid, r in results.items() if r["available"] and previous.get(pid, {}).get("available") is False]
    back = (now - timedelta(hours=SOLD_OUT_BACK_HOURS)).isoformat()
    for ids, when in ((sold_out, back), (restocked, stamp)):
        for chunk in _chunks(ids):
            store.set_last_seen(chunk, when)
    return {"checked": len(results), "sold_out": len(sold_out), "restocked": len(restocked)}


def verify(store: SupabaseSync, now: datetime | None = None, fetch=None, per_run: int = PER_RUN) -> dict:
    now = now or datetime.now(timezone.utc)
    fetch = fetch or fetch_status
    ranked, urls = _load_ranked(store, now)
    checks = _load_checks(store, ranked)
    picked = pick_candidates(ranked, checks, now, per_run)

    began = time.monotonic()
    blocked = 0
    results: dict[str, dict] = {}

    def one(product_id: str):
        nonlocal blocked
        if blocked >= BLOCK_LIMIT or time.monotonic() - began > RUN_BUDGET_SECONDS:
            return product_id, None
        try:
            return product_id, fetch(urls[product_id])
        except Blocked:
            blocked += 1
            return product_id, None
        except (requests.RequestException, ValueError):
            return product_id, None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for product_id, status in pool.map(one, picked):
            if status is not None:
                results[product_id] = status

    counters = apply_results(store, results, checks, now) if results else {"checked": 0, "sold_out": 0, "restocked": 0}
    counters.update(candidates=len(ranked), picked=len(picked), blocked=blocked, seconds=round(time.monotonic() - began))
    return counters


def run() -> int:
    store = SupabaseSync.from_env()
    if store is None:
        print("Verifier needs SUPABASE_URL and SUPABASE_SERVICE_KEY", file=sys.stderr)
        return 1
    try:
        counters = verify(store)
    except Exception as exc:
        log_failure("verify offers", exc)
        return 1
    print(
        f"Verified {counters['checked']}/{counters['picked']} product pages ({counters['candidates']} candidates): "
        f"{counters['sold_out']} sold out, {counters['restocked']} back on sale, {counters['blocked']} blocked, "
        f"{counters['seconds']}s",
        file=sys.stderr,
    )
    summary = httpclient.format_summary()
    if summary:
        print(summary, file=sys.stderr)
    if counters["sold_out"] or counters["restocked"]:
        try:
            store.refresh_feed()  # the lists read offer_feed: hide/show what just changed without waiting for the next scan
        except Exception as exc:
            log_failure("refresh the feed", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
