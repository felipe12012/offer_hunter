import Link from "next/link";

import { agoFrom, clp, storeName } from "@/lib/format";
import { dealView } from "@/lib/tiers";
import type { FeedRow } from "@/lib/types";

import { DiscountTag, VerifiedStamp } from "./DiscountTag";

/** Ruta interna de la ficha: /oferta/falabella/80726514 */
export function productPath(id: string): string {
  const [store, ...rest] = id.split(":");
  return `/oferta/${encodeURIComponent(store)}/${encodeURIComponent(rest.join(":"))}`;
}

export function DealCard({ row, priority = false }: { row: FeedRow; priority?: boolean }) {
  const view = dealView(row);
  const hasList = row.list_price > row.price;

  return (
    <article className="relative flex flex-col border-b border-r border-line bg-surface">
      <div className="photo relative">
        {/* <img> a propósito: cada tienda sirve sus fotos desde otro dominio y algunas bloquean si hay Referer. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={row.image_url}
          alt=""
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          referrerPolicy="no-referrer"
          width={300}
          height={300}
        />
        <div className="absolute left-2 top-2">
          <DiscountTag row={row} />
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-1.5 p-3 sm:p-4">
        <p className="text-sm text-muted">{storeName(row.store)}</p>

        <h3 className="line-clamp-2 min-h-[2.75rem] text-[0.95rem] font-medium leading-snug">
          <Link href={productPath(row.id)} className="after:absolute after:inset-0 hover:underline">
            {row.title}
          </Link>
        </h3>

        <div className="mt-auto pt-2">
          <p className="flex flex-wrap items-baseline gap-x-2">
            <span className="price text-[1.75rem] leading-none">{clp(row.price)}</span>
            {hasList ? (
              <s className="text-sm text-muted" aria-label={`precio normal ${clp(row.list_price)}`}>
                {clp(row.list_price)}
              </s>
            ) : null}
          </p>
          {hasList && row.saving > 0 ? <p className="mt-1 text-sm">Ahorras {clp(row.saving)}</p> : null}
        </div>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <VerifiedStamp verified={view.verified} />
          <span className="text-xs text-muted">{agoFrom(row.last_seen_at)}</span>
        </div>

        <a
          href={row.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="relative z-10 mt-2 block border border-ink px-3 py-2 text-center text-sm font-semibold hover:bg-ink hover:text-paper"
        >
          Ver en {storeName(row.store)}
        </a>
      </div>
    </article>
  );
}

export function DealGrid({ rows }: { rows: FeedRow[] }) {
  return (
    <div className="grid grid-cols-2 border-l border-t border-line md:grid-cols-3 xl:grid-cols-4">
      {rows.map((row, index) => (
        <DealCard key={row.id} row={row} priority={index < 4} />
      ))}
    </div>
  );
}
