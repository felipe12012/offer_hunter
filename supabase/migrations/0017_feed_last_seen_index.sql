-- Every page of the web asks for "the most recently seen product" (web/src/lib/data.ts: getReference), offer_stats() takes
-- the max of the same column and every list filters on it, and offer_feed had no index on last_seen_at: each of those was
-- a full scan of ~106k rows. Under load they piled up. The index survives "refresh materialized view".
create index if not exists offer_feed_last_seen_idx on public.offer_feed (last_seen_at desc);

-- The previous version of the view (kept after the taxonomy migration, 87 MB, nothing reads it any more).
drop materialized view if exists public.offer_feed_old;
