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
from datetime import datetime, timedelta, timezone

import requests

from models import Deal, ScoredDeal
from taxonomy import classify

BATCH_SIZE = 1000
POINT_BATCH_SIZE = 2000
REQUEST_TIMEOUT_SECONDS = 60
ATTEMPTS = 3


class SupabaseError(RuntimeError):
    pass


def _deal_row(deal: Deal) -> dict:
    group, subcategory = classify(deal.title, deal.category, deal.store)
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
        "grp": group,
        "subcat": subcategory,
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    # -- bot subscribers -------------------------------------------------------

    def _get_rows(self, table: str, params: dict) -> list[dict]:
        response = requests.get(
            f"{self.url}/rest/v1/{table}", headers=self._headers(), params=params, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code >= 400:
            raise SupabaseError(f"GET {table} failed (HTTP {response.status_code}: {response.text[:200]})")
        return response.json()

    def active_subscribers(self) -> list[int]:
        rows = self._get_rows("offer_subscribers", {"select": "chat_id", "active": "eq.true", "order": "chat_id"})
        return [int(row["chat_id"]) for row in rows]

    def upsert_subscriber(self, chat_id: int, username: str | None, first_name: str | None, active: bool) -> None:
        self._post(
            "offer_subscribers",
            [{"chat_id": chat_id, "username": username, "first_name": first_name, "active": active,
              "updated_at": _now_iso()}],
            prefer="resolution=merge-duplicates,return=minimal",
            params={"on_conflict": "chat_id"},
        )

    def set_subscribers_active(self, chat_ids: list[int], active: bool) -> None:
        if not chat_ids:
            return
        ids = ",".join(str(int(chat_id)) for chat_id in chat_ids)
        response = requests.patch(
            f"{self.url}/rest/v1/offer_subscribers",
            headers=self._headers("return=minimal"),
            params={"chat_id": f"in.({ids})"},
            data=json.dumps({"active": active, "updated_at": _now_iso()}),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise SupabaseError(f"PATCH offer_subscribers failed (HTTP {response.status_code}: {response.text[:200]})")

    def get_bot_state(self, key: str) -> str | None:
        rows = self._get_rows("offer_bot_state", {"select": "value", "key": f"eq.{key}"})
        return rows[0]["value"] if rows else None

    def set_bot_state(self, key: str, value: str) -> None:
        self._post(
            "offer_bot_state",
            [{"key": key, "value": value, "updated_at": _now_iso()}],
            prefer="resolution=merge-duplicates,return=minimal",
            params={"on_conflict": "key"},
        )

    def recent_sent_keys(self, hours: int = 48, page_size: int = 1000, max_pages: int = 30) -> set[str]:
        """"product_id:price" of every offer sent in the last ``hours``: what another workflow (the Cyber hot
        scan) already announced, so this one does not announce it again. PostgREST returns at most
        1000 rows per request, hence the paging."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        keys: set[str] = set()
        for page in range(max_pages):
            rows = self._get_rows(
                "offer_sent",
                {
                    "select": "product_id,price",
                    "sent_at": f"gte.{since}",
                    "order": "id",
                    "limit": page_size,
                    "offset": page * page_size,
                },
            )
            keys.update(f"{row['product_id']}:{row['price']}" for row in rows)
            if len(rows) < page_size:
                break
        return keys

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

    def refresh_feed(self) -> None:
        """Rebuild the public feed materialized view (offer_feed) after a scan, so
        the web sees this run's data. Server-side function, service_role only."""
        self._post("rpc/offer_refresh_feed", {})

    # -- one-time import of the JSON files ------------------------------------

    def import_history(self, history: dict) -> dict:
        products = []
        points = []
        seen_points: set[tuple[str, str, int]] = set()
        for product_id, snapshots in history.items():
            if not snapshots:
                continue
            latest = snapshots[-1]["price"]
            products.append(
                {"id": product_id, "store": product_id.split(":", 1)[0], "price": latest, "list_price": latest}
            )
            for snapshot in snapshots:
                # The table is unique on (product, day, price): a price that goes
                # 100 -> 90 -> 100 within one day is a single stored point.
                point_key = (product_id, snapshot["date"], snapshot["price"])
                if point_key in seen_points:
                    continue
                seen_points.add(point_key)
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


    def recent_store_status(self, limit: int = 2) -> list[dict | None]:
        """Per-store status of the latest runs, newest first: [{store: status}, ...].

        A run recorded before diagnostics existed (no store_status) is ``None``."""
        response = requests.get(
            f"{self.url}/rest/v1/offer_scan_runs",
            headers=self._headers(),
            params={"select": "store_status", "order": "started_at.desc", "limit": limit},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise SupabaseError(
                f"recent_store_status failed (HTTP {response.status_code}: {response.text[:200]})"
            )
        statuses: list[dict | None] = []
        for row in response.json():
            raw = row.get("store_status")
            statuses.append({store: info.get("status") for store, info in raw.items()} if raw else None)
        return statuses


def log_failure(action: str, exc: Exception) -> None:
    print(f"Supabase {action} failed (JSON state is unaffected): {exc}", file=sys.stderr)
