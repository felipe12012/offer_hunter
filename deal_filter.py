from models import Deal, ScoredDeal


def _matches_watchlist(deal: Deal, watchlist: dict) -> bool:
    categories = [c.lower() for c in watchlist.get("categories", [])]
    keywords = [k.lower() for k in watchlist.get("keywords", [])]
    haystack = f"{deal.category} {deal.title}".lower()
    if any(cat in haystack for cat in categories):
        return True
    if any(kw in haystack for kw in keywords):
        return True
    return False


def _historical_min(deal: Deal, history: dict) -> int | None:
    snapshots = history.get(deal.id)
    if not snapshots:
        return None
    return min(snapshot["price"] for snapshot in snapshots)


# A store's "normal price" only counts if we have actually seen the product
# selling at (roughly) that price before. Otherwise it may be an inflated
# crossed-out figure shown just to make the sale price look like a bargain.
LIST_PRICE_TOLERANCE = 0.05


def _confirmed_list_price(deal: Deal, history: dict) -> int | None:
    """Highest price this item was previously seen selling at, if it is within
    tolerance of the advertised list price; None if the list price is unproven."""
    snapshots = history.get(deal.id)
    if not snapshots:
        return None
    highest = max(snapshot["price"] for snapshot in snapshots)
    if highest >= deal.list_price * (1 - LIST_PRICE_TOLERANCE):
        return highest
    return None


def _format_clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def evaluate(deal: Deal, watchlist: dict, history: dict) -> ScoredDeal | None:
    if not _matches_watchlist(deal, watchlist):
        return None

    min_discount_pct = watchlist.get("min_discount_pct", 0)
    min_real_discount_pct = watchlist.get("min_real_discount_pct", 0)

    reasons = []
    qualifies = False
    advertised_confirmed = False

    if deal.discount_pct >= min_discount_pct:
        if watchlist.get("verify_advertised_discount", True):
            confirmed = _confirmed_list_price(deal, history)
            if confirmed is not None:
                qualifies = True
                advertised_confirmed = True
                reasons.append(
                    f"-{deal.discount_pct:.0f}% vs precio normal "
                    f"(confirmado: se vendio a {_format_clp(confirmed)})"
                )
        else:
            qualifies = True
            advertised_confirmed = True  # the user opted out of verification
            reasons.append(f"-{deal.discount_pct:.0f}% vs precio normal")

    real_discount_pct = 0.0
    historical_min = _historical_min(deal, history)
    if historical_min is not None and deal.price < historical_min:
        real_discount_pct = round((historical_min - deal.price) / historical_min * 100, 1)
        if real_discount_pct >= min_real_discount_pct:
            qualifies = True
            reasons.append(f"-{real_discount_pct:.0f}% vs minimo historico ({_format_clp(historical_min)})")

    if not qualifies:
        return None

    # A store percentage is only trusted when history confirmed its list price;
    # otherwise rank and announce by our own history-based drop.
    verified_pct = max(real_discount_pct, deal.discount_pct if advertised_confirmed else 0.0)
    return ScoredDeal(
        deal=deal,
        real_discount_pct=real_discount_pct,
        reasons=reasons,
        verified_pct=verified_pct,
        advertised_confirmed=advertised_confirmed or deal.discount_pct <= 0,
    )
