import type { FeedRow, PricePoint } from "./types";
import { dealView } from "./tiers";

export type Verdict = {
  key: "record" | "real" | "inflated" | "unproven";
  label: string;
  /** Una frase para la ficha: qué significa y en qué datos se apoya. */
  detail: string;
  tone: "ok" | "warn" | "info";
};

/** Puntos mínimos para hablar de "mínimo histórico": con menos, cualquier precio lo sería. */
const MIN_POINTS = 3;

type VerdictRow = Pick<
  FeedRow,
  "price" | "list_price" | "web_discount_pct" | "verified_pct" | "web_confirmed" | "prev_min" | "prev_max" | "points" | "distinct_prices"
>;

/** Veredicto de una oferta según el historial que registramos. `null` = no hay nada claro que decir. */
export function verdictFor(row: VerdictRow): Verdict | null {
  const points = row.points ?? 0;
  const view = dealView(row);

  if (points < MIN_POINTS) {
    return view.claimOnly
      ? {
          key: "unproven",
          label: "Sin historial aún",
          detail: "Llevamos poco tiempo siguiendo este producto: no podemos confirmar si el descuento es real.",
          tone: "info",
        }
      : null;
  }

  if (row.prev_min != null && row.price <= row.prev_min && (row.distinct_prices ?? 1) > 1) {
    return {
      key: "record",
      label: "Mínimo histórico",
      detail: "Es el precio más bajo que hemos registrado para este producto.",
      tone: "ok",
    };
  }

  if (view.verified && row.web_confirmed) {
    return {
      key: "real",
      label: "Descuento real",
      detail: "La tienda lo vendía al precio normal antes de la rebaja: lo registramos.",
      tone: "ok",
    };
  }

  if (
    !view.verified &&
    row.web_discount_pct >= 20 &&
    row.prev_max != null &&
    row.prev_max < row.list_price * 0.95
  ) {
    return {
      key: "inflated",
      label: "Precio normal dudoso",
      detail: "Nunca lo vimos al precio normal que anuncia la tienda: el descuento podría estar inflado.",
      tone: "warn",
    };
  }

  return null;
}

export type PriceStats = {
  min: number;
  max: number;
  current: number;
  /** Cuánto más caro que el mínimo está hoy, en porcentaje (0 = en el mínimo). */
  aboveMinPct: number;
  /** Cuántos cambios de precio hay registrados. */
  changes: number;
};

/** Resumen del historial para la ficha. `null` si no hay precios. */
export function priceStats(points: PricePoint[]): PriceStats | null {
  if (points.length === 0) return null;
  const prices = points.map((p) => p.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const current = points[points.length - 1].price;
  return {
    min,
    max,
    current,
    aboveMinPct: min > 0 ? Math.round(((current - min) / min) * 100) : 0,
    changes: points.length - 1,
  };
}
