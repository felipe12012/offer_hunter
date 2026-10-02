import main_fast


def test_browser_shoe_stores_get_only_footwear_keywords():
    # These stores launch a Chromium per keyword; the full watchlist would mean
    # ~30 launches each for queries like "kerastase" they can never match.
    watchlist = {"keywords": ["audifonos", "kerastase", "zapatillas", "crema facial"]}

    narrowed = main_fast.watchlist_for("nike", watchlist)

    assert narrowed["keywords"] == main_fast.BROWSER_SHOE_KEYWORDS
    assert narrowed["keywords"] == ["zapatillas", "zapatilla"]


def test_non_shoe_stores_keep_the_full_watchlist():
    watchlist = {"keywords": ["audifonos", "kerastase"]}

    assert main_fast.watchlist_for("falabella", watchlist) is watchlist
    assert main_fast.watchlist_for("sodimac", watchlist) is watchlist
