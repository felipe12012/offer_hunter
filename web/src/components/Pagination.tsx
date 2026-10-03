import Link from "next/link";

import { filtersHref, type Filters } from "@/lib/filters";
import { pageWindow, totalPages } from "@/lib/pagination";

export function Pagination({ filters, total }: { filters: Filters; total: number }) {
  const pages = totalPages(total);
  if (pages <= 1) return null;
  const current = Math.min(filters.page, pages);
  const link = "flex h-11 min-w-11 items-center justify-center border border-line bg-surface px-3 font-medium hover:border-ink";

  return (
    <nav aria-label="Páginas" className="mt-8 flex flex-wrap items-center justify-center gap-2">
      {current > 1 ? (
        <Link href={filtersHref(filters, { page: current - 1 })} rel="prev" className={link}>
          Anterior
        </Link>
      ) : null}
      {pageWindow(current, pages).map((page, index) =>
        page === null ? (
          <span key={`gap-${index}`} aria-hidden="true" className="px-1 text-muted">
            …
          </span>
        ) : page === current ? (
          <span key={page} aria-current="page" className="flex h-11 min-w-11 items-center justify-center border border-ink bg-ink px-3 font-semibold text-paper">
            {page}
          </span>
        ) : (
          <Link key={page} href={filtersHref(filters, { page })} className={link} aria-label={`Página ${page}`}>
            {page}
          </Link>
        ),
      )}
      {current < pages ? (
        <Link href={filtersHref(filters, { page: current + 1 })} rel="next" className={link}>
          Siguiente
        </Link>
      ) : null}
    </nav>
  );
}
