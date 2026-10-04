"""Cyber hot scan: only the biggest discounts of Falabella and Sodimac, every few minutes.

The regular scan (main_fast.py) reads ~50,000 products and takes ~10 minutes, so a pricing mistake
could wait that long and then be bought out. This one asks both stores only for products with 70 % off
or more (a filter their listings offer), over every category and keyword: ~1,700 products in about
a minute, and announces what is worth a hurry:

* possible pricing mistakes (price_error.py);
* discounts our own history confirms at 60 % or more.

Everything else waits for the regular scan. This workflow does not commit data/: what it announced is
recorded in Supabase (offer_sent), and the regular scan reads it from there so nothing is sent twice.
"""

from __future__ import annotations

import sys
import time
from dataclasses import replace

import main_fast
from dedup import deal_key, load_seen
from deal_filter import evaluate
from notifier import send_offers
from price_error import as_scored, find_price_errors
from price_history import load_price_history
from reports import format_log
from sources import httpclient
from supabase_sync import SupabaseSync, log_failure

# Stores whose listings can be filtered by discount.
HOT_STORES = ("falabella", "sodimac")
# Only verified discounts at least this big are worth announcing ahead of the regular scan.
HOT_MIN_VERIFIED_PCT = 60
# A hot scan that has not finished in this long is dropped: the next one starts in a few minutes.
HOT_TIMEOUT_SECONDS = 240


def hot_watchlist(watchlist: dict) -> dict:
    """The watchlist with every other store disabled and the scan switched to hot mode."""
    others = {store for store, _attr in main_fast.SOURCE_FETCHERS if store not in HOT_STORES}
    disabled = sorted({name.lower() for name in watchlist.get("disabled_stores", [])} | others)
    return {**watchlist, "disabled_stores": disabled, "scan": {**watchlist.get("scan", {}), "hot_only": True}}


def pick_candidates(deals, watchlist: dict, history: dict, seen_keys: set[str]) -> list:
    """Offers worth announcing now: pricing mistakes (anywhere) and confirmed big discounts."""
    price_errors = find_price_errors(deals, history)
    candidates = []
    for deal in deals:
        if deal_key(deal) in seen_keys:
            continue
        scored = evaluate(deal, watchlist, history)
        if scored is not None and not (
            scored.advertised_confirmed and (scored.verified_pct or 0) >= HOT_MIN_VERIFIED_PCT
        ):
            scored = None  # worth telling, but not in a hurry: the regular scan sends it
        if deal.id in price_errors:
            reason, drop = price_errors[deal.id]
            scored = replace(scored, price_error=reason) if scored else as_scored(deal, reason, drop)
        if scored is not None:
            candidates.append(scored)
    return candidates


def run() -> int:
    started = time.time()
    main_fast.SOURCE_TIMEOUT_SECONDS = HOT_TIMEOUT_SECONDS
    watchlist = main_fast.load_watchlist()
    try:
        deals, reports = main_fast.scan_stores(hot_watchlist(watchlist))
    except Exception as exc:
        print(f"Hot scan failed: {exc}", file=sys.stderr)
        return 1
    print(format_log(reports), file=sys.stderr)
    network = httpclient.format_summary()
    if network:
        print(network, file=sys.stderr)

    history = load_price_history(main_fast.HISTORY_PATH)
    seen_keys = load_seen(main_fast.SEEN_PATH) | main_fast.remote_sent_keys()
    candidates = pick_candidates(deals, watchlist, history, seen_keys)
    candidates, _aliases = main_fast.dedupe_cross_store(candidates)

    store = SupabaseSync.from_env()
    subscribers: list[int] = []
    if store is not None:
        try:
            subscribers = store.active_subscribers()
        except Exception as exc:
            log_failure("read subscribers", exc)

    delivered = (
        send_offers(
            candidates,
            alerts=watchlist.get("alerts"),
            max_unverified=0,
            max_priority_unverified=0,
            subscriber_chat_ids=subscribers,
        )
        if candidates
        else []
    )
    mistakes = sum(1 for offer in delivered if offer.price_error)
    print(
        f"Hot scan: {len(deals)} products, {len(candidates)} to announce, {len(delivered)} delivered "
        f"({mistakes} possible mistakes) in {time.time() - started:.0f}s",
        file=sys.stderr,
    )

    if store is not None:
        # Recorded first: the regular scan skips whatever is here. Then the fresh prices.
        try:
            store.record_sent(delivered)
        except Exception as exc:
            log_failure("record hot offers", exc)
        try:
            store.sync_scan(deals)
        except Exception as exc:
            log_failure("mirror hot scan", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
