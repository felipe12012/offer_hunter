# tests/test_workflow.py
import json
from pathlib import Path

import main_fast
from models import Deal


def make_deal(
    deal_id: str,
    price: int,
    scraped_at: str = "2026-10-01T12:00:00+00:00",
    list_price: int | None = None,
) -> Deal:
    list_price = list_price or price
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    return Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://www.sodimac.cl/sodimac-cl/product/{deal_id}/taladro/{deal_id}/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=scraped_at,
        image_url="https://img.example/p.jpg",
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


def _stub_all_sources(monkeypatch, **overrides):
    """Replace every registered source fetcher so the workflow tests never hit
    the network. Derived from main_fast.SOURCE_NAMES so adding a store can't
    silently start making live requests from the test suite."""
    for attr in main_fast.SOURCE_NAMES:
        monkeypatch.setattr(main_fast, attr, overrides.get(attr, lambda watchlist: []))


def test_run_sends_digest_and_persists_state(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])

    sent = {}
    monkeypatch.setattr(main_fast, "send_offers", lambda scored: sent.setdefault("offers", list(scored)) or scored)

    exit_code = main_fast.run()

    assert exit_code == 0
    assert "offers" not in sent  # nothing qualified (no history yet), so nothing is sent
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
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])

    captured = {}
    monkeypatch.setattr(main_fast, "send_offers", lambda scored: captured.setdefault("scored", list(scored)) or scored)

    main_fast.run()

    assert len(captured["scored"]) == 1
    # (9990 - 5000) / 9990 = 49.9%, clears min_real_discount_pct=15 from _patch_paths's watchlist
    assert captured["scored"][0].real_discount_pct == 49.9


def test_run_skips_already_seen_id_price_pairs(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "seen_items.json").write_text(json.dumps(["sodimac:1:5000"]), encoding="utf-8")
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])

    captured = {"scored": []}
    monkeypatch.setattr(main_fast, "send_offers", lambda scored: captured.__setitem__("scored", list(scored)) or scored)

    main_fast.run()

    assert captured["scored"] == []


def test_run_returns_1_when_source_raises(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    def boom(watchlist):
        raise RuntimeError("site down")

    _stub_all_sources(monkeypatch, **{attr: boom for attr in main_fast.SOURCE_NAMES})

    assert main_fast.run() == 1


def test_run_leaves_undelivered_offers_unseen_so_they_retry_next_run(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "price_history.json").write_text(
        json.dumps({"sodimac:1": [{"date": "2026-09-20", "price": 9990}], "sodimac:2": [{"date": "2026-09-20", "price": 9990}]}),
        encoding="utf-8",
    )
    _stub_all_sources(
        monkeypatch,
        fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000), make_deal("sodimac:2", 5000)],
    )
    # Telegram only manages to deliver the first offer.
    monkeypatch.setattr(main_fast, "send_offers", lambda scored: [s for s in scored if s.deal.id == "sodimac:1"])

    assert main_fast.run() == 0

    seen = json.loads((tmp_path / "seen_items.json").read_text(encoding="utf-8"))
    assert seen == ["sodimac:1:5000"]  # sodimac:2 not marked seen -> retried next run


def test_run_returns_1_and_persists_nothing_when_no_offer_can_be_delivered(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "price_history.json").write_text(
        json.dumps({"sodimac:1": [{"date": "2026-09-20", "price": 9990}]}), encoding="utf-8"
    )
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    monkeypatch.setattr(main_fast, "send_offers", lambda scored: [])

    assert main_fast.run() == 1
    assert not (tmp_path / "seen_items.json").exists()


def test_run_does_not_notify_advertised_discount_that_history_cannot_confirm(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    # Lower the bar so the 60% "discount" would qualify if it were taken at face value.
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(
        json.dumps({"categories": ["herramientas"], "keywords": [], "min_discount_pct": 30, "min_real_discount_pct": 15}),
        encoding="utf-8",
    )
    # First sighting at "-60%": nothing proves the $25.000 list price was ever charged.
    _stub_all_sources(
        monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 10000, list_price=25000)]
    )
    calls = []
    monkeypatch.setattr(main_fast, "send_offers", lambda scored: calls.append(list(scored)) or scored)

    assert main_fast.run() == 0

    assert calls == []  # unverified discount must never reach Telegram


def test_disabled_stores_are_not_fetched(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(
        json.dumps({"categories": ["herramientas"], "keywords": [], "disabled_stores": ["Paris", "ripley"]}),
        encoding="utf-8",
    )
    called = []

    def tracker(name):
        def fetch(watchlist):
            called.append(name)
            return []
        return fetch

    _stub_all_sources(monkeypatch, **{attr: tracker(attr) for attr in main_fast.SOURCE_NAMES})
    monkeypatch.setattr(main_fast, "send_offers", lambda scored: scored)

    assert main_fast.run() == 0

    assert "fetch_paris_deals" not in called
    assert "fetch_ripley_deals" not in called
    assert "fetch_sodimac_deals" in called
