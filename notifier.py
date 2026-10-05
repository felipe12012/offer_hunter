import html
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit

import requests

import prefs as prefs_module
from models import ScoredDeal

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
# Telegram throttles a single chat to ~1 message/second; stay just under it.
# A channel or group takes about 20 per minute and each offer may go to two of them: space the sends out (a flood ban
# from Telegram lasted 2.5 h and stopped every offer).
SEND_DELAY_SECONDS = 2.0
# Subscribers are different chats, so only Telegram's global limit (~30 messages/s) applies.
SUBSCRIBER_DELAY_SECONDS = 0.1
# Each subscriber gets at most this many offers per run (the best ones), and the whole fan-out
# stops after this long so a big subscriber list cannot run the job into its timeout.
MAX_SUBSCRIBER_MESSAGES_PER_RUN = 35
SUBSCRIBER_TIME_BUDGET_SECONDS = 300
# Chats that answered 403 (blocked the bot) during this process. The caller deactivates them.
UNREACHABLE_CHATS: set[str] = set()
# Chats Telegram told to wait longer than MAX_RETRY_AFTER_SECONDS (flood ban): chat -> seconds still to wait. Nothing is sent
# to them for the rest of the run (asking again during a ban can extend it); the caller keeps the ban between runs.
RATE_LIMITED: dict[str, float] = {}
# Ceiling per run so a huge sale can't flood the chat. Offers beyond it are not
# reported as sent, so the caller leaves them unseen and they go out next run.
MAX_MESSAGES_PER_RUN = 100
# Advertised discounts we could NOT confirm against price history are capped per
# run, separately from the verified quota. They are the 99% of qualifying offers
# and the ones most likely to be inflated "always 60% off" prices.
MAX_UNVERIFIED_PER_RUN = 40
# Priority interests (watchlist "priority") have their own quota for unconfirmed
# discounts, on top of the generic one, so they never compete with it.
MAX_PRIORITY_UNVERIFIED_PER_RUN = 50
# Possible pricing mistakes are announced first and outside every quota above, but not without limit.
MAX_PRICE_ERRORS_PER_RUN = 20
# Wall-clock ceiling for sending to the owner's chats. A run that sent 112 offers took 27 minutes (photos Telegram
# could not fetch were downloaded and uploaded once per destination) and was killed by the job timeout before it
# saved anything. What is not sent stays unseen and goes out in the next run.
TELEGRAM_TIME_BUDGET_SECONDS = 480
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


