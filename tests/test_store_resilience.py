"""The new HTTP stores: a refusal stops the store at once, a search with no results is not an error, and
the slow Tus Mascotas endpoint gets the time it needs."""
import pytest
import requests

from sources import health, httpclient, kliper, maconline, surprice, tusmascotas


def response(status: int, text: str = "") -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = text.encode()
    r.url = "https://shop.example/catalogsearch/result/?q=x"
    return r


# ---- a refusal is not retried and stops the store -------------------------------------------------

@pytest.mark.parametrize("module", [surprice, kliper])
@pytest.mark.parametrize("status", [403, 405, 429])
def test_a_refusal_is_not_retried(monkeypatch, module, status):
    calls = []
    monkeypatch.setattr(module.httpclient, "get", lambda url, headers=None, **kw: calls.append(url) or response(status))
    monkeypatch.setattr(module.time, "sleep", lambda s: None)

    with pytest.raises(httpclient.Blocked):
        module.fetch_html("audifonos")

    assert len(calls) == 1  # no 3 attempts with sleeps: the site said no


@pytest.mark.parametrize("module", [surprice, kliper])
def test_a_store_that_refuses_us_is_dropped_after_the_first_answer(monkeypatch, module):
    asked = []

    def blocked(keyword):
        asked.append(keyword)
        raise httpclient.Blocked("HTTP 405 from shop.example")

    monkeypatch.setattr(module, "fetch_html", blocked)

    with pytest.raises(RuntimeError, match="refusing us"):
        module.fetch_deals({"keywords": ["a", "b", "c", "d"]})

    assert asked == ["a"]  # three more keywords were not asked: that was 250 s of retries per scan


def test_a_missing_page_is_still_a_normal_error(monkeypatch):
    monkeypatch.setattr(surprice.httpclient, "get", lambda url, headers=None, **kw: response(404))
    monkeypatch.setattr(surprice.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as err:
        surprice.fetch_html("x")
    assert not isinstance(err.value, httpclient.Blocked)


# ---- no results is not a failure --------------------------------------------------------------------

NO_CARDS = "<html><head><title>Buscar</title></head><body><p>Sin resultados</p></body></html>"


@pytest.mark.parametrize("module", [maconline, kliper, surprice])
def test_a_search_with_no_products_is_empty_not_an_error(monkeypatch, module):
    monkeypatch.setattr(module, "fetch_html", lambda keyword: NO_CARDS)
    health.drain()

    assert module.fetch_deals({"keywords": ["taladro", "sony"]}) == []

    kinds = [event["kind"] for event in health.drain()]
    assert kinds == ["empty", "empty"]  # not "error": the store just does not sell it


@pytest.mark.parametrize("module", [maconline, kliper, surprice])
def test_a_real_failure_is_still_an_error(monkeypatch, module):
    def boom(keyword):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(module, "fetch_html", boom)
    health.drain()
    with pytest.raises(RuntimeError, match="All .* keywords failed"):
        module.fetch_deals({"keywords": ["taladro"]})
    assert [event["kind"] for event in health.drain()] == ["error"]


# ---- Tus Mascotas answers slowly --------------------------------------------------------------------

def test_tus_mascotas_gets_a_long_timeout(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["timeout"] = timeout
        return response(200, "[]")

    monkeypatch.setattr(tusmascotas.httpclient, "get", fake_get)
    assert tusmascotas._fetch_page("perro", 1) == []
    assert seen["timeout"] == tusmascotas.REQUEST_TIMEOUT_SECONDS == 45
    assert seen["timeout"] > httpclient.DEFAULT_TIMEOUT_SECONDS
