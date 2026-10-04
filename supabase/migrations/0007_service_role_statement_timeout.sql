-- offer_refresh_feed() rebuilds the offer_feed materialized view (~53k rows, ~9 s), and PostgREST
-- runs every request under the 8 s statement_timeout of the `authenticator` role. From about
-- 2026-10-03 21:00 UTC the refresh was cancelled ("canceling statement due to statement timeout"),
-- the feed stopped updating and the web, which only shows offers seen in the last 6 hours,
-- ended up empty.
--
-- Only the pipeline and the web's server-side fetch use the service_role key; anon and
-- authenticated keep their short limits.
alter role service_role set statement_timeout = '120s';
