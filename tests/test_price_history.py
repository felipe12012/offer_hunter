# tests/test_price_history.py
import json
from pathlib import Path

from models import Deal
from price_history import load_price_history, save_price_history, update_price_history, MAX_SNAPSHOTS


def make_deal(price: int, scraped_at: str = "2026-10-01T12:00:00+00:00") -> Deal:
    return Deal(
        id="sodimac:123",
        title="Taladro percutor",
        url="https://www.sodimac.cl/sodimac-cl/product/123/taladro/123/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=price,
        discount_pct=0.0,
        scraped_at=scraped_at,
    )


def test_load_price_history_missing_file_returns_empty_dict(tmp_path: Path):
    path = tmp_path / "price_history.json"
    assert load_price_history(path) == {}


def test_update_price_history_adds_first_snapshot():
    history = {}
    update_price_history(history, make_deal(29990))
    assert history["sodimac:123"] == [{"date": "2026-10-01", "price": 29990}]


def test_update_price_history_skips_duplicate_unchanged_price():
    history = {"sodimac:123": [{"date": "2026-09-20", "price": 29990}]}
    update_price_history(history, make_deal(29990, scraped_at="2026-10-01T12:00:00+00:00"))
    assert history["sodimac:123"] == [{"date": "2026-09-20", "price": 29990}]


def test_update_price_history_appends_when_price_changes():
    history = {"sodimac:123": [{"date": "2026-09-20", "price": 29990}]}
    update_price_history(history, make_deal(19990, scraped_at="2026-10-01T12:00:00+00:00"))
    assert history["sodimac:123"] == [
        {"date": "2026-09-20", "price": 29990},
        {"date": "2026-10-01", "price": 19990},
    ]


def test_update_price_history_truncates_to_max_snapshots():
    history = {"sodimac:123": [{"date": f"2026-01-{i:02d}", "price": i} for i in range(1, MAX_SNAPSHOTS + 1)]}
    update_price_history(history, make_deal(MAX_SNAPSHOTS + 1, scraped_at="2026-10-01T12:00:00+00:00"))
    assert len(history["sodimac:123"]) == MAX_SNAPSHOTS
    assert history["sodimac:123"][0]["price"] == 2
    assert history["sodimac:123"][-1]["price"] == MAX_SNAPSHOTS + 1


def test_save_price_history_round_trips(tmp_path: Path):
    path = tmp_path / "price_history.json"
    history = {"sodimac:123": [{"date": "2026-10-01", "price": 29990}]}
    save_price_history(path, history)
    assert json.loads(path.read_text(encoding="utf-8")) == history
    assert load_price_history(path) == history
