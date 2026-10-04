import Link from "next/link";

import { activeFilterCount, filtersHref, filtersToQuery, GROUPS, MIN_OPTIONS, type Filters } from "@/lib/filters";
import { groupName, storeName, subName } from "@/lib/format";
import { SUBCATEGORIES } from "@/lib/taxonomy";
import type { FeedStats } from "@/lib/types";

const MAX_STORES_SHOWN = 14;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-line py-4 first:pt-0 last:border-b-0">
      <h2 className="mb-2 font-display text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/** Flecha que avisa de que la categoría tiene subcategorías: apunta a la derecha y baja al abrirse. */
function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 16 16"
      className={`h-3.5 w-3.5 shrink-0 transition-transform motion-reduce:transition-none ${open ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M6 3.5L10.5 8L6 12.5" />
    </svg>
  );
}

function Choice({
  href,
  active,
  current,
  children,
  count,
  chevron,
}: {
  href: string;
  active: boolean;
  /** La categoría tiene subcategorías: "closed" las anuncia con una flecha, "open" ya las muestra debajo. */
  chevron?: "closed" | "open";
  /** El elemento es la rama abierta aunque no sea la selección exacta (la categoría con una subcategoría elegida). */
  current?: boolean;
  children: React.ReactNode;
  count?: number;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "true" : current ? "location" : undefined}
      className={`flex min-h-11 items-center justify-between gap-2 px-2 text-[0.95rem] ${
        active ? "bg-ink font-semibold text-paper" : current ? "font-semibold hover:bg-claim-bg" : "hover:bg-claim-bg"
      }`}
    >
      <span className="flex items-center gap-2">
        {chevron ? <Chevron open={chevron === "open"} /> : null}
        <span>{children}</span>
        {chevron === "closed" ? <span className="sr-only">: tiene subcategorías</span> : null}
      </span>
      {count !== undefined ? <span className={`text-sm ${active ? "" : "text-muted"}`}>{count.toLocaleString("es-CL")}</span> : null}
    </Link>
  );
}

function FilterBody({ filters, stats }: { filters: Filters; stats: FeedStats }) {
  const groups = GROUPS.filter((g) => (stats.groups[g] ?? 0) > 0);
  const stores = Object.entries(stats.stores)
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_STORES_SHOWN);

  const toggleStore = (slug: string) =>
    filters.stores.includes(slug) ? filters.stores.filter((s) => s !== slug) : [...filters.stores, slug];

  // El formulario de precio conserva el resto de los filtros como campos ocultos.
  const hidden = new URLSearchParams(filtersToQuery({ ...filters, pmin: null, pmax: null, page: 1 }));

  return (
    <div>
      <Section title="Categoría">
        <nav aria-label="Categoría" className="-mx-2 flex flex-col">
          <Choice href={filtersHref(filters, { cat: null })} active={filters.cat === null}>
            Todas
          </Choice>
          {groups.map((group) => (
            <div key={group}>
              <Choice
                href={filtersHref(filters, { cat: group, sub: null })}
                active={filters.cat === group && filters.sub === null}
                current={filters.cat === group}
                chevron={Object.keys(stats.subs?.[group] ?? {}).length > 0 ? (filters.cat === group ? "open" : "closed") : undefined}
                count={stats.groups[group]}
              >
                {groupName(group)}
              </Choice>
              {filters.cat === group ? (
                <div className="ml-3 border-l border-line pl-1" role="group" aria-label={`Subcategorías de ${groupName(group)}`}>
                  {Object.keys(SUBCATEGORIES[group] ?? {})
                    .filter((sub) => (stats.subs?.[group]?.[sub] ?? 0) > 0)
                    .map((sub) => (
                      <Choice
                        key={sub}
                        href={filtersHref(filters, { cat: group, sub })}
                        active={filters.sub === sub}
                        count={stats.subs?.[group]?.[sub]}
                      >
                        {subName(group, sub)}
                      </Choice>
                    ))}
                </div>
              ) : null}
            </div>
          ))}
        </nav>
      </Section>

      <Section title="Descuento mínimo">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Descuento mínimo">
          {MIN_OPTIONS.map((value) => {
            const active = filters.min === value;
            return (
              <Link
                key={value}
                href={filtersHref(filters, { min: active ? null : value })}
                aria-current={active ? "true" : undefined}
                className={`inline-flex min-h-11 items-center border px-3 font-display text-lg font-semibold leading-none ${
                  active ? "border-ink bg-ink text-paper" : "border-line bg-surface hover:border-ink"
                }`}
              >
                {value}%
              </Link>
            );
          })}
        </div>
      </Section>

      <Section title="Verificación">
        <Link
          href={filtersHref(filters, { ver: !filters.ver })}
          className="flex min-h-11 items-start gap-3 py-1"
        >
          <span
            aria-hidden="true"
            className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center border-2 ${
              filters.ver ? "border-verified bg-verified text-paper" : "border-ink"
            }`}
          >
            {filters.ver ? (
              <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M3 8.5l3.2 3L13 4.5" />
              </svg>
            ) : null}
          </span>
          <span className="text-[0.95rem]">
            Solo con descuento verificado
            <span className="sr-only">{filters.ver ? ": activado" : ": desactivado"}</span>
            <span className="block text-sm text-muted">
              {stats.verified.toLocaleString("es-CL")} productos
            </span>
          </span>
        </Link>
      </Section>

      <Section title="Precio">
        <form action="/" method="get" className="flex flex-col gap-2">
          {[...hidden.entries()].map(([name, value]) => (
            <input key={name} type="hidden" name={name} value={value} />
          ))}
          <div className="flex items-center gap-2">
            <label className="sr-only" htmlFor="pmin">
              Precio mínimo en pesos
            </label>
            <input
              id="pmin"
              name="pmin"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="Desde"
              defaultValue={filters.pmin ?? ""}
              className="h-10 w-full min-w-0 border border-line bg-surface px-2"
            />
            <span aria-hidden="true">–</span>
            <label className="sr-only" htmlFor="pmax">
              Precio máximo en pesos
            </label>
            <input
              id="pmax"
              name="pmax"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="Hasta"
              defaultValue={filters.pmax ?? ""}
              className="h-10 w-full min-w-0 border border-line bg-surface px-2"
            />
          </div>
          <button type="submit" className="h-10 border border-ink font-semibold hover:bg-ink hover:text-paper">
            Aplicar precio
          </button>
        </form>
      </Section>

      <Section title="Tienda">
        <nav aria-label="Tienda" className="-mx-2 flex flex-col">
          {stores.map(([slug, count]) => (
            <Choice
              key={slug}
              href={filtersHref(filters, { stores: toggleStore(slug) })}
              active={filters.stores.includes(slug)}
              count={count}
            >
              {storeName(slug)}
            </Choice>
          ))}
        </nav>
      </Section>
    </div>
  );
}

export function FilterPanel({ filters, stats }: { filters: Filters; stats: FeedStats }) {
  const active = activeFilterCount(filters);
  const clear = (
    <Link href="/" className="text-sm font-medium underline underline-offset-4">
      Limpiar filtros
    </Link>
  );

  return (
    <>
      {/* Móvil: un cajón nativo, sin JavaScript. */}
      <details className="group border border-line bg-surface lg:hidden">
        <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between px-4 font-semibold">
          <span>Filtros{active ? ` (${active})` : ""}</span>
          <span aria-hidden="true" className="group-open:hidden">+</span>
          <span aria-hidden="true" className="hidden group-open:inline">−</span>
        </summary>
        <div className="border-t border-line p-4">
          <FilterBody filters={filters} stats={stats} />
          {active ? <div className="pt-4">{clear}</div> : null}
        </div>
      </details>

      {/* Escritorio: columna fija a la izquierda. */}
      <aside aria-label="Filtros" className="hidden lg:block">
        <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto pr-3">
          <FilterBody filters={filters} stats={stats} />
          {active ? <div className="pt-4">{clear}</div> : null}
        </div>
      </aside>
    </>
  );
}
