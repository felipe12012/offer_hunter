"""Shared query runner for the Salesforce Commerce Cloud stores (Hites, Ahumada).

Both read the store's own ``Search-UpdateGrid`` endpoint over plain HTTP and
page through it with ``start``/``sz``. They used to loop over their queries one
by one and treated every "no product cards" page as a failure, which was wrong
in two ways: a query that matches nothing is normal (a pharmacy has no
"notebook"), and a query that ends exactly on a page boundary asks for one page
too many, gets that same empty fragment and used to discard everything it had
already read.
"""
from concurrent.futures import ThreadPoolExecutor

from models import Deal
from sources import health
from sources.health import NoResultsError

QUERY_WORKERS = 4
# The grid answers a query with no results (or a page past the end) with a tiny
# fragment holding only tracking scripts: ~2 KB against ~800 KB for a real page.
EMPTY_PAGE_MAX_BYTES = 8000

_EMPTY = object()


def is_empty_fragment(html: str) -> bool:
    return len(html) < EMPTY_PAGE_MAX_BYTES


def run_queries(store: str, queries: list[str], scan_query, workers: int = QUERY_WORKERS) -> list[Deal]:
    """Run ``scan_query(query) -> list[Deal]`` for every query, ``workers`` at a time.

    * a ``NoResultsError`` is recorded as an empty query (not an error);
    * any other exception is a failure of that query only;
    * raises only when every query failed, so a dead store is visible.
    """

    def one(query: str):
        try:
            return query, scan_query(query), None
        except NoResultsError:
            return query, [], _EMPTY
        except Exception as exc:
            return query, [], exc

    if not queries:
        return []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(one, queries))

    deals: dict[str, Deal] = {}
    failures = 0
    for query, found, outcome in outcomes:
        if outcome is _EMPTY:
            health.empty(store, query)
            continue
        if outcome is not None:
            failures += 1
            health.warn(store, f"{store} query {query!r} failed: {outcome}")
            continue
        for deal in found:
            deals.setdefault(deal.id, deal)

    if failures == len(queries):
        raise RuntimeError(f"All {store} queries failed")
    return list(deals.values())
