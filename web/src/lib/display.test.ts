import { describe, expect, it } from "vitest";

import { agoFrom, clp, groupName, isStale, storeName } from "./format";
import { dealView, tierFor } from "./tiers";

describe("tierFor", () => {
  it("usa los mismos umbrales que las alertas de Telegram (60 / 80 / 90)", () => {
    expect(tierFor(59.9)).toBeNull();
    expect(tierFor(60)?.key).toBe("gran");
    expect(tierFor(79.9)?.key).toBe("gran");
    expect(tierFor(80)?.key).toBe("ofertaza");
    expect(tierFor(89.9)?.key).toBe("ofertaza");
    expect(tierFor(90)?.key).toBe("super");
    expect(tierFor(100)?.key).toBe("super");
  });
});

describe("dealView", () => {
  it("un descuento verificado muestra su porcentaje y su nivel", () => {
    expect(dealView({ verified_pct: 66, web_discount_pct: 66 })).toEqual({
      verified: true, pct: 66, tier: expect.objectContaining({ key: "gran" }), claimOnly: false,
    });
  });

  it("lo que solo anuncia la tienda NO recibe nivel, por alto que sea", () => {
    const view = dealView({ verified_pct: 0, web_discount_pct: 92 });
    expect(view.verified).toBe(false);
    expect(view.tier).toBeNull();
    expect(view.claimOnly).toBe(true);
    expect(view.pct).toBe(92);
  });

  it("una baja verificada pequeña (menos de 10 %) no cuenta como verificada", () => {
    const view = dealView({ verified_pct: 6.3, web_discount_pct: 57.2 });
    expect(view.verified).toBe(false);
    expect(view.pct).toBe(57);
  });

  it("sin ningún descuento no hay nada que anunciar", () => {
    expect(dealView({ verified_pct: 0, web_discount_pct: 0 }).claimOnly).toBe(false);
  });

  it("cuando el verificado es menor que el anunciado, manda el verificado", () => {
    expect(dealView({ verified_pct: 45, web_discount_pct: 78 }).pct).toBe(45);
  });
});

describe("clp", () => {
  it("formatea pesos chilenos con punto de miles", () => {
    expect(clp(149990)).toMatch(/^\$\s?149\.990$/);
    expect(clp(0)).toMatch(/^\$\s?0$/);
  });
});

describe("agoFrom", () => {
  const now = Date.parse("2026-10-03T12:00:00Z");
  it("expresa la antigüedad en lenguaje simple", () => {
    expect(agoFrom("2026-10-03T11:59:40Z", now)).toBe("hace un momento");
    expect(agoFrom("2026-10-03T11:48:00Z", now)).toBe("hace 12 min");
    expect(agoFrom("2026-10-03T11:00:00Z", now)).toBe("hace 1 hora");
    expect(agoFrom("2026-10-03T07:00:00Z", now)).toBe("hace 5 horas");
    expect(agoFrom("2026-10-01T12:00:00Z", now)).toBe("hace 2 días");
  });
  it("tolera datos faltantes o inválidos", () => {
    expect(agoFrom(null, now)).toBe("sin datos");
    expect(agoFrom("no es una fecha", now)).toBe("sin datos");
  });
});

describe("nombres", () => {
  it("conoce las tiendas y capitaliza las desconocidas", () => {
    expect(storeName("hushpuppies")).toBe("Hush Puppies");
    expect(storeName("lapolar")).toBe("La Polar");
    expect(storeName("nuevatienda")).toBe("Nuevatienda");
  });
  it("traduce los grupos", () => {
    expect(groupName("tecnologia")).toBe("Tecnología");
    expect(groupName("raro")).toBe("raro");
  });
});

describe("isStale", () => {
  const now = Date.parse("2026-10-03T12:00:00Z");
  it("marca como vencido lo que no se ve hace más de N horas", () => {
    expect(isStale("2026-10-03T07:00:00Z", 6, now)).toBe(false);
    expect(isStale("2026-10-03T05:59:00Z", 6, now)).toBe(true);
    expect(isStale("basura", 6, now)).toBe(true);
  });
});
