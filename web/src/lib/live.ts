// ¿Una oferta sigue a la venta? Lo deducimos de cuándo la vimos por última vez.
//
// El pipeline refresca `last_seen_at` en cada escaneo para los productos con 50 % de descuento o más (y los
// anunciados en los últimos 3 días): si llevan más de una hora sin verse, ya no están en la tienda. Los demás
// se refrescan una vez por hora, así que se les da más margen.

/** Desde este descuento un producto se refresca en cada escaneo. */
export const FINE_MIN_DISCOUNT = 50;
export const FINE_END_MINUTES = 60;
export const COARSE_END_MINUTES = 150;
/** Pasado este tiempo la ficha no muestra el producto: solo avisa de que ya no está. */
export const GONE_HOURS = 24;

export type Availability = { ended: boolean; minutes: number };

export function endMinutes(webDiscountPct: number): number {
  return webDiscountPct >= FINE_MIN_DISCOUNT ? FINE_END_MINUTES : COARSE_END_MINUTES;
}

/** `ended`: lleva más tiempo sin verse del que cabe en un producto que sigue a la venta. */
export function availability(
  row: { web_discount_pct: number; last_seen_at: string },
  now: number = Date.now(),
): Availability {
  const seen = Date.parse(row.last_seen_at);
  if (Number.isNaN(seen)) return { ended: true, minutes: Number.POSITIVE_INFINITY };
  const minutes = Math.max(0, Math.round((now - seen) / 60_000));
  return { ended: minutes > endMinutes(row.web_discount_pct), minutes };
}
