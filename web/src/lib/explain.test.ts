import { describe, expect, it } from "vitest";

import { buildChart } from "./chart";
import { explainDeal } from "./explain";
import { pageWindow, totalPages } from "./pagination";
import type { FeedRow } from "./types";

function row(overrides: Partial<FeedRow> = {}): FeedRow {
  return {
    id: "falabella:1", store: "falabella", title: "x", url: "https://x", image_url: "https://x/i.jpg",
    category: "ropa", category_group: "ropa", price: 5000, list_price: 10000, web_discount_pct: 50, saving: 5000,
    verified_pct: 0, web_confirmed: false, history_drop_pct: 0, points: 2, distinct_prices: 2,
    prev_min: 5000, prev_max: 10000, last_seen_at: "2026-10-03T12:00:00Z", first_point_at: "2026-10-02T12:00:00Z",
    ...overrides,
  };
}

describe("explainDeal", () => {
  it("un descuento confirmado por el historial dice que el precio normal es real", () => {
    const reasons = explainDeal(row({ verified_pct: 50, web_confirmed: true }));
    expect(reasons[0].tone).toBe("ok");
    expect(reasons[0].text).toMatch(/Antes costaba \$\s?10\.000/);
    expect(reasons.some((r) => r.tone === "warn")).toBe(false);
  });

  it("una baja contra el historial se explica con el precio anterior", () => {
    const reasons = explainDeal(row({ verified_pct: 45, history_drop_pct: 45, prev_min: 9000, web_discount_pct: 78 }));
    expect(reasons.some((r) => r.tone === "ok" && /Bajó 45%/.test(r.text) && /9\.000/.test(r.text))).toBe(true);
  });

  it("lo que solo anuncia la tienda se marca como advertencia", () => {
    const reasons = explainDeal(row({ verified_pct: 0, prev_max: null, prev_min: null, distinct_prices: 1 }));
    expect(reasons[0].tone).toBe("warn");
    expect(reasons[0].text).toMatch(/anuncia -50%/);
  });

  it("avisa cuando el precio más alto visto está lejos del precio normal (posible precio inflado)", () => {
    const reasons = explainDeal(row({ verified_pct: 0, prev_max: 12000, list_price: 60000, web_discount_pct: 80 }));
    expect(reasons.some((r) => r.tone === "warn" && /podría estar inflado/.test(r.text))).toBe(true);
  });

  it("sin descuento anunciado lo dice", () => {
    const reasons = explainDeal(row({ list_price: 5000, web_discount_pct: 0, saving: 0 }));
    expect(reasons.some((r) => /no tiene un descuento anunciado/.test(r.text))).toBe(true);
  });

  it("siempre cuenta cuánto llevamos siguiendo el producto", () => {
    expect(explainDeal(row()).at(-1)?.text).toMatch(/2 precios distintos/);
    expect(explainDeal(row({ distinct_prices: 1 })).at(-1)?.text).toMatch(/solo hemos visto un precio/);
  });
});

describe("buildChart", () => {
  const points = [
    { observed_at: "2026-10-01T00:00:00Z", price: 10000, list_price: 10000 },
    { observed_at: "2026-10-02T00:00:00Z", price: 6000, list_price: 10000 },
    { observed_at: "2026-10-03T00:00:00Z", price: 6000, list_price: 10000 },
  ];

  it("dibuja una línea escalonada: el precio se mantiene hasta que cambia", () => {
    const chart = buildChart(points, { width: 400, height: 200 });
    expect(chart.single).toBe(false);
    expect(chart.pricePath).toMatch(/^M[\d.]+ [\d.]+H[\d.]+V[\d.]+H[\d.]+V[\d.]+H[\d.]+$/);
    expect(chart.dots).toHaveLength(3);
  });

  it("los precios más altos quedan más arriba", () => {
    const chart = buildChart(points);
    expect(chart.dots[0].y).toBeLessThan(chart.dots[1].y);
  });

  it("con una sola observación no hay línea, solo un punto", () => {
    const chart = buildChart([points[0]]);
    expect(chart.single).toBe(true);
    expect(chart.dots).toHaveLength(1);
    expect(chart.pricePath).not.toContain("H");
  });

  it("sin datos no falla", () => {
    expect(buildChart([]).dots).toEqual([]);
  });

  it("un precio constante igual deja espacio vertical (no divide por cero)", () => {
    const chart = buildChart([
      { observed_at: "2026-10-01T00:00:00Z", price: 5000, list_price: null },
      { observed_at: "2026-10-02T00:00:00Z", price: 5000, list_price: null },
    ]);
    expect(Number.isFinite(chart.dots[0].y)).toBe(true);
    expect(chart.yMax).toBeGreaterThan(chart.yMin);
  });

  it("ordena los puntos por fecha aunque lleguen desordenados", () => {
    const chart = buildChart([points[2], points[0], points[1]]);
    expect(chart.dots.map((d) => d.at)).toEqual(points.map((p) => p.observed_at));
  });

  it("endAt extiende el último precio hasta ahora", () => {
    const short = buildChart(points, { width: 400 });
    const extended = buildChart(points, { width: 400, endAt: "2026-10-05T00:00:00Z" });
    expect(extended.dots[2].x).toBeLessThan(short.dots[2].x);
  });

  it("omite la línea de precio normal cuando no hay precio tachado", () => {
    const chart = buildChart(points.map((p) => ({ ...p, list_price: null })));
    expect(chart.listPath).toBe("");
  });
});

describe("paginación", () => {
  it("calcula las páginas con un tope", () => {
    expect(totalPages(0)).toBe(1);
    expect(totalPages(24)).toBe(1);
    expect(totalPages(25)).toBe(2);
    expect(totalPages(10_000_000)).toBe(200);
  });

  it("muestra primera, última y una ventana alrededor de la actual", () => {
    expect(pageWindow(1, 3)).toEqual([1, 2, 3]);
    expect(pageWindow(10, 50)).toEqual([1, null, 8, 9, 10, 11, 12, null, 50]);
    expect(pageWindow(2, 50)).toEqual([1, 2, 3, 4, null, 50]);
  });
});
