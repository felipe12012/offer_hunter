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
    # 30% off ($6990 vs $9990) qualifies on list-price discount alone
    result = evaluate(deal, WATCHLIST, {})
    assert result is not None


def test_qualifies_via_list_price_discount_with_no_history():
    deal = make_deal(6990, 9990)  # 30.03% off
    result = evaluate(deal, WATCHLIST, {})
    assert result is not None
    assert result.real_discount_pct == 0.0
    assert any("precio normal" in reason for reason in result.reasons)


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
