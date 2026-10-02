# CyberDay Hunter — Core Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the core, deployable pipeline of a new `cyberday-hunter` project — deal model, dedup, price-history tracking, rule-based filtering, Telegram notification, and one real working scraper (Sodimac) — wired into a GitHub Actions workflow that runs every 10-15 minutes.

**Architecture:** Structurally parallel to `job-hunter-agent` (fetch → dedup → filter/score → notify → persist), but with `judge.py`/`matcher.py`'s LLM-based matching replaced by `deal_filter.py`'s rule-based scoring, since deal price/discount/category are structured fields, not free text. `price_history.py` is new: it tracks per-item price snapshots over time so "real discount" can be verified against the item's own history instead of trusting the store's displayed "was $X" price.

**Tech Stack:** Python 3.12, Playwright (sync API) for scraping (JS-rendered storefronts), BeautifulSoup for parsing already-rendered HTML (keeps parsing logic unit-testable without a live browser), `requests` for Telegram, `pytest` for tests, GitHub Actions for scheduling.

**Spec:** `docs/superpowers/specs/2026-10-01-cyberday-hunter-design.md`

**Scope note:** This plan builds the core pipeline plus **one** reference scraper (Sodimac, fast tier). The spec's remaining 6 sources (Casa Royal, Sony, MercadoLibre, Falabella, Paris, Ripley) and the hard-tier workflow are deliberately out of scope here — each requires live inspection of a site that wasn't pre-verified, and is better done as its own follow-up plan/session once this core is working end-to-end. See "Open Items" in the spec.

## Global Constraints

- Python 3.12, matching `job-hunter-agent`'s `.github/workflows/daily.yml` setup.
- No LLM calls anywhere in this pipeline (spec Non-goals) — `deal_filter.py` is pure rules, no external API, no API key.
- All persisted state lives under `data/*.json`, committed back to the repo by CI, same pattern as `job-hunter-agent/data/seen_jobs.json`.
- Telegram digest: top 5 deals per message, 4000-char text cap (spec Notification section).
- No proxy/residential-IP infrastructure in v1 (spec Non-goals) — hard-tier blocking is accepted and logged, not solved, and is irrelevant to this plan since no hard-tier source is built here.
- `price_history.json` caps each item at 30 snapshots (spec Storage section).
- Repo must be **public** on GitHub so Actions runs are unmetered, same reasoning as `job-hunter-agent`.

## Review Focus

- **Same-scan self-comparison:** `real_discount_pct` must be computed against price history that does **not** yet include the current scrape's own price snapshot. If the orchestrator updates history before evaluating, the very run where a price first drops will compare the price against itself and silently report a 0% real discount. Covered in Task 7 (`test_workflow.py`).
- **First-seen item, no history:** an item with no prior `price_history` entry must not crash and must only be judged against `min_discount_pct`, never `min_real_discount_pct` (there is no history to compare against). Covered in Task 4 (`test_deal_filter.py`).
- **Price increase must not notify:** if `deal.price` is higher than the historical minimum, `real_discount_pct` must stay `0` and the deal must not qualify via the history path. Covered in Task 4 (`test_deal_filter.py`).
- **Duplicate DOM nodes per SKU:** Sodimac renders the same product's price in both a mobile and a desktop block on the same page; `parse_html` must de-duplicate by SKU within one page so a single product doesn't produce two identical `Deal`s (double-counted in the digest and in `price_history`). Covered in Task 6 (`test_sodimac.py`).
- **Case/substring category matching:** watchlist category and keyword matching must be case-insensitive substring matching (mirrors the existing `getonbrd.py` keyword-matching convention), so e.g. watchlist `"tecnologia"` still matches a deal whose category or title is `"Tecnología"` / mixed case. Covered in Task 4 (`test_deal_filter.py`).

---

### Task 1: Project scaffold + data models

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `conftest.py` (empty, mirrors `job-hunter-agent/conftest.py` — its presence makes pytest add the repo root to `sys.path`)
- Create: `models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Deal` dataclass (`id`, `title`, `url`, `store`, `category`, `price: int`, `list_price: int`, `discount_pct: float`, `scraped_at: str`) and `ScoredDeal` dataclass (`deal: Deal`, `real_discount_pct: float`, `reasons: list[str]`) — every later task imports these from `models.py`.

- [ ] **Step 1: Create directory structure and non-code scaffolding**

Create these empty directories (with a `.gitkeep` where needed so git tracks them): `sources/`, `data/`, `config/`, `tests/fixtures/`.

`requirements.txt`:
```
requests==2.32.3
beautifulsoup4==4.12.3
playwright==1.47.0
pytest==8.3.3
python-dotenv==1.0.1
```

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
.env
```

`conftest.py` — empty file (same as `job-hunter-agent`).

- [ ] **Step 2: Write the failing test for `Deal`/`ScoredDeal`**

```python
# tests/test_models.py
from models import Deal, ScoredDeal


def make_deal(**overrides) -> Deal:
    defaults = dict(
        id="sodimac:123",
        title="Taladro percutor",
        url="https://www.sodimac.cl/sodimac-cl/product/123/taladro/123/",
        store="sodimac",
        category="herramientas",
        price=29990,
        list_price=39990,
        discount_pct=25.0,
        scraped_at="2026-10-01T12:00:00+00:00",
    )
    defaults.update(overrides)
    return Deal(**defaults)


def test_deal_is_frozen_and_holds_fields():
    deal = make_deal()
    assert deal.id == "sodimac:123"
    assert deal.price == 29990
    try:
        deal.price = 1
        assert False, "Deal should be immutable"
    except AttributeError:
        pass


