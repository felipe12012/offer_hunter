# tests/test_source_isolation.py
import importlib
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# store slug -> its sanitized sample fixture
STORES = {
    "sodimac": "sodimac_sample.html",
    "falabella": "falabella_sample.html",
    "paris": "paris_sample.html",
    "ripley": "ripley_sample.html",
    "tottus": "tottus_sample.html",
    "hites": "hites_sample.html",
}


@pytest.mark.parametrize("store,fixture_name", STORES.items())
def test_a_failing_keyword_does_not_abort_the_other_keywords(monkeypatch, store, fixture_name):
    # A search that resolves to a product/category page with no grid (e.g.
    # "notebook" being a paper notebook in Chile) must not take down the whole
    # store: the other keywords still have to produce their deals.
    module = importlib.import_module(f"sources.{store}")
    good_html = (FIXTURES / fixture_name).read_text(encoding="utf-8")

    def fake_fetch_html(keyword: str) -> str:
        if keyword == "bad":
            raise RuntimeError("search resolved to a page with no product grid")
        return good_html

    monkeypatch.setattr(module, "fetch_html", fake_fetch_html)

    deals = module.fetch_deals({"keywords": ["bad", "good"]})

    assert deals, f"{store} dropped the surviving keyword's deals"


@pytest.mark.parametrize("store", STORES)
def test_every_keyword_failing_raises_so_a_dead_store_is_visible(monkeypatch, store):
    module = importlib.import_module(f"sources.{store}")

    def boom(keyword: str) -> str:
        raise RuntimeError("site down")

    monkeypatch.setattr(module, "fetch_html", boom)

    with pytest.raises(RuntimeError):
        module.fetch_deals({"keywords": ["bad", "worse"]})
