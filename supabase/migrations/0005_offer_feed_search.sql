-- Accent-insensitive search for the web: PostgREST `ilike` cannot unaccent, so
-- "colchon" never matched "Colchón". The feed gets a normalised copy of the title.
-- Recreates offer_feed (a materialized view cannot be altered); the definition is
-- 0002's plus `title_norm`, a trigram index on it, and `first_seen_at` ordering support.
-- Applied 2026-10-03 (as 0005 + a follow-up that added dup_rank; this file is the final definition). The pipeline only refers to the view by name, so nothing else changes.

create extension if not exists pg_trgm with schema extensions;

drop materialized view if exists public.offer_feed;

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
  select p.id, p.store, p.title,
         lower(translate(p.title, 'áéíóúüñÁÉÍÓÚÜÑ', 'aeiouunAEIOUUN')) as title_norm,
         p.url, p.image_url, p.category,
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
         a.first_point_at,
         p.first_seen_at, p.last_seen_at, p.updated_at,
         -- Falabella and Sodimac share one catalogue, so the same product (same SKU and
         -- price) is listed by both. dup_rank = 1 marks the one the web shows.
         row_number() over (
           partition by case when p.store in ('falabella', 'sodimac') then split_part(p.id, ':', 2) else p.id end,
                        p.price
           order by case p.store when 'falabella' then 1 when 'sodimac' then 2 else 3 end, p.id
         ) as dup_rank
  from public.offer_products p
  left join agg a on a.product_id = p.id
  where p.title is not null and p.image_url is not null and p.last_seen_at is not null
)
select f.*,
       greatest(f.history_drop_pct, case when f.web_confirmed then f.web_discount_pct else 0 end) as verified_pct
from feed f;

create unique index offer_feed_id_idx on public.offer_feed (id);
create index offer_feed_verified_idx on public.offer_feed (verified_pct desc, web_discount_pct desc);
create index offer_feed_group_idx on public.offer_feed (category_group);
create index offer_feed_store_idx on public.offer_feed (store);
create index offer_feed_price_idx on public.offer_feed (price);
create index offer_feed_primary_idx on public.offer_feed (verified_pct desc, web_discount_pct desc) where dup_rank = 1;
create index offer_feed_first_seen_idx on public.offer_feed (first_seen_at desc);
create index offer_feed_title_trgm_idx on public.offer_feed using gin (title_norm extensions.gin_trgm_ops);

revoke all on public.offer_feed from anon, authenticated;
grant select on public.offer_feed to service_role;
