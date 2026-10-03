// Niveles de descuento, alineados con las alertas de Telegram (notifier.py).
export const VERIFIED_MIN_PCT = 10;

export type Tier = { min: number; key: "super" | "ofertaza" | "gran"; label: string };

export const TIERS: Tier[] = [
  { min: 90, key: "super", label: "Súper oferta" },
  { min: 80, key: "ofertaza", label: "Ofertaza" },
  { min: 60, key: "gran", label: "Gran oferta" },
];

export function tierFor(pct: number): Tier | null {
  return TIERS.find((tier) => pct >= tier.min) ?? null;
}

export type DealView = {
  verified: boolean;
  /** Porcentaje que se muestra: el verificado si lo hay, si no el que anuncia la tienda. */
  pct: number;
  tier: Tier | null;
  /** El porcentaje mostrado es solo lo que anuncia la tienda. */
  claimOnly: boolean;
};

export function dealView(row: { verified_pct: number; web_discount_pct: number }): DealView {
  const verified = row.verified_pct >= VERIFIED_MIN_PCT;
  const pct = verified ? row.verified_pct : row.web_discount_pct;
  return {
    verified,
    pct: Math.round(pct),
    // Solo lo verificado recibe niveles llamativos: un anuncio sin respaldo no debe parecer una súper oferta.
    tier: verified ? tierFor(row.verified_pct) : null,
    claimOnly: !verified && row.web_discount_pct > 0,
  };
}
