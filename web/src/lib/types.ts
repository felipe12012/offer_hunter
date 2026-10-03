// Forma de las filas de la vista offer_feed (ver supabase/migrations/0005).
export type FeedRow = {
  id: string;
  store: string;
  title: string;
  url: string;
  image_url: string;
  category: string;
  category_group: string;
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
};
