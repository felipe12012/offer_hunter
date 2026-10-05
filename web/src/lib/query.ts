// Construye las consultas a la vista offer_feed (PostgREST). Puro: sin red, sin claves.
// Todo valor del usuario ya viene validado por filters.ts; aquí solo se codifica.
import { PAGE_SIZE, queryWords, type Filters, type Sort } from "./filters";
import { ENDED_MINUTES } from "./live";
import { VERIFIED_MIN_PCT } from "./tiers";

const ROUND_MS = 10 * 60_000; // la hora se redondea para que la URL (y su caché) no cambie en cada petición

export const LIST_COLUMNS = [
  "id", "store", "title", "url", "image_url", "category_group", "subcat", "price", "list_price",
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

export function liveSince(minutes: number, now: number = Date.now()): string {
  const rounded = Math.floor((now - minutes * 60_000) / ROUND_MS) * ROUND_MS;
  return new Date(rounded).toISOString();
}

/** Solo lo que sigue a la venta: visto en las últimas horas (ver live.ts: no verlo un rato no es estar agotado).
 *  `orGroups`: condiciones "o" de la consulta; PostgREST solo admite un `or`, así que varias van dentro de `and`. */
function applyLive(params: URLSearchParams, orGroups: string[], now: number): void {
  params.set("last_seen_at", `gte.${liveSince(ENDED_MINUTES, now)}`);
  if (orGroups.length === 1) params.set("or", `(${orGroups[0]})`);
  else if (orGroups.length > 1) params.set("and", `(${orGroups.map((group) => `or(${group})`).join(",")})`);
}

/** `excludeIds`: productos que la página ya muestra en otro bloque (el carrusel), para no repetirlos en el listado. */
export function buildListQuery(
  filters: Filters,
  now: number = Date.now(),
  pageSize: number = PAGE_SIZE,
  excludeIds: string[] = [],
): string {
  const params = new URLSearchParams();
  const orGroups: string[] = [];
  params.set("select", LIST_COLUMNS);
  params.set("dup_rank", "eq.1"); // Falabella y Sodimac comparten catálogo: una sola vez

  const excluded = excludeIds.filter(isValidProductId);
  if (excluded.length) params.set("id", `not.in.(${excluded.join(",")})`);

  if (filters.cat) params.set("category_group", `eq.${filters.cat}`);
  if (filters.cat && filters.sub) params.set("subcat", `eq.${filters.sub}`);
  if (filters.stores.length) params.set("store", `in.(${filters.stores.join(",")})`);

  if (filters.min !== null) {
    if (filters.ver) {
      params.set("verified_pct", `gte.${filters.min}`);
    } else {
      orGroups.push(`verified_pct.gte.${filters.min},web_discount_pct.gte.${filters.min}`);
    }
  } else if (filters.ver) {
    params.set("verified_pct", `gte.${VERIFIED_MIN_PCT}`);
  }

  if (filters.pmin !== null) params.append("price", `gte.${filters.pmin}`);
  if (filters.pmax !== null) params.append("price", `lte.${filters.pmax}`);

  // Búsqueda sin tildes: cada palabra es una condición (todas deben estar en el título).
  for (const word of queryWords(filters.q)) params.append("title_norm", `ilike.*${word}*`);

  applyLive(params, orGroups, now);
  params.set("order", ORDERS[filters.sort]);
  params.set("limit", String(pageSize));
  params.set("offset", String((filters.page - 1) * pageSize));
  return params.toString();
}

export function buildSuperQuery(now: number = Date.now(), limit = 12): string {
  const params = new URLSearchParams();
  params.set("select", LIST_COLUMNS);
  applyLive(params, [], now);
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

/** Falabella y Sodimac comparten catálogo: el mismo código es el mismo producto en las dos tiendas.
 *  Devuelve la consulta de la(s) otra(s) publicación(es) o null si el producto no tiene gemelas. */
export function buildSiblingsQuery(id: string, now: number = Date.now()): string | null {
  const [store, sku] = id.split(":");
  if ((store !== "falabella" && store !== "sodimac") || !sku || !isValidProductId(id)) return null;
  const params = new URLSearchParams();
  params.set("select", LIST_COLUMNS);
  applyLive(params, [], now);
  params.append("id", `in.(falabella:${sku},sodimac:${sku})`);
  params.append("id", `neq.${id}`);
  params.set("order", "price.asc");
  return params.toString();
}

/** Posibles errores de precio anunciados en las últimas horas (los escribe el pipeline en offer_sent). */
export const MISTAKE_HOURS = 48;

export function buildMistakesQuery(now: number = Date.now(), limit = 40): string {
  const params = new URLSearchParams();
  params.set("select", "product_id,price,price_error,sent_at");
  params.set("price_error", "not.is.null");
  const since = Math.floor((now - MISTAKE_HOURS * 3_600_000) / ROUND_MS) * ROUND_MS;
  params.set("sent_at", `gte.${new Date(since).toISOString()}`);
  params.set("order", "sent_at.desc,id.desc");
  params.set("limit", String(limit));
  return params.toString();
}

/** Productos del catálogo por id (solo ids con forma válida: nada del exterior entra en la consulta). */
export function buildByIdsQuery(ids: string[]): string {
  const valid = [...new Set(ids.filter(isValidProductId))];
  const params = new URLSearchParams();
  params.set("select", LIST_COLUMNS);
  params.set("id", `in.(${valid.join(",")})`);
  params.set("limit", String(Math.max(valid.length, 1)));
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
  applyLive(params, [], now);
  params.set("dup_rank", "eq.1");
  params.set("category_group", `eq.${group}`);
  params.set("id", `neq.${excludeId}`);
  params.set("order", ORDERS.best);
  params.set("limit", String(limit));
  return params.toString();
}
