import { agoFrom, clp, storeName } from "@/lib/format";
import type { MistakeItem } from "@/lib/types";

import { DealCard, productPath } from "./DealCard";

function Status({ item }: { item: MistakeItem }) {
  const { row, mistake } = item;
  if (item.stillValid) {
    return <p className="font-semibold text-verified">Sigue a ese precio en la tienda</p>;
  }
  if (row && row.price !== mistake.price) {
    return <p className="text-muted">Ya cambió de precio: ahora {clp(row.price)}</p>;
  }
  return <p className="text-muted">Ya no lo vemos a la venta</p>;
}

/** Posibles errores de precio: la tarjeta del producto con el motivo y su estado actual debajo. */
export function MistakeList({ items }: { items: MistakeItem[] }) {
  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <li key={`${item.mistake.product_id}:${item.mistake.price}`} className="flex flex-col border border-line bg-surface">
          {item.row ? (
            <DealCard row={item.row} />
          ) : (
            <div className="p-4">
              <p className="font-display text-xl font-semibold">{storeName(item.mistake.product_id.split(":")[0])}</p>
              <p className="text-muted">{clp(item.mistake.price)}</p>
            </div>
          )}
          <div className="flex flex-col gap-1 border-t border-line p-4 text-[0.95rem]">
            <p>
              <span className="font-semibold">Por qué:</span> {item.mistake.price_error}
            </p>
            <Status item={item} />
            <p className="text-sm text-muted">Anunciado {agoFrom(item.mistake.sent_at)}</p>
            {item.row ? (
              <a href={productPath(item.row.id)} className="mt-1 text-sm font-medium underline underline-offset-4">
                Ver el historial de precios
              </a>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
