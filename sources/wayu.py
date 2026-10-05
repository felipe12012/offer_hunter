from models import Deal
from sources.shopify import StoreConfig, fetch_store_deals

BASE_URL = "https://wayu.cl"
CONFIG = StoreConfig(store="wayu", base_url=BASE_URL, category="muebles")


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
