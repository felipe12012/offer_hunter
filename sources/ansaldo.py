from models import Deal
from sources.shopify import StoreConfig, fetch_store_deals

BASE_URL = "https://ansaldo.cl"
CONFIG = StoreConfig(store="ansaldo", base_url=BASE_URL, category="ropa")


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