def test_scored_deal_wraps_deal_with_reasons():
    deal = make_deal()
    scored = ScoredDeal(deal=deal, real_discount_pct=10.0, reasons=["-25% vs precio normal"])
    assert scored.deal is deal
    assert scored.real_discount_pct == 10.0
    assert scored.reasons == ["-25% vs precio normal"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 4: Write `models.py`**

```python
# models.py
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore conftest.py models.py tests/test_models.py
git commit -m "feat: scaffold project and add Deal/ScoredDeal models"
```

---

### Task 2: Dedup tracking

**Files:**
- Create: `dedup.py`
- Test: `tests/test_dedup.py`

**Interfaces:**
- Consumes: `Deal` from `models.py`.
- Produces: `load_seen(path) -> set[str]`, `deal_key(deal: Deal) -> str`, `filter_unseen(deals: list[Deal], seen_keys: set[str]) -> list[Deal]`, `mark_seen(path, seen_keys: set[str], new_keys: list[str]) -> None`. Task 7's orchestrator calls all four.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dedup.py
import json
from pathlib import Path

from dedup import load_seen, deal_key, filter_unseen, mark_seen
from models import Deal


def make_deal(deal_id: str, price: int) -> Deal:
    return Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://www.sodimac.cl/sodimac-cl/product/{deal_id}/taladro/{deal_id}/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=price,
        discount_pct=0.0,
        scraped_at="2026-10-01T12:00:00+00:00",
    )


def test_load_seen_missing_file_returns_empty_set(tmp_path: Path):
    path = tmp_path / "seen_items.json"
    assert load_seen(path) == set()


def test_load_seen_reads_existing_keys(tmp_path: Path):
    path = tmp_path / "seen_items.json"
    path.write_text(json.dumps(["sodimac:123:29990"]), encoding="utf-8")
    assert load_seen(path) == {"sodimac:123:29990"}


def test_deal_key_combines_id_and_price():
    deal = make_deal("sodimac:123", 29990)
    assert deal_key(deal) == "sodimac:123:29990"


def test_filter_unseen_drops_known_id_price_pairs():
    deals = [make_deal("sodimac:123", 29990), make_deal("sodimac:456", 9990)]
    seen = {"sodimac:123:29990"}
    result = filter_unseen(deals, seen)
    assert [d.id for d in result] == ["sodimac:456"]


def test_filter_unseen_keeps_same_id_at_new_price():
    deals = [make_deal("sodimac:123", 19990)]
    seen = {"sodimac:123:29990"}
    result = filter_unseen(deals, seen)
    assert len(result) == 1


