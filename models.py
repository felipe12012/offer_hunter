from dataclasses import dataclass


@dataclass(frozen=True)
class Deal:
    id: str
    title: str
    url: str
    store: str
    category: str
    price: int
    list_price: int
    discount_pct: float
    scraped_at: str


@dataclass(frozen=True)
class ScoredDeal:
    deal: Deal
    real_discount_pct: float
    reasons: list[str]
