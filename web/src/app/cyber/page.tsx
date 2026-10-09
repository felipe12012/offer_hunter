import type { Metadata } from "next";
import Link from "next/link";

import { DealGrid } from "@/components/DealCard";
import { MistakeList } from "@/components/MistakeList";
import { getFeed, getMistakes, getReference } from "@/lib/data";
import { parseFilters } from "@/lib/filters";

// Se renderiza al pedirla (no al compilar: allí no hay credenciales); los datos se cachean 60 s en cada consulta.
export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Cyber: errores de precio y mayores descuentos" };

export default async function CyberPage() {
  const [mistakes, top, asOf] = await Promise.all([
    getMistakes(),
    getFeed(parseFilters({ ver: "1", min: "50" })),
    getReference(),
  ]);

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 sm:py-10">
      <h1 className="font-display text-[2.4rem] font-bold leading-[1.02] sm:text-6xl">Cyber: lo que vamos viendo</h1>
      <p className="mt-2 max-w-2xl text-base text-muted sm:text-lg">
        Revisamos las tiendas cada pocos minutos. Aquí están los precios que cayeron más de lo normal y los mayores
        descuentos que nuestro historial respalda.
      </p>

      <section aria-labelledby="titulo-errores" className="mt-10">
        <h2 id="titulo-errores" className="font-display text-3xl font-bold">
          Posibles errores de precio
        </h2>
        <p className="mt-2 max-w-2xl">
          Un precio que parece tener un cero de menos (por ejemplo $150.000 que aparece como $15.000), que cae un 85 % o más
          frente a lo que vimos antes, o que cuesta una quinta parte del mismo producto en la tienda hermana. Un descuento
          de 50 % o 70 % es una oferta, no un error. <strong>Las tiendas suelen cancelar las compras con precio equivocado</strong>:
          confirma en la tienda antes de contar con él.
        </p>
        <div className="mt-5">
          {mistakes.length > 0 ? (
            <MistakeList items={mistakes} asOf={asOf} />
          ) : (
            <p className="border border-line bg-surface p-6 text-muted">
              Todavía no detectamos ninguno en las últimas 48 horas. Cuando aparezca uno se avisa también en el canal de
              Telegram.
            </p>
          )}
        </div>
      </section>

      <section aria-labelledby="titulo-top" className="mt-14">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 id="titulo-top" className="font-display text-3xl font-bold">
            Mayores descuentos verificados
          </h2>
          <Link href="/?ver=1&min=50" className="font-medium underline underline-offset-4">
            Ver todos ({top.total.toLocaleString("es-CL")})
          </Link>
        </div>
        {top.rows.length > 0 ? (
          <DealGrid rows={top.rows.slice(0, 12)} eager={0} asOf={asOf} />
        ) : (
          <p className="border border-line bg-surface p-6 text-muted">Aún no hay descuentos de 50 % o más con historial que los respalde.</p>
        )}
      </section>
    </main>
  );
}