def test_mark_seen_persists_union_of_keys(tmp_path: Path):
    path = tmp_path / "seen_items.json"
    path.write_text(json.dumps(["sodimac:123:29990"]), encoding="utf-8")
    mark_seen(path, {"sodimac:123:29990"}, ["sodimac:456:9990"])
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(saved) == ["sodimac:123:29990", "sodimac:456:9990"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dedup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dedup'`

- [ ] **Step 3: Write `dedup.py`**

```python
# dedup.py
import json
from pathlib import Path

from models import Deal


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8") as f:
        return set(json.load(f))


def deal_key(deal: Deal) -> str:
    return f"{deal.id}:{deal.price}"


def filter_unseen(deals: list[Deal], seen_keys: set[str]) -> list[Deal]:
    return [deal for deal in deals if deal_key(deal) not in seen_keys]


def mark_seen(path: Path, seen_keys: set[str], new_keys: list[str]) -> None:
    updated = seen_keys | set(new_keys)
    with path.open("w", encoding="utf-8") as f:
        json.dump(sorted(updated), f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dedup.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add dedup.py tests/test_dedup.py
git commit -m "feat: add dedup tracking keyed by id+price"
```

---

### Task 3: Price history tracking

**Files:**
- Create: `price_history.py`
- Test: `tests/test_price_history.py`

**Interfaces:**
- Consumes: `Deal` from `models.py`.
- Produces: `load_price_history(path) -> dict`, `update_price_history(history: dict, deal: Deal) -> None` (mutates `history` in place), `save_price_history(path, history: dict) -> None`. Task 4's `evaluate()` reads the `history` dict this produces/mutates; Task 7's orchestrator calls all three.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_price_history.py
import json
from pathlib import Path

from models import Deal
from price_history import load_price_history, save_price_history, update_price_history, MAX_SNAPSHOTS


def make_deal(price: int, scraped_at: str = "2026-10-01T12:00:00+00:00") -> Deal:
    return Deal(
        id="sodimac:123",
        title="Taladro percutor",
        url="https://www.sodimac.cl/sodimac-cl/product/123/taladro/123/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=price,
        discount_pct=0.0,
        scraped_at=scraped_at,
    )


def test_load_price_history_missing_file_returns_empty_dict(tmp_path: Path):
    path = tmp_path / "price_history.json"
    assert load_price_history(path) == {}


def test_update_price_history_adds_first_snapshot():
    history = {}
    update_price_history(history, make_deal(29990))
    assert history["sodimac:123"] == [{"date": "2026-10-01", "price": 29990}]


def test_update_price_history_skips_duplicate_unchanged_price():
    history = {"sodimac:123": [{"date": "2026-09-20", "price": 29990}]}
    update_price_history(history, make_deal(29990, scraped_at="2026-10-01T12:00:00+00:00"))
    assert history["sodimac:123"] == [{"date": "2026-09-20", "price": 29990}]


def test_update_price_history_appends_when_price_changes():
    history = {"sodimac:123": [{"date": "2026-09-20", "price": 29990}]}
    update_price_history(history, make_deal(19990, scraped_at="2026-10-01T12:00:00+00:00"))
    assert history["sodimac:123"] == [
        {"date": "2026-09-20", "price": 29990},
        {"date": "2026-10-01", "price": 19990},
    ]


def test_update_price_history_truncates_to_max_snapshots():
    history = {"sodimac:123": [{"date": f"2026-01-{i:02d}", "price": i} for i in range(1, MAX_SNAPSHOTS + 1)]}
    update_price_history(history, make_deal(MAX_SNAPSHOTS + 1, scraped_at="2026-10-01T12:00:00+00:00"))
    assert len(history["sodimac:123"]) == MAX_SNAPSHOTS
    assert history["sodimac:123"][0]["price"] == 2
    assert history["sodimac:123"][-1]["price"] == MAX_SNAPSHOTS + 1


def test_save_price_history_round_trips(tmp_path: Path):
    path = tmp_path / "price_history.json"
    history = {"sodimac:123": [{"date": "2026-10-01", "price": 29990}]}
    save_price_history(path, history)
    assert json.loads(path.read_text(encoding="utf-8")) == history
    assert load_price_history(path) == history
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_price_history.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'price_history'`

- [ ] **Step 3: Write `price_history.py`**

```python
# price_history.py
import json
from pathlib import Path

from models import Deal

MAX_SNAPSHOTS = 30


def load_price_history(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def update_price_history(history: dict, deal: Deal) -> None:
    snapshots = history.setdefault(deal.id, [])
    if snapshots and snapshots[-1]["price"] == deal.price:
        return
    snapshots.append({"date": deal.scraped_at[:10], "price": deal.price})
    if len(snapshots) > MAX_SNAPSHOTS:
        del snapshots[: len(snapshots) - MAX_SNAPSHOTS]


def save_price_history(path: Path, history: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_price_history.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add price_history.py tests/test_price_history.py
git commit -m "feat: add per-item price history tracking with snapshot cap"
```

---

### Task 4: Watchlist config + rule-based deal filter

**Files:**
- Create: `config/watchlist.json`
- Create: `config/watchlist.example.json` (committed template; `watchlist.json` itself is the user's real config and should NOT be gitignored here — unlike `job-hunter-agent`'s `cv.json`, it holds no personal data, just category/keyword preferences, so it's fine to commit directly)
- Create: `deal_filter.py`
- Test: `tests/test_deal_filter.py`

**Interfaces:**
- Consumes: `Deal`, `ScoredDeal` from `models.py`.
- Produces: `evaluate(deal: Deal, watchlist: dict, history: dict) -> ScoredDeal | None`. Task 7's orchestrator calls this per deal, passing the watchlist dict loaded from `config/watchlist.json` and the `history` dict produced by Task 3 — **critically, called with history that does not yet include the current deal's own just-scraped snapshot** (see Review Focus).

- [ ] **Step 1: Create the watchlist config files**

`config/watchlist.json`:
```json
{
  "categories": ["tecnologia", "mascotas", "muebles", "sony"],
  "keywords": ["audifonos", "notebook", "alimento perro", "sillon", "taladro"],
  "min_discount_pct": 30,
  "min_real_discount_pct": 15
}
```

`config/watchlist.example.json` (identical content, serves as the documented template):
```json
{
  "categories": ["tecnologia", "mascotas", "muebles", "sony"],
  "keywords": ["audifonos", "notebook", "alimento perro", "sillon", "taladro"],
  "min_discount_pct": 30,
  "min_real_discount_pct": 15
}
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_deal_filter.py
from deal_filter import evaluate
from models import Deal

WATCHLIST = {
    "categories": ["tecnologia", "herramientas"],
    "keywords": ["taladro"],
    "min_discount_pct": 30,
    "min_real_discount_pct": 15,
}


def make_deal(price: int, list_price: int, category: str = "herramientas", title: str = "Taladro percutor") -> Deal:
    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    return Deal(
        id="sodimac:123",
        title=title,
        url="https://www.sodimac.cl/sodimac-cl/product/123/taladro/123/",
        store="sodimac",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at="2026-10-01T12:00:00+00:00",
    )


def test_rejects_deal_outside_watchlist_categories_and_keywords():
    deal = make_deal(9990, 9990, category="ropa", title="Polera de algodon")
    assert evaluate(deal, WATCHLIST, {}) is None


def test_category_and_keyword_matching_is_case_insensitive_substring():
    deal = make_deal(6990, 9990, category="Herramientas Electricas", title="Oferta")
    # 30% off ($6990 vs $9990) qualifies on list-price discount alone
    result = evaluate(deal, WATCHLIST, {})
    assert result is not None


def test_qualifies_via_list_price_discount_with_no_history():
    deal = make_deal(6990, 9990)  # 30.03% off
    result = evaluate(deal, WATCHLIST, {})
    assert result is not None
    assert result.real_discount_pct == 0.0
    assert any("precio normal" in reason for reason in result.reasons)


def test_rejects_when_discount_below_threshold_and_no_history():
    deal = make_deal(9000, 9990)  # ~9.9% off, below 30% and no history to check
    assert evaluate(deal, WATCHLIST, {}) is None


def test_qualifies_via_real_discount_against_history_even_if_list_price_discount_is_small():
    deal = make_deal(16990, 17990)  # ~5.6% off list price, below min_discount_pct
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 24990}]}
    # vs historical min 24990: (24990-16990)/24990 = 32% real discount, clears 15%
    result = evaluate(deal, WATCHLIST, history)
    assert result is not None
    assert result.real_discount_pct == 32.0
    assert any("historico" in reason for reason in result.reasons)


