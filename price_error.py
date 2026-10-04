"""Possible pricing mistakes: prices that fell far more than any sale does.

A store's own "was $X" proves nothing (it is the thing a sale inflates), so the signals are the ones
we can see ourselves:

* the price is at most 20 % of what we last saw it at, or of the lowest price we ever saw
  (a drop of 80 % or more in one step);
* Falabella and Sodimac share one catalogue: the same product costs less than half in one of them.

Two guards keep ordinary sales out. A product has to have been worth a minimum before the drop
(an item that fell from $4,000 to $500 is not worth an alert), and a *campaign* is not a mistake: when
many products of one store drop by the same percentage in the same scan (a brand's "70 % off everything"),
nobody mispriced anything.

Pure functions: no network, no files.
"""

from __future__ import annotations

from collections import Counter

from models import Deal, ScoredDeal

# At most this share of the previous price (0.2 = a drop of 80 % or more).
MAX_PRICE_SHARE = 0.20
# At most this share of the sister store's price for the same SKU.
MAX_CROSS_STORE_SHARE = 0.50
# The product has to have been worth at least this before for the drop to matter (CLP).
MIN_REFERENCE_PRICE = 15_000
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


def find_price_errors(deals: list[Deal], history: dict) -> dict[str, tuple[str, float]]:
    """Deal id -> (reason, percentage below the reference price). ``history`` must still be the one from
    before this scan (the scan's own prices not yet recorded)."""
    campaigns = _campaign_drops(deals, history)
    sisters = _sister_prices(deals)
    found: dict[str, tuple[str, float]] = {}

    for deal in deals:
        reference = _history_reference(deal, history)
        if reference is not None:
            reference_price, label = reference
            drop = _drop_pct(reference_price, deal.price)
            if (
                deal.price <= reference_price * MAX_PRICE_SHARE
                and (deal.store, drop) not in campaigns
            ):
                found[deal.id] = (
                    f"bajó de {_clp(reference_price)} a {_clp(deal.price)} (-{drop}% vs {label})",
                    float(drop),
                )
                continue

        if deal.store in SISTER_STORES:
            other_store = SISTER_STORES[1 - SISTER_STORES.index(deal.store)]
            other_price = sisters.get(deal.id.split(":", 1)[1], {}).get(other_store)
            if (
                other_price is not None
                and other_price >= MIN_REFERENCE_PRICE
                and deal.price <= other_price * MAX_CROSS_STORE_SHARE
            ):
                drop = _drop_pct(other_price, deal.price)
                found[deal.id] = (
                    f"cuesta {_clp(deal.price)} en {deal.store.title()} y {_clp(other_price)} en {other_store.title()} "
                    f"(-{drop}% frente a la otra tienda)",
                    float(drop),
                )
    return found
