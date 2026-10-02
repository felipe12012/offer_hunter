# tests/test_dedup.py
import json
from pathlib import Path

from dedup import load_seen, deal_key, filter_unseen, mark_seen
from models import Deal


def make_deal(deal_id: str, price: int) -> Deal:
    return Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://www.sodimac.cl/sodimac-cl/product/{deal_id}/taladro/{deal_id}/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=price,
        discount_pct=0.0,
        scraped_at="2026-10-01T12:00:00+00:00",
    )


def test_load_seen_missing_file_returns_empty_set(tmp_path: Path):
    path = tmp_path / "seen_items.json"
    assert load_seen(path) == set()


def test_load_seen_reads_existing_keys(tmp_path: Path):
    path = tmp_path / "seen_items.json"
    path.write_text(json.dumps(["sodimac:123:29990"]), encoding="utf-8")
    assert load_seen(path) == {"sodimac:123:29990"}


def test_deal_key_combines_id_and_price():
    deal = make_deal("sodimac:123", 29990)
    assert deal_key(deal) == "sodimac:123:29990"


def test_filter_unseen_drops_known_id_price_pairs():
    deals = [make_deal("sodimac:123", 29990), make_deal("sodimac:456", 9990)]
    seen = {"sodimac:123:29990"}
    result = filter_unseen(deals, seen)
    assert [d.id for d in result] == ["sodimac:456"]


def test_filter_unseen_keeps_same_id_at_new_price():
    deals = [make_deal("sodimac:123", 19990)]
    seen = {"sodimac:123:29990"}
    result = filter_unseen(deals, seen)
    assert len(result) == 1


def test_mark_seen_persists_union_of_keys(tmp_path: Path):
    path = tmp_path / "seen_items.json"
    path.write_text(json.dumps(["sodimac:123:29990"]), encoding="utf-8")
    mark_seen(path, {"sodimac:123:29990"}, ["sodimac:456:9990"])
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(saved) == ["sodimac:123:29990", "sodimac:456:9990"]
