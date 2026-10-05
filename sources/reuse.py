from models import Deal
from sources.shopify import StoreConfig, fetch_store_deals

BASE_URL = "https://www.reuse.cl"
CONFIG = StoreConfig(store="reuse", base_url=BASE_URL, category="tecnologia")


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
