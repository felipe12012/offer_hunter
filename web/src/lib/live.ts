// ¿Una oferta sigue a la venta? Por ahora solo lo damos por terminado tras MUCHO tiempo sin verla.
//
// Un producto que deja de aparecer en nuestros escaneos NO está necesariamente agotado: leemos las primeras páginas de
// cada listado (Falabella, ~18.000 de 26.000 productos) y el orden cambia entre un escaneo y otro, de modo que un
// producto con stock sale y entra. Una primera versión lo daba por terminado a la hora sin verlo y se equivocó en 2 de
// cada 4 casos. Marcarlo antes exige comprobarlo en la tienda (ver docs/availability.md).

/** Tiempo sin verse a partir del cual se oculta de los listados y la ficha lo marca como terminado. */
export const ENDED_MINUTES = 360;
/** Pasado este tiempo la ficha no muestra el producto: solo avisa de que ya no está. */
export const GONE_HOURS = 24;

/** Si el último escaneo que funcionó tiene más de esto, la web avisa de que los datos están desactualizados. */
export const STALE_NOTICE_MINUTES = 90;

/** Hora de referencia para decidir qué sigue a la venta: la del último escaneo que funcionó, nunca el futuro.
 *  Si el escaneo se detiene unas horas, medir contra "ahora" vaciaría la web entera; medido contra el último escaneo,
 *  lo que se veía entonces sigue visible (con un aviso de que los datos son viejos). */
export function referenceTime(latestSeen: string | null | undefined, now: number = Date.now()): number {
  const seen = Date.parse(latestSeen ?? "");
  return Number.isNaN(seen) ? now : Math.min(seen, now);
}

export function staleMinutes(reference: number, now: number = Date.now()): number {
  return Math.max(0, Math.round((now - reference) / 60_000));
}

export type Availability = { ended: boolean; minutes: number };

/** `ended`: lleva más tiempo sin verse del que cabe en un producto que sigue a la venta. */
export function availability(row: { last_seen_at: string }, now: number = Date.now()): Availability {
  const seen = Date.parse(row.last_seen_at);
  if (Number.isNaN(seen)) return { ended: true, minutes: Number.POSITIVE_INFINITY };
  const minutes = Math.max(0, Math.round((now - seen) / 60_000));
  return { ended: minutes > ENDED_MINUTES, minutes };
}
