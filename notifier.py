import html
import os
import sys
import time

import requests

from models import ScoredDeal

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
# Telegram throttles a single chat to ~1 message/second; stay just under it.
SEND_DELAY_SECONDS = 1.1
# Ceiling per run so a huge sale can't flood the chat. Offers beyond it are not
# reported as sent, so the caller leaves them unseen and they go out next run.
MAX_MESSAGES_PER_RUN = 25
MAX_CAPTION_LENGTH = 1024
MAX_TITLE_LENGTH = 180
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_RETRY_AFTER_SECONDS = 30
IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
}


def _rank_key(scored: ScoredDeal) -> float:
    # A deal qualifies either on a real drop against its own price history, or
    # on the store's own advertised discount. Rank on whichever is larger.
    return max(scored.real_discount_pct, scored.deal.discount_pct)


def _format_clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def format_offer(scored: ScoredDeal, max_title: int = MAX_TITLE_LENGTH) -> str:
    deal = scored.deal
    title = deal.title if len(deal.title) <= max_title else deal.title[: max_title - 1] + "…"
    lines = [f"🔥 <b>{html.escape(title)}</b>", f"🏬 {html.escape(deal.store.title())}"]

    price_line = f"💰 <b>{_format_clp(deal.price)}</b>"
    if deal.list_price > deal.price:
        price_line += f"  <s>{_format_clp(deal.list_price)}</s>"
    if deal.discount_pct > 0:
        price_line += f"  (-{deal.discount_pct:.0f}%)"
    lines.append(price_line)

    for reason in scored.reasons:
        lines.append(f"✅ {html.escape(reason[:200])}")

    lines.append(f'🔗 <a href="{html.escape(deal.url, quote=True)}">Ver oferta</a>')
    text = "\n".join(lines)
    if len(text) > MAX_CAPTION_LENGTH and max_title > 60:
        return format_offer(scored, max_title=60)
    return text


def _post(token: str, method: str, **kwargs) -> bool:
    """POST to the Telegram Bot API. Returns True on success. Waits and retries
    once when Telegram answers 429 (rate limited)."""
    url = TELEGRAM_API.format(token=token, method=method)
    for attempt in (1, 2):
        try:
            response = requests.post(url, timeout=30, **kwargs)
        except requests.RequestException as exc:
            print(f"Telegram {method} request error: {exc}", file=sys.stderr)
            return False
        if response.status_code == 429 and attempt == 1:
            try:
                wait = float(response.json().get("parameters", {}).get("retry_after", 1))
            except Exception:
                wait = 1.0
            time.sleep(min(wait, MAX_RETRY_AFTER_SECONDS))
            continue
        if response.status_code >= 400:
            print(f"Telegram {method} failed with HTTP {response.status_code}", file=sys.stderr)
            return False
        return True
    return False


def _download_image(url: str) -> bytes | None:
    try:
        response = requests.get(url, headers=IMAGE_HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None
    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("image/") or not response.content:
        return None
    if len(response.content) > MAX_IMAGE_BYTES:
        return None
    return response.content


def _send_one(scored: ScoredDeal, token: str, chat_id: str) -> bool:
    caption = format_offer(scored)
    image_url = scored.deal.image_url

    if image_url:
        # 1) let Telegram fetch the image itself (cheapest).
        if _post(
            token,
            "sendPhoto",
            json={"chat_id": chat_id, "photo": image_url, "caption": caption, "parse_mode": "HTML"},
        ):
            return True
        # 2) some CDNs refuse Telegram's fetcher or serve formats it rejects:
        #    download the image ourselves and upload the bytes.
        image = _download_image(image_url)
        if image is not None and _post(
            token,
            "sendPhoto",
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": ("offer.jpg", image)},
        ):
            return True

    # 3) never lose an offer just because its picture failed.
    return _post(
        token,
        "sendMessage",
        json={"chat_id": chat_id, "text": caption, "parse_mode": "HTML"},
    )


def send_offers(
    scored_deals: list[ScoredDeal],
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> list[ScoredDeal]:
    """Send each offer as its own Telegram message (photo + caption).

    Returns the offers that were actually delivered, in send order, so the
    caller can mark only those as seen and retry the rest on the next run."""
    if not scored_deals:
        return []

    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    ordered = sorted(scored_deals, key=_rank_key, reverse=True)[:MAX_MESSAGES_PER_RUN]

    delivered: list[ScoredDeal] = []
    for index, scored in enumerate(ordered):
        if index:
            time.sleep(SEND_DELAY_SECONDS)
        if _send_one(scored, bot_token, chat_id):
            delivered.append(scored)
        else:
            print(f"Could not deliver offer {scored.deal.id}", file=sys.stderr)
    return delivered
