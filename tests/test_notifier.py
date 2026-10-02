import requests as real_requests

from models import Deal, ScoredDeal
from notifier import MAX_MESSAGES_PER_RUN, format_offer, send_offers


def make_scored(
    deal_id: str,
    price: int = 29990,
    store: str = "sodimac",
    discount_pct: float = 10.0,
    real_discount_pct: float = 20.0,
    image_url: str = "https://img.example/p.jpg",
    title: str = "Taladro percutor",
) -> ScoredDeal:
    deal = Deal(
        id=deal_id,
        title=title,
        url=f"https://www.{store}.cl/product/{deal_id}",
        store=store,
        category="herramientas",
        price=price,
        list_price=price + 10000,
        discount_pct=discount_pct,
        scraped_at="2026-10-01T12:00:00+00:00",
        image_url=image_url,
    )
    return ScoredDeal(deal=deal, real_discount_pct=real_discount_pct, reasons=["-20% vs minimo historico ($39.990)"])


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"img", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.headers = headers or {"Content-Type": "image/jpeg"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.HTTPError(f"{self.status_code}")

    def json(self):
        return self._payload


class Recorder:
    """Fake requests.post that records every call and answers per API method."""

    def __init__(self, fail_methods=(), fail_photo_for=()):
        self.calls = []
        self.fail_methods = set(fail_methods)
        self.fail_photo_for = set(fail_photo_for)

    def __call__(self, url, json=None, data=None, files=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        body = json if json is not None else data
        self.calls.append((method, body, files))
        if method in self.fail_methods:
            return FakeResponse(400)
        if method == "sendPhoto" and body and any(tag in str(body.get("photo", "")) for tag in self.fail_photo_for):
            return FakeResponse(400)
        return FakeResponse(200)


def install(monkeypatch, recorder, get=None):
    monkeypatch.setattr("notifier.requests.post", recorder)
    monkeypatch.setattr("notifier.requests.get", get or (lambda url, **kw: FakeResponse(200)))
    monkeypatch.setattr("notifier.time.sleep", lambda s: None)


def test_sends_one_photo_message_per_offer(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offers = [make_scored(f"sodimac:{i}", store=f"s{i}") for i in range(3)]

    sent = send_offers(offers, bot_token="tok", chat_id="123")

    assert sent == offers or sorted(o.deal.id for o in sent) == sorted(o.deal.id for o in offers)
    assert [c[0] for c in rec.calls] == ["sendPhoto"] * 3
    for _method, body, _files in rec.calls:
        assert body["chat_id"] == "123"
        assert body["photo"] == "https://img.example/p.jpg"
        assert "Taladro percutor" in body["caption"]


def test_does_nothing_without_offers(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    assert send_offers([], bot_token="tok", chat_id="123") == []
    assert rec.calls == []


def test_sends_every_offer_not_just_top_five(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offers = [make_scored(f"sodimac:{i}", store="sodimac") for i in range(9)]

    sent = send_offers(offers, bot_token="tok", chat_id="123")

    assert len(sent) == 9
    assert len(rec.calls) == 9


def test_best_discounts_are_sent_first(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offers = [
        make_scored("sodimac:low", discount_pct=5.0, real_discount_pct=0.0),
        make_scored("sodimac:high", discount_pct=60.0, real_discount_pct=0.0),
        make_scored("sodimac:mid", discount_pct=10.0, real_discount_pct=25.0),
    ]

    send_offers(offers, bot_token="tok", chat_id="123")

    order = [c[1]["caption"] for c in rec.calls]
    assert "sodimac:high" in order[0] or "/product/sodimac:high" in order[0]
    assert "sodimac:mid" in order[1]
    assert "sodimac:low" in order[2]


def test_caps_messages_per_run_and_reports_only_what_was_sent(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offers = [make_scored(f"sodimac:{i}") for i in range(MAX_MESSAGES_PER_RUN + 4)]

    sent = send_offers(offers, bot_token="tok", chat_id="123")

    assert len(sent) == MAX_MESSAGES_PER_RUN
    assert len(rec.calls) == MAX_MESSAGES_PER_RUN


def test_falls_back_to_uploading_the_image_when_telegram_cannot_fetch_the_url(monkeypatch):
    rec = Recorder(fail_photo_for=("hotlink-blocked",))
    install(monkeypatch, rec)
    offer = make_scored("sodimac:1", image_url="https://img.example/hotlink-blocked.jpg")

    sent = send_offers([offer], bot_token="tok", chat_id="123")

    assert sent == [offer]
    methods = [c[0] for c in rec.calls]
    assert methods == ["sendPhoto", "sendPhoto"]
    assert rec.calls[0][2] is None           # first try: by URL
    assert rec.calls[1][2] is not None       # second try: uploaded bytes


def test_falls_back_to_text_when_photo_cannot_be_sent_at_all(monkeypatch):
    rec = Recorder(fail_methods=("sendPhoto",))
    install(monkeypatch, rec)
    offer = make_scored("sodimac:1")

    sent = send_offers([offer], bot_token="tok", chat_id="123")

    assert sent == [offer]
    assert rec.calls[-1][0] == "sendMessage"
    assert "Taladro percutor" in rec.calls[-1][1]["text"]


def test_offer_without_image_is_sent_as_text(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offer = make_scored("sodimac:1", image_url="")

    sent = send_offers([offer], bot_token="tok", chat_id="123")

    assert sent == [offer]
    assert [c[0] for c in rec.calls] == ["sendMessage"]


def test_one_failed_offer_does_not_block_the_rest_and_is_not_reported_as_sent(monkeypatch):
    rec = Recorder(fail_methods=("sendPhoto", "sendMessage"))
    install(monkeypatch, rec)
    offers = [make_scored("sodimac:1"), make_scored("sodimac:2")]

    sent = send_offers(offers, bot_token="tok", chat_id="123")

    assert sent == []          # nothing delivered, nothing reported as sent
    assert len(rec.calls) >= 4  # each offer was still attempted (photo+text)


def test_retries_once_after_telegram_rate_limit(monkeypatch):
    calls = {"n": 0}

    def post(url, json=None, data=None, files=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(429, payload={"parameters": {"retry_after": 1}})
        return FakeResponse(200)

    monkeypatch.setattr("notifier.requests.post", post)
    monkeypatch.setattr("notifier.requests.get", lambda url, **kw: FakeResponse(200))
    monkeypatch.setattr("notifier.time.sleep", lambda s: None)

    sent = send_offers([make_scored("sodimac:1")], bot_token="tok", chat_id="123")

    assert len(sent) == 1
    assert calls["n"] == 2


def test_caption_is_html_escaped_and_within_telegram_limit():
    offer = make_scored("sodimac:1", title="Taladro <b>&</b> " + "x" * 3000)
    text = format_offer(offer)
    assert "<b>&</b>" not in text
    assert "&lt;b&gt;" in text
    assert len(text) <= 1024


def test_format_offer_shows_store_prices_discount_and_link():
    offer = make_scored("sodimac:1", price=149990, store="falabella", discount_pct=32.0)
    text = format_offer(offer)
    assert "Falabella" in text
    assert "$149.990" in text
    assert "$159.990" in text           # list price (price + 10000 in the helper)
    assert "https://www.falabella.cl/product/sodimac:1" in text
