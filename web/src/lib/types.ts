// Forma de las filas de la vista offer_feed (ver supabase/migrations/0005).
export type FeedRow = {
  id: string;
  store: string;
  title: string;
  url: string;
  image_url: string;
  category: string;
  category_group: string;
  subcat?: string | null;
  price: number;
  list_price: number;
  web_discount_pct: number;
  saving: number;
  verified_pct: number;
  web_confirmed: boolean;
  history_drop_pct: number;
  points: number | null;
  distinct_prices?: number | null;
  hist_min?: number | null;
  hist_max?: number | null;
  prev_min?: number | null;
  prev_max?: number | null;
  first_point_at?: string | null;
  first_seen_at?: string;
  last_seen_at: string;
};

export type PricePoint = {
  observed_at: string;
  price: number;
  list_price: number | null;
};

export type FeedStats = {
  total: number;
  verified: number;
  super: number;
  last_seen: string | null;
  stores: Record<string, number>;
  groups: Record<string, number>;
  /** categoría → subcategoría → cantidad */
  subs?: Record<string, Record<string, number>>;
};

/** Un posible error de precio anunciado (fila de offer_sent con price_error). */
export type Mistake = {
  product_id: string;
  price: number;
  price_error: string;
  sent_at: string;
};

/** Lo que la propia tienda dice de un producto (offer_availability, la escribe verify_offers.py). */
export type StoreStatus = {
  available: boolean;
  price: number | null;
  detail: string | null;
  checked_at: string;
};

export type MistakeItem = {
  mistake: Mistake;
  /** El producto hoy en el catálogo; null si ya no se ve. */
  row: FeedRow | null;
  /** Sigue a ese mismo precio y a la venta. */
  stillValid: boolean;
};
