"""Shared product-image extraction for the store scrapers.

Storefront cards contain more than the product photo: lazy-load placeholders
(``data:`` URIs), warranty ribbons, payment-card icons, stickers. ``pick_image``
returns the first URL that looks like the real product photo, or ``""``.
"""
import re
from urllib.parse import urljoin

_NOISE = re.compile(
    r"(icon|logo|ribbon|sticker|badge|sprite|placeholder|tag_icons|tarjeta|"
    r"warranty|proteccion|garantia|\.svg(\?|$)|/static/|spacer|blank)",
    re.IGNORECASE,
)
_NOISE_ALT = re.compile(r"(ripley card|protecci|logo|icono|garant)", re.IGNORECASE)


def _largest_from_srcset(srcset: str) -> str:
    best_url, best_w = "", -1
    for part in srcset.split(","):
        pieces = part.strip().split()
        if not pieces:
            continue
        url = pieces[0]
        weight = 0
        if len(pieces) > 1:
            m = re.match(r"(\d+(?:\.\d+)?)[wx]", pieces[1])
            weight = float(m.group(1)) if m else 0
        if weight >= best_w:
            best_url, best_w = url, weight
    return best_url


def _candidates(img) -> list[str]:
    urls = []
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        value = img.get(attr)
        if value:
            urls.append(value)
    srcset = img.get("srcset") or img.get("data-srcset")
    if srcset:
        urls.append(_largest_from_srcset(srcset))
    return urls


def _usable(url: str) -> bool:
    if not url or url.startswith("data:"):
        return False
    return not _NOISE.search(url)


def pick_image(card, base_url: str = "") -> str:
    for img in card.select("img"):
        if _NOISE_ALT.search(img.get("alt") or ""):
            continue
        for url in _candidates(img):
            url = url.replace("&amp;", "&").strip()
            if _usable(url):
                return urljoin(base_url, url) if base_url else url
    for source in card.select("source"):
        url = _largest_from_srcset(source.get("srcset") or "")
        if _usable(url):
            return urljoin(base_url, url) if base_url else url
    return ""


def scroll_to_load(page, steps: int = 8, pause_ms: int = 350) -> None:
    """Scroll down so lazy-loaded product images replace their skeletons."""
    try:
        for _ in range(steps):
            page.mouse.wheel(0, 1400)
            page.wait_for_timeout(pause_ms)
        page.wait_for_timeout(500)
    except Exception:
        pass
