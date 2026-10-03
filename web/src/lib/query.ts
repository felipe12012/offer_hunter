// Construye las consultas a la vista offer_feed (PostgREST). Puro: sin red, sin claves.
// Todo valor del usuario ya viene validado por filters.ts; aquí solo se codifica.
import { PAGE_SIZE, queryWords, type Filters, type Sort } from "./filters";
import { VERIFIED_MIN_PCT } from "./tiers";

/** Productos vistos en las últimas horas: lo que sigue a la venta. */
export const FRESH_HOURS = 6;
const ROUND_MS = 10 * 60_000; // la hora se redondea para que la URL (y su caché) no cambie en cada petición

export const LIST_COLUMNS = [
  "id", "store", "title", "url", "image_url", "category_group", "price", "list_price",
  "web_discount_pct", "saving", "verified_pct", "web_confirmed", "history_drop_pct", "points",
  "prev_min", "last_seen_at",
].join(",");

export const DETAIL_COLUMNS = [
  LIST_COLUMNS, "category", "distinct_prices", "hist_min", "hist_max", "prev_max", "first_point_at", "first_seen_at",
].join(",");

const ORDERS: Record<Sort, string> = {
  best: "verified_pct.desc,web_discount_pct.desc,id.asc",
  web: "web_discount_pct.desc,verified_pct.desc,id.asc",
  price_asc: "price.asc,id.asc",
  price_desc: "price.desc,id.asc",
  saving: "saving.desc,id.asc",
  new: "first_seen_at.desc,id.asc",
};

export function freshSince(now: number = Date.now()): string {
  const rounded = Math.floor((now - FRESH_HOURS * 3_600_000) / ROUND_MS) * ROUND_MS;
  return new Date(rounded).toISOString();
}

export function buildListQuery(filters: Filters, now: number = Date.now(), pageSize: number = PAGE_SIZE): string {
  const params = new URLSearchParams();
  params.set("select", LIST_COLUMNS);
  params.set("last_seen_at", `gte.${freshSince(now)}`);
  params.set("dup_rank", "eq.1"); // Falabella y Sodimac comparten catálogo: una sola vez

  if (filters.cat) params.set("category_group", `eq.${filters.cat}`);
  if (filters.stores.length) params.set("store", `in.(${filters.stores.join(",")})`);

  if (filters.min !== null) {
    if (filters.ver) {
      params.set("verified_pct", `gte.${filters.min}`);
    } else {
      params.set("or", `(verified_pct.gte.${filters.min},web_discount_pct.gte.${filters.min})`);
    }
  } else if (filters.ver) {
    params.set("verified_pct", `gte.${VERIFIED_MIN_PCT}`);
  }

  if (filters.pmin !== null) params.append("price", `gte.${filters.pmin}`);
  if (filters.pmax !== null) params.append("price", `lte.${filters.pmax}`);

  // Búsqueda sin tildes: cada palabra es una condición (todas deben estar en el título).
  for (const word of queryWords(filters.q)) params.append("title_norm", `ilike.*${word}*`);

  params.set("order", ORDERS[filters.sort]);
  params.set("limit", String(pageSize));
  params.set("offset", String((filters.page - 1) * pageSize));
  return params.toString();
}

export function buildSuperQuery(now: number = Date.now(), limit = 12): string {
  const params = new URLSearchParams();
  params.set("select", LIST_COLUMNS);
  params.set("last_seen_at", `gte.${freshSince(now)}`);
  params.set("dup_rank", "eq.1");
  params.set("verified_pct", "gte.60");
  params.set("order", ORDERS.best);
  params.set("limit", String(limit));
  return params.toString();
}

/** Ids como "falabella:80726514": solo letras/números/guion/punto/guion bajo. */
export function isValidProductId(id: string): boolean {
  return /^[a-z0-9]{2,20}:[A-Za-z0-9._-]{1,80}$/.test(id);
}

export function buildProductQuery(id: string): string {
  const params = new URLSearchParams();
  params.set("select", DETAIL_COLUMNS);
  params.set("id", `eq.${id}`);
  params.set("limit", "1");
  return params.toString();
}

export function buildHistoryQuery(id: string): string {
  const params = new URLSearchParams();
  params.set("select", "observed_at,price,list_price");
  params.set("product_id", `eq.${id}`);
  params.set("order", "observed_at.asc");
  params.set("limit", "200");
  return params.toString();
}

export function buildRelatedQuery(group: string, excludeId: string, now: number = Date.now(), limit = 8): string {
  const params = new URLSearchParams();
  params.set("select", LIST_COLUMNS);
  params.set("last_seen_at", `gte.${freshSince(now)}`);
  params.set("dup_rank", "eq.1");
  params.set("category_group", `eq.${group}`);
  params.set("id", `neq.${excludeId}`);
  params.set("order", ORDERS.best);
  params.set("limit", String(limit));
  return params.toString();
}
