"""One-time import of data/price_history.json and data/seen_items.json into Supabase.

Safe to re-run: every insert ignores rows that already exist. Needs SUPABASE_URL
and SUPABASE_SERVICE_KEY (in CI they come from the GitHub environment secrets).
Run it from the Actions tab: "Run workflow" with `migrate` ticked.
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from supabase_sync import SupabaseError, SupabaseSync

DATA_DIR = Path(__file__).parent / "data"

load_dotenv(Path(__file__).parent / ".env")


def migrate(mirror: SupabaseSync, history: dict, seen: list[str]) -> bool:
    imported = mirror.import_history(history)
    sent = mirror.import_seen(seen)
    counts = {
        "offer_products": mirror.count("offer_products"),
        "offer_price_points": mirror.count("offer_price_points"),
        "offer_sent": mirror.count("offer_sent"),
    }
    print(f"JSON  : {imported['products']} products, {imported['points']} price points, {sent} sent keys")
    print(f"Supabase now holds: {counts}")

    # The database may hold more (live scans), never less than what we imported.
    ok = (
        counts["offer_products"] >= imported["products"]
        and counts["offer_price_points"] >= imported["points"]
        and counts["offer_sent"] >= sent
    )
    print("Migration verified" if ok else "Migration INCOMPLETE: counts are lower than the JSON files")
    return ok


def main() -> int:
    mirror = SupabaseSync.from_env()
    if mirror is None:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY are not set", file=sys.stderr)
        return 1
    history = json.loads((DATA_DIR / "price_history.json").read_text(encoding="utf-8"))
    seen = json.loads((DATA_DIR / "seen_items.json").read_text(encoding="utf-8"))
    try:
        return 0 if migrate(mirror, history, seen) else 1
    except SupabaseError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
