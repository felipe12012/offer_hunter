// Capa de datos de la web: único punto que decide de dónde salen los productos.
// - Con credenciales: Supabase (vista offer_feed), siempre de solo lectura.
// - Sin credenciales y fuera de producción: una muestra real (fixtures.ts), para desarrollar.
// - Sin credenciales en producción: error visible (nunca datos falsos).
import "server-only";

import { FIXTURE_ROWS } from "./fixtures";
import { DEFAULT_FILTERS, PAGE_SIZE, queryWords, type Filters } from "./filters";
import {
  buildHistoryQuery,
  buildListQuery,
  buildProductQuery,
  buildRelatedQuery,
  buildSuperQuery,
  isValidProductId,
} from "./query";
import { hasCredentials, rest, SupabaseConfigError } from "./supabase";
import { VERIFIED_MIN_PCT } from "./tiers";
import type { FeedRow, FeedStats, PricePoint } from "./types";

export const REVALIDATE_SECONDS = 120;

const fixtureMode = () => !hasCredentials() && process.env.NODE_ENV !== "production";

function requireCredentials(): void {
  if (!hasCredentials()) throw new SupabaseConfigError();
}

// ---------- muestra local (solo desarrollo) ----------

type FixtureRow = FeedRow & { title_norm: string };
const FIXTURES = FIXTURE_ROWS as FixtureRow[];

function fixtureFilter(filters: Filters): FixtureRow[] {
  const words = queryWords(filters.q);
  const rows = FIXTURES.filter((row) => {
    if (filters.cat && row.category_group !== filters.cat) return false;
    if (filters.stores.length && !filters.stores.includes(row.store)) return false;
    if (filters.min !== null) {
      const pool = filters.ver ? row.verified_pct : Math.max(row.verified_pct, row.web_discount_pct);
      if (pool < filters.min) return false;
    } else if (filters.ver && row.verified_pct < VERIFIED_MIN_PCT) {
      return false;
    }
    if (filters.pmin !== null && row.price < filters.pmin) return false;
    if (filters.pmax !== null && row.price > filters.pmax) return false;
    return words.every((word) => row.title_norm.includes(word));
  });
  const key: Record<Filters["sort"], (row: FixtureRow) => number> = {
    best: (r) => r.verified_pct * 1000 + r.web_discount_pct,
    web: (r) => r.web_discount_pct * 1000 + r.verified_pct,
    price_asc: (r) => -r.price,
    price_desc: (r) => r.price,
    saving: (r) => r.saving,
    new: (r) => Date.parse(r.first_seen_at ?? r.last_seen_at),
  };
  return rows.sort((a, b) => key[filters.sort](b) - key[filters.sort](a));
}

function fixtureStats(): FeedStats {
  const stores: Record<string, number> = {};
  const groups: Record<string, number> = {};
  for (const row of FIXTURES) {
    stores[row.store] = (stores[row.store] ?? 0) + 1;
    groups[row.category_group] = (groups[row.category_group] ?? 0) + 1;
  }
  return {
    total: FIXTURES.length,
    verified: FIXTURES.filter((r) => r.verified_pct >= VERIFIED_MIN_PCT).length,
    super: FIXTURES.filter((r) => r.verified_pct >= 80).length,
    last_seen: FIXTURES.map((r) => r.last_seen_at).sort().at(-1) ?? null,
    stores,
    groups,
  };
}

// ---------- consultas ----------

export async function getFeed(filters: Filters): Promise<{ rows: FeedRow[]; total: number }> {
  if (fixtureMode()) {
    const all = fixtureFilter(filters);
    const start = (filters.page - 1) * PAGE_SIZE;
    return { rows: all.slice(start, start + PAGE_SIZE), total: all.length };
  }
  requireCredentials();
  const { rows, total } = await rest<FeedRow[]>(`offer_feed?${buildListQuery(filters)}`, {
    count: true,
    revalidate: REVALIDATE_SECONDS,
  });
  return { rows, total: total ?? rows.length };
}

export async function getSuperDeals(): Promise<FeedRow[]> {
  if (fixtureMode()) return fixtureFilter({ ...DEFAULT_FILTERS, ver: true, min: 60 }).slice(0, 12);
  requireCredentials();
  const { rows } = await rest<FeedRow[]>(`offer_feed?${buildSuperQuery()}`, { revalidate: REVALIDATE_SECONDS });
  return rows;
}

export async function getStats(): Promise<FeedStats> {
  if (fixtureMode()) return fixtureStats();
  requireCredentials();
  const { rows } = await rest<FeedStats>("rpc/offer_stats", {
    method: "POST",
    body: {},
    revalidate: REVALIDATE_SECONDS,
  });
  return rows;
}

export async function getProduct(id: string): Promise<FeedRow | null> {
  if (!isValidProductId(id)) return null;
  if (fixtureMode()) return FIXTURES.find((row) => row.id === id) ?? null;
  requireCredentials();
  const { rows } = await rest<FeedRow[]>(`offer_feed?${buildProductQuery(id)}`, { revalidate: REVALIDATE_SECONDS });
  return rows[0] ?? null;
}

export async function getHistory(row: FeedRow): Promise<PricePoint[]> {
  if (fixtureMode()) {
    const points: PricePoint[] = [];
    if (row.prev_max != null) {
      points.push({ observed_at: row.first_point_at ?? row.last_seen_at, price: row.prev_max, list_price: row.list_price });
    }
    points.push({ observed_at: row.last_seen_at, price: row.price, list_price: row.list_price });
    return points;
  }
  requireCredentials();
  const { rows } = await rest<PricePoint[]>(`offer_price_points?${buildHistoryQuery(row.id)}`, {
    revalidate: REVALIDATE_SECONDS,
  });
  return rows;
}

export async function getRelated(row: FeedRow): Promise<FeedRow[]> {
  if (fixtureMode()) {
    return fixtureFilter({ ...DEFAULT_FILTERS, cat: row.category_group as Filters["cat"] })
      .filter((other) => other.id !== row.id)
      .slice(0, 8);
  }
  requireCredentials();
  const { rows } = await rest<FeedRow[]>(`offer_feed?${buildRelatedQuery(row.category_group, row.id)}`, {
    revalidate: REVALIDATE_SECONDS,
  });
  return rows;
}
