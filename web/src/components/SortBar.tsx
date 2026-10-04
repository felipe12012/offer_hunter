import Link from "next/link";

import { filtersHref, type Filters, type Sort } from "@/lib/filters";

const OPTIONS: { value: Sort; label: string }[] = [
  { value: "best", label: "Mejor descuento" },
  { value: "web", label: "Mayor descuento anunciado" },
  { value: "saving", label: "Mayor ahorro" },
  { value: "price_asc", label: "Menor precio" },
  { value: "price_desc", label: "Mayor precio" },
  { value: "new", label: "Recién llegadas" },
];

export function SortBar({ filters }: { filters: Filters }) {
  return (
    <nav aria-label="Ordenar por" className="-mx-4 flex max-w-[100vw] gap-x-1 overflow-x-auto px-4 sm:mx-0 sm:max-w-none sm:flex-wrap sm:overflow-visible sm:px-0">
      {OPTIONS.map((option) => {
        const active = filters.sort === option.value;
        return (
          <Link
            key={option.value}
            href={filtersHref(filters, { sort: option.value })}
            aria-current={active ? "true" : undefined}
            className={`inline-flex min-h-11 shrink-0 items-center whitespace-nowrap px-2.5 text-sm ${active ? "bg-ink font-semibold text-paper" : "text-muted hover:text-ink hover:underline"}`}
          >
            {option.label}
          </Link>
        );
      })}
    </nav>
  );
}
