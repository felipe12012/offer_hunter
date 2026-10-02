# tests/test_deal_filter.py
from deal_filter import evaluate
from models import Deal

WATCHLIST = {
    "categories": ["tecnologia", "herramientas"],
    "keywords": ["taladro"],
    "min_discount_pct": 30,
    "min_real_discount_pct": 15,
}


def make_deal(price: int, list_price: int, category: str = "herramientas", title: str = "Taladro percutor") -> Deal:
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    return Deal(
        id="sodimac:123",
        title=title,
        url="https://www.sodimac.cl/sodimac-cl/product/123/taladro/123/",
        store="sodimac",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at="2026-10-01T12:00:00+00:00",
    )


def test_rejects_deal_outside_watchlist_categories_and_keywords():
    deal = make_deal(9990, 9990, category="ropa", title="Polera de algodon")
    assert evaluate(deal, WATCHLIST, {}) is None


def test_category_and_keyword_matching_is_case_insensitive_substring():
    deal = make_deal(6990, 9990, category="Herramientas Electricas", title="Oferta")
    # 30% off ($6990 vs $9990) qualifies once history confirms it sold near $9990
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 9990}]}
    result = evaluate(deal, WATCHLIST, history)
    assert result is not None


def test_qualifies_via_list_price_discount_when_history_confirms_list_price():
    deal = make_deal(6990, 9990)  # 30.03% off
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 9990}]}
    result = evaluate(deal, WATCHLIST, history)
    assert result is not None
    assert result.real_discount_pct == 30.0  # also a real drop vs the $9.990 it sold at
    assert any("precio normal" in reason and "confirmado" in reason for reason in result.reasons)


def test_rejects_advertised_discount_with_no_history_as_unverified():
    deal = make_deal(6990, 9990)  # 30% off, but nothing proves $9990 was ever charged
    assert evaluate(deal, WATCHLIST, {}) is None


def test_rejects_inflated_list_price_never_charged_in_history():
    # Store now shows "was $20.000, now $12.000" (-40%) but we only ever saw it at ~$12.000.
    deal = make_deal(12000, 20000)
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 12500}, {"date": "2026-09-15", "price": 12000}]}
    assert evaluate(deal, WATCHLIST, history) is None


def test_list_price_confirmation_allows_small_tolerance():
    deal = make_deal(6990, 10000)  # 30.1% off
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 9600}]}  # within 5% of 10000
    assert evaluate(deal, WATCHLIST, history) is not None


def test_verification_can_be_disabled_in_watchlist():
    deal = make_deal(6990, 9990)
    watchlist = {**WATCHLIST, "verify_advertised_discount": False}
    assert evaluate(deal, watchlist, {}) is not None


def test_rejects_when_discount_below_threshold_and_no_history():
    deal = make_deal(9000, 9990)  # ~9.9% off, below 30% and no history to check
    assert evaluate(deal, WATCHLIST, {}) is None


def test_qualifies_via_real_discount_against_history_even_if_list_price_discount_is_small():
    deal = make_deal(16990, 17990)  # ~5.6% off list price, below min_discount_pct
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 24990}]}
    # vs historical min 24990: (24990-16990)/24990 = 32% real discount, clears 15%
    result = evaluate(deal, WATCHLIST, history)
    assert result is not None
    assert result.real_discount_pct == 32.0
    assert any("historico" in reason for reason in result.reasons)


def test_price_increase_vs_history_does_not_qualify_via_real_discount():
    deal = make_deal(9000, 9990)  # below list-price threshold too
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 5000}]}  # price went UP
    assert evaluate(deal, WATCHLIST, history) is None


def test_single_historical_snapshot_does_not_crash_and_is_its_own_minimum():
    deal = make_deal(5000, 5000)  # no list-price discount at all
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 5000}]}
    assert evaluate(deal, WATCHLIST, history) is None


def test_history_only_offer_ignores_the_stores_inflated_percentage():
    # Web claims -78% (crossed-out $50.000) but history only ever saw ~$20.000,
    # so the claim can't be confirmed. It still qualifies as a real drop vs
    # history (20.000 -> 11.000 = -45%), and that is the percentage to trust.
    deal = make_deal(11000, 50000)
    history = {"sodimac:123": [{"date": "2026-09-20", "price": 20000}]}
    result = evaluate(deal, WATCHLIST, history)
    assert result is not None
    assert result.real_discount_pct == 45.0
    assert result.verified_pct == 45.0
    assert result.advertised_confirmed is False


def test_confirmed_advertised_discount_is_trusted_as_the_verified_percentage():
    deal = make_deal(6990, 9990)                          # web: -30%
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 9990}]}
    result = evaluate(deal, WATCHLIST, history)
    assert result.advertised_confirmed is True
    assert result.verified_pct == max(result.real_discount_pct, deal.discount_pct)
