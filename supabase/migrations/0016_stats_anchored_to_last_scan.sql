-- offer_stats counted "the last 6 hours" from now(): when the scan stops for a few hours the site showed 0 products. The
-- window is now anchored to the freshest product in the feed (the time of the last scan that worked), like the web's
-- queries (web/src/lib/data.ts: getReference). When the scan is healthy the two are the same.
create or replace function public.offer_stats()
returns jsonb
language sql
stable
set search_path = public
as $$
  -- materialized: without it the planner re-evaluates the anchor per row (7 s instead of 0.9 s)
  with anchor as materialized (
    select least(now(), coalesce(max(last_seen_at), now())) as at from public.offer_feed
  ),
  live as materialized (
    select f.* from public.offer_feed f where f.last_seen_at > (select at from anchor) - interval '6 hours'
  )
  select jsonb_build_object(
    'total',     (select count(*) from live),
    'verified',  (select count(*) from live where verified_pct >= 10),
    'super',     (select count(*) from live where verified_pct >= 80),
    'last_seen', (select max(last_seen_at) from live),
    'stores',    coalesce((select jsonb_object_agg(store, n) from
                    (select store, count(*) n from live group by store) s), '{}'::jsonb),
    'groups',    coalesce((select jsonb_object_agg(category_group, n) from
                    (select category_group, count(*) n from live where dup_rank = 1 group by category_group) g), '{}'::jsonb),
    'subs',      coalesce((select jsonb_object_agg(category_group, subs) from
                    (select category_group, jsonb_object_agg(subcat, n) as subs from
                      (select category_group, subcat, count(*) n from live where dup_rank = 1 group by 1, 2) a
                     group by category_group) b), '{}'::jsonb)
  );
$$;
