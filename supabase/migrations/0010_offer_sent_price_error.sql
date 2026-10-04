-- Why an announced offer looked like a pricing mistake (price_error.py), so the web's Cyber page can list
-- the possible mistakes of the last days. NULL for ordinary offers.
alter table public.offer_sent add column price_error text;
create index offer_sent_price_error_idx on public.offer_sent (sent_at desc) where price_error is not null;
