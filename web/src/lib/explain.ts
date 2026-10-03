import { clp, shortDate } from "./format";
import { dealView, VERIFIED_MIN_PCT } from "./tiers";
import type { FeedRow } from "./types";

export type Reason = { tone: "ok" | "warn" | "info"; text: string };

/** Por qué un descuento está (o no) verificado, en lenguaje simple. */
export function explainDeal(row: FeedRow): Reason[] {
  const view = dealView(row);
  const reasons: Reason[] = [];

  if (view.verified && row.web_confirmed && row.prev_max != null) {
    reasons.push({
      tone: "ok",
      text: `Antes costaba ${clp(row.prev_max)}. Lo registramos a ese precio, así que el precio normal que muestra la tienda es real.`,
    });
  }

  if (row.history_drop_pct >= VERIFIED_MIN_PCT && row.prev_min != null) {
    reasons.push({
      tone: "ok",
      text: `Bajó ${Math.round(row.history_drop_pct)}% respecto de su precio más bajo anterior (${clp(row.prev_min)}).`,
    });
  }

  if (!view.verified && row.web_discount_pct > 0) {
    reasons.push({
      tone: "warn",
      text: `La tienda anuncia -${Math.round(row.web_discount_pct)}% (antes ${clp(row.list_price)}), pero todavía no tenemos un historial que lo respalde.`,
    });
    if (row.prev_max != null && row.prev_max < row.list_price * 0.95) {
      reasons.push({
        tone: "warn",
        text: `El precio más alto que hemos visto es ${clp(row.prev_max)}, bastante menos que el precio normal de ${clp(row.list_price)}: ese precio normal podría estar inflado.`,
      });
    }
  }

  if (!view.verified && row.web_discount_pct <= 0) {
    reasons.push({ tone: "info", text: "Este producto no tiene un descuento anunciado." });
  }

  const distinct = row.distinct_prices ?? 1;
  const since = row.first_point_at ? ` desde el ${shortDate(row.first_point_at)}` : "";
  reasons.push({
    tone: "info",
    text:
      distinct > 1
        ? `Seguimos este producto${since} y hemos visto ${distinct} precios distintos.`
        : `Seguimos este producto${since} y por ahora solo hemos visto un precio.`,
  });

  return reasons;
}
