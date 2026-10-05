from models import Deal
from sources.vtex import StoreConfig, fetch_store_deals

BASE_URL = "https://cl.hm.com"
CONFIG = StoreConfig(store="hm", base_url=BASE_URL)


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
