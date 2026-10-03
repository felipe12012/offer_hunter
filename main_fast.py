# main_fast.py
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from deal_filter import evaluate
from dedup import deal_key, load_seen, mark_seen
from models import Deal, ScoredDeal
from notifier import send_offers
from price_history import load_price_history, save_price_history, update_price_history
from supabase_sync import SupabaseSync, log_failure
from sources.ahumada import fetch_deals as fetch_ahumada_deals
from sources.asics import fetch_deals as fetch_asics_deals
from sources.converse import fetch_deals as fetch_converse_deals
from sources.crocs import fetch_deals as fetch_crocs_deals
from sources.cruzverde import fetch_deals as fetch_cruzverde_deals
from sources.falabella import fetch_deals as fetch_falabella_deals
from sources.fila import fetch_deals as fetch_fila_deals
from sources.hites import fetch_deals as fetch_hites_deals
from sources.hushpuppies import fetch_deals as fetch_hushpuppies_deals
from sources.merrell import fetch_deals as fetch_merrell_deals
from sources.newbalance import fetch_deals as fetch_newbalance_deals
from sources.nike import fetch_deals as fetch_nike_deals
from sources.paris import fetch_deals as fetch_paris_deals
from sources.puma import fetch_deals as fetch_puma_deals
from sources.reebok import fetch_deals as fetch_reebok_deals
from sources.ripley import fetch_deals as fetch_ripley_deals
from sources.salcobrand import fetch_deals as fetch_salcobrand_deals
from sources.salomon import fetch_deals as fetch_salomon_deals
from sources.skechers import fetch_deals as fetch_skechers_deals
from sources.sodimac import fetch_deals as fetch_sodimac_deals
from sources.tottus import fetch_deals as fetch_tottus_deals
from sources.vans import fetch_deals as fetch_vans_deals

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
    ("vans", "fetch_vans_deals"),
    ("crocs", "fetch_crocs_deals"),
    ("merrell", "fetch_merrell_deals"),
    ("salomon", "fetch_salomon_deals"),
    ("hushpuppies", "fetch_hushpuppies_deals"),
    ("asics", "fetch_asics_deals"),
    ("reebok", "fetch_reebok_deals"),
    ("nike", "fetch_nike_deals"),
    ("converse", "fetch_converse_deals"),
    ("puma", "fetch_puma_deals"),
    ("newbalance", "fetch_newbalance_deals"),
    ("fila", "fetch_fila_deals"),
    ("skechers", "fetch_skechers_deals"),
    ("salcobrand", "fetch_salcobrand_deals"),
    ("cruzverde", "fetch_cruzverde_deals"),
    ("ahumada", "fetch_ahumada_deals"),
]
SOURCE_NAMES = [attr for _store, attr in SOURCE_FETCHERS]

# Stores that need a browser and launch one Chromium per keyword. Handed the
# full 31-keyword watchlist they would pay ~30 browser launches each, so they
# get only the queries that match what they sell.
BROWSER_SHOE_STORES = {
    "nike", "converse", "puma", "newbalance", "fila", "skechers",
}
BROWSER_SHOE_KEYWORDS = ["zapatillas", "zapatilla"]
# Pharmacies: dermocosmetics first (the priority), then other beauty. Kept to a
# focused list because Salcobrand and Cruz Verde launch one browser per keyword;
# Ahumada reads HTTP so it shares the same list cheaply.
PHARMACY_STORES = {"salcobrand", "cruzverde", "ahumada"}
PHARMACY_KEYWORDS = [
    # dermocosmetics (priority)
    "dermocosmetica",
    "crema facial",
    "facial",
    "hidratante",
    "protector solar",
    "serum",
    "agua micelar",
    "acido hialuronico",
    "vitamina c",
    "retinol",
    "la roche-posay",
    "cerave",
    "vichy",
    "eucerin",
    "avene",
    "isdin",
    # other beauty (not the only thing)
    "kerastase",
    "redken",
    "perfume",
    "maquillaje",
]