def test_price_increase_vs_history_does_not_qualify_via_real_discount():
    deal = make_deal(9000, 9990)  # below list-price threshold too
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 5000}]}  # price went UP
    assert evaluate(deal, WATCHLIST, history) is None


def test_single_historical_snapshot_does_not_crash_and_is_its_own_minimum():
    deal = make_deal(5000, 5000)  # no list-price discount at all
    history = {"sodimac:123": [{"date": "2026-09-01", "price": 5000}]}
    assert evaluate(deal, WATCHLIST, history) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_deal_filter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deal_filter'`

- [ ] **Step 4: Write `deal_filter.py`**

```python
# deal_filter.py
from models import Deal, ScoredDeal


def _matches_watchlist(deal: Deal, watchlist: dict) -> bool:
    categories = [c.lower() for c in watchlist.get("categories", [])]
    keywords = [k.lower() for k in watchlist.get("keywords", [])]
    haystack = f"{deal.category} {deal.title}".lower()
    if any(cat in haystack for cat in categories):
        return True
    if any(kw in haystack for kw in keywords):
        return True
    return False


def _historical_min(deal: Deal, history: dict) -> int | None:
    snapshots = history.get(deal.id)
    if not snapshots:
        return None
    return min(snapshot["price"] for snapshot in snapshots)


def evaluate(deal: Deal, watchlist: dict, history: dict) -> ScoredDeal | None:
    if not _matches_watchlist(deal, watchlist):
        return None

    min_discount_pct = watchlist.get("min_discount_pct", 0)
    min_real_discount_pct = watchlist.get("min_real_discount_pct", 0)

    reasons = []
    qualifies = False

    if deal.discount_pct >= min_discount_pct:
        qualifies = True
        reasons.append(f"-{deal.discount_pct:.0f}% vs precio normal")

    real_discount_pct = 0.0
    historical_min = _historical_min(deal, history)
    if historical_min is not None and deal.price < historical_min:
        real_discount_pct = round((historical_min - deal.price) / historical_min * 100, 1)
        if real_discount_pct >= min_real_discount_pct:
            qualifies = True
            reasons.append(f"-{real_discount_pct:.0f}% vs minimo historico (${historical_min:,})".replace(",", "."))

    if not qualifies:
        return None

    return ScoredDeal(deal=deal, real_discount_pct=real_discount_pct, reasons=reasons)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_deal_filter.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add config/watchlist.json config/watchlist.example.json deal_filter.py tests/test_deal_filter.py
git commit -m "feat: add rule-based deal filter against watchlist and price history"
```

---

### Task 5: Telegram notifier

**Files:**
- Create: `notifier.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- Consumes: `ScoredDeal` from `models.py`.
- Produces: `send_digest(scored_deals: list[ScoredDeal], bot_token: str | None = None, chat_id: str | None = None) -> bool`. Task 7's orchestrator calls this with the list of qualifying `ScoredDeal`s.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_notifier.py
from models import Deal, ScoredDeal
from notifier import send_digest


def make_scored(deal_id: str, price: int, real_discount_pct: float = 20.0) -> ScoredDeal:
    deal = Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://www.sodimac.cl/sodimac-cl/product/{deal_id}/taladro/{deal_id}/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=price + 10000,
        discount_pct=10.0,
        scraped_at="2026-10-01T12:00:00+00:00",
    )
    return ScoredDeal(deal=deal, real_discount_pct=real_discount_pct, reasons=["-20% vs minimo historico ($39.990)"])


class FakeResponse:
    def raise_for_status(self):
        return None


def test_send_digest_sends_when_deals_exist(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["url"] = url
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    result = send_digest([make_scored("sodimac:1", 29990)], bot_token="fake-token", chat_id="12345")

    assert result is True
    assert sent["json"]["chat_id"] == "12345"
    assert "Taladro percutor" in sent["json"]["text"]
    assert "fake-token" in sent["url"]


def test_send_digest_skips_send_when_no_deals(monkeypatch):
    called = {"count": 0}

    def fake_post(url, json, timeout):
        called["count"] += 1
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    result = send_digest([], bot_token="fake-token", chat_id="12345")

    assert result is False
    assert called["count"] == 0


def test_send_digest_caps_at_five_deals_sorted_by_real_discount(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    scored = [make_scored(f"sodimac:{i}", 10000 + i, real_discount_pct=float(i)) for i in range(7)]
    send_digest(scored, bot_token="fake-token", chat_id="12345")

    assert sent["json"]["text"].count("@ sodimac") == 5
    # Highest real_discount_pct values are 6, 5, 4, 3, 2 — item "sodimac:0" and "sodimac:1" must be dropped.
    assert "sodimac:0" not in sent["json"]["text"]
    assert "sodimac:1" not in sent["json"]["text"]


def test_send_digest_truncates_long_text(monkeypatch):
    sent = {}

    def fake_post(url, json, timeout):
        sent["json"] = json
        return FakeResponse()

    monkeypatch.setattr("notifier.requests.post", fake_post)

    scored = make_scored("sodimac:1", 29990)
    scored.reasons.append("x" * 5000)
    result = send_digest([scored], bot_token="fake-token", chat_id="12345")

    assert result is True
    assert len(sent["json"]["text"]) <= 4000


def test_send_digest_raises_on_telegram_error(monkeypatch):
    import requests as real_requests

    def fake_post(url, json, timeout):
        raise real_requests.RequestException("telegram down")

    monkeypatch.setattr("notifier.requests.post", fake_post)

    try:
        send_digest([make_scored("sodimac:1", 29990)], bot_token="fake-token", chat_id="12345")
        assert False, "expected RequestException to propagate"
    except real_requests.RequestException:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_notifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'notifier'`

