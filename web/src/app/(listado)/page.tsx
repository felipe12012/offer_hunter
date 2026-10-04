import Link from "next/link";

import { DealGrid } from "@/components/DealCard";
import { FilterPanel } from "@/components/FilterPanel";
import { Pagination } from "@/components/Pagination";
import { SortBar } from "@/components/SortBar";
import { SuperDeals } from "@/components/SuperDeals";
import { getFeed, getStats, getSuperDeals } from "@/lib/data";
import { activeFilterCount, parseFilters } from "@/lib/filters";
import { agoFrom, groupName, subName } from "@/lib/format";

export const revalidate = 120;

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata({ searchParams }: { searchParams: SearchParams }) {
  const filters = parseFilters(await searchParams);
  if (filters.q) return { title: `“${filters.q}”` };
  if (filters.cat && filters.sub) return { title: `${subName(filters.cat, filters.sub)} · ${groupName(filters.cat)}` };
  if (filters.cat) return { title: groupName(filters.cat) };
  return {};
}

export default async function Home({ searchParams }: { searchParams: SearchParams }) {
  const filters = parseFilters(await searchParams);
  const filtered = activeFilterCount(filters) > 0;
  // El carrusel solo se dibuja en la primera página, pero sus productos se excluyen del listado en todas
  // (si no, la página 2 repetiría o se saltaría productos al mover el desfase).
  const defaultView = !filtered && filters.sort === "best";
  const showSuper = defaultView && filters.page === 1;

  const [stats, superDeals] = await Promise.all([getStats(), defaultView ? getSuperDeals() : Promise.resolve([])]);
  const feed = await getFeed(
    filters,
    superDeals.map((row) => row.id),
  );

  const storeCount = Object.keys(stats.stores).length;
  const verifiedShare = stats.total > 0 ? stats.verified / stats.total : 0;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:py-10">
      {!filtered ? (
        <section className="mb-5 max-w-3xl sm:mb-8">
          <h1 className="font-display text-[2.4rem] font-bold leading-[1.02] sm:text-6xl">
            Descuentos con el precio comprobado
          </h1>
          <p className="mt-2 max-w-2xl text-base text-muted sm:mt-3 sm:text-lg">
            {stats.total.toLocaleString("es-CL")} productos en {storeCount} tiendas ·{" "}
            {stats.verified.toLocaleString("es-CL")} con descuento verificado · actualizado {agoFrom(stats.last_seen)}
          </p>
          <p className="mt-3">
            <Link href="/cyber" className="inline-flex min-h-11 items-center font-semibold text-verified underline underline-offset-4">
              Cyber: posibles errores de precio y mayores descuentos →
            </Link>
          </p>
          {verifiedShare < 0.05 ? (
            <p className="mt-4 hidden border border-verified bg-verified-bg px-4 py-3 text-[0.95rem] sm:block">
              Estamos construyendo el historial de precios, por eso aún son pocos los productos verificados. Los que llevan
              el sello <strong>✓ Verificada</strong> están comprobados; en el resto, el descuento es el que anuncia la
              tienda.{" "}
              <Link href="/como-verificamos" className="font-semibold underline underline-offset-4">
                Cómo lo verificamos
              </Link>
            </p>
          ) : null}
        </section>
      ) : (
        <h1 className="mb-4 font-display text-3xl font-bold sm:text-4xl">
          {filters.q ? (
            <>Resultados para “{filters.q}”</>
          ) : filters.cat && filters.sub ? (
            `${groupName(filters.cat)}: ${subName(filters.cat, filters.sub)}`
          ) : filters.cat ? (
            groupName(filters.cat)
          ) : (
            "Resultados filtrados"
          )}
        </h1>
      )}

      <div className="grid gap-6 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-10">
        <FilterPanel filters={filters} stats={stats} />

        <section aria-labelledby="titulo-listado" className="min-w-0">
          {showSuper ? <SuperDeals rows={superDeals} /> : null}
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
            <h2 id="titulo-listado" className="font-display text-2xl font-semibold">
              {feed.total.toLocaleString("es-CL")} {feed.total === 1 ? "producto" : "productos"}
            </h2>
            <SortBar filters={filters} />
          </div>

          {feed.rows.length > 0 ? (
            <>
              <DealGrid rows={feed.rows} eager={showSuper && superDeals.length > 0 ? 0 : 4} />
              <Pagination filters={filters} total={feed.total} />
            </>
          ) : (
            <div className="border border-line bg-surface p-8">
              <p className="font-display text-2xl font-semibold">No hay productos con esos filtros</p>
              <p className="mt-2 max-w-md text-muted">
                Prueba con otra palabra, baja el descuento mínimo o quita el filtro de tienda.
              </p>
              <Link href="/" className="mt-4 inline-block border border-ink px-4 py-2 font-semibold hover:bg-ink hover:text-paper">
                Limpiar filtros
              </Link>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
