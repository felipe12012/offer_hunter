import json
from pathlib import Path

import pytest

from sources import nextdata
from sources.nextdata import StoreConfig

FIXTURE = Path(__file__).parent / "fixtures" / "falabella_listing_props.json"


def props() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


CFG = StoreConfig(
    store="falabella",
    base_url="https://www.falabella.com",
    home_url="https://www.falabella.com/falabella-cl",
    search_url="https://www.falabella.com/falabella-cl/search?Ntt={query}",
    category_url="https://www.falabella.com/falabella-cl/category/{id}/{slug}",
    category_href_re=r"/category/(cat\d+)/([A-Za-z0-9%\-_.]+)",
)


def test_parse_results_uses_public_internet_price_not_card_only_price():
    deals = nextdata.parse_results(props(), CFG, category="tecnologia")
    victus = next(d for d in deals if d.id == "falabella:80726514")
    assert victus.price == 719990          # internetPrice, not the CMR-card-only 699.990
    assert victus.list_price == 1069990    # crossed normalPrice
    assert victus.discount_pct == 32.7
    assert victus.store == "falabella"
    assert victus.category == "tecnologia"
    assert victus.image_url == "https://media.falabella.com/falabellaCL/80726514_01/public"
    assert victus.title.startswith("HP ") or "VICTUS" in victus.title.upper() or "Victus" in victus.title


def test_parse_results_takes_first_variant_when_several_prices_listed():
    deals = nextdata.parse_results(props(), CFG, category="tecnologia")
    macbook = next(d for d in deals if d.id == "falabella:80725441")
    assert macbook.price == 819990
    assert macbook.list_price == 869990


def test_parse_results_prefers_event_price_and_ignores_cmr_only_price():
    deals = nextdata.parse_results(props(), CFG, category="tecnologia")
    audio = next(d for d in deals if d.id == "falabella:142403285")
    assert audio.price == 18990            # eventPrice (public), not cmr 17.990
    assert audio.list_price == 28988


def test_parse_results_without_crossed_price_has_no_discount():
    deals = nextdata.parse_results(props(), CFG, category="tecnologia")
    kit = next(d for d in deals if d.id == "falabella:17256548")
    assert kit.price == 336990
    assert kit.list_price == 336990
    assert kit.discount_pct == 0.0


def test_parse_results_deduplicates_sponsored_repeats_and_skips_unpriced():
    data = props()
    data["results"].append(dict(data["results"][0]))                       # sponsored repeat
    data["results"].append({"productId": "x", "displayName": "Sin precio", "url": "/p/x", "prices": []})
    deals = nextdata.parse_results(data, CFG, category="tecnologia")
    ids = [d.id for d in deals]
    assert len(ids) == len(set(ids)) == 4


def test_with_page_sets_and_replaces_the_page_parameter():
    assert nextdata.with_page("https://x.cl/a/b", 3) == "https://x.cl/a/b?page=3"
    assert nextdata.with_page("https://x.cl/a?Ntt=tv&page=1", 2) == "https://x.cl/a?Ntt=tv&page=2"


def _page_of(url: str) -> int:
    return int(url.rsplit("page=", 1)[1]) if "page=" in url else 1


def test_scan_listing_paginates_until_max_pages():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        page = _page_of(url)
        data = props()
        for index, result in enumerate(data["results"]):
            result["productId"] = f"{result['productId']}-p{page}"
        data["pagination"] = {"count": 480, "perPage": 48, "currentPage": page}
        return data

    deals = nextdata.scan_listing(
        "https://www.falabella.com/falabella-cl/category/cat1/Audifonos",
        CFG, "tecnologia", max_pages=3, fetch=fake_fetch, sleep=lambda s: None,
    )

    assert [_page_of(u) for u in calls] == [1, 2, 3]
    assert len(deals) == 12


def test_scan_listing_stops_after_the_last_page():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        data = props()
        data["pagination"] = {"count": 50, "perPage": 48, "currentPage": 1}  # only 2 pages exist
        for result in data["results"]:
            result["productId"] += str(_page_of(url))
        return data

    nextdata.scan_listing("https://x.cl/c", CFG, "t", max_pages=10, fetch=fake_fetch, sleep=lambda s: None)
    assert len(calls) == 2


def test_scan_listing_stops_when_a_page_adds_nothing_new():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        data = props()
        data["pagination"] = {"count": 9999, "perPage": 48, "currentPage": 1}
        return data  # same products every page (site ignored the page parameter)

    deals = nextdata.scan_listing("https://x.cl/c", CFG, "t", max_pages=10, fetch=fake_fetch, sleep=lambda s: None)
    assert len(calls) == 2
    assert len(deals) == 4


def test_scan_listing_follows_current_url_when_search_is_rewritten_to_a_category():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        data = props()
        data["currentUrl"] = "/sodimac-cl/lista/cat14080023/Taladros?subdomain=sodimac"
        data["pagination"] = {"count": 200, "perPage": 48, "currentPage": 1}
        for result in data["results"]:
            result["productId"] += url[-3:]
        return data

    nextdata.scan_listing(
        "https://www.sodimac.cl/sodimac-cl/search?Ntt=taladro", CFG, "taladro",
        max_pages=2, fetch=fake_fetch, sleep=lambda s: None,
    )
    assert "Ntt=taladro" in calls[0]
    assert calls[1].startswith("https://www.falabella.com/sodimac-cl/lista/cat14080023/Taladros")
    assert "page=2" in calls[1]


