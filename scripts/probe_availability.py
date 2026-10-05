"""One-off probe (run from GitHub Actions, where the IP is not the developer's): can we tell from the stores
whether a product is still on sale? Samples stale and fresh Falabella/Sodimac products from Supabase and checks
each by (a) searching the listing for its product id and (b) opening its product page. Prints one line per check."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import falabella, nextdata, sodimac  # noqa: E402

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": KEY}
if KEY.startswith("eyJ"):
    HEADERS["Authorization"] = f"Bearer {KEY}"


def sample(store: str, stale: bool, n: int) -> list[dict]:
    cond = (
        "last_seen_at=lt.{ago}&last_seen_at=gt.{older}" if stale else "last_seen_at=gt.{recent}"
    )
    now = time.time()
    iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - s))
    query = cond.format(ago=iso(75 * 60), older=iso(5 * 3600), recent=iso(10 * 60))
    r = requests.get(
        f"{URL}/rest/v1/offer_products?select=id,url,price,title,last_seen_at&store=eq.{store}&discount_pct=gte.50&{query}&limit=200",
        headers=HEADERS, timeout=60,
    )
    rows = r.json()
    import random

    random.seed(7)
    return random.sample(rows, min(n, len(rows)))


def search_check(cfg, row: dict) -> str:
    pid = row["id"].split(":", 1)[1]
    began = time.time()
    try:
        props = nextdata.fetch_page_props(cfg.search_url.format(query=pid))
    except Exception as exc:  # noqa: BLE001
        return f"search ERROR {str(exc)[:70]}"
    hits = [x for x in props.get("results", []) if str(x.get("productId")) == pid]
    prices = [(e.get("type"), e.get("price")) for e in hits[0].get("prices", [])][:2] if hits else []
    return f"search results={len(props.get('results', []))} exact={bool(hits)} prices={prices} {time.time() - began:.1f}s"


def page_check(row: dict) -> str:
    began = time.time()
    try:
        r = requests.get(row["url"], headers=nextdata.HEADERS, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return f"page ERROR {type(exc).__name__}"
    info = f"page {r.status_code} {time.time() - began:.1f}s"
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        return info + " no-next-data"
    data = json.loads(m.group(1))["props"]["pageProps"].get("productData") or {}
    out = []
    flag = re.compile(r"avail|stock|sellable|soldout|buyable|inventory|status|active|visible|publish", re.I)
    for variant in (data.get("variants") or [])[:6]:
        flags = {k: v for k, v in variant.items() if flag.search(k) and not isinstance(v, (dict, list))}
        prices = [(x.get("type"), x.get("price")) for x in (variant.get("prices") or [])][:2]
        out.append(f"{flags} prices={prices}")
    top = {k: v for k, v in data.items() if flag.search(k) and not isinstance(v, (dict, list))}
    return info + f" top={top} variants={len(data.get('variants') or [])}
         " + "
         ".join(out[:4])


for store, cfg in (("falabella", falabella.CONFIG), ("sodimac", sodimac.CONFIG)):
    for stale in (True, False):
        rows = sample(store, stale, 4)
        print(f"== {store} {'STALE (75 min - 5 h unseen)' if stale else 'FRESH (<10 min)'}: {len(rows)} sampled", flush=True)
        for row in rows:
            print(f"- {row['id']} db_price={row['price']} seen={row['last_seen_at'][11:16]} {row['title'][:40]!r}", flush=True)
            print("    ", search_check(cfg, row), flush=True)
            print("    ", page_check(row), flush=True)
            time.sleep(1.0)
