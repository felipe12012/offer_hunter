# main_fast.py
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from deal_filter import evaluate
from dedup import deal_key, load_seen, mark_seen
from models import Deal, ScoredDeal
from notifier import send_offers
from price_history import load_price_history, save_price_history, update_price_history
from sources.falabella import fetch_deals as fetch_falabella_deals
from sources.hites import fetch_deals as fetch_hites_deals
from sources.paris import fetch_deals as fetch_paris_deals
from sources.ripley import fetch_deals as fetch_ripley_deals
from sources.sodimac import fetch_deals as fetch_sodimac_deals
from sources.tottus import fetch_deals as fetch_tottus_deals

# The single roster of registered sources as (store, module attribute name).
# The attribute is resolved at call time so tests can monkeypatch
# main_fast.fetch_<store>_deals and have fetch_all_deals see the replacement.
SOURCE_FETCHERS = [
    ("sodimac", "fetch_sodimac_deals"),
    ("falabella", "fetch_falabella_deals"),
    ("paris", "fetch_paris_deals"),
    ("ripley", "fetch_ripley_deals"),
    ("tottus", "fetch_tottus_deals"),
    ("hites", "fetch_hites_deals"),
]
SOURCE_NAMES = [attr for _store, attr in SOURCE_FETCHERS]

SEEN_PATH = Path(__file__).parent / "data" / "seen_items.json"
HISTORY_PATH = Path(__file__).parent / "data" / "price_history.json"
WATCHLIST_PATH = Path(__file__).parent / "config" / "watchlist.json"

load_dotenv(Path(__file__).parent / ".env")


def load_watchlist() -> dict:
    with WATCHLIST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_all_deals(watchlist: dict) -> list[Deal]:
    # Resolved on every call so a monkeypatched module attribute is picked up —
    # same reasoning as job-hunter-agent/main.py.
    source_fetchers = [(store, globals()[attr]) for store, attr in SOURCE_FETCHERS]

    deals: list[Deal] = []
    failures = 0
    for name, fetch in source_fetchers:
        try:
            deals.extend(fetch(watchlist))
        except Exception as exc:
            failures += 1
            print(f"{name} scraper failed: {exc}", file=sys.stderr)

    if failures == len(source_fetchers):
        raise RuntimeError("All fast-tier sources failed to fetch deals")

    return deals


def _store_summary(deals: list[Deal]) -> str:
    counts = {store: 0 for store, _attr in SOURCE_FETCHERS}
    for deal in deals:
        counts[deal.store] = counts.get(deal.store, 0) + 1
    return ", ".join(f"{store}={count}" for store, count in counts.items())


def run() -> int:
    watchlist = load_watchlist()

    try:
        deals = fetch_all_deals(watchlist)
    except Exception as exc:
        print(f"Scraper failed: {exc}", file=sys.stderr)
        return 1

    history = load_price_history(HISTORY_PATH)
    seen_keys = load_seen(SEEN_PATH)
    unverified_watchlist = {**watchlist, "verify_advertised_discount": False}

    candidates: list[ScoredDeal] = []
    new_keys: list[str] = []
    unverified = 0
    for deal in deals:
        key = deal_key(deal)
        already_seen = key in seen_keys
        # Evaluate against history BEFORE this run's own snapshot is recorded,
        # so a price drop compares against prior runs, not against itself.
        scored = None if already_seen else evaluate(deal, watchlist, history)
        if not already_seen and scored is None and evaluate(deal, unverified_watchlist, history):
            unverified += 1
        update_price_history(history, deal)
        if already_seen:
            continue
        new_keys.append(key)
        if scored:
            candidates.append(scored)

    delivered = send_offers(candidates) if candidates else []
    delivered_keys = {deal_key(scored.deal) for scored in delivered}
    pending_keys = {deal_key(scored.deal) for scored in candidates} - delivered_keys

    print(f"Deals per store: {_store_summary(deals)}", file=sys.stderr)
    print(
        f"Scanned {len(deals)} deals, {len(new_keys)} new, {len(candidates)} qualifying, "
        f"{unverified} advertised discounts discarded as unverified",
        file=sys.stderr,
    )
    print(
        f"Telegram: delivered {len(delivered)}/{len(candidates)} individual messages "
        f"({len(pending_keys)} pending retry next run)",
        file=sys.stderr,
    )

    if candidates and not delivered:
        print("Notification failed: no offer could be delivered to Telegram", file=sys.stderr)
        return 1

    # Offers that failed to send stay unseen so the next run retries them.
    mark_seen(SEEN_PATH, seen_keys, [key for key in new_keys if key not in pending_keys])
    save_price_history(HISTORY_PATH, history)
    return 0


def selftest(limit: int = 3) -> int:
    """Send a few real scraped products to Telegram as clearly-labelled test
    messages, to verify photo + formatting + delivery end to end. Touches no
    state files and ignores dedup and verification."""
    watchlist = load_watchlist()
    deals = [deal for deal in fetch_all_deals(watchlist) if deal.image_url]
    deals.sort(key=lambda deal: deal.discount_pct, reverse=True)

    picked: list[Deal] = []
    stores_used: set[str] = set()
    for deal in deals:
        if deal.store not in stores_used:
            stores_used.add(deal.store)
            picked.append(deal)
        if len(picked) == limit:
            break

    offers = [
        ScoredDeal(deal=deal, real_discount_pct=0.0, reasons=["PRUEBA de envio: no es una oferta verificada"])
        for deal in picked
    ]
    delivered = send_offers(offers)
    print(f"Selftest: delivered {len(delivered)}/{len(offers)} test messages", file=sys.stderr)
    return 0 if offers and len(delivered) == len(offers) else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else run())
