-- Category and subcategory per product, decided by the pipeline from the title (taxonomy.py).
-- The `category` column keeps the scanner keyword ("nike", "perro"); `grp`/`subcat` say what the
-- product is. The next scans fill them in: a product is rewritten when its classification changes.
-- A pipeline that does not send them yet (old code) never erases them.

alter table public.offer_products add column grp text;
alter table public.offer_products add column subcat text;
create index offer_products_grp_idx on public.offer_products (grp, subcat);

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
