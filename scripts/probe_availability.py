"""One-off probe (run from GitHub Actions, where the IP is not the developer's): how many Falabella/Sodimac products
that stopped appearing in our scans are really sold out? Samples stale and fresh products (50%+ off) from Supabase,
opens each product page and applies the availability rule below. Prints a tally and examples."""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources import nextdata  # noqa: E402

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {"apikey": KEY}
if KEY.startswith("eyJ"):
    HEADERS["Authorization"] = f"Bearer {KEY}"
PER_GROUP = int(os.environ.get("PROBE_N", "120"))


def sample(store: str, lo_s: int, hi_s: int, n: int) -> list[dict]:
    now = time.time()
    iso = lambda s: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - s))
    r = requests.get(
        f"{URL}/rest/v1/offer_products?select=id,url,price,title,last_seen_at&store=eq.{store}&discount_pct=gte.50"
        f"&last_seen_at=lt.{iso(lo_s)}&last_seen_at=gt.{iso(hi_s)}&limit=1000",
        headers=HEADERS, timeout=60,
    )
    rows = r.json()
    random.seed(11)
    return random.sample(rows, min(n, len(rows)))


def check(row: dict) -> dict:
    try:
        r = requests.get(row["url"], headers=nextdata.HEADERS, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return {"verdict": f"error:{type(exc).__name__}"}
    if r.status_code in (404, 410):
        return {"verdict": "gone"}
    if r.status_code != 200:
        return {"verdict": f"http{r.status_code}"}
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        return {"verdict": "no-data"}
    data = (json.loads(m.group(1))["props"]["pageProps"].get("productData")) or {}
    if not data:
        return {"verdict": "no-product"}
    variants = data.get("variants") or []
    sellable = [
        v for v in variants
        if v.get("isOnlineSellable") or v.get("isHDAvailable") or v.get("isCCAvailable")
    ]
    detail = f"published={data.get('isPublished')} outOfStock={data.get('isOutOfStock')} variants={len(variants)} sellable={len(sellable)}"
    if data.get("isPublished") is False:
        return {"verdict": "unpublished", "detail": detail}
    if data.get("isOutOfStock") or not sellable:
        return {"verdict": "sold-out", "detail": detail}
    return {"verdict": "available", "detail": detail}


def run_group(label: str, rows: list[dict]) -> None:
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(check, rows))
    tally: dict[str, int] = {}
    for res in results:
        tally[res["verdict"]] = tally.get(res["verdict"], 0) + 1
    print(f"== {label}: {len(rows)} checked -> {tally}", flush=True)
    shown = 0
    for row, res in zip(rows, results):
        if res["verdict"] != "available" and shown < 6:
            shown += 1
            print(f"   {res['verdict']:12} {row['id']} {row['title'][:42]!r} seen={row['last_seen_at'][11:16]} {res.get('detail', '')}", flush=True)


for store in ("falabella", "sodimac"):
    run_group(f"{store} unseen 75 min - 3 h", sample(store, 75 * 60, 3 * 3600, PER_GROUP))
    run_group(f"{store} unseen 3 h - 24 h", sample(store, 3 * 3600, 24 * 3600, PER_GROUP))
    run_group(f"{store} FRESH (control)", sample(store, -3600, 8 * 60, PER_GROUP // 2))
