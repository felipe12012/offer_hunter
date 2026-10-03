import main_fast


def test_browser_shoe_stores_get_only_footwear_keywords():
    # These stores launch a Chromium per keyword; the full watchlist would mean
    # ~30 launches each for queries like "kerastase" they can never match.
    watchlist = {"keywords": ["audifonos", "kerastase", "zapatillas", "crema facial"]}

    narrowed = main_fast.watchlist_for("nike", watchlist)

    assert narrowed["keywords"] == main_fast.BROWSER_SHOE_KEYWORDS
    assert narrowed["keywords"][:2] == ["zapatillas", "zapatilla"]


def test_browser_shoe_stores_also_search_the_priority_footwear_segments():
    keywords = main_fast.watchlist_for("converse", {"keywords": []})["keywords"]
    for segment in ("zapatillas mujer", "zapatillas hombre", "zapatillas bebe"):
        assert segment in keywords


def test_pharmacies_get_the_dermocosmetics_first_keyword_list():
    watchlist = {"keywords": ["zapatillas", "kerastase", "crema facial", "notebook"]}

    for store in ("salcobrand", "cruzverde", "ahumada"):
        narrowed = main_fast.watchlist_for(store, watchlist)
        assert narrowed["keywords"] == main_fast.PHARMACY_KEYWORDS
        assert "dermocosmetica" in narrowed["keywords"]


def test_pharmacies_search_kerastase_blond_before_anything_else():
    # A priority interest: searched first, so a slow pharmacy cannot time out before it.
    for store in ("salcobrand", "cruzverde", "ahumada"):
        assert main_fast.watchlist_for(store, {"keywords": []})["keywords"][0] == "kerastase blond"


def test_non_shoe_stores_keep_the_full_watchlist():
    watchlist = {"keywords": ["audifonos", "kerastase"]}

    assert main_fast.watchlist_for("falabella", watchlist) is watchlist
    assert main_fast.watchlist_for("sodimac", watchlist) is watchlist
