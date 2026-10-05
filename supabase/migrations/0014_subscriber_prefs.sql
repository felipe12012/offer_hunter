-- What each subscriber wants to receive (set from the bot with /categorias, /minimo and /tiendas):
-- {"groups": ["tecnologia", ...], "stores": ["falabella", ...], "min_pct": 40}. Empty = everything.
alter table public.offer_subscribers add column prefs jsonb not null default '{}'::jsonb;
