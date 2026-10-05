"""Merge the state files of two scans that ran at the same time (the HTTP tier and the browser tier).

Both workflows start from the same commit, change data/*.json and commit them. A plain `git rebase` cannot
combine that (price_history.json is a single line, so every concurrent change conflicts), and the second
push was lost or failed. Here the rules are explicit:

* seen_items.json   union of both sets;
* price_history.json per product, the union of both snapshot lists (by date and price), newest 30 kept;
* alert_budget.json  the same UTC day: the larger counter of each kind (conservative: never lets more
                     through than either scan counted); different days: the later day wins.

    python scripts/merge_state.py <dir with this run's copies>

The files in data/ (the other scan's, freshly checked out) are replaced by the merge.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from price_history import MAX_SNAPSHOTS  # noqa: E402

FILES = ("seen_items.json", "price_history.json", "alert_budget.json")


def merge_seen(ours: list, theirs: list) -> list:
    return sorted(set(ours) | set(theirs))


def merge_history(ours: dict, theirs: dict) -> dict:
    merged: dict[str, list] = {}
    for product_id in ours.keys() | theirs.keys():
        seen: set[tuple[str, int]] = set()
        snapshots = []
        for snapshot in [*theirs.get(product_id, []), *ours.get(product_id, [])]:
            key = (snapshot["date"], snapshot["price"])
            if key not in seen:
                seen.add(key)
                snapshots.append(snapshot)
        snapshots.sort(key=lambda s: s["date"])  # stable: same-day entries keep their order
        merged[product_id] = snapshots[-MAX_SNAPSHOTS:]
    return merged


def merge_budget(ours: dict, theirs: dict) -> dict:
    if not ours:
        return theirs
    if not theirs:
        return ours
    if ours.get("date") != theirs.get("date"):
        return ours if ours.get("date", "") > theirs.get("date", "") else theirs
    merged = dict(theirs)
    for key, value in ours.items():
        if isinstance(value, (int, float)) and isinstance(theirs.get(key), (int, float)):
            merged[key] = max(value, theirs[key])
        else:
            merged.setdefault(key, value)
    return merged


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def merge_files(ours_dir: Path, data_dir: Path) -> None:
    ours_seen = _load(ours_dir / "seen_items.json", [])
    theirs_seen = _load(data_dir / "seen_items.json", [])
    (data_dir / "seen_items.json").write_text(json.dumps(merge_seen(ours_seen, theirs_seen), indent=2), encoding="utf-8")

    merged_history = merge_history(_load(ours_dir / "price_history.json", {}), _load(data_dir / "price_history.json", {}))
    (data_dir / "price_history.json").write_text(
        json.dumps(merged_history, separators=(",", ":"), sort_keys=True), encoding="utf-8"
    )

    merged_budget = merge_budget(_load(ours_dir / "alert_budget.json", {}), _load(data_dir / "alert_budget.json", {}))
    (data_dir / "alert_budget.json").write_text(json.dumps(merged_budget), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    merge_files(Path(argv[1]), ROOT / "data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
