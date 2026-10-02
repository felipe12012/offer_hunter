# tests/test_models.py
from models import Deal, ScoredDeal


def make_deal(**overrides) -> Deal:
    defaults = dict(
        id="sodimac:123",
        title="Taladro percutor",
        url="https://www.sodimac.cl/sodimac-cl/product/123/taladro/123/",
        store="sodimac",
        category="herramientas",
        price=29990,
        list_price=39990,
        discount_pct=25.0,
        scraped_at="2026-10-01T12:00:00+00:00",
    )
    defaults.update(overrides)
    return Deal(**defaults)


def test_deal_is_frozen_and_holds_fields():
    deal = make_deal()
    assert deal.id == "sodimac:123"
    assert deal.price == 29990
    try:
        deal.price = 1
        assert False, "Deal should be immutable"
    except AttributeError:
        pass


def test_scored_deal_wraps_deal_with_reasons():
    deal = make_deal()
    scored = ScoredDeal(deal=deal, real_discount_pct=10.0, reasons=["-25% vs precio normal"])
    assert scored.deal is deal
    assert scored.real_discount_pct == 10.0
    assert scored.reasons == ["-25% vs precio normal"]
