# tests/test_workflow.py
import json
from datetime import datetime, timezone
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
    monkeypatch.setattr(main_fast, "BUDGET_PATH", tmp_path / "alert_budget.json")


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
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: sent.setdefault("offers", list(scored)) or scored)

    exit_code = main_fast.run()

    assert exit_code == 0
    assert "offers" not in sent  # nothing qualified (no history yet), so nothing is sent
    seen = json.loads((tmp_path / "seen_items.json").read_text(encoding="utf-8"))
    assert seen == []  # nothing was delivered, so nothing is remembered as seen
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
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: captured.setdefault("scored", list(scored)) or scored)

    main_fast.run()

    assert len(captured["scored"]) == 1
    # (9990 - 5000) / 9990 = 49.9%, clears min_real_discount_pct=15 from _patch_paths's watchlist
    assert captured["scored"][0].real_discount_pct == 49.9


def test_run_skips_already_seen_id_price_pairs(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "seen_items.json").write_text(json.dumps(["sodimac:1:5000"]), encoding="utf-8")
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])

    captured = {"scored": []}
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: captured.__setitem__("scored", list(scored)) or scored)

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
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: [s for s in scored if s.deal.id == "sodimac:1"])

    assert main_fast.run() == 0

    seen = json.loads((tmp_path / "seen_items.json").read_text(encoding="utf-8"))
    assert seen == ["sodimac:1:5000"]  # sodimac:2 not marked seen -> retried next run


def test_run_returns_1_and_persists_nothing_when_no_offer_can_be_delivered(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "price_history.json").write_text(
        json.dumps({"sodimac:1": [{"date": "2026-09-20", "price": 9990}]}), encoding="utf-8"
    )
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: [])

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
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: calls.append(list(scored)) or scored)

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
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: scored)

    assert main_fast.run() == 0

    assert "fetch_paris_deals" not in called
    assert "fetch_ripley_deals" not in called
    assert "fetch_sodimac_deals" in called


def test_same_marketplace_product_on_two_stores_is_sent_once_but_remembered_for_both(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "price_history.json").write_text(
        json.dumps({
            "falabella:777": [{"date": "2026-09-20", "price": 9990}],
            "sodimac:777": [{"date": "2026-09-20", "price": 9990}],
        }),
        encoding="utf-8",
    )

    def deal_for(store):
        return Deal(
            id=f"{store}:777", title="Seccional", url=f"https://www.{store}.cl/p/777", store=store,
            category="herramientas", price=5000, list_price=5000, discount_pct=0.0,
            scraped_at="2026-10-01T12:00:00+00:00", image_url="https://img.example/p.jpg",
        )

    _stub_all_sources(
        monkeypatch,
        fetch_falabella_deals=lambda watchlist: [deal_for("falabella")],
        fetch_sodimac_deals=lambda watchlist: [deal_for("sodimac")],
    )
    sent = []
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: sent.append(list(scored)) or scored)

    assert main_fast.run() == 0

    assert len(sent) == 1 and len(sent[0]) == 1          # one message, not two
    seen = json.loads((tmp_path / "seen_items.json").read_text(encoding="utf-8"))
    assert sorted(seen) == ["falabella:777:5000", "sodimac:777:5000"]  # neither is re-sent next run


def test_selftest_includes_one_simulated_big_alert_and_touches_no_state(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    import dataclasses

    deals = [
        dataclasses.replace(make_deal(f"{store}:{i}", 10000 + i), store=store)
        for i, store in enumerate(["sodimac", "falabella", "hites"])
    ]
    monkeypatch.setattr(main_fast, "fetch_all_deals", lambda watchlist: deals)
    sent = []
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: sent.append(list(scored)) or scored)

    assert main_fast.selftest() == 0

    assert len(sent[0]) == 3
    assert sent[0][0].verified_pct >= 80                  # one goes through the alert path
    assert all("PRUEBA" in offer.reasons[0] for offer in sent[0])
    assert not (tmp_path / "seen_items.json").exists()
    assert not (tmp_path / "price_history.json").exists()


class FakeMirror:
    def __init__(self, fail=False):
        self.fail = fail
        self.scans, self.sent, self.runs = [], [], []

    def sync_scan(self, deals):
        if self.fail:
            raise RuntimeError("supabase down")
        self.scans.append(list(deals))
        return {"received": len(deals), "new": 1, "updated": 1, "points": 1}

    def record_sent(self, offers):
        self.sent.append(list(offers))

    def record_run(self, stats):
        self.runs.append(stats)


def _history_with_drop(tmp_path):
    (tmp_path / "price_history.json").write_text(
        json.dumps({"sodimac:1": [{"date": "2026-09-20", "price": 9990}]}), encoding="utf-8"
    )


def test_run_mirrors_scan_delivered_offers_and_run_stats_to_supabase(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _history_with_drop(tmp_path)
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: scored)
    mirror = FakeMirror()
    monkeypatch.setattr(main_fast.SupabaseSync, "from_env", classmethod(lambda cls: mirror))

    assert main_fast.run() == 0

    assert [d.id for d in mirror.scans[0]] == ["sodimac:1"]
    assert [o.deal.id for o in mirror.sent[0]] == ["sodimac:1"]
    stats = mirror.runs[0]
    assert stats["scanned"] == 1 and stats["qualifying"] == 1 and stats["delivered"] == 1
    assert stats["per_store"] == {"sodimac": 1}
    assert stats["duration_seconds"] >= 0


def test_a_supabase_outage_never_fails_the_run_or_loses_json_state(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _history_with_drop(tmp_path)
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: scored)
    monkeypatch.setattr(main_fast.SupabaseSync, "from_env", classmethod(lambda cls: FakeMirror(fail=True)))

    assert main_fast.run() == 0

    seen = json.loads((tmp_path / "seen_items.json").read_text(encoding="utf-8"))
    assert seen == ["sodimac:1:5000"]


def test_run_without_supabase_configuration_just_skips_the_mirror(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _stub_all_sources(monkeypatch)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert main_fast.run() == 0


def test_budget_resets_daily_and_carries_over_within_the_day(tmp_path):
    path = tmp_path / "alert_budget.json"
    path.write_text(json.dumps({"date": "2026-01-01", "unverified": 10}), encoding="utf-8")

    assert main_fast.load_budget(path, "2026-01-01")["unverified"] == 10   # same day: carried over
    assert main_fast.load_budget(path, "2026-01-02")["unverified"] == 0    # new day: reset
    assert main_fast.load_budget(tmp_path / "missing.json", "2026-01-02") == {
        "date": "2026-01-02",
        "unverified": 0,
    }


def test_run_passes_the_remaining_daily_unverified_budget_to_the_notifier(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _history_with_drop(tmp_path)
    today = datetime.now(timezone.utc).date().isoformat()
    (tmp_path / "alert_budget.json").write_text(
        json.dumps({"date": today, "unverified": main_fast.DAILY_UNVERIFIED_CAP - 3}), encoding="utf-8"
    )
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    captured = {}
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: captured.update(kw) or list(scored))

    assert main_fast.run() == 0

    assert captured["max_unverified"] == 3


def test_mirror_is_skipped_when_telegram_delivery_fails_entirely(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    _history_with_drop(tmp_path)
    _stub_all_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: [])
    mirror = FakeMirror()
    monkeypatch.setattr(main_fast.SupabaseSync, "from_env", classmethod(lambda cls: mirror))

    assert main_fast.run() == 1
    assert mirror.scans == []          # JSON state was not saved either, so both stay aligned
