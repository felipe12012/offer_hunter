from models import Deal
from sources.nextdata import StoreConfig, fetch_store_deals

BASE_URL = "https://www.falabella.com"
CONFIG = StoreConfig(
    store="falabella",
    base_url=BASE_URL,
    home_url=f"{BASE_URL}/falabella-cl",
    search_url=f"{BASE_URL}/falabella-cl/search?Ntt={{query}}",
    category_url=f"{BASE_URL}/falabella-cl/category/{{id}}/{{slug}}",
    category_href_re=r"/(?:category|lista)/(cat\d+)/([A-Za-z0-9%\-_.]+)",
)


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
