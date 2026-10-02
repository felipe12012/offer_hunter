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
    image_url: str = ""


@dataclass(frozen=True)
class ScoredDeal:
    deal: Deal
    real_discount_pct: float
    reasons: list[str]
    # The discount we can stand behind: the drop against our own price history,
    # or the store's advertised discount only when history confirms its "normal
    # price" was really charged. None = not computed (falls back to the larger
    # of the two, the pre-verification behaviour).
    verified_pct: float | None = None
    advertised_confirmed: bool = True
