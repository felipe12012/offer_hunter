import os

import requests

from models import ScoredDeal

TELEGRAM_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_DEALS_PER_DIGEST = 5
MAX_TELEGRAM_TEXT_LENGTH = 4000


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

    top = sorted(scored_deals, key=lambda s: s.real_discount_pct, reverse=True)[:MAX_DEALS_PER_DIGEST]

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
