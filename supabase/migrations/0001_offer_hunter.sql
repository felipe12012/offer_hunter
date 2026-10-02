-- offer_hunter storage on Supabase.
--
-- Tables live in `public` with an `offer_` prefix because this project's Data
-- API only exposes `public`. They are NOT readable or writable by anon or
-- authenticated: RLS is on with no policies, and every grant to those roles is
-- revoked. Only the server-side secret key (service_role) can use them.

create table public.offer_products (
  id            text primary key,                 -- "falabella:80726514"
  store         text not null,
  title         text,
  url           text,
  image_url     text,
  category      text,
  price         integer not null,                 -- lowest public price (CLP)
  list_price    integer not null,                 -- crossed-out "normal" price
  discount_pct  numeric(5,1),
  first_seen_at timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index offer_products_store_idx on public.offer_products (store);

create table public.offer_price_points (
  id          bigint generated always as identity primary key,
  product_id  text not null references public.offer_products (id) on delete cascade,
  observed_at timestamptz not null default now(),
  price       integer not null,
  list_price  integer,                            -- null for points migrated from the JSON history
  source      text not null default 'scan',       -- 'scan' | 'migrated'
  unique (product_id, observed_at, price)         -- makes the JSON import safe to re-run
);
-- also serves the product_id foreign key
create index offer_price_points_product_time_idx
  on public.offer_price_points (product_id, observed_at desc);

create table public.offer_sent (
  id             bigint generated always as identity primary key,
  product_id     text not null,                   -- no FK: migrated keys may predate the product row
  price          integer not null,
  sent_at        timestamptz not null default now(),
  store          text,
  title          text,
  url            text,
  verified_pct   numeric(5,1),
  advertised_pct numeric(5,1),
  real_pct       numeric(5,1),
  reasons        text[],
  source         text not null default 'live',    -- 'live' | 'migrated'
  unique (product_id, price)                      -- same rule as seen_items.json: id + price
);
create index offer_sent_sent_at_idx on public.offer_sent (sent_at desc);

create table public.offer_scan_runs (
  id               bigint generated always as identity primary key,
  started_at       timestamptz not null default now(),
  github_run_id    text,
  scanned          integer,
  new_deals        integer,
  qualifying       integer,
  delivered        integer,
  unverified       integer,
  per_store        jsonb,
  duration_seconds numeric(7,1)
);
create index offer_scan_runs_started_idx on public.offer_scan_runs (started_at desc);

-- Lock everything down: RLS on, no policies, no grants to API roles.
alter table public.offer_products     enable row level security;
alter table public.offer_price_points enable row level security;
alter table public.offer_sent         enable row level security;
alter table public.offer_scan_runs    enable row level security;

revoke all on public.offer_products, public.offer_price_points,
              public.offer_sent, public.offer_scan_runs from anon, authenticated;
revoke all on sequence public.offer_price_points_id_seq, public.offer_sent_id_seq,
                       public.offer_scan_runs_id_seq from anon, authenticated;

grant select, insert, update, delete on public.offer_products, public.offer_price_points,
                                         public.offer_sent, public.offer_scan_runs to service_role;
grant usage on sequence public.offer_price_points_id_seq, public.offer_sent_id_seq,
                        public.offer_scan_runs_id_seq to service_role;

-- One round trip per batch of scanned products: inserts new products, refreshes
-- changed ones and appends a price point only when the price or the crossed-out
-- price differs from the last one stored. SECURITY INVOKER on purpose: it runs
-- with the caller's rights, so it cannot be used to bypass RLS.
create or replace function public.offer_sync_scan(deals jsonb)
returns jsonb
language sql
security invoker
set search_path = public
as $$
  with incoming as (
    select distinct on (d->>'id')
           d->>'id'                     as id,
           d->>'store'                  as store,
           d->>'title'                  as title,
           d->>'url'                    as url,
           nullif(d->>'image_url', '')  as image_url,
           d->>'category'               as category,
           (d->>'price')::integer       as price,
           (d->>'list_price')::integer  as list_price,
           (d->>'discount_pct')::numeric as discount_pct
    from jsonb_array_elements(deals) as d
    order by d->>'id'
  ),
  changed as (
    select i.*,
           (p.id is null
            or p.price      <> i.price
            or p.list_price <> i.list_price) as price_changed,
           (p.id is null) as is_new
    from incoming i
    left join public.offer_products p on p.id = i.id
    where p.id is null
       or p.price      <> i.price
       or p.list_price <> i.list_price
       or p.title is null
       or p.title      is distinct from i.title
       or p.url        is distinct from i.url
       or p.image_url  is distinct from i.image_url
  ),
  upserted as (
    insert into public.offer_products as p
           (id, store, title, url, image_url, category, price, list_price, discount_pct)
    select id, store, title, url, image_url, category, price, list_price, discount_pct
    from changed
    on conflict (id) do update set
      store        = excluded.store,
      title        = excluded.title,
      url          = excluded.url,
      image_url    = excluded.image_url,
      category     = coalesce(p.category, excluded.category),
      price        = excluded.price,
      list_price   = excluded.list_price,
      discount_pct = excluded.discount_pct,
      updated_at   = now()
    returning 1
  ),
  points as (
    insert into public.offer_price_points (product_id, price, list_price)
    select id, price, list_price from changed where price_changed
    returning 1
  )
  select jsonb_build_object(
    'received',  (select count(*) from incoming),
    'new',       (select count(*) from changed where is_new),
    'updated',   (select count(*) from upserted),
    'points',    (select count(*) from points)
  );
$$;

revoke execute on function public.offer_sync_scan(jsonb) from public, anon, authenticated;
grant  execute on function public.offer_sync_scan(jsonb) to service_role;
