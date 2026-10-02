# tests/test_workflow.py
import json
from pathlib import Path

import main_fast
from models import Deal


def make_deal(deal_id: str, price: int, scraped_at: str = "2026-10-01T12:00:00+00:00") -> Deal:
    return Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://www.sodimac.cl/sodimac-cl/product/{deal_id}/taladro/{deal_id}/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=price,
        discount_pct=0.0,
        scraped_at=scraped_at,
    )


def _patch_paths(monkeypatch, tmp_path: Path):
    watchlist = {
        "categories": ["herramientas"],
        "keywords": [],
        "min_discount_pct": 100,  # unreachable via list price alone in this test
        "min_real_discount_pct": 15,
    }
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps(watchlist), encoding="utf-8")
    monkeypatch.setattr(main_fast, "WATCHLIST_PATH", watchlist_path)
    monkeypatch.setattr(main_fast, "SEEN_PATH", tmp_path / "seen_items.json")
    monkeypatch.setattr(main_fast, "HISTORY_PATH", tmp_path / "price_history.json")


def test_run_sends_digest_and_persists_state(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(main_fast, "fetch_sodimac_deals", lambda watchlist: [make_deal("sodimac:1", 5000)])

    sent = {}
    monkeypatch.setattr(main_fast, "send_digest", lambda scored: sent.setdefault("count", len(scored)) or True)

    exit_code = main_fast.run()

    assert exit_code == 0
    seen = json.loads((tmp_path / "seen_items.json").read_text(encoding="utf-8"))
    assert seen == ["sodimac:1:5000"]
    history = json.loads((tmp_path / "price_history.json").read_text(encoding="utf-8"))
    assert history["sodimac:1"] == [{"date": "2026-10-01", "price": 5000}]


def test_run_does_not_compare_real_discount_against_its_own_just_scraped_price(monkeypatch, tmp_path):
    """
    Regression guard: on the very first run where price_history.json does not
    yet exist, a deal's real_discount_pct must be computed from history BEFORE
    this run's own snapshot is appended — never against a history that already
    contains today's price (which would make every item its own minimum and
    real_discount_pct always 0).
    """
    _patch_paths(monkeypatch, tmp_path)
    # Seed history with a *previous*, higher price so a real discount exists.
    (tmp_path / "price_history.json").write_text(
        json.dumps({"sodimac:1": [{"date": "2026-09-20", "price": 9990}]}), encoding="utf-8"
    )
    monkeypatch.setattr(main_fast, "fetch_sodimac_deals", lambda watchlist: [make_deal("sodimac:1", 5000)])

    captured = {}
    monkeypatch.setattr(main_fast, "send_digest", lambda scored: captured.setdefault("scored", scored) or True)

    main_fast.run()

    assert len(captured["scored"]) == 1
    # (9990 - 5000) / 9990 = 49.9%, clears min_real_discount_pct=15 from _patch_paths's watchlist
    assert captured["scored"][0].real_discount_pct == 49.9


def test_run_skips_already_seen_id_price_pairs(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "seen_items.json").write_text(json.dumps(["sodimac:1:5000"]), encoding="utf-8")
    monkeypatch.setattr(main_fast, "fetch_sodimac_deals", lambda watchlist: [make_deal("sodimac:1", 5000)])

    captured = {}
    monkeypatch.setattr(main_fast, "send_digest", lambda scored: captured.setdefault("scored", scored) or True)

    main_fast.run()

    assert captured["scored"] == []


def test_run_returns_1_when_source_raises(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    def boom(watchlist):
        raise RuntimeError("site down")

    monkeypatch.setattr(main_fast, "fetch_sodimac_deals", boom)

    assert main_fast.run() == 1
