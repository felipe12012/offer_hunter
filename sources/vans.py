from models import Deal
from sources.shopify import StoreConfig, fetch_store_deals

BASE_URL = "https://www.vans.cl"
CONFIG = StoreConfig(store="vans", base_url=BASE_URL, category="zapatillas")


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
