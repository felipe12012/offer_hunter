# CyberDay Hunter — Design Spec

Date: 2026-10-01
Status: Approved for implementation planning

## Purpose

CyberDay (Chilean Black-Friday-style event) runs for a few days with flash
discounts across many retailers. The user wants near-real-time visibility
into genuinely good deals (not inflated "was $X" discounts) across a set
of stores, without manually refreshing tabs. Success = a Telegram digest
that surfaces only deals that are both on-topic (categories the user
cares about) and actually discounted (verified against price history),
within minutes of the deal appearing.

This is a new project, structurally based on the existing
`job-hunter-agent` pipeline (fetch → dedup → filter/score → notify →
persist), but adapted from unstructured text matching (LLM-based CV/job
fit) to structured price/deal data (rule-based filtering, no LLM).

## Scope — Sites

- **Fast tier** (lighter anti-bot, request/API-friendly): Sodimac, Casa
  Royal, Sony (official store), MercadoLibre (uses internal API where
  possible).
- **Hard tier** (strong anti-bot — Cloudflare/Akamai, JS challenges):
  Falabella, Paris, Ripley.

Categories of interest: tecnología, mascotas (alimento), muebles, Sony
products. Exact keywords live in `config/watchlist.json`, not hardcoded.

## Non-goals

