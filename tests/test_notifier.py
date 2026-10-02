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
    title: str | None = None,
    category: str = "herramientas",
) -> ScoredDeal:
    deal = Deal(
        id=deal_id,
        title=title if title is not None else f"Taladro percutor {deal_id}",
        url=f"https://www.{store}.cl/product/{deal_id}",
        store=store,
        category=category,
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
    for name in ("TELEGRAM_ALERT_CHAT_ID", "TELEGRAM_ALERT_THREAD_ID"):
        monkeypatch.delenv(name, raising=False)
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


def test_every_category_gets_a_message_before_any_category_repeats(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    # 30 clothing offers at 80% and a single tablet at 40%: ranking by discount
    # alone buries the tablet below all 30, so it never gets sent.
    offers = [
        make_scored(f"hites:r{i}", store="hites", title=f"Polera {i}", category="ropa", discount_pct=80.0)
        for i in range(30)
    ]
    offers.append(
        make_scored("falabella:t1", store="falabella", title="Tablet Samsung", category="tablet", discount_pct=40.0)
    )

    send_offers(offers, bot_token="tok", chat_id="123")

    captions = [c[1]["caption"] for c in rec.calls]
    assert any("Tablet Samsung" in caption for caption in captions[:2])


def test_dedupes_same_title_within_a_store_keeping_the_best_rank(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offers = [
        make_scored("hites:1", store="hites", title="Polera de pijama", discount_pct=50.0),
        make_scored("hites:2", store="hites", title="Polera  de   pijama ", discount_pct=80.0),
        make_scored("falabella:3", store="falabella", title="Polera de pijama", discount_pct=60.0),
    ]

    send_offers(offers, bot_token="tok", chat_id="123")

    # The product link now lives in the button, so identify offers by its URL.
    urls = [c[1]["reply_markup"]["inline_keyboard"][0][0]["url"] for c in rec.calls]
    assert len(urls) == 2  # one per store
    assert any("hites:2" in url for url in urls)      # the 80% one survives
    assert not any("hites:1" in url for url in urls)
    assert any("falabella:3" in url for url in urls)  # other store is not collapsed


ALERTS = {
    "tiers": [
        {"min_pct": 90, "label": "🚨🚨🚨 SUPER OFERTA"},
        {"min_pct": 80, "label": "🚨 OFERTAZA"},
        {"min_pct": 60, "label": "🔥 GRAN OFERTA"},
    ],
}


def test_default_tiers_put_a_loud_header_on_90_percent_and_up():
    text = format_offer(make_scored("sodimac:1", discount_pct=92.0, real_discount_pct=0.0))
    assert text.splitlines()[0].startswith("🚨🚨🚨")
    assert "-92%" in text.splitlines()[0]


def test_default_tiers_label_80_percent_differently_from_90():
    text = format_offer(make_scored("sodimac:1", discount_pct=85.0, real_discount_pct=0.0))
    assert text.splitlines()[0].startswith("🚨")
    assert not text.splitlines()[0].startswith("🚨🚨🚨")


def test_tier_uses_the_larger_of_advertised_and_historical_discount():
    text = format_offer(make_scored("sodimac:1", discount_pct=10.0, real_discount_pct=91.0))
    assert text.splitlines()[0].startswith("🚨🚨🚨")


def test_ordinary_offer_keeps_the_plain_header():
    text = format_offer(make_scored("sodimac:1", discount_pct=35.0, real_discount_pct=0.0))
    assert text.splitlines()[0].startswith("🔥 <b>")


def test_extreme_discount_warns_it_may_be_a_price_error():
    extreme = format_offer(make_scored("sodimac:1", discount_pct=88.0, real_discount_pct=0.0))
    ordinary = format_offer(make_scored("sodimac:2", discount_pct=40.0, real_discount_pct=0.0))
    assert "error de precio" in extreme
    assert "error de precio" not in ordinary


def test_tiers_can_be_overridden_from_the_watchlist():
    custom = {"tiers": [{"min_pct": 50, "label": "⭐ BUENA"}]}
    text = format_offer(make_scored("sodimac:1", discount_pct=55.0, real_discount_pct=0.0), alerts=custom)
    assert text.splitlines()[0].startswith("⭐ BUENA")


def test_offers_notify_with_sound_by_default(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    send_offers([make_scored("sodimac:1", discount_pct=35.0)], bot_token="tok", chat_id="123")
    assert "disable_notification" not in rec.calls[0][1]


def test_low_discounts_are_silent_but_big_ones_still_ring_when_configured(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    alerts = {**ALERTS, "silent_below_pct": 60}
    offers = [
        make_scored("sodimac:small", discount_pct=35.0, real_discount_pct=0.0),
        make_scored("sodimac:big", discount_pct=85.0, real_discount_pct=0.0),
    ]

    send_offers(offers, bot_token="tok", chat_id="123", alerts=alerts)

    by_id = {("big" if "sodimac:big" in c[1]["caption"] else "small"): c[1] for c in rec.calls}
    assert by_id["big"].get("disable_notification") in (None, False)
    assert by_id["small"]["disable_notification"] is True


def test_silent_flag_also_applies_to_text_fallback(monkeypatch):
    rec = Recorder(fail_methods=("sendPhoto",))
    install(monkeypatch, rec)
    send_offers(
        [make_scored("sodimac:1", discount_pct=35.0, real_discount_pct=0.0)],
        bot_token="tok", chat_id="123", alerts={"silent_below_pct": 60},
    )
    assert rec.calls[-1][0] == "sendMessage"
    assert rec.calls[-1][1]["disable_notification"] is True


def _history_only_offer():
    scored = make_scored("sodimac:1", discount_pct=78.0, real_discount_pct=45.0)
    return ScoredDeal(deal=scored.deal, real_discount_pct=45.0, reasons=scored.reasons,
                      verified_pct=45.0, advertised_confirmed=False)


def test_header_and_ranking_use_the_verified_percentage_not_the_web_one():
    from notifier import _rank_key
    offer = _history_only_offer()
    assert _rank_key(offer) == 45.0
    text = format_offer(offer)
    assert "-78%" not in text.splitlines()[0]


def test_unconfirmed_web_discount_is_flagged_instead_of_shown_as_the_discount():
    text = format_offer(_history_only_offer())
    assert "<s>" not in text                      # no crossed-out price presented as fact
    assert "no verificado" in text
    assert "78%" in text                           # but the user can still see what the web claims
    assert "error de precio" not in text           # 45% verified is not an extreme discount


# ---- link button -----------------------------------------------------------

def _keyboard(body):
    markup = body["reply_markup"]
    if isinstance(markup, str):          # multipart uploads carry it as a JSON string
        import json as _json
        markup = _json.loads(markup)
    return markup["inline_keyboard"]


def test_photo_message_has_a_link_button_instead_of_a_caption_link(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offer = make_scored("sodimac:1", store="falabella")

    send_offers([offer], bot_token="tok", chat_id="123")

    body = rec.calls[0][1]
    button = _keyboard(body)[0][0]
    assert button["url"] == offer.deal.url
    assert "Ir a la oferta" in button["text"]
    assert "Ver oferta" not in body["caption"]      # the link moved out of the caption


def test_text_fallback_and_uploaded_photo_keep_the_button(monkeypatch):
    rec = Recorder(fail_methods=("sendPhoto",))
    install(monkeypatch, rec)
    send_offers([make_scored("sodimac:1")], bot_token="tok", chat_id="123")
    assert _keyboard(rec.calls[-1][1])[0][0]["url"].startswith("https://")

    rec2 = Recorder(fail_photo_for=("blocked",))
    install(monkeypatch, rec2)
    send_offers([make_scored("sodimac:2", image_url="https://img.example/blocked.jpg")], bot_token="tok", chat_id="123")
    assert rec2.calls[1][2] is not None                    # second attempt is the upload
    assert _keyboard(rec2.calls[1][1])[0][0]["url"].startswith("https://")


def test_offer_with_an_unusable_url_gets_no_button_so_telegram_cannot_reject_it(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offer = make_scored("sodimac:1")
    bad = ScoredDeal(
        deal=Deal(**{**offer.deal.__dict__, "url": "not-a-url"}),
        real_discount_pct=20.0, reasons=offer.reasons,
    )

    sent = send_offers([bad], bot_token="tok", chat_id="123")

    assert sent == [bad]
    assert "reply_markup" not in rec.calls[0][1]


def test_format_offer_still_includes_the_link_by_default():
    assert "https://www.sodimac.cl/product/sodimac:1" in format_offer(make_scored("sodimac:1"))


# ---- separate destination for big discounts -------------------------------

def _chat(call):
    return str(call[1]["chat_id"])


def _by_chat(rec):
    result = {}
    for call in rec.calls:
        result.setdefault(_chat(call), []).append(call)
    return result


BIG = dict(discount_pct=85.0, real_discount_pct=0.0)
SMALL = dict(discount_pct=35.0, real_discount_pct=0.0)


def test_big_discounts_go_to_the_alert_chat_and_the_rest_to_the_main_chat(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offers = [make_scored("sodimac:big", **BIG), make_scored("sodimac:small", **SMALL)]

    sent = send_offers(offers, bot_token="tok", chat_id="MAIN", alert_chat_id="ALERT")

    assert len(sent) == 2
    chats = _by_chat(rec)
    assert "sodimac:big" in chats["ALERT"][0][1]["caption"]
    assert "sodimac:small" in chats["MAIN"][0][1]["caption"]
    assert len(chats["ALERT"]) == 1 and len(chats["MAIN"]) == 1


def test_everything_goes_to_the_main_chat_when_no_alert_chat_is_configured(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    send_offers([make_scored("sodimac:big", **BIG), make_scored("sodimac:small", **SMALL)],
                bot_token="tok", chat_id="MAIN")
    assert set(_by_chat(rec)) == {"MAIN"}


def test_alert_chat_can_come_from_the_environment(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "ENVALERT")
    send_offers([make_scored("sodimac:big", **BIG)], bot_token="tok", chat_id="MAIN")
    assert set(_by_chat(rec)) == {"ENVALERT"}


def test_empty_alert_chat_env_is_treated_as_unset(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "")   # an unset GitHub secret arrives as ""
    send_offers([make_scored("sodimac:big", **BIG)], bot_token="tok", chat_id="MAIN")
    assert set(_by_chat(rec)) == {"MAIN"}


def test_alert_chat_threshold_is_configurable(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    send_offers([make_scored("sodimac:mid", discount_pct=65.0, real_discount_pct=0.0)],
                bot_token="tok", chat_id="MAIN", alert_chat_id="ALERT", alerts={"alert_chat_min_pct": 60})
    assert set(_by_chat(rec)) == {"ALERT"}


def test_alert_topic_is_applied_only_to_alert_messages(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    send_offers([make_scored("sodimac:big", **BIG), make_scored("sodimac:small", **SMALL)],
                bot_token="tok", chat_id="MAIN", alert_chat_id="ALERT", alert_thread_id="7")
    chats = _by_chat(rec)
    assert chats["ALERT"][0][1]["message_thread_id"] == 7
    assert "message_thread_id" not in chats["MAIN"][0][1]


def test_a_broken_alert_chat_falls_back_to_the_main_chat_instead_of_losing_the_offer(monkeypatch):
    class AlertDown(Recorder):
        def __call__(self, url, json=None, data=None, files=None, timeout=None):
            body = json if json is not None else data
            if str(body.get("chat_id")) == "ALERT":
                self.calls.append((url.rsplit("/", 1)[-1], body, files))
                return FakeResponse(400)
            return super().__call__(url, json=json, data=data, files=files, timeout=timeout)

    rec = AlertDown()
    install(monkeypatch, rec)
    offer = make_scored("sodimac:big", **BIG)

    sent = send_offers([offer], bot_token="tok", chat_id="MAIN", alert_chat_id="ALERT")

    assert sent == [offer]
    assert "MAIN" in _by_chat(rec)


def test_alert_chat_messages_always_ring_even_when_small_offers_are_silent(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    alerts = {"silent_below_pct": 95}                     # would silence the 85% offer in the main chat
    send_offers([make_scored("sodimac:big", **BIG), make_scored("sodimac:small", **SMALL)],
                bot_token="tok", chat_id="MAIN", alert_chat_id="ALERT", alerts=alerts)
    chats = _by_chat(rec)
    assert "disable_notification" not in chats["ALERT"][0][1]
    assert chats["MAIN"][0][1]["disable_notification"] is True
