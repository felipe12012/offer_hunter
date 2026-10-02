"""Mirror of the scan state in Supabase (Postgres), over the REST API.

Tables and the ``offer_sync_scan`` function are defined in
``supabase/migrations/0001_offer_hunter.sql``. The client is configured by two
environment variables, both secrets:

  SUPABASE_URL          https://<ref>.supabase.co
  SUPABASE_SERVICE_KEY  the project's *secret* key (server-side only)

When either is missing ``SupabaseSync.from_env()`` returns None and the
pipeline simply skips the database.
"""
import json
import os
import sys
import time

import requests

from models import Deal, ScoredDeal

BATCH_SIZE = 1000
POINT_BATCH_SIZE = 2000
REQUEST_TIMEOUT_SECONDS = 60
ATTEMPTS = 3


class SupabaseError(RuntimeError):
    pass


def _deal_row(deal: Deal) -> dict:
    return {
        "id": deal.id,
        "store": deal.store,
        "title": deal.title,
        "url": deal.url,
        "image_url": deal.image_url,
        "category": deal.category,
        "price": deal.price,
        "list_price": deal.list_price,
        "discount_pct": deal.discount_pct,
    }


def _sent_row(offer: ScoredDeal) -> dict:
    deal = offer.deal
    return {
        "product_id": deal.id,
        "price": deal.price,
        "store": deal.store,
        "title": deal.title,
        "url": deal.url,
        "verified_pct": offer.verified_pct,
        "advertised_pct": deal.discount_pct,
        "real_pct": offer.real_discount_pct,
        "reasons": list(offer.reasons),
        "source": "live",
    }


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


class SupabaseSync:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key
        self.batch_size = BATCH_SIZE

    @classmethod
    def from_env(cls) -> "SupabaseSync | None":
        # An unset GitHub secret reaches the job as an empty string.
        url = os.environ.get("SUPABASE_URL") or ""
        key = os.environ.get("SUPABASE_SERVICE_KEY") or ""
        if not url or not key:
            return None
        return cls(url, key)

    # -- HTTP ----------------------------------------------------------------

    def _headers(self, prefer: str | None = None) -> dict:
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        # New-style secret keys (sb_secret_...) are not JWTs and go in `apikey`
        # only; the legacy service_role key is a JWT and is also sent as Bearer.
        if self.key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {self.key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _post(self, path: str, payload, prefer: str | None = None, params: dict | None = None):
        url = f"{self.url}/rest/v1/{path}"
        last_error = "unknown error"
        for attempt in range(1, ATTEMPTS + 1):
            try:
                response = requests.post(
                    url,
                    headers=self._headers(prefer),
                    data=json.dumps(payload),
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.RequestException as exc:
                last_error = f"request error: {exc}"
            else:
                if response.status_code < 400:
                    return response
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code < 500 and response.status_code != 429:
                    break  # a client error will not fix itself on retry
            if attempt < ATTEMPTS:
                time.sleep(2 * attempt)
        raise SupabaseError(f"POST {path} failed ({last_error})")

    # -- scan mirror ---------------------------------------------------------

    def sync_scan(self, deals: list[Deal]) -> dict:
        """Upsert the scanned products and append price points for the ones whose
        price changed (done in SQL by offer_sync_scan). Returns summed counters."""
        totals = {"received": 0, "new": 0, "updated": 0, "points": 0}
        for batch in _chunks([_deal_row(d) for d in deals], self.batch_size):
            result = self._post("rpc/offer_sync_scan", {"deals": batch}).json()
            for key in totals:
                totals[key] += int(result.get(key, 0))
        return totals

    def record_sent(self, offers: list[ScoredDeal]) -> None:
        if not offers:
            return
        self._post(
            "offer_sent",
            [_sent_row(offer) for offer in offers],
            prefer="resolution=ignore-duplicates,return=minimal",
            params={"on_conflict": "product_id,price"},
        )

    def record_run(self, stats: dict) -> None:
        self._post("offer_scan_runs", [stats], prefer="return=minimal")

    # -- one-time import of the JSON files ------------------------------------

    def import_history(self, history: dict) -> dict:
        products = []
        points = []
        for product_id, snapshots in history.items():
            if not snapshots:
                continue
            latest = snapshots[-1]["price"]
            products.append(
                {"id": product_id, "store": product_id.split(":", 1)[0], "price": latest, "list_price": latest}
            )
            for snapshot in snapshots:
                points.append(
                    {
                        "product_id": product_id,
                        "observed_at": f"{snapshot['date']}T12:00:00Z",
                        "price": snapshot["price"],
                        "source": "migrated",
                    }
                )

        ignore = "resolution=ignore-duplicates,return=minimal"
        for batch in _chunks(products, BATCH_SIZE):  # products first: points reference them
            self._post("offer_products", batch, prefer=ignore, params={"on_conflict": "id"})
        for batch in _chunks(points, POINT_BATCH_SIZE):
            self._post(
                "offer_price_points", batch, prefer=ignore,
                params={"on_conflict": "product_id,observed_at,price"},
            )
        return {"products": len(products), "points": len(points)}

    def import_seen(self, keys: list[str]) -> int:
        rows = []
        for key in keys:
            product_id, _, price = key.rpartition(":")
            if product_id and price.isdigit():
                rows.append({"product_id": product_id, "price": int(price), "source": "migrated"})
        for batch in _chunks(rows, BATCH_SIZE):
            self._post(
                "offer_sent", batch, prefer="resolution=ignore-duplicates,return=minimal",
                params={"on_conflict": "product_id,price"},
            )
        return len(rows)

    def count(self, table: str) -> int:
        response = requests.get(
            f"{self.url}/rest/v1/{table}",
            headers={**self._headers("count=exact"), "Range": "0-0"},
            params={"select": "id"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise SupabaseError(f"count {table} failed (HTTP {response.status_code}: {response.text[:200]})")
        return int(response.headers["Content-Range"].rsplit("/", 1)[1])


def log_failure(action: str, exc: Exception) -> None:
    print(f"Supabase {action} failed (JSON state is unaffected): {exc}", file=sys.stderr)
