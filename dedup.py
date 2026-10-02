import json
from pathlib import Path

from models import Deal


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8") as f:
        return set(json.load(f))


def deal_key(deal: Deal) -> str:
    return f"{deal.id}:{deal.price}"


def filter_unseen(deals: list[Deal], seen_keys: set[str]) -> list[Deal]:
    return [deal for deal in deals if deal_key(deal) not in seen_keys]


def mark_seen(path: Path, seen_keys: set[str], new_keys: list[str]) -> None:
    updated = seen_keys | set(new_keys)
    with path.open("w", encoding="utf-8") as f:
        json.dump(sorted(updated), f, indent=2)
