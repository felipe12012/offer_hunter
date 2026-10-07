import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DealGrid } from "@/components/DealCard";
import { DiscountTag, VerifiedStamp } from "@/components/DiscountTag";
import { VerdictBadge } from "@/components/VerdictBadge";
import { PriceChart } from "@/components/PriceChart";
import { getHistory, getProduct, getRelated, getSiblings, getStoreStatus } from "@/lib/data";
import { explainDeal } from "@/lib/explain";
import { followLink } from "@/lib/follow";
import { agoFrom, clp, groupName, storeName, subName } from "@/lib/format";
import { availability, GONE_HOURS } from "@/lib/live";
import { dealView } from "@/lib/tiers";
import { verdictFor } from "@/lib/verdict";

export const revalidate = 120;

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

  const status = availability(row);
  if (status.minutes > GONE_HOURS * 60) {
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

  const [history, related, siblings, storeStatus] = await Promise.all([
    getHistory(row),
    getRelated(row),
    getSiblings(row),
    getStoreStatus(row.id),
  ]);
  // La tienda dice que no tiene stock: más fiable que deducirlo de que dejó de aparecer.
  const soldOut = storeStatus?.available === false;
  const ended = status.ended || soldOut;
  const view = dealView(row);
  const reasons = explainDeal(row);
  const hasList = row.list_price > row.price;
  const verdict = ended ? null : verdictFor(row);
  const follow = ended ? null : followLink(row.store, row.id.slice(row.store.length + 1), process.env.TELEGRAM_BOT_USERNAME);

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
        {row.subcat ? (
          <>
            {" "}
            /{" "}
            <Link href={`/?cat=${row.category_group}&sub=${row.subcat}`} className="underline underline-offset-4">
              {subName(row.category_group, row.subcat)}
            </Link>
          </>
        ) : null}
      </nav>

      <div className="grid gap-8 md:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] md:gap-12">
        <div className={`photo relative border border-line ${ended ? "ended" : ""}`}>
          {ended ? <span className="ended-badge">{soldOut ? "Agotado" : "Oferta terminada"}</span> : null}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={row.image_url} alt={row.title} referrerPolicy="no-referrer" width={600} height={600} />
          <div className="absolute left-3 top-3">
            <DiscountTag row={row} size="lg" />
          </div>
        </div>

        <div className={ended ? "ended" : undefined}>
          {ended ? (
            <p role="status" className="mb-3 border border-ink bg-claim-bg px-3 py-2 font-semibold">
              {soldOut && storeStatus ? (
                <>
                  Agotado: la tienda lo marca sin stock (revisado {agoFrom(storeStatus.checked_at)}). El precio de abajo fue el
                  último que vimos.
                </>
              ) : (
                <>
                  Oferta terminada o agotada: no la vemos en la tienda desde {agoFrom(row.last_seen_at)}. El precio de abajo
                  fue el último que vimos.
                </>
              )}
            </p>
          ) : null}
          <p className="text-muted">{storeName(row.store)}</p>
          <h1 className="mt-1 font-display text-3xl font-bold leading-tight sm:text-4xl">{row.title}</h1>

          <p className="mt-5 flex flex-wrap items-baseline gap-x-3">
            <span className="price text-5xl leading-none">{clp(row.price)}</span>
            {hasList ? <s className="text-lg text-muted">{clp(row.list_price)}</s> : null}
          </p>
          {hasList && !ended ? <p className="mt-2 text-lg">Ahorras {clp(row.saving)}</p> : null}

          <div className="mt-4 flex flex-wrap items-center gap-3">
            {ended ? null : <VerifiedStamp verified={view.verified} showUnverified />}
            {verdict ? <VerdictBadge verdict={verdict} /> : null}
            <span className="text-sm text-muted">Actualizado {agoFrom(row.last_seen_at)}</span>
          </div>
          {verdict ? <p className="mt-2 max-w-md text-sm text-muted">{verdict.detail}</p> : null}

          <div className="mt-6 flex flex-wrap gap-3">
          <a
            href={row.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="inline-block bg-ink px-6 py-3 text-lg font-semibold text-paper hover:opacity-90"
          >
            {ended ? "Revisar en" : "Ver en"} {storeName(row.store)}
          </a>
          {follow ? (
            <a
              href={follow}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block border border-ink px-6 py-3 text-lg font-semibold hover:bg-ink hover:text-paper"
            >
              Avísame si baja
            </a>
          ) : null}
          </div>
          <p className="mt-2 max-w-md text-sm text-muted">
            Se abre la tienda en otra pestaña. Confirma el precio ahí antes de comprar.
            {follow ? " «Avísame si baja» te escribe por Telegram cuando el precio caiga un 5 % o más." : ""}
          </p>

          {siblings.length > 0 ? (
            <section aria-labelledby="titulo-otras" className="mt-8 border-t border-line pt-6">
              <h2 id="titulo-otras" className="font-display text-2xl font-semibold">
                También en otra tienda
              </h2>
              <p className="mt-1 text-sm text-muted">Mismo código de producto, publicado por otra tienda de la cadena.</p>
              <ul className="mt-3 flex max-w-xl flex-col gap-2">
                {siblings.map((other) => (
                  <li key={other.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border border-line bg-surface px-3 py-2">
                    <span>
                      <span className="font-medium">{storeName(other.store)}</span>{" "}
                      <span className="price text-xl">{clp(other.price)}</span>
                      {other.price < row.price ? (
                        <span className="ml-2 text-sm font-semibold text-verified">{clp(row.price - other.price)} más barato</span>
                      ) : other.price > row.price ? (
                        <span className="ml-2 text-sm text-muted">{clp(other.price - row.price)} más caro</span>
                      ) : (
                        <span className="ml-2 text-sm text-muted">mismo precio</span>
                      )}
                    </span>
                    <a
                      href={other.url}
                      target="_blank"
                      rel="noopener noreferrer nofollow"
                      className="inline-flex min-h-11 items-center font-semibold underline underline-offset-4"
                    >
                      Ver en {storeName(other.store)}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

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
