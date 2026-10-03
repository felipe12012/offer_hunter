"""Per-store reports, the run summary, failure reasons and store-health alerts."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import main_fast
from models import Deal
from sources import health


def make_deal(deal_id: str, price: int = 5000, list_price: int | None = None) -> Deal:
    list_price = list_price or price
    return Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://shop.example/{deal_id}",
        store=deal_id.split(":")[0],
        category="herramientas",
        price=price,
        list_price=list_price,
        discount_pct=round((list_price - price) / list_price * 100, 1) if list_price else 0.0,
        scraped_at="2026-10-01T12:00:00+00:00",
        image_url="https://img.example/p.jpg",
    )


def patch_paths(monkeypatch, tmp_path: Path, watchlist: dict | None = None):
    watchlist = watchlist or {
        "categories": ["herramientas"], "keywords": [], "min_discount_pct": 100, "min_real_discount_pct": 15,
    }
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps(watchlist), encoding="utf-8")
    monkeypatch.setattr(main_fast, "WATCHLIST_PATH", path)
    monkeypatch.setattr(main_fast, "SEEN_PATH", tmp_path / "seen_items.json")
    monkeypatch.setattr(main_fast, "HISTORY_PATH", tmp_path / "price_history.json")
    monkeypatch.setattr(main_fast, "BUDGET_PATH", tmp_path / "alert_budget.json")
    monkeypatch.setattr(main_fast, "RUN_STATUS_PATH", tmp_path / "run_status.txt")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    health.drain()
    return summary


def stub_sources(monkeypatch, **overrides):
    for attr in main_fast.SOURCE_NAMES:
        monkeypatch.setattr(main_fast, attr, overrides.get(attr, lambda watchlist: []))


class FakeMirror:
    def __init__(self, previous=None, fail=False):
        self.previous_status = previous or []
        self.fail = fail
        self.scans, self.sent, self.runs = [], [], []

    def sync_scan(self, deals):
        if self.fail:
            raise RuntimeError("supabase down")
        self.scans.append(list(deals))
        return {"received": len(deals), "new": 0, "updated": 0, "points": 0}

    def record_sent(self, offers):
        self.sent.append(list(offers))

    def record_run(self, stats):
        self.runs.append(stats)

    def recent_store_status(self, limit=2):
        return list(self.previous_status)


def use_mirror(monkeypatch, mirror):
    monkeypatch.setattr(main_fast.SupabaseSync, "from_env", classmethod(lambda cls: mirror))


# ---- scan_stores ---------------------------------------------------------------

def test_scan_stores_reports_the_status_of_every_store(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)

    def partial(watchlist):
        health.warn("hushpuppies", "hushpuppies keyword 'x' failed: boom")
        return [make_deal("hushpuppies:1")]

    def boom(watchlist):
        raise RuntimeError("All Vans keywords failed")

    stub_sources(
        monkeypatch,
        fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")],
        fetch_hushpuppies_deals=partial,
        fetch_vans_deals=boom,
    )

    deals, reports = main_fast.scan_stores({"disabled_stores": ["paris"]})

    by_store = {r.store: r for r in reports}
    assert by_store["sodimac"].status == "ok" and by_store["sodimac"].deals == 1
    assert by_store["hushpuppies"].status == "partial"
    assert by_store["vans"].status == "failed" and "All Vans keywords failed" in by_store["vans"].detail
    assert by_store["crocs"].status == "empty"
    assert by_store["paris"].status == "disabled"
    assert [r.store for r in reports] == [store for store, _attr in main_fast.SOURCE_FETCHERS]
    assert len(deals) == 2


def test_scan_stores_marks_a_store_that_overruns_as_timeout_and_keeps_the_rest(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(main_fast, "SOURCE_TIMEOUT_SECONDS", 0.2)

    def hang(watchlist):
        time.sleep(1.0)
        return []

    stub_sources(
        monkeypatch,
        fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")],
        fetch_hites_deals=hang,
    )

    deals, reports = main_fast.scan_stores({})

    by_store = {r.store: r for r in reports}
    assert by_store["hites"].status == "timeout"
    assert by_store["sodimac"].status == "ok"
    assert len(deals) == 1


def test_fetch_all_deals_still_returns_just_the_deals(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")])
    assert [d.id for d in main_fast.fetch_all_deals({})] == ["sodimac:1"]


def test_every_store_failing_raises_with_the_reports_attached(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)

    def boom(watchlist):
        raise RuntimeError("down")

    stub_sources(monkeypatch, **{attr: boom for attr in main_fast.SOURCE_NAMES})

    try:
        main_fast.scan_stores({})
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert exc.reports and all(r.status == "failed" for r in exc.reports)


# ---- run summary and failure reasons -----------------------------------------------

def test_run_writes_a_github_step_summary_with_the_store_table(monkeypatch, tmp_path):
    summary = patch_paths(monkeypatch, tmp_path)
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")])

    assert main_fast.run() == 0

    text = summary.read_text(encoding="utf-8")
    assert "| sodimac |" in text and "Tienda" in text
    assert "Productos leídos" in text


def test_a_scraper_failure_writes_the_reason_for_the_failure_alert(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)

    def boom(watchlist):
        raise RuntimeError("blocked")

    stub_sources(monkeypatch, **{attr: boom for attr in main_fast.SOURCE_NAMES})

    assert main_fast.run() == 1

    assert "All fast-tier sources failed" in (tmp_path / "run_status.txt").read_text(encoding="utf-8")


def test_a_real_telegram_failure_writes_its_reason_too(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    (tmp_path / "price_history.json").write_text(
        json.dumps({"sodimac:1": [{"date": "2026-09-20", "price": 9990}]}), encoding="utf-8"
    )
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: [])

    assert main_fast.run() == 1
    assert "Telegram" in (tmp_path / "run_status.txt").read_text(encoding="utf-8")


def test_an_uncaught_exception_is_recorded_before_it_propagates(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)

    def kaboom():
        raise ValueError("kaboom")

    monkeypatch.setattr(main_fast, "run", kaboom)

    try:
        main_fast.main([])
        assert False, "expected ValueError"
    except ValueError:
        pass

    assert "ValueError: kaboom" in (tmp_path / "run_status.txt").read_text(encoding="utf-8")


def test_a_successful_run_leaves_no_stale_failure_reason(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    (tmp_path / "run_status.txt").write_text("old failure", encoding="utf-8")
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")])

    assert main_fast.run() == 0
    assert not (tmp_path / "run_status.txt").exists()


# ---- Supabase payload and quota wording ------------------------------------------------

def test_run_records_store_status_errors_and_quota_in_supabase(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)

    def partial(watchlist):
        health.warn("hites", "hites query 'fila' failed: boom")
        return [make_deal("hites:1")]

    stub_sources(monkeypatch, fetch_hites_deals=partial)
    mirror = FakeMirror()
    use_mirror(monkeypatch, mirror)

    assert main_fast.run() == 0

    stats = mirror.runs[0]
    assert stats["store_status"]["hites"]["status"] == "partial"
    assert stats["store_status"]["hites"]["deals"] == 1
    assert any("fila" in e for e in stats["errors"])
    assert set(stats["quota"]) >= {"unverified_room", "eligible", "delivered", "quota_limited"}


def test_quota_limited_runs_say_so_instead_of_pretending_telegram_failed(monkeypatch, tmp_path, capsys):
    patch_paths(
        monkeypatch, tmp_path,
        {"categories": ["herramientas"], "keywords": [], "min_discount_pct": 30,
         "min_real_discount_pct": 15, "verify_advertised_discount": "label"},
    )
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 4000, list_price=10000)])
    today = datetime.now(timezone.utc).date().isoformat()
    (tmp_path / "alert_budget.json").write_text(
        json.dumps({"date": today, "unverified": main_fast.DAILY_UNVERIFIED_CAP}), encoding="utf-8"
    )
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: [])
    mirror = FakeMirror()
    use_mirror(monkeypatch, mirror)

    assert main_fast.run() == 0

    err = capsys.readouterr().err
    assert "quota" in err.lower() and "nothing sent" in err.lower()
    assert mirror.runs[0]["quota"]["quota_limited"] is True


# ---- store health alerts ---------------------------------------------------------------

def failing_hites_run(monkeypatch, tmp_path, previous):
    patch_paths(monkeypatch, tmp_path)

    def boom(watchlist):
        raise RuntimeError("Hites is blocking us")

    stub_sources(
        monkeypatch,
        fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")],
        fetch_hites_deals=boom,
    )
    use_mirror(monkeypatch, FakeMirror(previous))
    alerts = []
    monkeypatch.setattr(main_fast, "send_alert", lambda text, **kw: alerts.append(text) or True)
    return alerts


def test_a_store_failing_for_the_second_run_in_a_row_triggers_one_alert_with_the_reason(monkeypatch, tmp_path):
    alerts = failing_hites_run(monkeypatch, tmp_path, [{"hites": "failed"}, {"hites": "ok"}])

    assert main_fast.run() == 0

    assert len(alerts) == 1
    assert "hites" in alerts[0] and "Hites is blocking us" in alerts[0]


def test_the_first_bad_run_stays_quiet(monkeypatch, tmp_path):
    alerts = failing_hites_run(monkeypatch, tmp_path, [{"hites": "ok"}, {"hites": "ok"}])
    main_fast.run()
    assert alerts == []


def test_an_already_announced_outage_does_not_repeat_the_alert(monkeypatch, tmp_path):
    alerts = failing_hites_run(monkeypatch, tmp_path, [{"hites": "failed"}, {"hites": "failed"}])
    main_fast.run()
    assert alerts == []


def test_a_recovered_store_is_announced_once(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    stub_sources(monkeypatch, fetch_hites_deals=lambda watchlist: [make_deal("hites:1")])
    use_mirror(monkeypatch, FakeMirror([{"hites": "failed"}, {"hites": "timeout"}]))
    alerts = []
    monkeypatch.setattr(main_fast, "send_alert", lambda text, **kw: alerts.append(text) or True)

    main_fast.run()

    assert len(alerts) == 1 and "hites" in alerts[0] and "recuper" in alerts[0].lower()


def test_a_failing_alert_never_breaks_the_run(monkeypatch, tmp_path):
    failing_hites_run(monkeypatch, tmp_path, [{"hites": "failed"}, {"hites": "ok"}])

    def explode(text, **kw):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(main_fast, "send_alert", explode)
    assert main_fast.run() == 0


def test_alerts_are_skipped_quietly_when_the_history_cannot_be_read(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1")])

    class Unreadable(FakeMirror):
        def recent_store_status(self, limit=2):
            raise RuntimeError("column does not exist")

    mirror = Unreadable()
    use_mirror(monkeypatch, mirror)
    alerts = []
    monkeypatch.setattr(main_fast, "send_alert", lambda text, **kw: alerts.append(text) or True)

    assert main_fast.run() == 0
    assert alerts == [] and len(mirror.runs) == 1     # the run itself is still recorded


# ---- "no offers" is never an error --------------------------------------------------

def test_a_scan_where_every_store_returns_nothing_is_not_an_error(monkeypatch, tmp_path):
    summary = patch_paths(monkeypatch, tmp_path)
    stub_sources(monkeypatch)                                   # all 22 stores answer with zero products
    sent = []
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: sent.append(scored) or scored)

    assert main_fast.run() == 0

    assert sent == []                                           # nothing to send, nothing attempted
    assert not (tmp_path / "run_status.txt").exists()           # no failure reason left behind
    assert "Escaneo completado" in summary.read_text(encoding="utf-8")


def test_products_that_do_not_qualify_are_not_an_error(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])  # no discount
    sent = []
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: sent.append(scored) or scored)

    assert main_fast.run() == 0
    assert sent == []


def test_offers_that_were_all_delivered_before_are_not_an_error(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    (tmp_path / "price_history.json").write_text(
        json.dumps({"sodimac:1": [{"date": "2026-09-20", "price": 9990}]}), encoding="utf-8"
    )
    (tmp_path / "seen_items.json").write_text(json.dumps(["sodimac:1:5000"]), encoding="utf-8")
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    sent = []
    monkeypatch.setattr(main_fast, "send_offers", lambda scored, **kw: sent.append(scored) or scored)

    assert main_fast.run() == 0
    assert sent == []                                           # already seen, so not even a candidate


def test_a_run_with_no_offers_still_saves_history_and_mirrors_to_supabase(monkeypatch, tmp_path):
    patch_paths(monkeypatch, tmp_path)
    stub_sources(monkeypatch, fetch_sodimac_deals=lambda watchlist: [make_deal("sodimac:1", 5000)])
    mirror = FakeMirror()
    use_mirror(monkeypatch, mirror)

    assert main_fast.run() == 0

    assert (tmp_path / "price_history.json").exists()
    assert len(mirror.scans) == 1 and len(mirror.runs) == 1
