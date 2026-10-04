# main_fast.py
import json
import os
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from deal_filter import evaluate
from dedup import deal_key, load_seen, mark_seen
from models import Deal, ScoredDeal
import notifier
from notifier import MAX_PRIORITY_UNVERIFIED_PER_RUN, send_alert, send_offers
from subscribers import process_updates
from price_history import load_price_history, save_price_history, update_price_history
from reports import StoreReport, build_report, format_log, store_transitions, to_json, to_markdown
from sources import health
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
from sources.laikamascotas import fetch_deals as fetch_laikamascotas_deals
from sources.lapolar import fetch_deals as fetch_lapolar_deals
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
from sources.tricot import fetch_deals as fetch_tricot_deals
from sources.tusmascotas import fetch_deals as fetch_tusmascotas_deals
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
    ("lapolar", "fetch_lapolar_deals"),
    ("tricot", "fetch_tricot_deals"),
    ("laikamascotas", "fetch_laikamascotas_deals"),
    ("tusmascotas", "fetch_tusmascotas_deals"),
]
SOURCE_NAMES = [attr for _store, attr in SOURCE_FETCHERS]

# Stores that need a browser and launch one Chromium per keyword. Handed the
# full 31-keyword watchlist they would pay ~30 browser launches each, so they
# get only the queries that match what they sell.
BROWSER_SHOE_STORES = {
    "nike", "converse", "puma", "newbalance", "fila", "skechers",
}
BROWSER_SHOE_KEYWORDS = [
    "zapatillas",
    "zapatilla",
    # priority segments (config/watchlist.json -> priority)
    "zapatillas mujer",
    "zapatillas hombre",
    "zapatillas bebe",
]
# Pharmacies: dermocosmetics first (the priority), then other beauty. Kept to a
# focused list because Salcobrand and Cruz Verde launch one browser per keyword;
# Ahumada reads HTTP so it shares the same list cheaply.
PHARMACY_STORES = {"salcobrand", "cruzverde", "ahumada"}
PHARMACY_KEYWORDS = [
    # priority interest, first so a slow pharmacy cannot time out before it
    "kerastase blond",
    # dermocosmetics
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

# Dedicated pet stores: the phrase queries in the global watchlist ("alimento
# perro") match very little on a WooCommerce search, so they get single-word pet
# terms too.
PET_STORES = {"laikamascotas", "tusmascotas"}
PET_KEYWORDS = [
    "alimento perro",
    "alimento gato",
    "arena gato",
    "alimento",
    "perro",
    "gato",
    "arena",
    "snack",
    "higiene",
    "juguete",
]


def watchlist_for(store: str, watchlist: dict) -> dict:
    if store in BROWSER_SHOE_STORES:
        return {**watchlist, "keywords": BROWSER_SHOE_KEYWORDS}
    if store in PHARMACY_STORES:
        return {**watchlist, "keywords": PHARMACY_KEYWORDS}
    if store in PET_STORES:
        return {**watchlist, "keywords": PET_KEYWORDS}
    return watchlist

SEEN_PATH = Path(__file__).parent / "data" / "seen_items.json"
HISTORY_PATH = Path(__file__).parent / "data" / "price_history.json"
BUDGET_PATH = Path(__file__).parent / "data" / "alert_budget.json"
WATCHLIST_PATH = Path(__file__).parent / "config" / "watchlist.json"
# Why the last run failed, in one short text. The workflow's failure alert reads it
# so the Telegram message says what happened instead of only "the pipeline failed".
RUN_STATUS_PATH = Path(os.environ.get("RUN_STATUS_FILE") or Path(__file__).parent / "run_status.txt")
# A whole scan finishes in ~6 minutes; give any single store generous room but
# stop waiting forever, so one hung store cannot stall the run or the lock.
# Falabella (20k products, no partial result when it overruns) went from ~240 s to over 420 s on
# 2026-10-04 and lost whole scans, so the ceiling is 10 minutes (the job itself allows 20).
SOURCE_TIMEOUT_SECONDS = 600
# Ceiling on unconfirmed advertised discounts sent per day (across all runs), on
# top of the per-run cap in notifier. Resets at UTC midnight.
DAILY_UNVERIFIED_CAP = 300
# Most unconfirmed offers one run may send. Together with the pacing below this keeps the
# chat readable even when a scan finds thousands of candidates.
UNVERIFIED_PER_RUN = 15
# Hours of the daily cap available from the start of the (UTC) day, so alerts begin right away.
PACING_HEAD_START_MINUTES = 120
# Same idea for the priority interests, which have a quota of their own
# (overridable in the watchlist's "priority" block).
DEFAULT_PRIORITY_DAILY_CAP = 800


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def quota_room(cap: int, used: int, now: datetime) -> int:
    """How many more unconfirmed offers may go out right now.

    The daily cap is released gradually through the UTC day (with a head start), instead of
    being spendable all at once: before this, the whole cap was used up in the first hours
    of the day and nothing arrived for the rest of it."""
    minutes = now.hour * 60 + now.minute
    released = -(-cap * (minutes + PACING_HEAD_START_MINUTES) // 1440)  # ceil
    return max(0, min(cap - used, min(released, cap) - used))


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


def scan_stores(watchlist: dict) -> tuple[list[Deal], list[StoreReport]]:
    """Scan every enabled store at the same time and report how each one did.

    Returns the deals plus one StoreReport per registered store (disabled ones
    included). Raises RuntimeError, with ``.reports`` attached, when every
    enabled store failed."""
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

    health.drain()  # discard events left over from anything that ran before this scan

    def run_source(source):
        name, fetch = source
        began = time.time()
        try:
            return name, fetch(watchlist_for(name, watchlist)), None, time.time() - began
        except Exception as exc:
            return name, [], exc, time.time() - began

    # Stores are independent and network-bound: scan them at the same time, but
    # never wait forever. A store that overruns is treated as a failure and the
    # rest of the run proceeds with whatever finished.
    executor = ThreadPoolExecutor(max_workers=len(source_fetchers))
    futures = {executor.submit(run_source, source): source[0] for source in source_fetchers}
    done, pending = wait(futures, timeout=SOURCE_TIMEOUT_SECONDS)
    events = health.drain()

    def store_events(store: str) -> list[dict]:
        return [event for event in events if event["store"] == store]

    deals: list[Deal] = []
    failures = 0
    by_store: dict[str, StoreReport] = {}
    for future in done:
        name, found, error, seconds = future.result()
        if error is not None:
            failures += 1
            print(f"{name} scraper failed: {error}", file=sys.stderr)
        deals.extend(found)
        by_store[name] = build_report(name, len(found), seconds, store_events(name), raised=error)
    for future in pending:
        failures += 1
        future.cancel()
        name = futures[future]
        print(f"{name} scraper timed out after {SOURCE_TIMEOUT_SECONDS}s", file=sys.stderr)
        by_store[name] = build_report(
            name, 0, SOURCE_TIMEOUT_SECONDS, store_events(name), timed_out=True
        )
    executor.shutdown(wait=False, cancel_futures=True)

    reports = [
        by_store.get(store) or StoreReport(store=store, status="disabled")
        for store, _attr in SOURCE_FETCHERS
    ]

    if failures == len(source_fetchers):
        error = RuntimeError("All fast-tier sources failed to fetch deals")
        error.reports = reports
        raise error

    return deals, reports


def fetch_all_deals(watchlist: dict) -> list[Deal]:
    return scan_stores(watchlist)[0]


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


def write_step_summary(markdown: str) -> None:
    """Append to the GitHub Actions run summary page (a no-op outside Actions)."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    except OSError as exc:
        print(f"Could not write the run summary: {exc}", file=sys.stderr)


def clear_failure_reason() -> None:
    try:
        RUN_STATUS_PATH.unlink()
    except OSError:
        pass


def record_failure(reason: str, reports: list[StoreReport] | None = None) -> int:
    """Print why the run failed, keep the reason for the failure alert and put it
    on the run summary. Returns the process exit code (1)."""
    print(reason, file=sys.stderr)
    try:
        RUN_STATUS_PATH.write_text(reason[:400], encoding="utf-8")
    except OSError as exc:
        print(f"Could not write the failure reason: {exc}", file=sys.stderr)
    parts = ["### ❌ Escaneo fallido", "", reason]
    if reports:
        parts += ["", "### Tiendas", "", to_markdown(reports)]
    write_step_summary("\n".join(parts))
    return 1


def collect_errors(reports: list[StoreReport] | None, limit: int = 10) -> list[str]:
    errors: list[str] = []
    for report in reports or []:
        messages = report.errors or ([report.detail] if report.detail and report.status != "ok" else [])
        errors.extend(" ".join(message.split())[:200] for message in messages)
    return errors[:limit]


def announce_store_health(mirror, reports: list[StoreReport]) -> None:
    """Telegram note when a store has failed two scans in a row (once, with the
    reason) and when it comes back. Needs the previous runs from Supabase, so it
    is skipped when they cannot be read; never fatal."""
    try:
        previous = mirror.recent_store_status(2)
        down, recovered = store_transitions({r.store: r.status for r in reports}, previous)
        if not down and not recovered:
            return
        by_store = {r.store: r for r in reports}
        lines = []
        for store in down:
            report = by_store[store]
            reason = report.detail or (report.errors[0] if report.errors else "sin detalle")
            lines.append(f"🔴 {store}: sin datos en 2 escaneos seguidos ({report.status}). {reason[:160]}")
        lines += [f"🟢 {store}: recuperada" for store in recovered]
        if not send_alert("\n".join(lines)):
            print("The store health alert could not be sent to Telegram", file=sys.stderr)
    except Exception as exc:
        print(f"Store health check skipped: {exc}", file=sys.stderr)


def refresh_subscribers() -> list[int]:
    """Register /start and /stop received since the last run and return the active chats.

    Needs Supabase (that is where subscribers live); without it, or when it fails, the offers
    still go out to the configured chats."""
    store = SupabaseSync.from_env()
    if store is None:
        return []
    counts = process_updates(store)
    try:
        subscribers = store.active_subscribers()
    except Exception as exc:
        log_failure("read subscribers", exc)
        return []
    print(
        f"Subscribers: {len(subscribers)} active (+{counts['subscribed']} /start, -{counts['unsubscribed']} /stop)",
        file=sys.stderr,
    )
    return subscribers


def deactivate_unreachable(subscribers: list[int]) -> None:
    """Subscribers who blocked the bot (Telegram answered 403) stop being messaged."""
    gone = [chat for chat in subscribers if str(chat) in notifier.UNREACHABLE_CHATS]
    store = SupabaseSync.from_env() if gone else None
    if not store:
        return
    try:
        store.set_subscribers_active(gone, False)
        print(f"Subscribers: {len(gone)} blocked the bot and were deactivated", file=sys.stderr)
    except Exception as exc:
        log_failure("deactivate subscribers", exc)


def mirror_to_supabase(
    deals: list[Deal],
    delivered: list[ScoredDeal],
    qualifying: int,
    new_deals: int,
    unverified: int,
    started: float,
    reports: list[StoreReport] | None = None,
    quota: dict | None = None,
) -> str:
    """Copy this run's results into Supabase when it is configured and return a
    one-line status for the log and the run summary. Never fatal: the JSON files
    stay the source of truth for decisions, so a database outage must not stop
    alerts."""
    mirror = SupabaseSync.from_env()
    if mirror is None:
        return "Supabase: no configurado (solo archivos JSON)"
    try:
        totals = mirror.sync_scan(deals)
        mirror.record_sent(delivered)
        if reports:
            announce_store_health(mirror, reports)  # compares with the runs BEFORE this one
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
                "store_status": to_json(reports) if reports else None,
                "errors": collect_errors(reports),
                "quota": quota,
            }
        )
        # Rebuild the public feed so the web reflects this run. A refresh failure
        # is caught below like any other sync error and never aborts the scan.
        mirror.refresh_feed()
        line = (
            f"Supabase: {totals['received']} products received, {totals['new']} new, "
            f"{totals['points']} new price points, {len(delivered)} offers recorded"
        )
        print(line, file=sys.stderr)
        return line
    except Exception as exc:
        log_failure("sync", exc)
        return f"Supabase: ERROR al sincronizar ({str(exc)[:160]}). Los JSON no se ven afectados"


def build_summary(
    deals: list[Deal],
    reports: list[StoreReport],
    new_deals: int,
    qualifying: list[ScoredDeal],
    delivered: list[ScoredDeal],
    unverified_discarded: int,
    budget_used: int,
    telegram_line: str,
    supabase_line: str,
    seconds: float,
) -> str:
    unverified = sum(1 for c in qualifying if not c.advertised_confirmed)
    lines = [
        "### ✅ Escaneo completado",
        "",
        f"- **Productos leídos:** {len(deals)} ({new_deals} nuevos)",
        f"- **Ofertas calificadas:** {len(qualifying)} ({unverified} sin verificar; "
        f"{unverified_discarded} descuentos descartados)",
        f"- **Telegram:** {telegram_line}",
        f"- **Cupo diario de no verificadas:** {budget_used}/{DAILY_UNVERIFIED_CAP}",
        f"- **{supabase_line}**" if supabase_line.startswith("Supabase: ERROR") else f"- {supabase_line}",
        f"- **Duración:** {seconds:.0f}s",
        "",
        "### Tiendas",
        "",
        to_markdown(reports),
    ]
    errors = collect_errors(reports, limit=10)
    if errors:
        lines += ["", "### Primeros errores", ""] + [f"- `{error}`" for error in errors]
    return "\n".join(lines)


def run() -> int:
    started = time.time()
    clear_failure_reason()
    watchlist = load_watchlist()

    try:
        deals, reports = scan_stores(watchlist)
    except Exception as exc:
        return record_failure(f"Scraper failed: {exc}", getattr(exc, "reports", None))

    print(format_log(reports), file=sys.stderr)

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
    now_utc = utc_now()
    today = now_utc.date().isoformat()
    budget = load_budget(BUDGET_PATH, today)
    unverified_room = min(
        UNVERIFIED_PER_RUN, quota_room(DAILY_UNVERIFIED_CAP, budget.get("unverified", 0), now_utc)
    )
    priority_config = watchlist.get("priority") or {}
    priority_room = quota_room(
        priority_config.get("daily_cap", DEFAULT_PRIORITY_DAILY_CAP), budget.get("priority_unverified", 0), now_utc
    )
    priority_limit = min(
        priority_config.get("max_per_run", MAX_PRIORITY_UNVERIFIED_PER_RUN), priority_room
    )
    subscribers = refresh_subscribers()
    delivered = (
        send_offers(
            candidates,
            alerts=watchlist.get("alerts"),
            max_unverified=unverified_room,
            max_priority_unverified=priority_limit,
            subscriber_chat_ids=subscribers,
        )
        if candidates
        else []
    )
    deactivate_unreachable(subscribers)
    delivered_keys: set[str] = set()
    for scored in delivered:
        key = deal_key(scored.deal)
        delivered_keys.add(key)
        delivered_keys.update(aliases.get(key, []))
    pending_keys = {deal_key(scored.deal) for scored in candidates} - delivered_keys

    # Was anything eligible to be sent at all? Verified offers always are; the
    # unconfirmed ones only while the daily quota has room.
    unverified_candidates = sum(1 for c in candidates if not c.advertised_confirmed)
    attempted = (
        any(c.advertised_confirmed for c in candidates)
        or (unverified_room > 0 and any(not c.advertised_confirmed and not c.priority for c in candidates))
        or (priority_limit > 0 and any(not c.advertised_confirmed and c.priority for c in candidates))
    )
    quota_limited = bool(candidates) and not attempted

    print(f"Deals per store: {_store_summary(deals, watchlist.get('disabled_stores'))}", file=sys.stderr)
    print(
        f"Scanned {len(deals)} deals, {len(new_keys)} new, {len(candidates)} qualifying "
        f"({unverified_candidates} unverified), "
        f"{unverified} advertised discounts discarded as unverified",
        file=sys.stderr,
    )
    if quota_limited:
        telegram_line = (
            f"nothing sent: {unverified_candidates} unverified candidates are waiting but the daily "
            f"quotas are spent (generic {budget.get('unverified', 0)}/{DAILY_UNVERIFIED_CAP}, priority "
            f"{budget.get('priority_unverified', 0)}/{priority_config.get('daily_cap', DEFAULT_PRIORITY_DAILY_CAP)}) "
            f"and there are no verified offers"
        )
    else:
        priority_delivered = sum(1 for scored in delivered if scored.priority)
        telegram_line = (
            f"delivered {len(delivered)}/{len(candidates)} individual messages, "
            f"{priority_delivered} of them priority ({len(pending_keys)} pending retry next run)"
        )
    print(f"Telegram: {telegram_line}", file=sys.stderr)

    # Only a real delivery failure is an error: some offer was eligible to be sent
    # and none got through. Candidates that were never sendable (only unverified
    # ones while the daily/per-run quota is spent) are not a Telegram failure, and
    # returning here would skip saving history, the budget and the Supabase mirror.
    if candidates and attempted and not delivered:
        return record_failure("Notification failed: no offer could be delivered to Telegram", reports)

    # Only delivered offers are remembered: with thousands of products per scan,
    # recording every non-qualifying one would bloat the file for no benefit
    # (they are cheap to re-evaluate). Undelivered offers stay unseen so the
    # next run retries them.
    mark_seen(SEEN_PATH, seen_keys, sorted(delivered_keys))
    save_price_history(HISTORY_PATH, history)
    budget["unverified"] = budget.get("unverified", 0) + sum(
        1 for scored in delivered if not scored.advertised_confirmed and not scored.priority
    )
    budget["priority_unverified"] = budget.get("priority_unverified", 0) + sum(
        1 for scored in delivered if not scored.advertised_confirmed and scored.priority
    )
    save_budget(BUDGET_PATH, budget)

    quota = {
        "unverified_room": unverified_room,
        "priority_room": priority_room,
        "eligible": attempted,
        "delivered": len(delivered),
        "quota_limited": quota_limited,
    }
    supabase_line = mirror_to_supabase(
        deals, delivered, len(candidates), len(new_keys), unverified, started, reports=reports, quota=quota
    )
    write_step_summary(
        build_summary(
            deals, reports, len(new_keys), candidates, delivered, unverified,
            budget.get("unverified", 0), telegram_line, supabase_line, time.time() - started,
        )
    )
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        return selftest() if "--selftest" in argv else run()
    except Exception as exc:
        # Nothing handled it: leave the reason where the failure alert can read it,
        # then let the traceback reach the log as usual.
        record_failure(f"Excepción no controlada: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    sys.exit(main())
