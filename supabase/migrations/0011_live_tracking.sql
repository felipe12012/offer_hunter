-- Offers that ended or sold out: the web needs to know quickly that a product is no longer seen.
-- offer_sync_scan used to refresh last_seen_at once an hour per unchanged product; for products with 50 % off or more
-- and for the ones announced in the last 3 days it now does so in every scan (~25-30k rows), and offer_stats counts
-- like the web's list (see web/src/lib/live.ts).

create or replace function public.offer_sync_scan(deals jsonb)
returns jsonb
language sql
security invoker
set search_path = public
as $$
  with incoming as (
    select distinct on (d->>'id')
           d->>'id' as id, d->>'store' as store, d->>'title' as title, d->>'url' as url,
           nullif(d->>'image_url', '') as image_url, d->>'category' as category,
           (d->>'price')::integer as price, (d->>'list_price')::integer as list_price,
           (d->>'discount_pct')::numeric as discount_pct,
           nullif(d->>'grp', '') as grp, nullif(d->>'subcat', '') as subcat
    from jsonb_array_elements(deals) as d
    order by d->>'id'
  ),
  changed as (
    select i.*,
           (p.id is null or p.price <> i.price or p.list_price <> i.list_price) as price_changed,
           (p.id is null) as is_new
    from incoming i
    left join public.offer_products p on p.id = i.id
    where p.id is null
       or p.price <> i.price
       or p.list_price <> i.list_price
       or p.title is null
       or p.title is distinct from i.title
       or p.url is distinct from i.url
       or p.image_url is distinct from i.image_url
       or (i.grp is not null and (p.grp is distinct from i.grp or p.subcat is distinct from i.subcat))
  ),
  upserted as (
    insert into public.offer_products as p
           (id, store, title, url, image_url, category, price, list_price, discount_pct, grp, subcat, last_seen_at)
    select id, store, title, url, image_url, category, price, list_price, discount_pct, grp, subcat, now()
    from changed
    on conflict (id) do update set
      store = excluded.store, title = excluded.title, url = excluded.url,
      image_url = excluded.image_url, category = coalesce(p.category, excluded.category),
      price = excluded.price, list_price = excluded.list_price, discount_pct = excluded.discount_pct,
      grp = coalesce(excluded.grp, p.grp), subcat = coalesce(excluded.subcat, p.subcat),
      updated_at = now(), last_seen_at = now()
    returning 1
  ),
  touched as (
    update public.offer_products p set last_seen_at = now()
    from incoming i
    where p.id = i.id
      and (
        p.last_seen_at is null
        or p.last_seen_at < now() - interval '1 hour'
        -- Products that matter (50 % off or more, or announced in the last 3 days) are touched in every scan, so
        -- the web can tell "no longer seen for an hour" from "seen a moment ago" and mark the offer as ended.
        or (
          p.last_seen_at < now() - interval '10 minutes'
          and (
            i.discount_pct >= 50
            or exists (select 1 from public.offer_sent s where s.product_id = i.id and s.sent_at > now() - interval '72 hours')
          )
        )
      )
      and not exists (select 1 from changed c where c.id = i.id)
    returning 1
  ),
  points as (
    insert into public.offer_price_points (product_id, price, list_price)
    select id, price, list_price from changed where price_changed
    returning 1
  )
  select jsonb_build_object(
    'received', (select count(*) from incoming),
    'new',      (select count(*) from changed where is_new),
    'updated',  (select count(*) from upserted),
    'touched',  (select count(*) from touched),
    'points',   (select count(*) from points)
  );
$$;

-- The filter panel counts what the list shows: offers of 50 % or more disappear from the list after 60 minutes
-- without being seen, the rest after 150 (they are only touched hourly).
create or replace function public.offer_stats()
returns jsonb
language sql
stable
set search_path = public
as $$
  with live as (
    select * from public.offer_feed
    where last_seen_at > now() - interval '150 minutes'
      and (web_discount_pct < 50 or last_seen_at > now() - interval '60 minutes')
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
