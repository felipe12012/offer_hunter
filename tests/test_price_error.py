from models import Deal, ScoredDeal
from notifier import MAX_PRICE_ERRORS_PER_RUN, format_offer, send_offers
from price_error import CAMPAIGN_SIZE, MIN_REFERENCE_PRICE, as_scored, find_price_errors
from tests.test_notifier import Recorder, _by_chat, install, make_scored


def deal(deal_id, price, list_price=None, store=None, title="Producto"):
    store = store or deal_id.split(":")[0]
    list_price = list_price or price
    return Deal(
        id=deal_id, title=title, url=f"https://shop/{deal_id}", store=store, category="x", price=price,
        list_price=list_price, discount_pct=0.0, scraped_at="2026-10-05T03:00:00+00:00", image_url="https://img/x.jpg",
    )


def history_of(*prices_by_id):
    return {i: [{"date": "2026-10-04", "price": p} for p in prices] for i, prices in prices_by_id}


# ---- detection ------------------------------------------------------------------------------------

def test_a_drop_of_85_percent_or_more_from_the_last_price_is_flagged():
    found = find_price_errors([deal("falabella:1", 15_000)], history_of(("falabella:1", [100_000])))
    reason, drop = found["falabella:1"]
    assert drop == 85.0 and "último precio visto" in reason and "$100.000" in reason and "$15.000" in reason


def test_the_lowest_price_ever_seen_also_counts():
    history = history_of(("falabella:1", [90_000, 60_000, 70_000]))
    assert "falabella:1" not in find_price_errors([deal("falabella:1", 20_000)], history)  # vs 70k: -71 %
    history = history_of(("falabella:1", [150_000, 90_000, 150_000]))
    # vs the last (150k): -87 %
    assert "falabella:1" in find_price_errors([deal("falabella:1", 20_000)], history)


def test_an_ordinary_sale_is_not_a_mistake():
    history = history_of(("falabella:1", [100_000]))
    for price in (50_000, 40_000, 30_000, 20_000):  # -50 %, -60 %, -70 %, -80 %: sales, however deep
        assert find_price_errors([deal("falabella:1", price)], history) == {}


def test_cheap_products_are_never_worth_an_alert():
    history = history_of(("falabella:1", [MIN_REFERENCE_PRICE - 1]))
    assert find_price_errors([deal("falabella:1", 500)], history) == {}


def test_a_product_never_seen_before_has_nothing_to_compare_with():
    assert find_price_errors([deal("falabella:1", 500)], {}) == {}


def test_a_campaign_is_not_a_mistake():
    """Many products of one store dropping by the same percentage: a brand's 'everything 80% off'."""
    ids = [f"hushpuppies:{i}" for i in range(CAMPAIGN_SIZE)]
    history = history_of(*[(i, [100_000]) for i in ids])
    deals = [deal(i, 15_000) for i in ids]
    assert find_price_errors(deals, history) == {}
    # one fewer is a coincidence, not a campaign
    assert len(find_price_errors(deals[: CAMPAIGN_SIZE - 1], history)) == CAMPAIGN_SIZE - 1


def test_a_fifth_of_the_price_in_the_sister_store_is_flagged():
    deals = [deal("falabella:77", 10_000), deal("sodimac:77", 60_000)]
    found = find_price_errors(deals, {})
    reason, drop = found["falabella:77"]
    assert "sodimac:77" not in found
    assert "Falabella" in reason and "Sodimac" in reason and drop == 83.0


def test_half_the_price_in_the_sister_store_is_just_a_cheaper_store():
    """The two stores price the same SKU differently all the time: -50 % or -67 % between them is normal."""
    assert find_price_errors([deal("falabella:77", 30_000), deal("sodimac:77", 60_000)], {}) == {}
    assert find_price_errors([deal("falabella:77", 20_000), deal("sodimac:77", 60_000)], {}) == {}


def test_similar_prices_in_the_sister_store_are_normal():
    assert find_price_errors([deal("falabella:77", 55_000), deal("sodimac:77", 60_000)], {}) == {}


# ---- a missing digit --------------------------------------------------------------------------------

def test_a_missing_zero_against_a_price_we_saw_is_flagged():
    """$150,000 typed as $15,000."""
    found = find_price_errors([deal("falabella:5", 15_000)], history_of(("falabella:5", [150_000])))
    reason, drop = found["falabella:5"]
    assert "falta" in reason and "un cero" in reason and "$150.000" in reason and drop == 90.0


def test_two_missing_zeros_are_flagged_too():
    found = find_price_errors([deal("falabella:5", 1_500)], history_of(("falabella:5", [150_000])))
    assert "dos ceros" in found["falabella:5"][0]


def test_a_missing_zero_against_the_sister_store_is_flagged_without_any_history():
    deals = [deal("falabella:8", 15_990), deal("sodimac:8", 159_990)]
    found = find_price_errors(deals, {})
    assert "falabella:8" in found and "un cero" in found["falabella:8"][0] and "Sodimac" in found["falabella:8"][0]
    assert "sodimac:8" not in found