- [ ] **Step 3: Write `notifier.py`**

```python
# notifier.py
import os

import requests

from models import ScoredDeal

TELEGRAM_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_DEALS_PER_DIGEST = 5
MAX_TELEGRAM_TEXT_LENGTH = 4000


def _format_clp(amount: int) -> str:
    return f"${amount:,}".replace(",", ".")


def format_digest(scored_deals: list[ScoredDeal]) -> str:
    lines = [f"{len(scored_deals)} ofertas top CyberDay:\n"]
    for scored in scored_deals:
        deal = scored.deal
        reasons_text = ", ".join(scored.reasons)
        lines.append(
            f"*{deal.title}* @ {deal.store} - {reasons_text}\n"
            f"{deal.url}\n"
            f"Ahora: {_format_clp(deal.price)}\n"
        )
    return "\n".join(lines)


def send_digest(
    scored_deals: list[ScoredDeal],
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> bool:
    if not scored_deals:
        return False

    top = sorted(scored_deals, key=lambda s: s.real_discount_pct, reverse=True)[:MAX_DEALS_PER_DIGEST]

    bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    text = format_digest(top)
    if len(text) > MAX_TELEGRAM_TEXT_LENGTH:
        text = text[:MAX_TELEGRAM_TEXT_LENGTH]

    response = requests.post(
        TELEGRAM_URL_TEMPLATE.format(token=bot_token),
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    response.raise_for_status()
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_notifier.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add notifier.py tests/test_notifier.py
git commit -m "feat: add Telegram digest notifier"
```

---

### Task 6: Sodimac scraper (reference source, fast tier)

This is the one real, live-verified scraper for this plan. Selectors below were captured live against `https://www.sodimac.cl/sodimac-cl/search?Ntt=<keyword>` on 2026-10-01: product cards render as `.product-wrapper` elements, each containing a product link (`a.link.link-primary[href*="/product/"]`), a title (`.product-title`), and the current price rendered twice — once in a mobile block and once in a desktop block — both as `.parsedPrice` with identical text (e.g. `"$8.990"`). No live item had a visible "was $X" / struck-through original price at capture time (CyberDay 2026 had not started yet), so `.price-dis-grid` (the element that would hold that markup when present) was observed empty on every sampled product; the parser treats it defensively — if it's absent or empty, `list_price` falls back to `price` (0% list-price discount), and the item can still qualify later purely through `price_history`'s real-discount tracking once prices actually move. **Re-verify the `.price-dis-grid` content once live CyberDay discounts are showing**, since its populated shape has not been observed.

**Files:**
- Create: `sources/__init__.py` (empty)
- Create: `sources/sodimac.py`
- Create: `tests/fixtures/sodimac_sample.html`
- Test: `tests/test_sodimac.py`

**Interfaces:**
- Consumes: `Deal` from `models.py`.
- Produces: `fetch_deals(watchlist: dict) -> list[Deal]` — the contract every source module in this project implements. Task 7's orchestrator imports this as `fetch_sodimac_deals`.

- [ ] **Step 1: Create the fixture HTML**

This fixture reproduces the real, observed structure/classes/text of two product cards from the live `search?Ntt=notebook` results page (one with a brand, one without a visible discount marker — matching current live reality).

`tests/fixtures/sodimac_sample.html`:
```html
<html>
<body>
<div class="search-results-products-container">
  <div class="product-wrapper col-1">
    <div class="product ie11-product-container">
      <div class="link-with-wrapper">
        <a class="link link-primary" href="/sodimac-cl/product/6242030/ventilador-de-notebook/6242030/">
          <div class="product-image"></div>
        </a>
      </div>
      <div class="link-with-wrapper">
        <a class="link link-primary" href="/sodimac-cl/product/6242030/ventilador-de-notebook/6242030/">
          <div class="product-brand">Ultra</div>
        </a>
      </div>
      <h2 class="product-title">Ventilador de notebook</h2>
      <div class="price-dis-grid"></div>
      <div class="mobile-price-cart">(7)<span class="parsedPrice">$8.990</span><span class="price-unit">C/U</span></div>
      <div class="desktop-price-cart-btn">(7)<span class="parsedPrice">$8.990</span><span class="price-unit">C/U</span></div>
    </div>
  </div>
  <div class="product-wrapper col-2">
    <div class="product ie11-product-container">
      <div class="link-with-wrapper">
        <a class="link link-primary" href="/sodimac-cl/product/6409121/soporte-para-notebook-plegable-y-compacto-aluminio/6409121/">
          <div class="product-image"></div>
        </a>
      </div>
      <div class="link-with-wrapper">
        <a class="link link-primary" href="/sodimac-cl/product/6409121/soporte-para-notebook-plegable-y-compacto-aluminio/6409121/">
          <div class="product-brand">Importadora Usa</div>
        </a>
      </div>
      <h2 class="product-title">Soporte para notebook plegable y compacto aluminio</h2>
      <div class="price-dis-grid"></div>
      <div class="mobile-price-cart">(0)<span class="parsedPrice">$22.990</span><span class="price-unit">C/U</span></div>
      <div class="desktop-price-cart-btn">(0)<span class="parsedPrice">$22.990</span><span class="price-unit">C/U</span></div>
    </div>
  </div>
</div>
</body>
</html>
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_sodimac.py
from pathlib import Path

import pytest

from sources.sodimac import parse_html

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sodimac_sample.html"


def test_parse_html_extracts_one_deal_per_sku_deduping_mobile_and_desktop_blocks():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="notebook")

    assert len(result) == 2  # not 4 — each SKU's mobile+desktop price blocks must collapse to one Deal
    ids = {deal.id for deal in result}
    assert ids == {"sodimac:6242030", "sodimac:6409121"}


def test_parse_html_extracts_title_price_and_absolute_url():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="notebook")

    fan = next(d for d in result if d.id == "sodimac:6242030")
    assert fan.title == "Ventilador de notebook"
    assert fan.price == 8990
    assert fan.url == "https://www.sodimac.cl/sodimac-cl/product/6242030/ventilador-de-notebook/6242030/"
    assert fan.store == "sodimac"
    assert fan.category == "notebook"


def test_parse_html_falls_back_to_price_as_list_price_when_no_discount_markup():
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = parse_html(html, category="notebook")

    fan = next(d for d in result if d.id == "sodimac:6242030")
    assert fan.list_price == 8990
    assert fan.discount_pct == 0.0


def test_parse_html_raises_when_no_product_cards_found():
    html = "<html><body>no products here</body></html>"
    with pytest.raises(RuntimeError):
        parse_html(html, category="notebook")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_sodimac.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sources.sodimac'`

