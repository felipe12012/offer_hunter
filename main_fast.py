# main_fast.py
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from deal_filter import evaluate
from dedup import deal_key, load_seen, mark_seen
from models import Deal
from notifier import send_digest
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


def run() -> int:
    watchlist = load_watchlist()

    try:
        deals = fetch_all_deals(watchlist)
    except Exception as exc:
        print(f"Scraper failed: {exc}", file=sys.stderr)
        return 1

    history = load_price_history(HISTORY_PATH)
    seen_keys = load_seen(SEEN_PATH)

    candidates = []
    new_keys = []
    for deal in deals:
        key = deal_key(deal)
        already_seen = key in seen_keys
        # Evaluate against history BEFORE this run's own snapshot is recorded,
        # so a price drop compares against prior runs, not against itself.
        scored = None if already_seen else evaluate(deal, watchlist, history)
        update_price_history(history, deal)
        if already_seen:
            continue
        new_keys.append(key)
        if scored:
            candidates.append(scored)

    print(
        f"Scanned {len(deals)} deals, {len(new_keys)} new, {len(candidates)} qualifying",
        file=sys.stderr,
    )
    try:
        sent = send_digest(candidates)
        print(f"Telegram digest sent: {bool(sent)}", file=sys.stderr)
    except Exception as exc:
        print(f"Notification failed: {exc}", file=sys.stderr)
        return 1

    mark_seen(SEEN_PATH, seen_keys, new_keys)
    save_price_history(HISTORY_PATH, history)
    return 0


if __name__ == "__main__":
    sys.exit(run())
