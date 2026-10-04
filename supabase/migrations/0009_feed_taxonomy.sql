-- offer_feed with the category/subcategory the pipeline stores (offer_products.grp / subcat, 0008)
-- and a dup_rank that keeps the CHEAPEST copy of a product that Falabella and Sodimac both sell
-- (same SKU), instead of one copy per price.
--
-- A materialized view cannot be altered, so the new one is built next to the old one and swapped
-- by renaming inside this transaction: the web never sees a missing view. Products the pipeline has
-- not classified yet keep the old keyword-based group until their next scan.
--
-- offer_stats() also returns the subcategory counts the filter panel shows.
-- The old view is left as offer_feed_old: drop it once the web works (drop materialized view
-- public.offer_feed_old;).

create materialized view public.offer_feed_next as
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
  select p.id, p.store, p.title,
         lower(translate(p.title, 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')) as title_norm,
         p.url, p.image_url, p.category,
         coalesce(p.grp,
           case
             when lower(p.category) ~ 'zapat|adidas|nike|puma|skechers|converse|vans|reebok|new balance|fila|topper|asics|crocs|salomon|merrell|hush' then 'zapatillas'
             when lower(p.category) ~ 'ropa|polera|pantal|chaqueta|vestido|jeans|buzo|parka|abrigo|moda' then 'ropa'
             when lower(p.category) ~ 'kerastase|redken|belleza|crema|facial|dermo|hidratante|solar|serum|micelar|acido|vitamina|retinol|roche|cerave|vichy|eucerin|avene|isdin|perfume|maquillaje|blond|capilar' then 'belleza'
             when lower(p.category) ~ 'mascota|perro|gato|nyd|n&d|alimento|arena|snack' then 'mascotas'
             when lower(p.category) ~ 'colchon|mueble|sillon|sofa|cama|escritorio|comedor|living|closet' then 'muebles'
             when lower(p.category) ~ 'tecnolog|notebook|tablet|audifono|sony|parlante|televis|smart tv|celular|consola|monitor|videojuego|computador|smartphone' then 'tecnologia'
             when lower(p.category) ~ 'herramienta|taladro' then 'herramientas'
             else 'otros'
           end) as category_group,
         coalesce(p.subcat, 'otros') as subcat,
         p.price, p.list_price,
         coalesce(p.discount_pct, 0) as web_discount_pct,
         greatest(p.list_price - p.price, 0) as saving,
         a.points, a.distinct_prices, a.hist_min, a.hist_max, a.prev_min, a.prev_max,
         (p.list_price > p.price and a.prev_max is not null and a.prev_max >= p.list_price * 0.95) as web_confirmed,
         case when a.prev_min is not null and p.price < a.prev_min
              then round((a.prev_min - p.price)::numeric / a.prev_min * 100, 1) else 0 end as history_drop_pct,
         a.first_point_at,
         p.first_seen_at, p.last_seen_at, p.updated_at,
         -- Falabella and Sodimac share one catalogue: the same SKU is listed by both. dup_rank = 1 marks
         -- the copy the web shows: one that is still on sale (seen in the last 6 hours), then the cheapest.
         row_number() over (
           partition by case when p.store in ('falabella', 'sodimac') then split_part(p.id, ':', 2) else p.id end
           order by (p.last_seen_at < now() - interval '6 hours'), p.price,
                    case p.store when 'falabella' then 1 when 'sodimac' then 2 else 3 end, p.id
         ) as dup_rank
  from public.offer_products p
  left join agg a on a.product_id = p.id
  where p.title is not null and p.image_url is not null and p.last_seen_at is not null
)
select f.*,
       greatest(f.history_drop_pct, case when f.web_confirmed then f.web_discount_pct else 0 end) as verified_pct
from feed f;

create unique index offer_feed_next_id_idx on public.offer_feed_next (id);
create index offer_feed_next_verified_idx on public.offer_feed_next (verified_pct desc, web_discount_pct desc);
create index offer_feed_next_group_idx on public.offer_feed_next (category_group, subcat);
create index offer_feed_next_store_idx on public.offer_feed_next (store);
create index offer_feed_next_price_idx on public.offer_feed_next (price);
create index offer_feed_next_primary_idx on public.offer_feed_next (verified_pct desc, web_discount_pct desc) where dup_rank = 1;
create index offer_feed_next_first_seen_idx on public.offer_feed_next (first_seen_at desc);
create index offer_feed_next_title_trgm_idx on public.offer_feed_next using gin (title_norm extensions.gin_trgm_ops);

revoke all on public.offer_feed_next from anon, authenticated;
grant select on public.offer_feed_next to service_role;

-- Swap: the old view and its indexes get an _old name, the new ones take the final names.
alter materialized view public.offer_feed rename to offer_feed_old;
alter index public.offer_feed_id_idx rename to offer_feed_old_id_idx;
alter index public.offer_feed_verified_idx rename to offer_feed_old_verified_idx;
alter index public.offer_feed_group_idx rename to offer_feed_old_group_idx;
alter index public.offer_feed_store_idx rename to offer_feed_old_store_idx;
alter index public.offer_feed_price_idx rename to offer_feed_old_price_idx;
alter index public.offer_feed_primary_idx rename to offer_feed_old_primary_idx;
alter index public.offer_feed_first_seen_idx rename to offer_feed_old_first_seen_idx;
alter index public.offer_feed_title_trgm_idx rename to offer_feed_old_title_trgm_idx;

alter materialized view public.offer_feed_next rename to offer_feed;
alter index public.offer_feed_next_id_idx rename to offer_feed_id_idx;
alter index public.offer_feed_next_verified_idx rename to offer_feed_verified_idx;
alter index public.offer_feed_next_group_idx rename to offer_feed_group_idx;
alter index public.offer_feed_next_store_idx rename to offer_feed_store_idx;
alter index public.offer_feed_next_price_idx rename to offer_feed_price_idx;
alter index public.offer_feed_next_primary_idx rename to offer_feed_primary_idx;
alter index public.offer_feed_next_first_seen_idx rename to offer_feed_first_seen_idx;
alter index public.offer_feed_next_title_trgm_idx rename to offer_feed_title_trgm_idx;

create or replace function public.offer_stats()
returns jsonb
language sql
stable
set search_path = public
as $$
  with live as (
    select * from public.offer_feed where last_seen_at > now() - interval '6 hours'
  )
  select jsonb_build_object(
    'total',     (select count(*) from live),
    'verified',  (select count(*) from live where verified_pct >= 10),
    'super',     (select count(*) from live where verified_pct >= 80),
    'last_seen', (select max(last_seen_at) from live),
    'stores',    coalesce((select jsonb_object_agg(store, n) from
                    (select store, count(*) n from live group by store) s), '{}'::jsonb),
    -- Counts match what the list shows: one row per product (dup_rank = 1).
    'groups',    coalesce((select jsonb_object_agg(category_group, n) from
                    (select category_group, count(*) n from live where dup_rank = 1 group by category_group) g), '{}'::jsonb),
    'subs',      coalesce((select jsonb_object_agg(category_group, subs) from
                    (select category_group, jsonb_object_agg(subcat, n) as subs from
                      (select category_group, subcat, count(*) n from live where dup_rank = 1 group by 1, 2) a
                     group by category_group) b), '{}'::jsonb)
  );
$$;