- [ ] **Step 4: Write `sources/sodimac.py`**

```python
# sources/sodimac.py
import re
from datetime import datetime, timezone
from urllib.parse import quote

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from models import Deal

SEARCH_URL = "https://www.sodimac.cl/sodimac-cl/search?Ntt={query}"
BASE_URL = "https://www.sodimac.cl"


def _parse_price(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _extract_deal(card, category: str) -> Deal | None:
    link = card.select_one('a.link.link-primary[href*="/product/"]')
    title_el = card.select_one(".product-title")
    price_el = card.select_one(".parsedPrice")
    if link is None or title_el is None or price_el is None:
        return None

    href = link.get("href", "")
    sku_match = re.search(r"/product/([^/]+)/", href)
    sku = sku_match.group(1) if sku_match else href
    price = _parse_price(price_el.get_text())

    list_price = price
    dis_el = card.select_one(".price-dis-grid")
    if dis_el is not None:
        dis_price = _parse_price(dis_el.get_text())
        if dis_price > price:
            list_price = dis_price

    discount_pct = round((list_price - price) / list_price * 100, 1) if list_price else 0.0
    url = f"{BASE_URL}{href}" if href.startswith("/") else href

    return Deal(
        id=f"sodimac:{sku}",
        title=title_el.get_text(strip=True),
        url=url,
        store="sodimac",
        category=category,
        price=price,
        list_price=list_price,
        discount_pct=discount_pct,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )


def parse_html(html: str, category: str) -> list[Deal]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".product-wrapper")
    if not cards:
        raise RuntimeError(
            "No product cards found on Sodimac search results page; "
            "the site may be unreachable or its HTML structure may have changed"
        )

    deals: list[Deal] = []
    seen_ids: set[str] = set()
    for card in cards:
        deal = _extract_deal(card, category)
        if deal is not None and deal.id not in seen_ids:
            seen_ids.add(deal.id)
            deals.append(deal)
    return deals


def fetch_html(keyword: str) -> str:
    url = SEARCH_URL.format(query=quote(keyword))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=15000)
        page.wait_for_timeout(1500)
        html = page.content()
        browser.close()
    return html


def fetch_deals(watchlist: dict) -> list[Deal]:
    deals: list[Deal] = []
    for keyword in watchlist.get("keywords", []):
        deals.extend(parse_html(fetch_html(keyword), category=keyword))
    return deals
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sodimac.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Install Playwright's browser binary (one-time, local dev)**

Run: `playwright install chromium`
Expected: downloads and installs the Chromium binary Playwright drives; `fetch_deals`/`fetch_html` (not exercised by the test suite, which only calls `parse_html`) need this to run against the live site.

- [ ] **Step 7: Commit**

```bash
git add sources/__init__.py sources/sodimac.py tests/fixtures/sodimac_sample.html tests/test_sodimac.py
git commit -m "feat: add Sodimac scraper (fast tier reference source)"
```

---

### Task 7: Fast-tier orchestrator

**Files:**
- Create: `main_fast.py`
- Test: `tests/test_workflow.py`

**Interfaces:**
- Consumes: everything produced by Tasks 1-6 (`Deal`/`ScoredDeal`, `dedup.*`, `price_history.*`, `deal_filter.evaluate`, `notifier.send_digest`, `sources.sodimac.fetch_deals`).
- Produces: `run() -> int` (process exit code), and module-level `fetch_sodimac_deals` importable as `main_fast.fetch_sodimac_deals` so tests can monkeypatch it (mirrors `job-hunter-agent/main.py`'s existing pattern of importing fetchers by name rather than hoisting a list at import time, specifically so tests can replace them).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow.py
import json
from pathlib import Path

import main_fast
from models import Deal


def make_deal(deal_id: str, price: int, scraped_at: str = "2026-10-01T12:00:00+00:00") -> Deal:
    return Deal(
        id=deal_id,
        title="Taladro percutor",
        url=f"https://www.sodimac.cl/sodimac-cl/product/{deal_id}/taladro/{deal_id}/",
        store="sodimac",
        category="herramientas",
        price=price,
        list_price=price,
        discount_pct=0.0,
        scraped_at=scraped_at,
    )


def _patch_paths(monkeypatch, tmp_path: Path):
    watchlist = {
        "categories": ["herramientas"],
        "keywords": [],
        "min_discount_pct": 100,  # unreachable via list price alone in this test
        "min_real_discount_pct": 15,
    }
    watchlist_path = tmp_path / "watchlist.json"
    watchlist_path.write_text(json.dumps(watchlist), encoding="utf-8")
    monkeypatch.setattr(main_fast, "WATCHLIST_PATH", watchlist_path)
    monkeypatch.setattr(main_fast, "SEEN_PATH", tmp_path / "seen_items.json")
    monkeypatch.setattr(main_fast, "HISTORY_PATH", tmp_path / "price_history.json")


def test_run_sends_digest_and_persists_state(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(main_fast, "fetch_sodimac_deals", lambda watchlist: [make_deal("sodimac:1", 5000)])

    sent = {}
    monkeypatch.setattr(main_fast, "send_digest", lambda scored: sent.setdefault("count", len(scored)) or True)

    exit_code = main_fast.run()

    assert exit_code == 0
    seen = json.loads((tmp_path / "seen_items.json").read_text(encoding="utf-8"))
    assert seen == ["sodimac:1:5000"]
    history = json.loads((tmp_path / "price_history.json").read_text(encoding="utf-8"))
    assert history["sodimac:1"] == [{"date": "2026-10-01", "price": 5000}]


def test_run_does_not_compare_real_discount_against_its_own_just_scraped_price(monkeypatch, tmp_path):
    """
    Regression guard: on the very first run where price_history.json does not
    yet exist, a deal's real_discount_pct must be computed from history BEFORE
    this run's own snapshot is appended — never against a history that already
    contains today's price (which would make every item its own minimum and
    real_discount_pct always 0).
    """
    _patch_paths(monkeypatch, tmp_path)
    # Seed history with a *previous*, higher price so a real discount exists.
    (tmp_path / "price_history.json").write_text(
        json.dumps({"sodimac:1": [{"date": "2026-09-20", "price": 9990}]}), encoding="utf-8"
    )
    monkeypatch.setattr(main_fast, "fetch_sodimac_deals", lambda watchlist: [make_deal("sodimac:1", 5000)])

    captured = {}
    monkeypatch.setattr(main_fast, "send_digest", lambda scored: captured.setdefault("scored", scored) or True)

    main_fast.run()

    assert len(captured["scored"]) == 1
    # (9990 - 5000) / 9990 = 49.9%, clears min_real_discount_pct=15 from _patch_paths's watchlist
    assert captured["scored"][0].real_discount_pct == 49.9


def test_run_skips_already_seen_id_price_pairs(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "seen_items.json").write_text(json.dumps(["sodimac:1:5000"]), encoding="utf-8")
    monkeypatch.setattr(main_fast, "fetch_sodimac_deals", lambda watchlist: [make_deal("sodimac:1", 5000)])

    captured = {}
    monkeypatch.setattr(main_fast, "send_digest", lambda scored: captured.setdefault("scored", scored) or True)

    main_fast.run()

    assert captured["scored"] == []


def test_run_returns_1_when_source_raises(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)

    def boom(watchlist):
        raise RuntimeError("site down")

    monkeypatch.setattr(main_fast, "fetch_sodimac_deals", boom)

    assert main_fast.run() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main_fast'`

