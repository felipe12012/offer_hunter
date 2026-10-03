-- Fase 1.2 del plan docs/superpowers/plans/2026-10-03-offers-web.md
-- Estadísticas de portada para la web (offer_stats()).
--
-- APLICADA el 2026-10-03, tras validarla dentro de una transacción deshecha
-- (devolvió 22.092 productos vigentes, 19 tiendas y los grupos esperados).
-- Requiere 0002_offer_feed.sql (la vista offer_feed y su columna last_seen_at).
--
-- `security invoker`: respeta el RLS/permisos de quien llama; no da acceso a
-- nada extra, y solo service_role tiene EXECUTE.

create or replace function public.offer_stats()
returns jsonb
language sql
stable
security invoker
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
    'groups',    coalesce((select jsonb_object_agg(category_group, n) from
                    (select category_group, count(*) n from live group by category_group) g), '{}'::jsonb)
  );
$$;

revoke execute on function public.offer_stats() from public, anon, authenticated;
grant  execute on function public.offer_stats() to service_role;
