-- Products a Telegram chat follows ("tell me when this gets cheaper"). Created from the bot (/start seguir_<store>_<sku>,
-- the button on the web's product page) and checked on every scan (watches.py). Service role only.
create table public.offer_watches (
  id                  bigint generated always as identity primary key,
  chat_id             bigint not null,
  product_id          text not null,
  baseline_price      integer not null,   -- price when the chat started following
  target_price        integer,            -- optional: alert when the price is at or below this
  last_notified_price integer,            -- price of the last alert (no repeats until it drops further or re-arms)
  active              boolean not null default true,
  created_at          timestamptz not null default now(),
  unique (chat_id, product_id)
);
create index offer_watches_active_idx on public.offer_watches (product_id) where active;
alter table public.offer_watches enable row level security;