def test_the_slip_needs_a_reference_big_enough_for_the_typo_to_matter():
    # 1/10 of $14,000 is below the minimum for both rules; 1/10 of $20,000 is a drop, not a typo worth the name
    assert find_price_errors([deal("falabella:5", 1_400)], history_of(("falabella:5", [14_000]))) == {}


def test_the_stores_own_normal_price_alone_proves_nothing():
    """A crossed-out $150,000 next to $15,000 is how a seller advertises 90 % off: no history, no flag."""
    assert find_price_errors([deal("falabella:6", 15_000, list_price=150_000)], {}) == {}


def test_an_ordinary_discount_is_not_a_missing_digit():
    assert find_price_errors([deal("falabella:5", 75_000)], history_of(("falabella:5", [150_000]))) == {}


def test_only_the_sister_stores_are_compared_with_each_other():
    deals = [deal("hites:77", 20_000), deal("sodimac:77", 60_000)]
    assert find_price_errors(deals, {}) == {}


# ---- the announcement -----------------------------------------------------------------------------

def mistake(deal_id, drop=85.0, store="falabella"):
    return as_scored(deal(deal_id, 15_000, store=store), f"bajó (-{drop:.0f}%)", drop)


def test_the_alert_says_what_it_is_and_warns_about_cancellations():
    text = format_offer(mistake("falabella:1"))
    assert "POSIBLE ERROR DE PRECIO" in text and "bajó" in text and "cancelar" in text and "Ver oferta" in text


def test_a_mistake_is_not_an_unconfirmed_claim():
    scored = mistake("falabella:1")
    assert scored.advertised_confirmed and scored.price_error


def test_mistakes_go_first_to_the_alert_chat_and_everyone_else_after(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offers = [make_scored("sodimac:ok", discount_pct=10.0), mistake("falabella:9")]

    sent = send_offers(offers, bot_token="tok", chat_id="MAIN", alert_chat_id="ALERT")

    assert len(sent) == 2
    chats = _by_chat(rec)
    assert "POSIBLE ERROR" in chats["ALERT"][0][1]["caption"]
    assert len(chats["ALERT"]) == 1 and len(chats["MAIN"]) == 1
    assert rec.calls[0][1]["chat_id"] == "ALERT"          # sent before the ordinary offer


def test_mistakes_are_capped_per_run_and_the_rest_wait_for_the_next_one(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    offers = [mistake(f"falabella:{i}", drop=80.0 + i / 100) for i in range(MAX_PRICE_ERRORS_PER_RUN + 5)]

    sent = send_offers(offers, bot_token="tok", chat_id="MAIN")

    assert len(sent) == MAX_PRICE_ERRORS_PER_RUN
    assert {s.deal.id for s in offers} - {s.deal.id for s in sent} == {
        f"falabella:{i}" for i in range(5)  # the smallest drops are the ones left for later
    }


def test_mistakes_do_not_use_the_unverified_quota(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    sent = send_offers([mistake("falabella:1")], bot_token="tok", chat_id="MAIN", max_unverified=0, max_priority_unverified=0)
    assert len(sent) == 1


def test_subscribers_get_the_mistakes(monkeypatch):
    rec = Recorder()
    install(monkeypatch, rec)
    unconfirmed = ScoredDeal(deal=deal("sodimac:5", 9_000), real_discount_pct=0.0, reasons=[], verified_pct=None,
                             advertised_confirmed=False)
    send_offers([mistake("falabella:1"), unconfirmed], bot_token="tok", chat_id="MAIN", subscriber_chat_ids=[111])
    chats = _by_chat(rec)
    assert len(chats["111"]) == 1 and "POSIBLE ERROR" in chats["111"][0][1]["caption"]


# ---- end to end: found even when the watchlist would not have picked it ---------------------------

def test_the_run_flags_a_mistake_in_a_product_outside_the_watchlist(monkeypatch, tmp_path):
    import json

    import main_fast
    from tests.test_run_reporting import make_deal as run_deal, patch_paths
    from tests.test_workflow import _stub_all_sources

    patch_paths(monkeypatch, tmp_path)  # watchlist: only "herramientas" interests
    (tmp_path / "price_history.json").write_text(
        json.dumps({"falabella:9": [{"date": "2026-10-04", "price": 100_000}]}), encoding="utf-8"
    )
    cheap = run_deal("falabella:9", price=15_000, list_price=15_000)
    cheap = Deal(**{**cheap.__dict__, "title": "Zapatilla Urbana", "category": "zapatillas"})
    _stub_all_sources(monkeypatch, fetch_falabella_deals=lambda watchlist: [cheap])

    sent = {}

    def fake_send(scored, **kwargs):
        sent["offers"] = list(scored)
        return list(scored)

    monkeypatch.setattr(main_fast, "send_offers", fake_send)

    assert main_fast.run() == 0
    [offer] = sent["offers"]
    assert offer.deal.id == "falabella:9" and offer.price_error and "-85%" in offer.price_error
