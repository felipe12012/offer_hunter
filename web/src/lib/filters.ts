// Filtros de la portada: todo vive en la URL (se pueden compartir) y todo se valida aquí.
import { GROUPS, SUBCATEGORIES, type Group } from "./taxonomy";

export { GROUPS, type Group };

export const SORTS = ["best", "web", "price_asc", "price_desc", "saving", "new"] as const;
export type Sort = (typeof SORTS)[number];

export const MIN_OPTIONS = [30, 50, 70, 80] as const;
export const PAGE_SIZE = 24;
export const MAX_PAGE = 200;
export const MAX_QUERY_LENGTH = 60;
export const MAX_QUERY_WORDS = 5;
export const MAX_STORES = 12;
export const MAX_PRICE = 100_000_000;

export type Filters = {
  q: string;
  cat: Group | null;
  sub: string | null;
  stores: string[];
  min: number | null;
  pmin: number | null;
  pmax: number | null;
  ver: boolean;
  sort: Sort;
  page: number;
};

export const DEFAULT_FILTERS: Filters = {
  q: "",
  cat: null,
  sub: null,
  stores: [],
  min: null,
  pmin: null,
  pmax: null,
  ver: false,
  sort: "best",
  page: 1,
};

type Raw = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** Minúsculas, sin tildes, solo letras/números/espacio/guion: nada que PostgREST pueda interpretar. */
export function normalizeQuery(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9 -]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_QUERY_LENGTH)
    .trim();
}

export function queryWords(q: string): string[] {
  return normalizeQuery(q).split(" ").filter(Boolean).slice(0, MAX_QUERY_WORDS);
}

function toInt(value: string, min: number, max: number): number | null {
  if (!/^\d{1,9}$/.test(value)) return null;
  const n = Number(value);
  return n >= min && n <= max ? n : null;
}

export function parseFilters(raw: Raw): Filters {
  const cat = first(raw.cat) as Group;
  const stores = first(raw.store)
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter((s) => /^[a-z0-9]{2,20}$/.test(s));
  const min = toInt(first(raw.min), 1, 99);
  const pmin = toInt(first(raw.pmin), 0, MAX_PRICE);
  const pmax = toInt(first(raw.pmax), 0, MAX_PRICE);
  const sort = first(raw.sort) as Sort;
  const page = toInt(first(raw.page), 1, MAX_PAGE) ?? 1;
  const validCat = (GROUPS as readonly string[]).includes(cat) ? cat : null;
  const sub = first(raw.sub);
  return {
    q: normalizeQuery(first(raw.q)),
    cat: validCat,
    // La subcategoría solo vale dentro de su categoría (y solo las que existen).
    sub: validCat && Object.hasOwn(SUBCATEGORIES[validCat] ?? {}, sub) ? sub : null,
    stores: [...new Set(stores)].slice(0, MAX_STORES),
    min,
    pmin,
    pmax: pmin !== null && pmax !== null && pmax < pmin ? null : pmax,
    ver: first(raw.ver) === "1",
    sort: (SORTS as readonly string[]).includes(sort) ? sort : "best",
    page,
  };
}

/** Query string de un conjunto de filtros (solo lo que difiere del valor por defecto). */
export function filtersToQuery(filters: Filters, overrides: Partial<Filters> = {}): string {
  const f = { ...filters, ...overrides };
  const params = new URLSearchParams();
  if (f.q) params.set("q", f.q);
  if (f.cat) params.set("cat", f.cat);
  if (f.cat && f.sub) params.set("sub", f.sub);
  if (f.stores.length) params.set("store", f.stores.join(","));
  if (f.min !== null) params.set("min", String(f.min));
  if (f.pmin !== null) params.set("pmin", String(f.pmin));
  if (f.pmax !== null) params.set("pmax", String(f.pmax));
  if (f.ver) params.set("ver", "1");
  if (f.sort !== "best") params.set("sort", f.sort);
  if (f.page > 1) params.set("page", String(f.page));
  return params.toString();
}

export function filtersHref(filters: Filters, overrides: Partial<Filters> = {}): string {
  // Cualquier cambio de filtro vuelve a la página 1, salvo que se pida otra explícitamente.
  const query = filtersToQuery(filters, { page: 1, ...overrides });
  return query ? `/?${query}` : "/";
}

export function activeFilterCount(f: Filters): number {
  return (
    (f.q ? 1 : 0) +
    (f.cat ? 1 : 0) +
    (f.sub ? 1 : 0) +
    (f.stores.length ? 1 : 0) +
    (f.min !== null ? 1 : 0) +
    (f.pmin !== null || f.pmax !== null ? 1 : 0) +
    (f.ver ? 1 : 0)
  );
}
