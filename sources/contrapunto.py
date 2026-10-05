from models import Deal
from sources.shopify import StoreConfig, fetch_store_deals

BASE_URL = "https://contrapunto.cl"
CONFIG = StoreConfig(store="contrapunto", base_url=BASE_URL, category="libros")


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
