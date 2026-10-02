from models import Deal
from sources.nextdata import StoreConfig, fetch_store_deals

BASE_URL = "https://www.sodimac.cl"
# Sodimac serves category listings under /lista/ (its /category/ path redirects
# to the home page) and rewrites keyword searches to those same pages.
CONFIG = StoreConfig(
    store="sodimac",
    base_url=BASE_URL,
    home_url=f"{BASE_URL}/sodimac-cl",
    search_url=f"{BASE_URL}/sodimac-cl/search?Ntt={{query}}",
    category_url=f"{BASE_URL}/sodimac-cl/lista/{{id}}/{{slug}}",
    category_href_re=r"/(?:category|lista)/(cat\d+)/([A-Za-z0-9%\-_.]+)",
)


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
