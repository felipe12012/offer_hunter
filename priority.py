"""Priority interests: products the user cares about most.

A rule is ``{"label", "all": [[alternatives], ...], "none": [tokens], "not_stores": []}``.
A product matches when EVERY group in ``all`` has at least one alternative present in
its text, NO ``none`` token is present and its store is not in ``not_stores``.

The text is the product's title plus a "hint": the store's own department name
(for example "Zapatillas Mujer"), so a dress found in Falabella's "Moda Mujer" counts
as women's clothing even though its title never says "mujer". The search term that
happened to return the product is deliberately NOT part of the text: stores answer
any query with loosely related products (a "zapatillas mujer" search returns socks,
a "comida gato nyd" search returns every cat food), and counting the query made all
of them look like priority interests.

Matching is accent- and case-insensitive. Tokens of up to 3 characters match whole
words only (so "top" is not inside "laptop"); a leading ``=`` forces a whole-word
match on a longer token.
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Rule:
    label: str
    all_groups: tuple[tuple[str, ...], ...]
    none: tuple[str, ...]
    not_stores: tuple[str, ...] = ()


def normalize(text: str) -> str:
    """Lowercase, no accents, punctuation as spaces, padded with one space each side."""
    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split()) + " "


def _token(raw: str) -> tuple[str, bool]:
    whole_word = raw.startswith("=")
    token = normalize(raw.lstrip("=")).strip()
    return token, whole_word or len(token) <= 3


def _present(raw: str, haystack: str) -> bool:
    token, whole_word = _token(raw)
    if not token:
        return False
    return f" {token} " in haystack if whole_word else token in haystack


@lru_cache(maxsize=8)
def _compile(serialised: str) -> tuple[Rule, ...]:
    config = json.loads(serialised)
    rules = []
    for item in config.get("rules", []):
        groups = tuple(tuple(group) for group in item.get("all", []) if group)
        if not groups:
            continue
        rules.append(
            Rule(
                label=item["label"],
                all_groups=groups,
                none=tuple(item.get("none", [])),
                not_stores=tuple(store.lower() for store in item.get("not_stores", [])),
            )
        )
    return tuple(rules)


def rules_from(config: dict | None) -> tuple[Rule, ...]:
    """The compiled rules of a watchlist's ``priority`` block (cached per config)."""
    if not config or not config.get("rules"):
        return ()
    return _compile(json.dumps(config, sort_keys=True))


def first_match(
    rules: tuple[Rule, ...], title: str, hint: str = "", store: str = ""
) -> str | None:
    """Label of the first rule the product matches, or None. Rules are tried in order."""
    if not rules:
        return None
    haystack = normalize(f"{title} {hint}")
    store = store.lower()
    for rule in rules:
        if store and store in rule.not_stores:
            continue
        if all(any(_present(token, haystack) for token in group) for group in rule.all_groups) and not any(
            _present(token, haystack) for token in rule.none
        ):
            return rule.label
    return None
