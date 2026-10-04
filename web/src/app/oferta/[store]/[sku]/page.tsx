import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DealGrid } from "@/components/DealCard";
import { DiscountTag, VerifiedStamp } from "@/components/DiscountTag";
import { PriceChart } from "@/components/PriceChart";
import { getHistory, getProduct, getRelated } from "@/lib/data";
import { explainDeal } from "@/lib/explain";
import { agoFrom, clp, groupName, isStale, storeName } from "@/lib/format";
import { dealView } from "@/lib/tiers";

export const revalidate = 120;

const STALE_HOURS = 6;

type Params = Promise<{ store: string; sku: string }>;

function productId(store: string, sku: string): string {
  return `${decodeURIComponent(store)}:${decodeURIComponent(sku)}`;
}

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { store, sku } = await params;
  const row = await getProduct(productId(store, sku));
  return row ? { title: row.title } : { title: "Oferta no disponible" };
}

export default async function ProductPage({ params }: { params: Params }) {
  const { store, sku } = await params;
  const row = await getProduct(productId(store, sku));
  if (!row) notFound();

  if (isStale(row.last_seen_at, STALE_HOURS)) {
    return (
      <main className="mx-auto max-w-3xl px-4 py-16">
        <h1 className="font-display text-4xl font-bold">Esta oferta ya no está disponible</h1>
        <p className="mt-3 text-lg">
          No vemos {row.title} en {storeName(row.store)} desde {agoFrom(row.last_seen_at)}. Puede que se haya agotado o que
          la tienda lo haya retirado.
        </p>
        <Link href={`/?cat=${row.category_group}`} className="mt-6 inline-block border border-ink px-4 py-2 font-semibold hover:bg-ink hover:text-paper">
          Ver más de {groupName(row.category_group)}
        </Link>
      </main>
    );
  }

  const [history, related] = await Promise.all([getHistory(row), getRelated(row)]);
  const view = dealView(row);
  const reasons = explainDeal(row);
  const hasList = row.list_price > row.price;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:py-10">
      <nav aria-label="Ruta" className="mb-4 text-sm text-muted">
        <Link href="/" className="underline underline-offset-4">
          Inicio
        </Link>{" "}
        /{" "}
        <Link href={`/?cat=${row.category_group}`} className="underline underline-offset-4">
          {groupName(row.category_group)}
        </Link>
      </nav>

      <div className="grid gap-8 md:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] md:gap-12">
        <div className="photo relative border border-line">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={row.image_url} alt={row.title} referrerPolicy="no-referrer" width={600} height={600} />
          <div className="absolute left-3 top-3">
            <DiscountTag row={row} size="lg" />
          </div>
        </div>

        <div>
          <p className="text-muted">{storeName(row.store)}</p>
          <h1 className="mt-1 font-display text-3xl font-bold leading-tight sm:text-4xl">{row.title}</h1>

          <p className="mt-5 flex flex-wrap items-baseline gap-x-3">
            <span className="price text-5xl leading-none">{clp(row.price)}</span>
            {hasList ? <s className="text-lg text-muted">{clp(row.list_price)}</s> : null}
          </p>
          {hasList ? <p className="mt-2 text-lg">Ahorras {clp(row.saving)}</p> : null}

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <VerifiedStamp verified={view.verified} showUnverified />
            <span className="text-sm text-muted">Actualizado {agoFrom(row.last_seen_at)}</span>
          </div>

          <a
            href={row.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="mt-6 inline-block bg-ink px-6 py-3 text-lg font-semibold text-paper hover:opacity-90"
          >
            Ver en {storeName(row.store)}
          </a>
          <p className="mt-2 max-w-md text-sm text-muted">
            Se abre la tienda en otra pestaña. Confirma el precio ahí antes de comprar.
          </p>

          <section aria-labelledby="titulo-real" className="mt-8 border-t border-line pt-6">
            <h2 id="titulo-real" className="font-display text-2xl font-semibold">
              ¿Es una oferta real?
            </h2>
            <ul className="mt-3 flex max-w-xl flex-col gap-2.5">
              {reasons.map((reason) => (
                <li
                  key={reason.text}
                  className={`border px-3 py-2 text-[0.95rem] ${
                    reason.tone === "ok"
                      ? "border-verified bg-verified-bg"
                      : reason.tone === "warn"
                        ? "border-[var(--tier-gran)] bg-claim-bg"
                        : "border-line"
                  }`}
                >
                  {reason.text}
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>

      <section aria-labelledby="titulo-historial" className="mt-12">
        <h2 id="titulo-historial" className="mb-3 font-display text-2xl font-semibold">
          Historial de precios
        </h2>
        <PriceChart points={history} endAt={row.last_seen_at} />
      </section>

      {related.length > 0 ? (
        <section aria-labelledby="titulo-relacionados" className="mt-14">
          <h2 id="titulo-relacionados" className="mb-3 font-display text-2xl font-semibold">
            Más de {groupName(row.category_group)}
          </h2>
          <DealGrid rows={related} eager={0} />
        </section>
      ) : null}
    </main>
  );
}