def watchlist_for(store: str, watchlist: dict) -> dict:
    if store in BROWSER_SHOE_STORES:
        return {**watchlist, "keywords": BROWSER_SHOE_KEYWORDS}
    if store in PHARMACY_STORES:
        return {**watchlist, "keywords": PHARMACY_KEYWORDS}
    return watchlist

SEEN_PATH = Path(__file__).parent / "data" / "seen_items.json"
HISTORY_PATH = Path(__file__).parent / "data" / "price_history.json"
BUDGET_PATH = Path(__file__).parent / "data" / "alert_budget.json"
WATCHLIST_PATH = Path(__file__).parent / "config" / "watchlist.json"
# A whole scan finishes in ~6 minutes; give any single store generous room but
# stop waiting forever, so one hung store cannot stall the run or the lock.
SOURCE_TIMEOUT_SECONDS = 420
# Ceiling on unconfirmed advertised discounts sent per day (across all runs), on
# top of the per-run cap in notifier. Resets at UTC midnight.
DAILY_UNVERIFIED_CAP = 60


def load_budget(path: Path, today: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or data.get("date") != today:
        return {"date": today, "unverified": 0}
    return data


def save_budget(path: Path, budget: dict) -> None:
    path.write_text(json.dumps(budget), encoding="utf-8")

load_dotenv(Path(__file__).parent / ".env")


def load_watchlist() -> dict:
    with WATCHLIST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_all_deals(watchlist: dict) -> list[Deal]:
    # Resolved on every call so a monkeypatched module attribute is picked up —
    # same reasoning as job-hunter-agent/main.py.
    disabled = {name.lower() for name in watchlist.get("disabled_stores", [])}
    source_fetchers = [
        (store, globals()[attr]) for store, attr in SOURCE_FETCHERS if store not in disabled
    ]
    if disabled:
        print(f"Skipping disabled stores: {', '.join(sorted(disabled))}", file=sys.stderr)
    if not source_fetchers:
        raise RuntimeError("Every store is disabled in config/watchlist.json")

    def run_source(source):
        name, fetch = source
        try:
            return name, fetch(watchlist_for(name, watchlist)), None
        except Exception as exc:
            return name, [], exc

    # Stores are independent and network-bound: scan them at the same time, but
    # never wait forever. A store that overruns is treated as a failure and the
    # rest of the run proceeds with whatever finished.
    executor = ThreadPoolExecutor(max_workers=len(source_fetchers))
    futures = {executor.submit(run_source, source): source[0] for source in source_fetchers}
    done, pending = wait(futures, timeout=SOURCE_TIMEOUT_SECONDS)

    deals: list[Deal] = []
    failures = 0
    for future in done:
        name, found, error = future.result()
        if error is not None:
            failures += 1
            print(f"{name} scraper failed: {error}", file=sys.stderr)
        deals.extend(found)
    for future in pending:
        failures += 1
        future.cancel()
        print(
            f"{futures[future]} scraper timed out after {SOURCE_TIMEOUT_SECONDS}s",
            file=sys.stderr,
        )
    executor.shutdown(wait=False, cancel_futures=True)

    if failures == len(source_fetchers):
        raise RuntimeError("All fast-tier sources failed to fetch deals")

    return deals


def dedupe_cross_store(candidates: list[ScoredDeal]) -> tuple[list[ScoredDeal], dict[str, list[str]]]:
    """Falabella and Sodimac share a marketplace catalogue, so one product can
    qualify on both at the same price. Keep one offer per (product id, price)
    and remember the other stores' keys so they are not re-sent next run."""
    unique: dict[tuple[str, int], ScoredDeal] = {}
    aliases: dict[str, list[str]] = {}
    for scored in candidates:
        identity = (scored.deal.id.split(":", 1)[-1], scored.deal.price)
        key = deal_key(scored.deal)
        if identity in unique:
            aliases[deal_key(unique[identity].deal)].append(key)
        else:
            unique[identity] = scored
            aliases[key] = []
    return list(unique.values()), aliases


def _store_summary(deals: list[Deal], disabled: list[str] | None = None) -> str:
    skipped = {name.lower() for name in disabled or []}
    counts = {store: 0 for store, _attr in SOURCE_FETCHERS if store not in skipped}
    for deal in deals:
        counts[deal.store] = counts.get(deal.store, 0) + 1
    return ", ".join(f"{store}={count}" for store, count in counts.items())


def mirror_to_supabase(
    deals: list[Deal],
    delivered: list[ScoredDeal],
    qualifying: int,
    new_deals: int,
    unverified: int,
    started: float,
) -> None:
    """Copy this run's results into Supabase when it is configured. Never fatal:
    the JSON files stay the source of truth for decisions, so a database outage
    must not stop alerts."""
    mirror = SupabaseSync.from_env()
    if mirror is None:
        return
    try:
        totals = mirror.sync_scan(deals)
        mirror.record_sent(delivered)
        mirror.record_run(
            {
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "scanned": len(deals),
                "new_deals": new_deals,
                "qualifying": qualifying,
                "delivered": len(delivered),
                "unverified": unverified,
                "per_store": dict(Counter(deal.store for deal in deals)),
                "duration_seconds": round(time.time() - started, 1),
            }
        )
        print(
            f"Supabase: {totals['received']} products received, {totals['new']} new, "
            f"{totals['points']} new price points, {len(delivered)} offers recorded",
            file=sys.stderr,
        )
    except Exception as exc:
        log_failure("sync", exc)


def run() -> int:
    started = time.time()
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

    candidates, aliases = dedupe_cross_store(candidates)
    today = datetime.now(timezone.utc).date().isoformat()
    budget = load_budget(BUDGET_PATH, today)
    unverified_room = max(0, DAILY_UNVERIFIED_CAP - budget.get("unverified", 0))
    delivered = (
        send_offers(candidates, alerts=watchlist.get("alerts"), max_unverified=unverified_room)
        if candidates
        else []
    )
    delivered_keys: set[str] = set()
    for scored in delivered:
        key = deal_key(scored.deal)
        delivered_keys.add(key)
        delivered_keys.update(aliases.get(key, []))
    pending_keys = {deal_key(scored.deal) for scored in candidates} - delivered_keys

    print(f"Deals per store: {_store_summary(deals, watchlist.get("disabled_stores"))}", file=sys.stderr)
    print(
        f"Scanned {len(deals)} deals, {len(new_keys)} new, {len(candidates)} qualifying "
        f"({sum(1 for c in candidates if not c.advertised_confirmed)} unverified), "
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

    # Only delivered offers are remembered: with thousands of products per scan,
    # recording every non-qualifying one would bloat the file for no benefit
    # (they are cheap to re-evaluate). Undelivered offers stay unseen so the
    # next run retries them.
    mark_seen(SEEN_PATH, seen_keys, sorted(delivered_keys))
    save_price_history(HISTORY_PATH, history)
    budget["unverified"] = budget.get("unverified", 0) + sum(
        1 for scored in delivered if not scored.advertised_confirmed
    )
    save_budget(BUDGET_PATH, budget)
    mirror_to_supabase(deals, delivered, len(candidates), len(new_keys), unverified, started)
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
    if offers:
        # Make the first one a simulated 85% alert so the test also exercises
        # the big-discount path (alert chat/channel, loud header, warning).
        first = offers[0]
        offers[0] = ScoredDeal(
            deal=first.deal,
            real_discount_pct=0.0,
            reasons=["PRUEBA de alerta grande (85% simulado): debe llegar al canal de alertas"],
            verified_pct=85.0,
        )
    delivered = send_offers(offers, alerts=watchlist.get("alerts"))
    print(f"Selftest: delivered {len(delivered)}/{len(offers)} test messages", file=sys.stderr)
    return 0 if offers and len(delivered) == len(offers) else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else run())