- [ ] **Step 3: Write `main_fast.py`**

```python
# main_fast.py
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from deal_filter import evaluate
from dedup import deal_key, load_seen, mark_seen
from models import Deal
from notifier import send_digest
from price_history import load_price_history, save_price_history, update_price_history
from sources.sodimac import fetch_deals as fetch_sodimac_deals

SEEN_PATH = Path(__file__).parent / "data" / "seen_items.json"
HISTORY_PATH = Path(__file__).parent / "data" / "price_history.json"
WATCHLIST_PATH = Path(__file__).parent / "config" / "watchlist.json"

load_dotenv(Path(__file__).parent / ".env")


def load_watchlist() -> dict:
    with WATCHLIST_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_all_deals(watchlist: dict) -> list[Deal]:
    # Built fresh on every call (not hoisted to module scope) so tests can
    # monkeypatch main_fast.fetch_sodimac_deals and have this function see
    # the replacement — same reasoning as job-hunter-agent/main.py.
    source_fetchers = [
        ("sodimac", fetch_sodimac_deals),
    ]

    deals: list[Deal] = []
    failures = 0
    for name, fetch in source_fetchers:
        try:
            deals.extend(fetch(watchlist))
        except Exception as exc:
            failures += 1
            print(f"{name} scraper failed: {exc}", file=sys.stderr)

    if failures == len(source_fetchers):
        raise RuntimeError("All fast-tier sources failed to fetch deals")

    return deals


def run() -> int:
    watchlist = load_watchlist()

    try:
        deals = fetch_all_deals(watchlist)
    except Exception as exc:
        print(f"Scraper failed: {exc}", file=sys.stderr)
        return 1

    history = load_price_history(HISTORY_PATH)
    seen_keys = load_seen(SEEN_PATH)

    candidates = []
    new_keys = []
    for deal in deals:
        key = deal_key(deal)
        already_seen = key in seen_keys
        # Evaluate against history BEFORE this run's own snapshot is recorded,
        # so a price drop compares against prior runs, not against itself.
        scored = None if already_seen else evaluate(deal, watchlist, history)
        update_price_history(history, deal)
        if already_seen:
            continue
        new_keys.append(key)
        if scored:
            candidates.append(scored)

    try:
        send_digest(candidates)
    except Exception as exc:
        print(f"Notification failed: {exc}", file=sys.stderr)
        return 1

    mark_seen(SEEN_PATH, seen_keys, new_keys)
    save_price_history(HISTORY_PATH, history)
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests across every task pass (models, dedup, price_history, deal_filter, notifier, sodimac, workflow)

- [ ] **Step 6: Commit**

```bash
git add main_fast.py tests/test_workflow.py
git commit -m "feat: add fast-tier orchestrator wiring the full pipeline"
```

---

### Task 8: GitHub Actions deployment

**Files:**
- Create: `.github/workflows/fast.yml`
- Create: `README.md`
- Test: `tests/test_fast_workflow_yaml.py`

**Interfaces:**
- Consumes: `main_fast.py` (Task 7) as the command the workflow runs.
- Produces: a scheduled CI job. Nothing downstream in this plan depends on it; it's the deployment target the whole pipeline was built for.

- [ ] **Step 1: Write the failing test for the workflow file**

```python
# tests/test_fast_workflow_yaml.py
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).parent.parent / ".github" / "workflows" / "fast.yml"


