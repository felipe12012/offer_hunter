from models import Deal
from sources.shopify import StoreConfig, fetch_store_deals

BASE_URL = "https://www.outletdelcafe.cl"
CONFIG = StoreConfig(store="outletdelcafe", base_url=BASE_URL, category="alimentos")


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
