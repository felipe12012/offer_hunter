"""Possible pricing mistakes: prices that are wrong by far more than any sale makes them.

A store's own "was $X" proves nothing (it is the thing a sale inflates), so the signals are the ones we
can see ourselves, against prices we or the sister store actually showed:

* **a missing digit**: the price is about 1/10 (or 1/100) of a price we saw it at, or of the same product
  in the sister store: $150,000 typed as $15,000. A 50 % or 70 % discount is a sale, not this;
* **an extreme drop**: at most 15 % of what we last saw it at, or of the lowest price we ever saw
  (85 % or more off in one step);
* **an extreme gap with the sister store**: Falabella and Sodimac share one catalogue and one of them
  charges at most 20 % of the other's price.

Guards keep ordinary sales out. A product has to have been worth a minimum (an item that fell from $4,000 to
$500 is not worth an alert), and a *campaign* is not a mistake: when many products of one store drop by the
same percentage in the same scan (a brand's "85 % off everything"), nobody mispriced anything.

Pure functions: no network, no files.
"""

from __future__ import annotations

from collections import Counter

from models import Deal, ScoredDeal

# At most this share of the previous price (0.15 = a drop of 85 % or more).
MAX_PRICE_SHARE = 0.15
# At most this share of the sister store's price for the same SKU.
MAX_CROSS_STORE_SHARE = 0.20
# The product has to have been worth at least this before for the drop to matter (CLP).
MIN_REFERENCE_PRICE = 15_000
# A missing digit: price x factor lands within this tolerance of a reference price. The reference
# has to be big enough for the typo to matter ($150,000 -> $15,000, not $400 -> $40).
DIGIT_SLIP_TOLERANCE = 0.05
DIGIT_SLIPS = ((10, 30_000), (100, 100_000))  # (factor, smallest reference price)
# This many products of a store dropping by the same percentage is a sale, not a mistake.
CAMPAIGN_SIZE = 5
# Falabella and Sodimac list the same SKUs.
SISTER_STORES = ("falabella", "sodimac")


def _clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def _drop_pct(reference: int, price: int) -> int:
    return round((reference - price) / reference * 100)


def _history_reference(deal: Deal, history: dict) -> tuple[int, str] | None:
    """The price to compare with: what we last saw, or the lowest we ever saw, whichever gives the
    bigger drop. None if there is nothing to compare with or the product was never worth much."""
    snapshots = history.get(deal.id) or []
    prior = [s["price"] for s in snapshots if s["price"] != deal.price]
    if not prior:
        return None
    last = snapshots[-1]["price"] if snapshots[-1]["price"] != deal.price else prior[-1]
    candidates = [(last, "último precio visto"), (min(prior), "mínimo histórico")]
    candidates = [(price, label) for price, label in candidates if price >= MIN_REFERENCE_PRICE]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[0])


def _digit_slip(price: int, reference: int) -> int | None:
    """10 or 100 when ``price`` is that many times smaller than ``reference`` (give or take 5 %)."""
    for factor, smallest in DIGIT_SLIPS:
        if reference >= smallest and abs(price * factor - reference) <= reference * DIGIT_SLIP_TOLERANCE:
            return factor
    return None


def _campaign_drops(deals: list[Deal], history: dict) -> set[tuple[str, int]]:
    """(store, drop %) pairs that many products share this scan: those are sales, not mistakes."""
    counts: Counter = Counter()
    for deal in deals:
        reference = _history_reference(deal, history)
        if reference and deal.price < reference[0]:
            counts[(deal.store, _drop_pct(reference[0], deal.price))] += 1
    return {key for key, n in counts.items() if n >= CAMPAIGN_SIZE}


def _sister_prices(deals: list[Deal]) -> dict[str, dict[str, int]]:
    """SKU -> {store: price} for the stores that share a catalogue."""
    by_sku: dict[str, dict[str, int]] = {}
    for deal in deals:
        if deal.store in SISTER_STORES:
            by_sku.setdefault(deal.id.split(":", 1)[1], {})[deal.store] = deal.price
    return by_sku


def as_scored(deal: Deal, reason: str, drop: float) -> ScoredDeal:
    """An offer built only from the mistake signal, for products the watchlist would not have picked."""
    return ScoredDeal(
        deal=deal,
        real_discount_pct=drop,
        reasons=[reason],
        verified_pct=drop,
        advertised_confirmed=True,  # not an unconfirmed store claim: it must not spend the daily quota
        price_error=reason,
    )


def _slip_reason(deal: Deal, history: dict, sister: tuple[str, int] | None) -> tuple[str, float] | None:
    """A missing digit against a price we saw this product at, or the sister store's price."""
    references = [(p, "un precio que vimos") for p in sorted({s["price"] for s in history.get(deal.id) or []}, reverse=True)]
    if sister is not None:
        references.append((sister[1], f"el precio en {sister[0].title()}"))
    for reference, source in references:
        factor = _digit_slip(deal.price, reference)
        if factor is not None:
            zeros = "un cero" if factor == 10 else "dos ceros"
            return (
                f"cuesta {_clp(deal.price)} y {source} es {_clp(reference)}: podría faltarle {zeros} "
                f"(1/{factor} del precio)",
                float(_drop_pct(reference, deal.price)),
            )
    return None


def find_price_errors(deals: list[Deal], history: dict) -> dict[str, tuple[str, float]]:
    """Deal id -> (reason, percentage below the reference price). ``history`` must still be the one from
    before this scan (the scan's own prices not yet recorded)."""
    campaigns = _campaign_drops(deals, history)
    sisters = _sister_prices(deals)
    found: dict[str, tuple[str, float]] = {}

    for deal in deals:
        sister = None
        if deal.store in SISTER_STORES:
            other_store = SISTER_STORES[1 - SISTER_STORES.index(deal.store)]
            other_price = sisters.get(deal.id.split(":", 1)[1], {}).get(other_store)
            if other_price is not None and other_price >= MIN_REFERENCE_PRICE:
                sister = (other_store, other_price)

        slip = _slip_reason(deal, history, sister)
        if slip is not None:
            found[deal.id] = slip
            continue

        reference = _history_reference(deal, history)
        if reference is not None:
            reference_price, label = reference
            drop = _drop_pct(reference_price, deal.price)
            if deal.price <= reference_price * MAX_PRICE_SHARE and (deal.store, drop) not in campaigns:
                found[deal.id] = (
                    f"bajó de {_clp(reference_price)} a {_clp(deal.price)} (-{drop}% vs {label})",
                    float(drop),
                )
                continue

        if sister is not None and deal.price <= sister[1] * MAX_CROSS_STORE_SHARE:
            drop = _drop_pct(sister[1], deal.price)
            found[deal.id] = (
                f"cuesta {_clp(deal.price)} en {deal.store.title()} y {_clp(sister[1])} en {sister[0].title()} "
                f"(-{drop}% frente a la otra tienda)",
                float(drop),
            )
    return found
