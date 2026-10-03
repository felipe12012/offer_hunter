# tests/test_hites.py
from pathlib import Path

import pytest

from sources.hites import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hites_sample.html"


def test_parse_html_extracts_one_deal_per_sku_deduping_duplicate_cards():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="taladro")

    assert len(result) == 2  # not 3 — duplicate SKU card must collapse to one Deal
    ids = {deal.id for deal in result}
    assert ids == {"hites:10560000309001", "hites:10560000305001"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="taladro")

    kit = next(d for d in result if d.id == "hites:10560000309001")
    assert kit.title == "Kit Taladro Inalámbrico 2 Baterías 16,8v 118 Piezas B01"
    assert kit.price == 49990
    assert kit.url == (
        "https://www.hites.com/kit-taladro-inalambrico-2-baterias-168v-118-piezas-b01-10560000309001.html"
    )
    assert kit.store == "hites"
    assert kit.category == "taladro"


def test_parse_html_falls_back_to_price_as_list_price_when_no_discount_markup():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="taladro")

    plain = next(d for d in result if d.id == "hites:10560000305001")
    assert plain.price == 99990
    assert plain.list_price == 99990
    assert plain.discount_pct == 0.0


def test_parse_html_computes_discount_when_crossed_price_present():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="taladro")

    kit = next(d for d in result if d.id == "hites:10560000309001")
    assert kit.list_price == 79990
    assert kit.discount_pct == 37.5


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><head><title>Hites</title></head><body>no products here</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="taladro")


def test_fetch_deals_paginates_with_start_offsets_and_stops_when_a_page_adds_nothing(monkeypatch):
    from sources import hites

    html = (Path(__file__).parent / "fixtures" / "hites_sample.html").read_text(encoding="utf-8")
    starts = []

    def fake_fetch_html(query, start=0):
        starts.append((query, start))
        return html  # identical every time: page 2 adds nothing new

    monkeypatch.setattr(hites, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(hites, "PAGE_SIZE", 1)  # fixture holds >1 product, so a "full" page
    monkeypatch.setattr(hites.time, "sleep", lambda s: None)

    deals = hites.fetch_deals({"keywords": ["notebook"], "scan": {"max_hites_pages": 5}})

    assert starts == [("notebook", 0), ("notebook", 1)]
    assert deals


def test_fetch_deals_includes_extra_hites_queries_without_duplicates(monkeypatch):
    from sources import hites

    html = (Path(__file__).parent / "fixtures" / "hites_sample.html").read_text(encoding="utf-8")
    queried = []
    monkeypatch.setattr(hites, "fetch_html", lambda q, start=0: queried.append(q) or html)
    monkeypatch.setattr(hites.time, "sleep", lambda s: None)

    hites.fetch_deals({"keywords": ["notebook"], "scan": {"hites_queries": ["notebook", "televisor"]}})

    assert sorted(set(queried)) == ["notebook", "televisor"]


def test_a_search_with_no_results_is_not_an_error_but_a_page_without_tiles_that_is_large_is():
    import pytest as _pytest
    from sources import hites
    from sources.health import NoResultsError

    empty_fragment = "<script>window.topsortTrackingConfig = {};</script>" + " " * 1500   # what the grid returns for 0 results
    with _pytest.raises(NoResultsError):
        hites.parse_html(empty_fragment, category="kerastase")

    broken_layout = "<html><body>" + "<div>x</div>" * 3000 + "</body></html>"           # big page, no tiles: layout changed
    with _pytest.raises(RuntimeError) as err:
        hites.parse_html(broken_layout, category="notebook")
    assert not isinstance(err.value, NoResultsError)


def test_running_off_the_end_of_the_results_keeps_the_earlier_pages(monkeypatch):
    """A query with exactly one full page asks for page 2 and gets the empty fragment;
    it used to raise and throw away the 48 products already read."""
    from sources import hites

    full_page = (Path(__file__).parent / "fixtures" / "hites_sample.html").read_text(encoding="utf-8")
    empty_fragment = "<script>x</script>" + " " * 1500
    pages = {0: full_page, 1: empty_fragment}
    monkeypatch.setattr(hites, "fetch_html", lambda q, start=0: pages[start // 1])
    monkeypatch.setattr(hites, "PAGE_SIZE", 1)
    monkeypatch.setattr(hites.time, "sleep", lambda s: None)

    deals = hites._scan_query("fila", max_pages=3)

    assert deals                                  # page 1 survived


def test_an_empty_first_page_is_reported_as_no_results(monkeypatch):
    import pytest as _pytest
    from sources import hites
    from sources.health import NoResultsError

    monkeypatch.setattr(hites, "fetch_html", lambda q, start=0: "<script>x</script>" + " " * 1500)
    with _pytest.raises(NoResultsError):
        hites._scan_query("redken", max_pages=3)