def _order_key(scored: ScoredDeal) -> tuple[bool, bool, bool, float, float]:
    """Sort key, best first: a big verified discount, then priority interests, then
    the verified discount; the store's own percentage is only a tie-break (so
    unverified offers rank below every verified one of the same kind)."""
    return (
        bool(scored.price_error),
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
    if scored.price_error:
        lines = ["🚨⚠️ <b>POSIBLE ERROR DE PRECIO</b>", f"<b>{html.escape(title)}</b>"]
    elif label:
        lines = [f"{html.escape(label)} -{_rank_key(scored):.0f}%", f"<b>{html.escape(title)}</b>"]
    else:
        lines = [f"🔥 <b>{html.escape(title)}</b>"]
    lines.append(f"🏬 {html.escape(deal.store.title())}")
    if scored.priority:
        lines.append(f"⭐ Prioridad: {html.escape(scored.priority)}")

    price_line = f"💰 <b>{_format_clp(deal.price)}</b>"
    unconfirmed_claim = not scored.advertised_confirmed and deal.discount_pct > 0
    if scored.price_error:
        lines.append(price_line)
        lines.append(f"📉 {html.escape(scored.price_error[:200])}")
        lines.append(
            "⚠️ Las tiendas suelen cancelar las compras con precio equivocado. Verifica en la tienda; "
            "si compras, es bajo tu responsabilidad."
        )
        if include_link:
            lines.append(f'🔗 <a href="{html.escape(deal.url, quote=True)}">Ver oferta</a>')
        return "\n".join(lines)
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
    """POST to the Telegram Bot API. Returns True on success."""
    return _post_result(token, method, **kwargs) is not None


def _post_result(token: str, method: str, **kwargs) -> dict | None:
    """POST to the Telegram Bot API. Returns the parsed answer ({} if it is not JSON) on success and None on
    failure. Waits and retries once when Telegram answers 429 (rate limited)."""
    url = TELEGRAM_API.format(token=token, method=method)
    body = kwargs.get("json") or kwargs.get("data") or {}
    chat = str(body["chat_id"]) if body.get("chat_id") is not None else None
    if chat in RATE_LIMITED:
        return None
    for attempt in (1, 2):
        try:
            response = requests.post(url, timeout=30, **kwargs)
        except requests.RequestException as exc:
            print(f"Telegram {method} request error: {exc}", file=sys.stderr)
            return None
        if response.status_code == 429:
            try:
                wait = float(response.json().get("parameters", {}).get("retry_after", 1))
            except Exception:
                wait = 1.0
            if wait > MAX_RETRY_AFTER_SECONDS:
                if chat is not None:
                    RATE_LIMITED[chat] = wait
                print(
                    f"Telegram {method}: chat {chat} is rate limited for {wait:.0f}s; sending to it stops",
                    file=sys.stderr,
                )
                return None
            if attempt == 1:
                time.sleep(wait)
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
            if response.status_code == 403:
                # The user blocked the bot or deleted the chat: it will never work again.
                body = kwargs.get("json") or kwargs.get("data") or {}
                if body.get("chat_id") is not None:
                    UNREACHABLE_CHATS.add(str(body["chat_id"]))
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return payload if isinstance(payload, dict) else {}
    return None


# A photo Telegram already holds can be sent to any other chat of this bot by its file_id: no new download by
# Telegram, no upload from us. The same offer goes to up to 4 destinations, so this is most of the work saved.
_PHOTO_FILE_IDS: dict[str, str] = {}
# Hosts whose image URLs Telegram could not fetch URL_FAILURES_BEFORE_SKIP times: from then on those photos are
# downloaded and uploaded directly instead of failing first (each failed attempt cost ~1-2 s).
URL_FAILURES_BEFORE_SKIP = 3
_URL_FAILURES: dict[str, int] = {}


def reset_photo_cache() -> None:
    _PHOTO_FILE_IDS.clear()
    _URL_FAILURES.clear()


def _remember_photo(image_url: str, payload: dict | None) -> None:
    try:
        photos = (payload or {}).get("result", {}).get("photo") or []
        if photos:
            _PHOTO_FILE_IDS[image_url] = photos[-1]["file_id"]
    except (AttributeError, KeyError, IndexError, TypeError):
        pass


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
        # 0) a photo Telegram already has (this offer went to another chat first): send it by id.
        file_id = _PHOTO_FILE_IDS.get(image_url)
        if file_id and _post(
            token,
            "sendPhoto",
            json={"chat_id": chat_id, "photo": file_id, "caption": caption, "parse_mode": "HTML", **extra},
        ):
            return "photo"
        # 1) let Telegram fetch the image itself (cheapest), unless it has already failed for this host.
        host = urlsplit(image_url).netloc
        if _URL_FAILURES.get(host, 0) < URL_FAILURES_BEFORE_SKIP:
            result = _post_result(
                token,
                "sendPhoto",
                json={"chat_id": chat_id, "photo": image_url, "caption": caption, "parse_mode": "HTML", **extra},
            )
            if result is not None:
                _remember_photo(image_url, result)
                return "photo"
            _URL_FAILURES[host] = _URL_FAILURES.get(host, 0) + 1
        # 2) some CDNs refuse Telegram's fetcher or serve formats it rejects:
        #    download the image ourselves, convert what it can't take, and upload.
        downloaded = _download_image(image_url)
        if downloaded is not None:
            image, ext = downloaded
            if ext not in _TELEGRAM_PHOTO_FORMATS:
                converted = _to_jpeg(image)
                if converted is not None:
                    image, ext = converted, "jpg"
            result = _post_result(
                token,
                "sendPhoto",
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML", **form_extra},
                files={"photo": (f"offer.{ext}", image)},
            )
            if result is not None:
                _remember_photo(image_url, result)
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


def _round_robin_by_category(
    scored_deals: list[ScoredDeal], limit: int, group_key=None
) -> list[ScoredDeal]:
    """Interleave categories so a single category can't fill the digest.

    Ranking by discount alone buried tablet and beauty deals under a flood of
    deeply-discounted clothing, so every category with offers gets a turn before
    any category gets a second one.
    """
    by_category: dict[str, list[ScoredDeal]] = {}
    for scored in scored_deals:
        by_category.setdefault(group_key(scored) if group_key else scored.deal.category, []).append(scored)
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
    public_chat_id: str | None = None,
    subscriber_chat_ids: list | None = None,
    subscriber_prefs: dict | None = None,
) -> list[ScoredDeal]:
    """Send each offer as its own Telegram message (photo + caption + link button).

    ``public_chat_id`` (or TELEGRAM_PUBLIC_CHAT_ID) is a channel that receives a copy of every
    delivered offer, so anyone can follow it without being registered in the bot.
    ``subscriber_chat_ids`` are the private chats that pressed /start: they get the best of the
    delivered offers (see ``_send_to_subscribers``).

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
    public_chat_id = public_chat_id or os.environ.get("TELEGRAM_PUBLIC_CHAT_ID") or None

    # Possible pricing mistakes first and outside every quota (but capped): the biggest drops win.
    mistakes = sorted(
        (s for s in scored_deals if s.price_error), key=lambda s: _rank_key(s), reverse=True
    )[:MAX_PRICE_ERRORS_PER_RUN]
    regular = [s for s in scored_deals if not s.price_error]

    verified = [scored for scored in regular if scored.advertised_confirmed]
    priority_unverified = [s for s in regular if not s.advertised_confirmed and s.priority]
    other_unverified = [s for s in regular if not s.advertised_confirmed and not s.priority]

    ordered = _round_robin_by_category(_dedupe_by_title(verified), MAX_MESSAGES_PER_RUN)
    room = MAX_MESSAGES_PER_RUN - len(ordered)
    limit = MAX_UNVERIFIED_PER_RUN if max_unverified is None else max_unverified
    if room > 0 and limit > 0:
        ordered += _round_robin_by_category(_dedupe_by_title(other_unverified), min(limit, room))
    priority_limit = (
        MAX_PRIORITY_UNVERIFIED_PER_RUN if max_priority_unverified is None else max_priority_unverified
    )
    if priority_limit > 0:
        # Hundreds of products can match a priority interest: take turns between the
        # interests (women's shoes, tablets, mattresses...) instead of letting the
        # biggest advertised discounts of one of them use the whole quota.
        ordered += _round_robin_by_category(
            _dedupe_by_title(priority_unverified), priority_limit, group_key=lambda scored: scored.priority
        )

    # Selection is done. Priority interests go out first; the sort is stable, so the
    # category interleaving chosen above is kept for everything else (and inside the
    # priority group).
    ordered.sort(key=lambda scored: not scored.priority)
    ordered = mistakes + ordered

    delivered: list[ScoredDeal] = []
    photo_messages = 0
    text_messages = 0
    send_started = time.monotonic()
    for index, scored in enumerate(ordered):
        if chat_id and str(chat_id) in RATE_LIMITED:
            print(f"Main chat rate limited: the other {len(ordered) - index} offers wait", file=sys.stderr)
            break
        if index:
            if time.monotonic() - send_started > TELEGRAM_TIME_BUDGET_SECONDS:
                print(
                    f"Telegram time budget ({TELEGRAM_TIME_BUDGET_SECONDS}s) spent after {len(delivered)} offers; "
                    f"the other {len(ordered) - index} wait for the next run",
                    file=sys.stderr,
                )
                break
            time.sleep(SEND_DELAY_SECONDS)

        result = ""
        sent_to = chat_id
        if alert_chat_id and (scored.price_error or _rank_key(scored) >= alert_min):
            result = _send_one(scored, bot_token, alert_chat_id, alerts, thread_id, allow_silent=False)
            if result:
                sent_to = alert_chat_id
            else:
                print(f"Alert chat failed for {scored.deal.id}; falling back to the main chat", file=sys.stderr)
        if not result:
            result = _send_one(scored, bot_token, chat_id, alerts)

        # The public channel gets a copy of everything the owner received. Its failures never
        # count against the offer: delivery to the owner is what marks it as seen.
        if result and public_chat_id and str(public_chat_id) != str(sent_to):
            time.sleep(SEND_DELAY_SECONDS)
            if not _send_one(scored, bot_token, public_chat_id, alerts):
                print(f"Public channel failed for {scored.deal.id}", file=sys.stderr)

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
    if subscriber_chat_ids and delivered:
        own_chats = {str(chat) for chat in (chat_id, alert_chat_id, public_chat_id) if chat}
        _send_to_subscribers(delivered, bot_token, subscriber_chat_ids, own_chats, alerts, alert_min, subscriber_prefs)
    return delivered


def _send_to_subscribers(
    delivered: list[ScoredDeal],
    token: str,
    subscriber_chat_ids: list,
    own_chats: set[str],
    alerts: dict | None,
    alert_min: float,
    subscriber_prefs: dict | None = None,
) -> None:
    """Send the best of this run's offers to everyone who pressed /start.

    ``subscriber_prefs`` ({chat_id: filters}, see prefs.py) narrows what each chat gets.

    Subscribers are not spammed with every unconfirmed discount: they get verified offers,
    priority interests and big discounts, best first, at most MAX_SUBSCRIBER_MESSAGES_PER_RUN."""
    worth_sending = [
        scored for scored in delivered
        if scored.price_error or scored.advertised_confirmed or scored.priority or _rank_key(scored) >= alert_min
    ]
    worth_sending.sort(key=_order_key, reverse=True)
    recipients = [str(chat) for chat in subscriber_chat_ids if str(chat) not in own_chats]
    if not worth_sending or not recipients:
        return
    prefs_by_chat = {str(chat): value for chat, value in (subscriber_prefs or {}).items()}
    plan = {
        chat: [s for s in worth_sending if prefs_module.matches(s, prefs_by_chat.get(chat))][:MAX_SUBSCRIBER_MESSAGES_PER_RUN]
        for chat in recipients
    }
    if not any(plan.values()):
        return

    started = time.monotonic()
    sent = 0
    for rank in range(MAX_SUBSCRIBER_MESSAGES_PER_RUN):
        for chat in recipients:
            if chat in UNREACHABLE_CHATS or rank >= len(plan[chat]):
                continue
            scored = plan[chat][rank]
            if time.monotonic() - started > SUBSCRIBER_TIME_BUDGET_SECONDS:
                print(f"Subscriber fan-out stopped after {SUBSCRIBER_TIME_BUDGET_SECONDS}s", file=sys.stderr)
                print(f"Subscribers: {sent} messages sent to {len(recipients)} chats", file=sys.stderr)
                return
            time.sleep(SUBSCRIBER_DELAY_SECONDS)
            if _send_one(scored, token, chat, alerts):
                sent += 1
    print(f"Subscribers: {sent} messages sent to {len(recipients)} chats", file=sys.stderr)


def send_alert(text: str, bot_token: str | None = None, chat_id: str | None = None) -> bool:
    """Plain-text message to the main chat (store health, service notices).

    No parse mode on purpose: the text may carry error messages with characters
    that would otherwise need HTML escaping. Returns False instead of raising."""
    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return False
    return _post(bot_token, "sendMessage", json={"chat_id": chat_id, "text": text[:4000]})
