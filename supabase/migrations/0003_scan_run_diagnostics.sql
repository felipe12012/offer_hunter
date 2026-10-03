-- Per-run diagnostics, so "what happened in this scan?" can be answered from SQL
-- (and later from the web). Additive and nullable: older rows stay valid.
-- Applied 2026-10-03.
alter table public.offer_scan_runs
  add column if not exists store_status jsonb,
  add column if not exists errors jsonb,
  add column if not exists quota jsonb;

comment on column public.offer_scan_runs.store_status is 'per store: {status, deals, seconds, empty_queries, errors[]}. status: ok|partial|failed|timeout|empty|disabled';
comment on column public.offer_scan_runs.errors is 'first error messages of the run (list of strings)';
comment on column public.offer_scan_runs.quota is 'unverified-alert quota state: {unverified_room, eligible, delivered, quota_limited}';
