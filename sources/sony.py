from models import Deal
from sources.vtex import StoreConfig, fetch_store_deals

BASE_URL = "https://store.sony.cl"
CONFIG = StoreConfig(store="sony", base_url=BASE_URL, use_intelligent_search=True)


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
