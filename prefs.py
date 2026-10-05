"""Per-subscriber preferences: which categories, stores and minimum discount a chat wants.

Stored as JSON in ``offer_subscribers.prefs``: ``{"groups": [...], "stores": [...], "min_pct": 40}``. A missing key
means "no filter". Pure functions (the bot commands and the filter used when sending), so they are unit tested.
"""

from __future__ import annotations

from taxonomy import GROUPS, classify, normalize

MAX_MIN_PCT = 95


def matches(scored, prefs: dict | None) -> bool:
    """Does this offer pass the subscriber's filters? Possible price mistakes always pass: they are rare and the
    point of the bot."""
    if not prefs or scored.price_error:
        return True
    deal = scored.deal
    groups = prefs.get("groups")
    if groups:
        group, _sub = classify(deal.title, deal.category, deal.store)
        if group not in groups:
            return False
    stores = prefs.get("stores")
    if stores and deal.store not in stores:
        return False
    min_pct = prefs.get("min_pct")
    if min_pct:
        pct = scored.verified_pct if scored.verified_pct is not None else max(scored.real_discount_pct, deal.discount_pct)
        if pct < min_pct:
            return False
    return True


def describe(prefs: dict | None) -> str:
    prefs = prefs or {}
    groups = ", ".join(GROUPS[g] for g in prefs.get("groups") or [] if g in GROUPS) or "todas"
    stores = ", ".join(prefs.get("stores") or []) or "todas"
    minimum = f"{prefs['min_pct']}%" if prefs.get("min_pct") else "sin mínimo"
    return f"Categorías: {groups}\nTiendas: {stores}\nDescuento mínimo: {minimum}"


def _keyword_to_group() -> dict[str, str]:
    table = {}
    for key, label in GROUPS.items():
        table[key] = key
    for key, label in GROUPS.items():
        for word in normalize(label).replace(" y ", " ").split():
            table.setdefault(word, key)
    return table


def apply_command(command: str, args: str, prefs: dict | None, known_stores: set[str]) -> tuple[dict, str]:
    """(new prefs, reply text) for /categorias, /minimo, /tiendas and /mis."""
    prefs = dict(prefs or {})
    args = (args or "").strip()
    if command == "/mis":
        return prefs, describe(prefs) + "\n\nCámbialo con /categorias, /tiendas y /minimo."

    if command == "/categorias":
        if not args:
            options = "\n".join(f"• {key} — {label}" for key, label in GROUPS.items())
            return prefs, (
                "Elige una o varias, por ejemplo: /categorias tecnologia mascotas\n"
                f"/categorias todas — sin filtro\n\n{options}"
            )
        if normalize(args) in ("todas", "todo", "ninguna"):
            prefs.pop("groups", None)
            return prefs, "Listo: recibirás todas las categorías."
        lookup = _keyword_to_group()
        chosen, unknown = [], []
        for word in normalize(args).replace(",", " ").split():
            group = lookup.get(word)
            if group is None:
                unknown.append(word)
            elif group not in chosen:
                chosen.append(group)
        if unknown or not chosen:
            return prefs, f"No reconozco: {', '.join(unknown) or args}. Escribe /categorias para ver la lista."
        prefs["groups"] = chosen
        return prefs, "Listo, solo recibirás: " + ", ".join(GROUPS[g] for g in chosen) + "."

    if command == "/tiendas":
        if not args:
            return prefs, (
                "Ejemplo: /tiendas falabella sodimac\n/tiendas todas — sin filtro\n\nTiendas: "
                + ", ".join(sorted(known_stores))
            )
        if normalize(args) in ("todas", "todo", "ninguna"):
            prefs.pop("stores", None)
            return prefs, "Listo: recibirás ofertas de todas las tiendas."
        words = [w for w in normalize(args).replace(",", " ").split() if w]
        unknown = [w for w in words if w not in known_stores]
        if unknown:
            return prefs, f"No conozco: {', '.join(unknown)}. Escribe /tiendas para ver la lista."
        prefs["stores"] = list(dict.fromkeys(words))
        return prefs, "Listo, solo recibirás ofertas de: " + ", ".join(prefs["stores"]) + "."

    if command == "/minimo":
        digits = args.replace("%", "").strip()
        if not digits:
            return prefs, "Ejemplo: /minimo 40 (solo ofertas con 40% o más). /minimo 0 — sin mínimo."
        if not digits.isdigit() or int(digits) > MAX_MIN_PCT:
            return prefs, f"Escribe un número entre 0 y {MAX_MIN_PCT}, por ejemplo /minimo 40."
        value = int(digits)
        if value:
            prefs["min_pct"] = value
            return prefs, f"Listo: solo ofertas con {value}% o más."
        prefs.pop("min_pct", None)
        return prefs, "Listo: sin descuento mínimo."

    return prefs, ""
