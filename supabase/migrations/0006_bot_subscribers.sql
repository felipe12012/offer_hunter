-- Telegram bot subscribers: anyone who presses /start in a private chat with the bot gets the
-- offers. The pipeline reads the bot's pending messages at the start of each run
-- (subscribers.py) and sends to every active chat.
--
-- Only the service_role key (the pipeline) touches these tables: RLS on, no policies.

create table public.offer_subscribers (
  chat_id       bigint primary key,
  username      text,
  first_name    text,
  active        boolean not null default true,
  subscribed_at timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index offer_subscribers_active_idx on public.offer_subscribers (chat_id) where active;
alter table public.offer_subscribers enable row level security;

-- Small key/value store for the bot's progress (the last Telegram update already handled).
create table public.offer_bot_state (
  key        text primary key,
  value      text not null,
  updated_at timestamptz not null default now()
);
alter table public.offer_bot_state enable row level security;
