import json
from pathlib import Path

from models import Deal

MAX_SNAPSHOTS = 30


def load_price_history(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def update_price_history(history: dict, deal: Deal) -> None:
    snapshots = history.setdefault(deal.id, [])
    if snapshots and snapshots[-1]["price"] == deal.price:
        return
    snapshots.append({"date": deal.scraped_at[:10], "price": deal.price})
    if len(snapshots) > MAX_SNAPSHOTS:
        del snapshots[: len(snapshots) - MAX_SNAPSHOTS]


def save_price_history(path: Path, history: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(history, f, separators=(",", ":"), sort_keys=True)
