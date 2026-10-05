from models import Deal
from sources.shopify import StoreConfig, fetch_store_deals

BASE_URL = "https://coreanachile.cl"
CONFIG = StoreConfig(store="coreanachile", base_url=BASE_URL, category="belleza")


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
