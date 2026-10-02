import os

import requests

from models import ScoredDeal

TELEGRAM_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_DEALS_PER_DIGEST = 5
# Per-store ceiling, so a single store with many discounted items can't fill the
# whole digest and crowd out the other five sources.
MAX_DEALS_PER_STORE = 2
MAX_TELEGRAM_TEXT_LENGTH = 4000


def _rank_key(scored: ScoredDeal) -> float:
    # A deal qualifies either on a real drop against its own price history, or
    # on the store's own advertised discount. Ranking on real_discount_pct
    # alone tied every store without history at 0.0, so a freshly added source's
    # 60%-off items could never outrank an old source's tiny history drop.
    return max(scored.real_discount_pct, scored.deal.discount_pct)


def _select_offers(scored_deals: list[ScoredDeal]) -> list[ScoredDeal]:
    ordered = sorted(scored_deals, key=_rank_key, reverse=True)

    per_store: dict[str, int] = {}
    picked: list[ScoredDeal] = []
    for scored in ordered:
        count = per_store.get(scored.deal.store, 0)
        if count >= MAX_DEALS_PER_STORE:
            continue
        per_store[scored.deal.store] = count + 1
        picked.append(scored)

    return picked[:MAX_DEALS_PER_DIGEST]


def _format_clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def format_digest(scored_deals: list[ScoredDeal]) -> str:
    lines = [f"{len(scored_deals)} ofertas top CyberDay:\n"]
    for scored in scored_deals:
        deal = scored.deal
        reasons_text = ", ".join(scored.reasons)
        lines.append(
            f"*{deal.title}* @ {deal.store} - {reasons_text}\n"
            f"{deal.url}\n"
            f"Ahora: {_format_clp(deal.price)}\n"
        )
    return "\n".join(lines)


def send_digest(
    scored_deals: list[ScoredDeal],
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> bool:
    if not scored_deals:
        return False

    top = _select_offers(scored_deals)

    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    text = format_digest(top)
    if len(text) > MAX_TELEGRAM_TEXT_LENGTH:
        text = text[:MAX_TELEGRAM_TEXT_LENGTH]

    response = requests.post(
        TELEGRAM_URL_TEMPLATE.format(token=bot_token),
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    response.raise_for_status()
    return True
