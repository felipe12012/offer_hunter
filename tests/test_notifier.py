# tests/test_notifier.py
from models import Deal, ScoredDeal
from notifier import send_digest


import notifier


def make_scored(
    deal_id: str,
    price: int,
    real_discount_pct: float = 0.0,
    discount_pct: float = 0.0,
    store: str = "sodimac",
) -> ScoredDeal:
    deal = Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://www.sodimac.cl/sodimac-cl/product/{deal_id}/taladro/{deal_id}/",
        store=store,
        category="herramientas",
        price=price,
        list_price=price + 10000,
        discount_pct=discount_pct,
        scraped_at="2026-10-01T12:00:00+00:00",
    )
    return ScoredDeal(deal=deal, real_discount_pct=real_discount_pct, reasons=["-20% vs minimo historico ($39.990)"])


class FakeResponse:
    def raise_for_status(self):
        return None


def test_send_digest_sends_when_deals_exist(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["url"] = url
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    result = send_digest([make_scored("sodimac:1", 29990)], bot_token="fake-token", chat_id="12345")

    assert result is True
    assert sent["json"]["chat_id"] == "12345"
    assert "Taladro percutor" in sent["json"]["text"]
    assert "fake-token" in sent["url"]


def test_send_digest_skips_send_when_no_deals(monkeypatch):
    called = {"count": 0}

    def fake_post(url, json, timeout):
        called["count"] += 1
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    result = send_digest([], bot_token="fake-token", chat_id="12345")

    assert result is False
    assert called["count"] == 0


def test_send_digest_caps_at_five_deals_sorted_by_rank(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    # Six distinct stores, one deal each: the run must keep the top 5 by rank.
    scored = [
        make_scored(f"s{i}:1", 10000, real_discount_pct=float(i), store=f"s{i}")
        for i in range(6)
    ]
    send_digest(scored, bot_token="fake-token", chat_id="12345")

    text = sent["json"]["text"]
    assert text.count("@ s") == 5
    assert "s0:1" not in text  # lowest rank dropped
    for kept in ("s5:1", "s4:1", "s3:1", "s2:1", "s1:1"):
        assert kept in text


def test_send_digest_caps_offers_per_store(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    scored = [make_scored(f"sodimac:{i}", 10000, real_discount_pct=float(i)) for i in range(7)]
    send_digest(scored, bot_token="fake-token", chat_id="12345")

    text = sent["json"]["text"]
    # per-store cap = 2: only the two highest-ranked survive
    assert text.count("@ sodimac") == notifier.MAX_DEALS_PER_STORE
    assert "sodimac:6" in text and "sodimac:5" in text
    assert "sodimac:0" not in text and "sodimac:1" not in text


def test_send_digest_ranks_advertised_discount_when_store_has_no_history(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    # New stores expose compare_at_price but have no history yet: their
    # advertised discount must still rank them, or they'd never be sent.
    scored = [
        make_scored("ripley:1", 10000, real_discount_pct=0.0, discount_pct=70.0, store="ripley"),
        make_scored("hites:1", 10000, real_discount_pct=0.0, discount_pct=10.0, store="hites"),
    ]
    send_digest(scored, bot_token="fake-token", chat_id="12345")

    text = sent["json"]["text"]
    assert text.index("ripley:1") < text.index("hites:1")


def test_send_digest_truncates_long_text(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    scored = make_scored("sodimac:1", 29990)
    scored.reasons.append("x" * 5000)
    result = send_digest([scored], bot_token="fake-token", chat_id="12345")

    assert result is True
    assert len(sent["json"]["text"]) <= 4000


def test_send_digest_raises_on_telegram_error(monkeypatch):
    import requests as real_requests

    def fake_post(url, json, timeout):
        raise real_requests.RequestException("telegram down")

    monkeypatch.setattr("notifier.requests.post", fake_post)

    try:
        send_digest([make_scored("sodimac:1", 29990)], bot_token="fake-token", chat_id="12345")
        assert False, "expected RequestException to propagate"
    except real_requests.RequestException:
        pass
