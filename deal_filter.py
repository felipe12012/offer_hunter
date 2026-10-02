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


def evaluate(deal: Deal, watchlist: dict, history: dict) -> ScoredDeal | None:
    if not _matches_watchlist(deal, watchlist):
        return None

    min_discount_pct = watchlist.get("min_discount_pct", 0)
    min_real_discount_pct = watchlist.get("min_real_discount_pct", 0)

    reasons = []
    qualifies = False

    if deal.discount_pct >= min_discount_pct:
        qualifies = True
        reasons.append(f"-{deal.discount_pct:.0f}% vs precio normal")

    real_discount_pct = 0.0
    historical_min = _historical_min(deal, history)
    if historical_min is not None and deal.price < historical_min:
        real_discount_pct = round((historical_min - deal.price) / historical_min * 100, 1)
        if real_discount_pct >= min_real_discount_pct:
            qualifies = True
            reasons.append(f"-{real_discount_pct:.0f}% vs minimo historico (${historical_min:,})".replace(",", "."))

    if not qualifies:
        return None

    return ScoredDeal(deal=deal, real_discount_pct=real_discount_pct, reasons=reasons)
