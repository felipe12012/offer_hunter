from models import Deal
from sources.vtex import StoreConfig, fetch_store_deals

BASE_URL = "https://www.asics.cl"
CONFIG = StoreConfig(store="asics", base_url=BASE_URL)


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