HOME_HTML = """
<a href="/falabella-cl/category/cat1640002/Audifonos">a</a>
<a href="/falabella-cl/category/cat40052/Computadores">b</a>
<a href="/falabella-cl/category/cat8960005/Sofas-y-Sillones">c</a>
<a href="/falabella-cl/category/cat999/Ropa-de-Mujer">d</a>
<a href="/falabella-cl/category/cat1640002/Audifonos">dup</a>
"""


def test_discover_categories_filters_by_group_patterns_and_deduplicates():
    patterns = {"tecnologia": ["audifono", "computador"], "muebles": ["sofa"]}
    found = nextdata.discover_categories(HOME_HTML, CFG, patterns)
    assert found == [
        ("tecnologia", "cat1640002", "Audifonos"),
        ("tecnologia", "cat40052", "Computadores"),
        ("muebles", "cat8960005", "Sofas-y-Sillones"),
    ]


def test_discover_categories_respects_the_limit():
    patterns = {"tecnologia": ["audifono", "computador"], "muebles": ["sofa"]}
    assert len(nextdata.discover_categories(HOME_HTML, CFG, patterns, limit=2)) == 2


def test_fetch_store_deals_scans_categories_and_keywords_and_dedupes():
    watchlist = {
        "keywords": ["sony"],
        "scan": {"category_patterns": {"tecnologia": ["audifono"]}, "max_category_pages": 1, "max_search_pages": 1},
    }
    urls = []

    def fake_fetch(url):
        urls.append(url)
        data = props()
        data["pagination"] = {"count": 4, "perPage": 48, "currentPage": 1}
        return data

    deals = nextdata.fetch_store_deals(
        CFG, watchlist, fetch=fake_fetch, fetch_home=lambda url: HOME_HTML, sleep=lambda s: None
    )

    assert any("/category/cat1640002/Audifonos" in u for u in urls)
    assert any("Ntt=sony" in u for u in urls)
    assert len(deals) == 4                         # identical products from both scans collapse
    assert {d.category for d in deals} == {"tecnologia"}  # category scan wins over keyword scan


def test_fetch_store_deals_raises_when_every_scan_fails():
    watchlist = {"keywords": ["sony"], "scan": {"category_patterns": {}, "max_search_pages": 1}}

    def boom(url):
        raise RuntimeError("blocked")

    with pytest.raises(RuntimeError):
        nextdata.fetch_store_deals(CFG, watchlist, fetch=boom, fetch_home=lambda u: "", sleep=lambda s: None)


def test_fetch_store_deals_survives_one_failing_scan():
    watchlist = {"keywords": ["bad", "good"], "scan": {"category_patterns": {}, "max_search_pages": 1}}

    def fake_fetch(url):
        if "Ntt=bad" in url:
            raise RuntimeError("page without product grid")
        data = props()
        data["pagination"] = {"count": 4, "perPage": 48, "currentPage": 1}
        return data

    deals = nextdata.fetch_store_deals(CFG, watchlist, fetch=fake_fetch, fetch_home=lambda u: "", sleep=lambda s: None)
    assert len(deals) == 4


def test_category_jobs_carry_the_slug_as_a_hint_for_priority_matching():
    watchlist = {"keywords": [], "scan": {"category_patterns": {"zapatillas": ["zapatillas-mujer"]},
                                         "max_category_pages": 1}}

    def fake_fetch(url):
        data = props()
        data["pagination"] = {"count": 4, "perPage": 48, "currentPage": 1}
        return data

    home = '<a href="/falabella-cl/category/cat1/Zapatillas-Mujer">z</a>'
    deals = nextdata.fetch_store_deals(CFG, watchlist, fetch=fake_fetch, fetch_home=lambda url: home, sleep=lambda s: None)

    assert deals and all(d.hint == "Zapatillas Mujer" for d in deals)
    assert all(d.category == "zapatillas" for d in deals)           # the group label is unchanged


def test_deep_slugs_are_scanned_with_more_pages_than_ordinary_categories():
    watchlist = {"keywords": [], "scan": {
        "category_patterns": {"ropa": ["moda", "ropa-de"]},
        "deep_slugs": ["moda-mujer"], "deep_pages": 3, "max_category_pages": 1,
    }}
    pages_per_category = {}

    def fake_fetch(url):
        key = url.split("/category/")[1].split("/")[1].split("?")[0]
        pages_per_category[key] = pages_per_category.get(key, 0) + 1
        data = props()
        for result in data["results"]:
            result["productId"] += f"{key}{pages_per_category[key]}"
        data["pagination"] = {"count": 480, "perPage": 48, "currentPage": 1}
        data["currentUrl"] = url.split("falabella.com")[1].split("?")[0]   # as the real site reports it
        return data

    home = ('<a href="/falabella-cl/category/cat1/Moda-Mujer">a</a>'
            '<a href="/falabella-cl/category/cat2/Ropa-de-bebe">b</a>')
    nextdata.fetch_store_deals(CFG, watchlist, fetch=fake_fetch, fetch_home=lambda url: home, sleep=lambda s: None)

    assert pages_per_category["Moda-Mujer"] == 3        # deep
    assert pages_per_category["Ropa-de-bebe"] == 1      # ordinary