def test_workflow_yaml_is_valid_and_scheduled_every_15_minutes():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    # PyYAML parses the bare `on:` key as the boolean True (YAML 1.1 quirk).
    triggers = parsed[True]
    assert triggers["schedule"][0]["cron"] == "*/15 * * * *"
    assert "workflow_dispatch" in triggers
    assert parsed["permissions"]["contents"] == "write"


def test_workflow_uses_required_secrets():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    for secret_name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        assert f"secrets.{secret_name}" in content


def test_workflow_installs_playwright_chromium():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "playwright install" in content
    assert "chromium" in content


def test_workflow_commits_data_files():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "data/seen_items.json" in content
    assert "data/price_history.json" in content


def test_workflow_notifies_telegram_on_failure():
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)

    steps = parsed["jobs"]["run-pipeline"]["steps"]
    failure_steps = [step for step in steps if step.get("if") == "failure()"]

    assert len(failure_steps) == 1
    assert "sendMessage" in failure_steps[0]["run"]
    assert steps[-1] is failure_steps[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_fast_workflow_yaml.py -v`
Expected: FAIL with `FileNotFoundError` (workflow file doesn't exist yet)

- [ ] **Step 3: Write `.github/workflows/fast.yml`**

```yaml
name: Fast Tier Deal Scan

on:
  schedule:
    - cron: "*/15 * * * *"
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Install Playwright chromium
        run: playwright install --with-deps chromium

      - name: Run pipeline
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python main_fast.py

      - name: Commit updated data files
        run: |
          git config user.name "cyberday-hunter"
          git config user.email "actions@users.noreply.github.com"
          git add data/seen_items.json data/price_history.json
          git diff --cached --quiet || git commit -m "chore: update seen items and price history"
          git push

      - name: Notify on failure
        if: failure()
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: |
          curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d chat_id="${TELEGRAM_CHAT_ID}" \
            -d text="⚠️ cyberday-hunter (fast tier): el pipeline falló. Logs: https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_fast_workflow_yaml.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Seed the initial data files and write the README**

Create `data/seen_items.json` with content `[]` and `data/price_history.json` with content `{}` (so the first CI run has a valid file to read/diff against, matching `job-hunter-agent/data/seen_jobs.json`'s convention).

`README.md`:
```markdown
# cyberday-hunter

Scans Sodimac (fast tier) every 15 minutes for deals matching
`config/watchlist.json`, filters out fake "was $X" discounts by tracking each
item's real price history, and pushes qualifying deals to Telegram.

## Setup

1. `pip install -r requirements.txt`
2. `playwright install chromium`
3. Edit `config/watchlist.json` with your categories/keywords/thresholds.
4. Copy your own `.env` with `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` for local runs,
   or set them as GitHub Actions repo secrets for CI (`.github/workflows/fast.yml`).

## Run locally

```
python main_fast.py
```

## Scope

This repo currently covers one source (Sodimac, fast tier). See
`docs/superpowers/specs/2026-10-01-cyberday-hunter-design.md` for the full
multi-site design and the hard-tier (Falabella/Paris/Ripley) plan still to come.
```

- [ ] **Step 6: Run the full test suite one last time**

Run: `pytest -v`
Expected: all tests pass across the whole project

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/fast.yml tests/test_fast_workflow_yaml.py data/seen_items.json data/price_history.json README.md
git commit -m "feat: deploy fast-tier pipeline via scheduled GitHub Actions workflow"
```

---

## After this plan

Creating the actual GitHub repo, pushing this code to it, and adding the
`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` secrets are actions with external,
hard-to-reverse effects (new public repo, real credentials) — confirm with
the user before doing them, same as any other push/publish action. Once
this core is live and confirmed working against the real Sodimac site, the
next plan adds a hard-tier source (starting with whichever of
Falabella/Paris/Ripley the user wants first) plus `main_hard.py` and
`.github/workflows/hard.yml`, each requiring its own live site inspection
the way Task 6 did here.
