# tests/test_notifier.py
from models import Deal, ScoredDeal
from notifier import send_digest


def make_scored(deal_id: str, price: int, real_discount_pct: float = 20.0) -> ScoredDeal:
    deal = Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://www.sodimac.cl/sodimac-cl/product/{deal_id}/taladro/{deal_id}/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=price + 10000,
        discount_pct=10.0,
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


def test_send_digest_caps_at_five_deals_sorted_by_real_discount(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    scored = [make_scored(f"sodimac:{i}", 10000 + i, real_discount_pct=float(i)) for i in range(7)]
    send_digest(scored, bot_token="fake-token", chat_id="12345")

    assert sent["json"]["text"].count("@ sodimac") == 5
    # Highest real_discount_pct values are 6, 5, 4, 3, 2 — item "sodimac:0" and "sodimac:1" must be dropped.
    assert "sodimac:0" not in sent["json"]["text"]
    assert "sodimac:1" not in sent["json"]["text"]


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
