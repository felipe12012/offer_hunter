import html
import json
import os
import re
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
# Advertised discounts we could NOT confirm against price history are capped per
# run, separately from the verified quota. They are the 99% of qualifying offers
# and the ones most likely to be inflated "always 60% off" prices.
MAX_UNVERIFIED_PER_RUN = 5
# Priority interests (watchlist "priority") have their own quota for unconfirmed
# discounts, on top of the generic one, so they never compete with it.
MAX_PRIORITY_UNVERIFIED_PER_RUN = 10
# A verified discount at or above this always goes first, priority or not.
BIG_VERIFIED_PCT = 60
MAX_CAPTION_LENGTH = 1024
MAX_TITLE_LENGTH = 180
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_RETRY_AFTER_SECONDS = 30
# Alert levels by discount (the larger of the advertised and the historical one).
# Overridable from the watchlist's "alerts" block. "warn_from_pct" adds a
# caution line, because an extreme discount can also be a store pricing error.
# "silent_below_pct" (off by default) sends smaller offers without a sound.
DEFAULT_ALERTS = {
    "tiers": [
        {"min_pct": 90, "label": "🚨🚨🚨 SUPER OFERTA"},
        {"min_pct": 80, "label": "🚨 OFERTAZA"},
        {"min_pct": 60, "label": "🔥 GRAN OFERTA"},
    ],
    "warn_from_pct": 80,
    "silent_below_pct": None,
    # Offers at or above this discount go to the alert chat (when one is set).
    "alert_chat_min_pct": 80,
}
BUTTON_TEXT = "🛒 Ir a la oferta"
MAX_BUTTON_URL_LENGTH = 2000
IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    # Ask for JPEG/PNG first: some CDNs serve webp/avif when advertised, and
    # Telegram rejects AVIF. JPEG avoids a conversion round-trip.
    "Accept": "image/jpeg,image/png,image/*;q=0.8",
}
_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/avif": "avif",
    "image/gif": "gif",
}
# Telegram accepts JPEG/PNG/WebP for sendPhoto but not AVIF; converting whatever
# it cannot take to JPEG is cheaper than losing the photo.
_TELEGRAM_PHOTO_FORMATS = {"jpg", "jpeg", "png", "webp"}


def _rank_key(scored: ScoredDeal) -> float:
    # Rank and announce by the verified discount, never by a store percentage
    # that history could not confirm. Offers built without verification data
    # (verified_pct is None) fall back to the larger of the two.
    if scored.verified_pct is not None:
        return scored.verified_pct
    return max(scored.real_discount_pct, scored.deal.discount_pct)


def _order_key(scored: ScoredDeal) -> tuple[bool, bool, float, float]:
    """Sort key, best first: a big verified discount, then priority interests, then
    the verified discount; the store's own percentage is only a tie-break (so
    unverified offers rank below every verified one of the same kind)."""
    return (
        _rank_key(scored) >= BIG_VERIFIED_PCT,
        bool(scored.priority),
        _rank_key(scored),
        scored.deal.discount_pct,
    )


def _format_clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def _alerts(alerts: dict | None) -> dict:
    return {**DEFAULT_ALERTS, **(alerts or {})}


def _tier_label(scored: ScoredDeal, alerts: dict) -> str | None:
    pct = _rank_key(scored)
    for tier in sorted(alerts["tiers"], key=lambda t: t["min_pct"], reverse=True):
        if pct >= tier["min_pct"]:
            return tier["label"]
    return None


def format_offer(
    scored: ScoredDeal,
    max_title: int = MAX_TITLE_LENGTH,
    alerts: dict | None = None,
    include_link: bool = True,
) -> str:
    deal = scored.deal
    config = _alerts(alerts)
    title = deal.title if len(deal.title) <= max_title else deal.title[: max_title - 1] + "…"

    label = _tier_label(scored, config)
    if label:
        lines = [f"{html.escape(label)} -{_rank_key(scored):.0f}%", f"<b>{html.escape(title)}</b>"]
    else:
        lines = [f"🔥 <b>{html.escape(title)}</b>"]
    lines.append(f"🏬 {html.escape(deal.store.title())}")
    if scored.priority:
        lines.append(f"⭐ Prioridad: {html.escape(scored.priority)}")

    price_line = f"💰 <b>{_format_clp(deal.price)}</b>"
    unconfirmed_claim = not scored.advertised_confirmed and deal.discount_pct > 0
    if not unconfirmed_claim:
        if deal.list_price > deal.price:
            price_line += f"  <s>{_format_clp(deal.list_price)}</s>"
        if deal.discount_pct > 0:
            price_line += f"  (-{deal.discount_pct:.0f}%)"
    lines.append(price_line)
    if unconfirmed_claim:
        lines.append(
            f"ℹ️ La web anuncia -{deal.discount_pct:.0f}% (antes {_format_clp(deal.list_price)}), no verificado"
        )

    for reason in scored.reasons:
        lines.append(f"✅ {html.escape(reason[:200])}")

    warn_from = config.get("warn_from_pct")
    if warn_from is not None and _rank_key(scored) >= warn_from:
        lines.append("⚠️ Descuento extremo: puede ser un error de precio. Confirma en la tienda antes de comprar.")

    if include_link:
        lines.append(f'🔗 <a href="{html.escape(deal.url, quote=True)}">Ver oferta</a>')
    text = "\n".join(lines)
    if len(text) > MAX_CAPTION_LENGTH and max_title > 60:
        return format_offer(scored, max_title=60, alerts=alerts, include_link=include_link)
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
            # Telegram explains the rejection in "description"; without it a
            # failed sendPhoto is just a bare 400 and undiagnosable.
            detail = ""
            try:
                detail = response.json().get("description", "")
            except Exception:
                detail = response.text[:200]
            print(f"Telegram {method} failed with HTTP {response.status_code}: {detail}", file=sys.stderr)
            return False
        return True
    return False