- No LLM-based judging (unlike job-hunter-agent's `judge.py`/`matcher.py`)
  — deal price/discount/category are structured fields, rules suffice.
  This also removes API cost and an external failure point.
- No proxy/residential-IP infrastructure in v1. Hard-tier sites running
  on GitHub-hosted runners may be blocked by Cloudflare outright; this is
  accepted for v1 and logged, not solved.
- No price cap filter in v1 (user did not select it as a requirement).
- No persistent external worker (VPS/Render) in v1 — stays on GitHub
  Actions per user's explicit ask to deploy "like job-hunter-agent."

## Architecture

New public repo, `cyberday-hunter`, structurally parallel to
`job-hunter-agent`:

```
cyberday-hunter/
├── main_fast.py          # entrypoint: fast-tier sources
├── main_hard.py           # entrypoint: hard-tier sources
├── models.py              # Deal, ScoredDeal
├── dedup.py               # seen tracking, keyed by (id, price)
├── price_history.py       # per-item price snapshots over time
├── deal_filter.py         # rule-based scoring (replaces judge.py + matcher.py)
├── notifier.py            # Telegram digest (same pattern as job-hunter-agent)
├── config/
│   └── watchlist.json     # categories, keywords, discount thresholds
├── sources/
│   ├── sodimac.py          # fast tier
│   ├── casaroyal.py        # fast tier
│   ├── sony.py             # fast tier
│   ├── mercadolibre.py     # fast tier
│   ├── falabella.py        # hard tier
│   ├── paris.py            # hard tier
│   └── ripley.py           # hard tier
├── data/
│   ├── seen_items.json
│   └── price_history.json
├── tests/
│   ├── fixtures/           # saved HTML/JSON per source, no live network in tests
│   └── test_*.py
└── .github/workflows/
    ├── fast.yml            # cron */15
    └── hard.yml            # cron */30
```

Each `sources/*.py` exposes `fetch_deals(watchlist: dict) -> list[Deal]`,
mirroring the existing `fetch_listings(keywords)` contract so scraping
logic stays swappable per source without touching the pipeline.

`main_fast.py` and `main_hard.py` are thin orchestrators (same shape as
today's `main.py`) that import only their tier's sources and call the
same shared core modules (`deal_filter`, `price_history`, `dedup`,
`notifier`).

## Data Model

```python
# models.py
@dataclass(frozen=True)
class Deal:
    id: str              # stable key: f"{store}:{sku}" or hash(url)
    title: str
    url: str
    store: str
    category: str
    price: int            # CLP, current price
    list_price: int        # store's displayed "normal" price (may be inflated)
    discount_pct: float    # derived: (list_price - price) / list_price
    scraped_at: str         # ISO timestamp

@dataclass(frozen=True)
class ScoredDeal:
    deal: Deal
    real_discount_pct: float   # vs historical minimum price, not list_price
    reasons: list[str]          # e.g. ["-15% vs historical min", "category=tecnologia"]
```

## Storage

**`data/price_history.json`** — key = `Deal.id`, value = bounded list of
snapshots (max 30 per item, oldest dropped on overflow):

```json
{
  "falabella:SKU123": [
    {"date": "2026-09-20", "price": 299990},
    {"date": "2026-09-27", "price": 279990},
    {"date": "2026-10-01", "price": 199990}
  ]
}
```

A snapshot is appended only when price differs from the last recorded
value for that item — avoids bloating the file on every 10-15 min run
when nothing changed.

`real_discount_pct = (min(historical prices) - current price) / min(historical prices)`.
This is the mechanism that defeats "fake discount" (list price shown
crossed-out was never the real lowest price).

**`data/seen_items.json`** — same pattern as job-hunter-agent's
`seen_jobs.json`, but keyed by `(deal.id, deal.price)` rather than just
`id`, so a renewed/deeper price drop on an already-seen item still
triggers a fresh notification.

## Config

**`config/watchlist.json`** (replaces `cv.json`):

```json
{
  "categories": ["tecnologia", "mascotas", "muebles", "sony"],
  "keywords": ["audifonos", "notebook", "alimento perro", "sillon"],
  "min_discount_pct": 30,
  "min_real_discount_pct": 15
}
```

A deal qualifies if it matches a category or keyword AND clears at least
one of the two discount thresholds (`min_discount_pct` against the
store's listed price, `min_real_discount_pct` against tracked history).
An item seen for the first time (no history yet) is judged only against
`min_discount_pct`.

## Data Flow (per tier entrypoint)

```
1. load_watchlist()
2. deals = fetch_deals(watchlist)       # per-source try/except, same resilience
                                          # pattern as today's fetch_listings()
3. history = load_price_history()
4. seen = load_seen()                    # keys: (id, price)
5. for deal in deals:
     update_price_history(history, deal) # append snapshot if price changed
     scored = deal_filter.evaluate(deal, watchlist, history)
     if scored and (deal.id, deal.price) not in seen:
         candidates.append(scored)
6. send_digest(candidates)               # top N by real_discount_pct desc
7. mark_seen(candidates); save_price_history(history)
```

No LLM call anywhere in this loop.

## Error Handling / Anti-Bot Resilience

- Per-source `try/except` in `fetch_deals` aggregation, identical to the
  existing `fetch_listings()` in `main.py`: one broken source does not
  abort the run. The workflow only hard-fails if **every** source in
  that tier fails (same `if failures == len(source_fetchers): raise`
  check already in place).
- Playwright: short per-page timeout (~15s), one retry on
  timeout/challenge, then skip — no unbounded retry loops; the next
  scheduled run (10-30 min later) is the natural retry.
- Realistic user-agent/viewport, randomized 1-3s delays between product
  page visits. This reduces (does not guarantee) bot detection; GitHub
  Actions runner IPs are known datacenter ranges and may be blocked by
  Cloudflare regardless — accepted as a v1 limitation per the Non-goals
  section.
- Selector drift: each `sources/*.py` has tests against a saved HTML/JSON
  fixture (same approach as `test_getonbrd.py`/`test_computrabajo.py`),
  so a site's markup change breaks a local/CI test before it breaks
  production silently.
- Failure notification: each workflow (`fast.yml`, `hard.yml`) keeps the
  existing `if: failure()` Telegram alert step, firing only when the
  whole tier's run fails — not on an individual expected-to-sometimes-fail
  source like Falabella.

## Notification

`notifier.py` mirrors `send_digest()`: top N (default 5) `ScoredDeal`s by
`real_discount_pct` descending, same 4000-char Telegram text cap. Message
shows store, real discount %, historical minimum, and current price so
the user can sanity-check the "fake discount" filtering at a glance:

```
3 ofertas top CyberDay:

*Audifonos Sony WH-1000XM5* @ Falabella - 42% real (vs min hist $199.990)
https://...
Antes: $349.990 tachado | Mínimo histórico: $199.990 | Ahora: $139.990
```

## Testing Strategy

- `test_<source>.py` per source, parsing saved fixtures — no live network
  calls in the test suite.
- `test_deal_filter.py` — discount/category/history rules; edge cases:
  first-time-seen item (no history → `min_discount_pct` only), price
  increases (must not qualify), price unchanged (must not re-notify).
- `test_price_history.py` — snapshot truncation at the cap, no duplicate
  snapshot when price is unchanged.
- `test_workflow.py` — full pipeline with sources mocked, matching the
  existing `test_workflow.py` style in job-hunter-agent.

## Deployment

Two scheduled workflows, both on the public `cyberday-hunter` repo (no
Actions-minute quota concern since the repo is public):

```yaml
# fast.yml
on:
  schedule: [{cron: "*/15 * * * *"}]
  workflow_dispatch: {}
steps:
  - checkout, setup-python
  - pip install -r requirements.txt
  - playwright install --with-deps chromium
  - run: python main_fast.py
  - commit data/seen_items.json + data/price_history.json
  - notify on failure (Telegram)

# hard.yml — same shape, cron "*/30 * * * *", runs main_hard.py
```

Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` only. No LLM API keys
needed (no `DEEPSEEK_API_KEY`/`JEV_API_KEY` equivalent) since there is no
LLM in the loop — zero per-run API cost and one less external failure
point compared to job-hunter-agent.

## Edge Cases Covered

- Item seen for the first time, no price history yet.
- Price goes up (must not notify).
- Price unchanged since last run (must not re-notify, must not duplicate
  history snapshot).
- Site permanently/frequently blocked by anti-bot (tier-level failure
  threshold, isolated per workflow).
- Inflated "crossed-out" list price vs. genuinely lower historical
  minimum (the `real_discount_pct` mechanism).
- Fast-tier and hard-tier run and fail independently of each other.

## Open Items for a Future Iteration (explicitly deferred, not v1)

- Proxy/residential IP rotation if hard-tier sites are blocked too often
  to be useful.
- Price cap / budget ceiling filter.
- Migrating to a persistent external worker (Approach 3 from the design
  discussion) if 10-30 min cadence via GitHub Actions proves too coarse
  once real CyberDay traffic/blocking data comes in.
