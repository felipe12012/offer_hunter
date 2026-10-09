import type { FeedRow } from "@/lib/types";

import { DealCard } from "./DealCard";

/** Fila horizontal con lo mejor comprobado. Si no hay nada que merezca estar aquí, no se muestra. */
export function SuperDeals({ rows, asOf }: { rows: FeedRow[]; asOf?: number }) {
  if (rows.length === 0) return null;
  return (
    <section aria-labelledby="titulo-destacadas" className="mb-10">
      <h2 id="titulo-destacadas" className="mb-3 font-display text-2xl font-bold">
        Los descuentos más grandes con precio comprobado
      </h2>
      <div className="rail border-l border-t border-line">
        {rows.map((row, index) => (
          <DealCard key={row.id} row={row} priority={index < 2} asOf={asOf} />
        ))}
      </div>
    </section>
  );
}
