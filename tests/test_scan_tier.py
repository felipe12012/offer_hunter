import json

import main_fast


def test_tier_allows_splits_http_and_browser_stores(monkeypatch):
    monkeypatch.setenv("SCAN_TIER", "http")
    assert main_fast.tier_allows("falabella") is True
    assert main_fast.tier_allows("nike") is False   # browser store

    monkeypatch.setenv("SCAN_TIER", "browser")
    assert main_fast.tier_allows("nike") is True
    assert main_fast.tier_allows("falabella") is False

    monkeypatch.delenv("SCAN_TIER", raising=False)
    assert main_fast.tier_allows("falabella") is True
    assert main_fast.tier_allows("nike") is True     # unset = everything


def test_browser_stores_set_matches_the_flagged_stores():
    # Guard against a new browser store being added but not tiered.
    for store in ("nike", "skechers", "salcobrand", "cruzverde", "antartica"):
        assert store in main_fast.BROWSER_STORES
    for store in ("falabella", "sodimac", "hites", "maconline", "surprice", "sony"):
        assert store not in main_fast.BROWSER_STORES


def test_scan_stores_http_tier_skips_browser_stores(monkeypatch, tmp_path):
    monkeypatch.setenv("SCAN_TIER", "http")
    monkeypatch.setattr(main_fast, "WATCHLIST_PATH", tmp_path / "watchlist.json")
    (tmp_path / "watchlist.json").write_text(
        json.dumps({"categories": [], "keywords": [], "min_discount_pct": 100}), encoding="utf-8"
    )
    called = []

    def tracker(name):
        def fetch(watchlist):
            called.append(name)
            return []
        return fetch

    for attr in main_fast.SOURCE_NAMES:
        monkeypatch.setattr(main_fast, attr, tracker(attr))

    main_fast.scan_stores(main_fast.load_watchlist())

    assert "fetch_falabella_deals" in called
    assert "fetch_nike_deals" not in called
    assert "fetch_salcobrand_deals" not in called
