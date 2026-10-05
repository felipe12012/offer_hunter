-- What the store itself says about a product: sold out or not (verify_offers.py opens the product page of the
-- offers people see). A product that is not in our scans is not necessarily sold out (we read the first pages of each
-- listing and the order changes), and one that is in them can be (about 2 % of the fresh ones were): only the product
-- page knows. Service role only.
create table public.offer_availability (
  product_id text primary key,
  available  boolean not null,
  price      integer,
  detail     text,
  checked_at timestamptz not null default now()
);
create index offer_availability_checked_idx on public.offer_availability (checked_at);
alter table public.offer_availability enable row level security;
