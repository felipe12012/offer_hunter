from models import Deal
from sources.shopify import StoreConfig, fetch_store_deals

BASE_URL = "https://fashionspark.com"
CONFIG = StoreConfig(store="fashionspark", base_url=BASE_URL, category="ropa")


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
