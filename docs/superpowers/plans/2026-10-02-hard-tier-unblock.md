# Hard-tier unblock plan (Paris, Ripley, Tottus)

Status: **deferred** (decided 2026-10-02). Not started.

## Problem

Paris (CloudFront), Ripley and Tottus (Cloudflare) reject GitHub Actions
runner IPs (datacenter ranges). Verified 2026-10-02 with a plain HTTP GET from
a runner: Ripley 403, Paris 403, Tottus 403. The same URLs return 200 from a
residential IP (Ripley embeds 56 products in `__NEXT_DATA__`; Paris serves the
catalogue in the HTML). Falabella is reachable from runners (200 +
`__NEXT_DATA__`), so it is not part of this plan.

The block is on the IP, so JSON endpoints, headers and stealth browsers are not
expected to help (stealth browsers untested).

## Options

| # | Option | Cost | Notes |
|---|---|---|---|
| A | Scraping API (ZenRows, ScraperAPI, Scrapfly) | Paid; free tiers too small | ~720 requests/day (3 stores x 5 keywords every 30 min) |
| B | Self-hosted runner with residential IP (mini-PC / Raspberry) | Hardware only | Workflow stays on Actions with `runs-on: self-hosted`; must stay powered on |
| C | Residential proxy in `SCRAPER_PROXY` | Paid per GB | Hook already exists (commit d9f5b31); needs Chilean exit IP |
| D | Stealth browser (Camoufox / patchright) | Free | Fixes fingerprint, not IP; likely insufficient alone |
| E | Alternative sources (price aggregators, affiliate feeds) | Free | Less coverage, some delay |

## Recommended order when resumed

1. Pick A or B (decision on cost vs. keeping a machine on).
2. Make the proxy/API setting per store instead of global, so Sodimac,
   Falabella and Hites keep running without it.
3. Move the three stores to their own workflow (`hard.yml`, cron `*/30`).
4. Block images/fonts/CSS in those scrapers to cut bandwidth if metered.
5. Add a Telegram alert when a store returns zero deals for N consecutive runs.
6. Verify with a manual `workflow_dispatch` run before enabling the cron.

## Interim state

Scrapers for all three stores exist and are covered by fixture tests, but
produce nothing in CI. Each failing run spends roughly 4 minutes on them. If
that time matters, drop them from the `source_fetchers` list in `main_fast.py`
until this plan is resumed.
