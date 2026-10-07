import { describe, expect, it } from "vitest";

import { priceStats, verdictFor } from "./verdict";

function row(overrides: Partial<Parameters<typeof verdictFor>[0]> = {}) {
  return {
    price: 5000, list_price: 10000, web_discount_pct: 50, verified_pct: 0, web_confirmed: false,
    prev_min: 6000, prev_max: 10000, points: 5, distinct_prices: 3,
    ...overrides,
  };
}

describe("verdictFor", () => {
  it("el precio más bajo registrado es mínimo histórico", () => {
    expect(verdictFor(row({ verified_pct: 50, web_confirmed: true }))?.key).toBe("record");
  });

  it("un descuento confirmado que no es el mínimo es descuento real", () => {
    expect(verdictFor(row({ price: 7000, prev_min: 6000, verified_pct: 30, web_confirmed: true }))?.key).toBe("real");
  });

  it("nunca vimos el precio normal que anuncia la tienda: precio normal dudoso", () => {
    const verdict = verdictFor(row({ price: 7000, prev_min: 6000, prev_max: 7500, list_price: 30000, web_discount_pct: 77 }));
    expect(verdict?.key).toBe("inflated");
    expect(verdict?.tone).toBe("warn");
  });

  it("con poco historial no se afirma nada: solo se avisa si hay un descuento anunciado", () => {
    expect(verdictFor(row({ points: 1 }))?.key).toBe("unproven");
    expect(verdictFor(row({ points: 2, web_discount_pct: 0, list_price: 5000 }))).toBeNull();
  });

  it("un solo precio visto no puede ser mínimo histórico", () => {
    expect(verdictFor(row({ distinct_prices: 1, prev_min: 5000 }))?.key).not.toBe("record");
  });

  it("sin nada claro que decir devuelve null", () => {
    expect(verdictFor(row({ price: 9000, prev_min: 6000, web_discount_pct: 10, list_price: 10000, prev_max: 10000 }))).toBeNull();
  });
});

describe("priceStats", () => {
  const at = (price: number, day: number) => ({ observed_at: `2026-10-0${day}T00:00:00Z`, price, list_price: null });

  it("resume mínimo, máximo y cuánto sobre el mínimo está hoy", () => {
    expect(priceStats([at(10000, 1), at(8000, 2), at(9000, 3)])).toEqual({
      min: 8000, max: 10000, current: 9000, aboveMinPct: 13, changes: 2,
    });
  });

  it("sin precios no hay resumen", () => {
    expect(priceStats([])).toBeNull();
  });
});