def _download_image(url: str) -> tuple[bytes, str] | None:
    try:
        response = requests.get(url, headers=IMAGE_HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return None
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/") or not response.content:
        return None
    if len(response.content) > MAX_IMAGE_BYTES:
        return None
    return response.content, _CONTENT_TYPE_EXT.get(content_type, "jpg")


def _to_jpeg(data: bytes) -> bytes | None:
    """Convert an image Telegram would reject (AVIF, or a mislabelled format) to
    JPEG. Returns None when Pillow is unavailable or the bytes are unreadable."""
    try:
        import io

        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception:
        return None


def _is_silent(scored: ScoredDeal, config: dict) -> bool:
    if scored.priority and scored.advertised_confirmed:
        return False  # a verified priority offer is worth a sound
    threshold = config.get("silent_below_pct")
    return threshold is not None and _rank_key(scored) < threshold


def _link_button(url: str) -> dict | None:
    """Inline keyboard with one URL button, or None when Telegram would reject
    the URL (a rejected button would fail the whole message)."""
    if not url.startswith(("http://", "https://")) or len(url) > MAX_BUTTON_URL_LENGTH:
        return None
    return {"inline_keyboard": [[{"text": BUTTON_TEXT, "url": url}]]}


def _send_one(
    scored: ScoredDeal,
    token: str,
    chat_id: str,
    alerts: dict | None = None,
    thread_id: int | None = None,
    allow_silent: bool = True,
) -> str:
    """Returns "photo", "text", or "" (nothing delivered)."""
    config = _alerts(alerts)
    markup = _link_button(scored.deal.url)
    # With a button the link leaves the caption; without one it stays inside it.
    caption = format_offer(scored, alerts=alerts, include_link=markup is None)
    image_url = scored.deal.image_url
    silent = allow_silent and _is_silent(scored, config)

    extra: dict = {}
    form_extra: dict = {}
    if silent:
        extra["disable_notification"] = True
        form_extra["disable_notification"] = "true"
    if thread_id is not None:
        extra["message_thread_id"] = thread_id
        form_extra["message_thread_id"] = str(thread_id)
    if markup is not None:
        extra["reply_markup"] = markup
        form_extra["reply_markup"] = json.dumps(markup)

    if image_url:
        # 1) let Telegram fetch the image itself (cheapest).
        if _post(
            token,
            "sendPhoto",
            json={"chat_id": chat_id, "photo": image_url, "caption": caption, "parse_mode": "HTML", **extra},
        ):
            return "photo"
        # 2) some CDNs refuse Telegram's fetcher or serve formats it rejects:
        #    download the image ourselves, convert what it can't take, and upload.
        downloaded = _download_image(image_url)
        if downloaded is not None:
            image, ext = downloaded
            if ext not in _TELEGRAM_PHOTO_FORMATS:
                converted = _to_jpeg(image)
                if converted is not None:
                    image, ext = converted, "jpg"
            if _post(
                token,
                "sendPhoto",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", **form_extra},
                files={"photo": (f"offer.{ext}", image)},
            ):
                return "photo"

    # 3) never lose an offer just because its picture failed.
    if _post(
        token,
        "sendMessage",
        json={"chat_id": chat_id, "text": caption, "parse_mode": "HTML", **extra},
    ):
        return "text"
    return ""


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _dedupe_by_title(scored_deals: list[ScoredDeal]) -> list[ScoredDeal]:
    """One offer per (store, normalized title), keeping the best-ranked.

    Retailers list the same product under several SKUs (sizes, colours, duplicate
    sponsored cards). Without this the chat fills with near-identical messages.
    """
    best: dict[tuple[str, str], ScoredDeal] = {}
    for scored in scored_deals:
        key = (scored.deal.store, _normalize_title(scored.deal.title))
        current = best.get(key)
        if current is None or _order_key(scored) > _order_key(current):
            best[key] = scored
    return list(best.values())


def _round_robin_by_category(scored_deals: list[ScoredDeal], limit: int) -> list[ScoredDeal]:
    """Interleave categories so a single category can't fill the digest.

    Ranking by discount alone buried tablet and beauty deals under a flood of
    deeply-discounted clothing, so every category with offers gets a turn before
    any category gets a second one.
    """
    by_category: dict[str, list[ScoredDeal]] = {}
    for scored in scored_deals:
        by_category.setdefault(scored.deal.category, []).append(scored)
    for items in by_category.values():
        items.sort(key=_order_key, reverse=True)
    order = sorted(by_category, key=lambda category: _order_key(by_category[category][0]), reverse=True)

    picked: list[ScoredDeal] = []
    index = 0
    while len(picked) < limit:
        added = False
        for category in order:
            items = by_category[category]
            if index < len(items):
                picked.append(items[index])
                added = True
                if len(picked) == limit:
                    break
        if not added:
            break
        index += 1
    return picked


def send_offers(
    scored_deals: list[ScoredDeal],
    bot_token: str | None = None,
    chat_id: str | None = None,
    alerts: dict | None = None,
    alert_chat_id: str | None = None,
    alert_thread_id: str | int | None = None,
    max_unverified: int | None = None,
    max_priority_unverified: int | None = None,
) -> list[ScoredDeal]:
    """Send each offer as its own Telegram message (photo + caption + link button).

    Offers at or above ``alerts["alert_chat_min_pct"]`` go to the alert chat when
    one is configured (argument or TELEGRAM_ALERT_CHAT_ID); everything else, and
    any alert-chat failure, goes to the main chat.

    Verified offers get the full ``MAX_MESSAGES_PER_RUN`` quota; unconfirmed
    advertised discounts are limited to ``max_unverified`` (default
    ``MAX_UNVERIFIED_PER_RUN``, and the caller can shrink it for a daily cap).
    Unconfirmed *priority* offers have a separate quota, ``max_priority_unverified``
    (default ``MAX_PRIORITY_UNVERIFIED_PER_RUN``), outside both of those.

    Returns the offers that were actually delivered, in send order, so the
    caller can mark only those as seen and retry the rest on the next run."""
    if not scored_deals:
        return []

    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    # An unset GitHub secret reaches the job as an empty string.
    alert_chat_id = alert_chat_id or os.environ.get("TELEGRAM_ALERT_CHAT_ID") or None
    raw_thread = alert_thread_id or os.environ.get("TELEGRAM_ALERT_THREAD_ID") or None
    thread_id = int(raw_thread) if raw_thread else None
    alert_min = _alerts(alerts)["alert_chat_min_pct"]

    verified = [scored for scored in scored_deals if scored.advertised_confirmed]
    priority_unverified = [s for s in scored_deals if not s.advertised_confirmed and s.priority]
    other_unverified = [s for s in scored_deals if not s.advertised_confirmed and not s.priority]

    ordered = _round_robin_by_category(_dedupe_by_title(verified), MAX_MESSAGES_PER_RUN)
    room = MAX_MESSAGES_PER_RUN - len(ordered)
    limit = MAX_UNVERIFIED_PER_RUN if max_unverified is None else max_unverified
    if room > 0 and limit > 0:
        ordered += _round_robin_by_category(_dedupe_by_title(other_unverified), min(limit, room))
    priority_limit = (
        MAX_PRIORITY_UNVERIFIED_PER_RUN if max_priority_unverified is None else max_priority_unverified
    )
    if priority_limit > 0:
        ordered += _round_robin_by_category(_dedupe_by_title(priority_unverified), priority_limit)

    # Selection is done. Priority interests go out first; the sort is stable, so the
    # category interleaving chosen above is kept for everything else (and inside the
    # priority group).
    ordered.sort(key=lambda scored: not scored.priority)

    delivered: list[ScoredDeal] = []
    photo_messages = 0
    text_messages = 0
    for index, scored in enumerate(ordered):
        if index:
            time.sleep(SEND_DELAY_SECONDS)

        result = ""
        if alert_chat_id and _rank_key(scored) >= alert_min:
            result = _send_one(scored, bot_token, alert_chat_id, alerts, thread_id, allow_silent=False)
            if not result:
                print(f"Alert chat failed for {scored.deal.id}; falling back to the main chat", file=sys.stderr)
        if not result:
            result = _send_one(scored, bot_token, chat_id, alerts)

        if result:
            delivered.append(scored)
            photo_messages += result == "photo"
            text_messages += result == "text"
        else:
            print(f"Could not deliver offer {scored.deal.id}", file=sys.stderr)
    if delivered:
        print(
            f"Telegram: {len(delivered)} delivered ({photo_messages} with photo, {text_messages} as text)",
            file=sys.stderr,
        )
    return delivered


def send_alert(text: str, bot_token: str | None = None, chat_id: str | None = None) -> bool:
    """Plain-text message to the main chat (store health, service notices).

    No parse mode on purpose: the text may carry error messages with characters
    that would otherwise need HTML escaping. Returns False instead of raising."""
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    return _post(bot_token, "sendMessage", json={"chat_id": chat_id, "text": text[:4000]})
