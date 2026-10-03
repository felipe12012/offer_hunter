-- Feed for the public web: freshness tracking + a materialized view that precomputes,
-- per product, the same "is this discount real?" signals the pipeline uses.
--
-- Applied 2026-10-03 (after validating it in a rolled-back transaction). Wire
-- `offer_refresh_feed()` into the pipeline (see docs/superpowers/plans/2026-10-03-offers-web.md).

-- 1) Freshness. Products are only rewritten when they change, so without this a
--    delisted product would show its last price forever. Existing rows that were
--    never re-scanned (title is null: imported from the JSON history) stay NULL
--    and are excluded from the feed.
alter table public.offer_products add column last_seen_at timestamptz;
update public.offer_products set last_seen_at = updated_at where title is not null;
create index offer_products_last_seen_idx on public.offer_products (last_seen_at desc);

-- 2) offer_sync_scan now also refreshes last_seen_at, at most once per hour per
--    product (changed products get it from the upsert; a row cannot be touched by
--    two sub-statements of the same command, hence the NOT EXISTS guard).
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
           (d->>'discount_pct')::numeric as discount_pct
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
  ),
  upserted as (
    insert into public.offer_products as p
           (id, store, title, url, image_url, category, price, list_price, discount_pct, last_seen_at)
    select id, store, title, url, image_url, category, price, list_price, discount_pct, now()
    from changed
    on conflict (id) do update set
      store = excluded.store, title = excluded.title, url = excluded.url,
      image_url = excluded.image_url, category = coalesce(p.category, excluded.category),
      price = excluded.price, list_price = excluded.list_price, discount_pct = excluded.discount_pct,
      updated_at = now(), last_seen_at = now()
    returning 1
  ),
  touched as (
    update public.offer_products p set last_seen_at = now()
    from incoming i
    where p.id = i.id
      and (p.last_seen_at is null or p.last_seen_at < now() - interval '1 hour')
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

-- 3) The feed. "prev_*" are computed over every price point except the latest one
--    (= the price before the current one), exactly like deal_filter.py, which
--    evaluates a deal against history recorded before the current scan.
--      web_confirmed    : the crossed-out price is real, because the product sold
--                         within 5% of it before (deal_filter._confirmed_list_price)
--      history_drop_pct : current price vs the lowest earlier price
--      verified_pct     : the discount we stand behind (history drop, or the web's
--                         percentage when web_confirmed)
create materialized view public.offer_feed as
with pts as (
  select product_id, price, observed_at,
         row_number() over (partition by product_id order by observed_at desc, id desc) as rn
  from public.offer_price_points
),
agg as (
  select product_id,
         count(*) as points, count(distinct price) as distinct_prices,
         min(price) as hist_min, max(price) as hist_max,
         min(price) filter (where rn > 1) as prev_min,
         max(price) filter (where rn > 1) as prev_max,
         min(observed_at) as first_point_at
  from pts group by product_id
),
feed as (
  select p.id, p.store, p.title, p.url, p.image_url, p.category,
         -- Pattern based (not exact lists), so new watchlist words land in the right
         -- group without a migration. `category` is the group label of a category scan
         -- or the search word of a keyword scan, so this is an approximation.
         case
           when lower(p.category) ~ 'zapat|adidas|nike|puma|skechers|converse|vans|reebok|new balance|fila|topper|asics|crocs|salomon|merrell|hush' then 'zapatillas'
           when lower(p.category) ~ 'ropa|polera|pantal|chaqueta|vestido|jeans|buzo|parka|abrigo|moda' then 'ropa'
           when lower(p.category) ~ 'kerastase|redken|belleza|crema|facial|dermo|hidratante|solar|serum|micelar|acido|vitamina|retinol|roche|cerave|vichy|eucerin|avene|isdin|perfume|maquillaje|blond|capilar' then 'belleza'
           when lower(p.category) ~ 'mascota|perro|gato|nyd|n&d|alimento|arena|snack' then 'mascotas'
           when lower(p.category) ~ 'colchon|mueble|sillon|sofa|cama|escritorio|comedor|living|closet' then 'muebles'
           when lower(p.category) ~ 'tecnolog|notebook|tablet|audifono|sony|parlante|televis|smart tv|celular|consola|monitor|videojuego|computador|smartphone' then 'tecnologia'
           when lower(p.category) ~ 'herramienta|taladro' then 'herramientas'
           else 'otros'
         end as category_group,
         p.price, p.list_price,
         coalesce(p.discount_pct, 0) as web_discount_pct,
         greatest(p.list_price - p.price, 0) as saving,
         a.points, a.distinct_prices, a.hist_min, a.hist_max, a.prev_min, a.prev_max,
         (p.list_price > p.price and a.prev_max is not null and a.prev_max >= p.list_price * 0.95) as web_confirmed,
         case when a.prev_min is not null and p.price < a.prev_min
              then round((a.prev_min - p.price)::numeric / a.prev_min * 100, 1) else 0 end as history_drop_pct,
         p.first_seen_at, p.last_seen_at, p.updated_at
  from public.offer_products p
  left join agg a on a.product_id = p.id
  where p.title is not null and p.image_url is not null and p.last_seen_at is not null
)
select f.*,
       greatest(f.history_drop_pct, case when f.web_confirmed then f.web_discount_pct else 0 end) as verified_pct
from feed f;

create unique index offer_feed_id_idx on public.offer_feed (id);   -- required by REFRESH ... CONCURRENTLY
create index offer_feed_verified_idx on public.offer_feed (verified_pct desc, web_discount_pct desc);
create index offer_feed_group_idx on public.offer_feed (category_group);
create index offer_feed_store_idx on public.offer_feed (store);
create index offer_feed_price_idx on public.offer_feed (price);

-- Not readable by the API roles: the web reads it server-side with the secret key.
revoke all on public.offer_feed from anon, authenticated;
grant select on public.offer_feed to service_role;

-- 4) Refresh after each scan. service_role cannot own objects in `public`, so a
--    plain function would fail with "must be owner of materialized view". This is
--    the one deliberate SECURITY DEFINER: empty search_path, a single fixed
--    statement, no parameters, and EXECUTE revoked from everyone but service_role.
create or replace function public.offer_refresh_feed()
returns void
language sql
security definer
set search_path = ''
as $$ refresh materialized view concurrently public.offer_feed; $$;

revoke execute on function public.offer_refresh_feed() from public, anon, authenticated;
grant  execute on function public.offer_refresh_feed() to service_role;
