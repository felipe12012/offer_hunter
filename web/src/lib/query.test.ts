import { describe, expect, it } from "vitest";

import { DEFAULT_FILTERS, parseFilters } from "./filters";
import {
  buildHistoryQuery,
  buildListQuery,
  buildProductQuery,
  buildRelatedQuery,
  buildSiblingsQuery,
  buildSuperQuery,
  freshSince,
  isValidProductId,
} from "./query";

const NOW = Date.parse("2026-10-03T12:07:31Z");

function params(query: string) {
  return new URLSearchParams(query);
}

describe("freshSince", () => {
  it("resta 6 horas y redondea a 10 minutos (la URL no cambia en cada petición)", () => {
    expect(freshSince(NOW)).toBe("2026-10-03T06:00:00.000Z");
    expect(freshSince(NOW + 60_000)).toBe(freshSince(NOW));
  });
});

describe("buildListQuery", () => {
  it("pide solo productos vigentes, sin duplicados entre tiendas, con orden y paginación", () => {
    const p = params(buildListQuery(DEFAULT_FILTERS, NOW));
    expect(p.get("last_seen_at")).toBe("gte.2026-10-03T06:00:00.000Z");
    expect(p.get("dup_rank")).toBe("eq.1");
    expect(p.get("order")).toBe("verified_pct.desc,web_discount_pct.desc,id.asc");
    expect(p.get("limit")).toBe("24");
    expect(p.get("offset")).toBe("0");
  });

  it("nunca pide todas las columnas", () => {
    expect(params(buildListQuery(DEFAULT_FILTERS, NOW)).get("select")).not.toContain("*");
  });

  it("calcula el offset según la página", () => {
    expect(params(buildListQuery({ ...DEFAULT_FILTERS, page: 3 }, NOW)).get("offset")).toBe("48");
  });

  it("filtra por categoría y tiendas", () => {
    const p = params(buildListQuery({ ...DEFAULT_FILTERS, cat: "ropa", stores: ["falabella", "hites"] }, NOW));
    expect(p.get("category_group")).toBe("eq.ropa");
    expect(p.get("store")).toBe("in.(falabella,hites)");
  });

  it("descuento mínimo: sin 'solo verificadas' mira lo verificado o lo anunciado", () => {
    expect(params(buildListQuery({ ...DEFAULT_FILTERS, min: 50 }, NOW)).get("or")).toBe(
      "(verified_pct.gte.50,web_discount_pct.gte.50)",
    );
  });

  it("descuento mínimo con 'solo verificadas' mira solo lo verificado", () => {
    const p = params(buildListQuery({ ...DEFAULT_FILTERS, min: 50, ver: true }, NOW));
    expect(p.get("verified_pct")).toBe("gte.50");
    expect(p.get("or")).toBeNull();
  });

  it("'solo verificadas' sin mínimo usa el umbral de verificación", () => {
    expect(params(buildListQuery({ ...DEFAULT_FILTERS, ver: true }, NOW)).get("verified_pct")).toBe("gte.10");
  });

  it("el rango de precio usa dos condiciones sobre la misma columna", () => {
    const p = params(buildListQuery({ ...DEFAULT_FILTERS, pmin: 1000, pmax: 5000 }, NOW));
    expect(p.getAll("price")).toEqual(["gte.1000", "lte.5000"]);
  });

  it("cada palabra de la búsqueda es una condición sobre el título sin tildes", () => {
    const p = params(buildListQuery(parseFilters({ q: "Colchón 1 Plaza" }), NOW));
    expect(p.getAll("title_norm")).toEqual(["ilike.*colchon*", "ilike.*1*", "ilike.*plaza*"]);
  });

  it("una búsqueda maliciosa no puede inyectar operadores ni columnas", () => {
    const f = parseFilters({ q: "x*)&select=*&or=(id.gt.0,y", cat: "ropa&limit=1000000", sort: "id.desc" });
    const p = params(buildListQuery(f, NOW));
    expect(p.get("select")).not.toContain("*");
    expect(p.get("limit")).toBe("24");
    expect(p.getAll("or")).toEqual([]);
    expect(p.getAll("title_norm").every((value) => /^ilike\.\*[a-z0-9-]+\*$/.test(value))).toBe(true);
    expect(p.get("category_group")).toBeNull();
  });

  it("cada orden tiene un desempate por id (paginación estable)", () => {
    for (const sort of ["best", "web", "price_asc", "price_desc", "saving", "new"] as const) {
      expect(params(buildListQuery({ ...DEFAULT_FILTERS, sort }, NOW)).get("order")).toMatch(/id\.asc$/);
    }
  });
});

describe("otras consultas", () => {
  it("súper ofertas: solo verificadas de 60 % o más", () => {
    const p = params(buildSuperQuery(NOW));
    expect(p.get("verified_pct")).toBe("gte.60");
    expect(p.get("dup_rank")).toBe("eq.1");
  });

  it("ficha: un solo producto por id exacto", () => {
    const p = params(buildProductQuery("falabella:80726514"));
    expect(p.get("id")).toBe("eq.falabella:80726514");
    expect(p.get("limit")).toBe("1");
  });

  it("historial: ordenado por fecha y acotado", () => {
    const p = params(buildHistoryQuery("falabella:80726514"));
    expect(p.get("order")).toBe("observed_at.asc");
    expect(p.get("limit")).toBe("200");
  });

  it("relacionados: misma categoría, sin el propio producto", () => {
    const p = params(buildRelatedQuery("ropa", "falabella:1", NOW));
    expect(p.get("category_group")).toBe("eq.ropa");
    expect(p.get("id")).toBe("neq.falabella:1");
  });
});

describe("subcategoría", () => {
  it("filtra por subcat solo si hay categoría", () => {
    const p = params(buildListQuery(parseFilters({ cat: "zapatillas", sub: "mujer" }), NOW));
    expect(p.get("category_group")).toBe("eq.zapatillas");
    expect(p.get("subcat")).toBe("eq.mujer");
    expect(params(buildListQuery(parseFilters({ sub: "mujer" }), NOW)).has("subcat")).toBe(false);
  });
});

describe("sin repetidos entre bloques y tiendas", () => {
  it("el listado puede excluir lo que ya muestra el carrusel", () => {
    const q = params(buildListQuery(DEFAULT_FILTERS, NOW, 24, ["falabella:1", "sodimac:2"]));
    expect(q.get("id")).toBe("not.in.(falabella:1,sodimac:2)");
  });

  it("solo se excluyen ids con forma válida (nada se cuela en la consulta)", () => {
    const q = params(buildListQuery(DEFAULT_FILTERS, NOW, 24, ["falabella:1", "x),(or=1", "otro"]));
    expect(q.get("id")).toBe("not.in.(falabella:1)");
  });

  it("sin exclusiones no hay filtro por id", () => {
    expect(params(buildListQuery(DEFAULT_FILTERS, NOW)).has("id")).toBe(false);
  });

  it("gemela: Falabella y Sodimac comparten código; las demás tiendas no tienen", () => {
    const q = params(buildSiblingsQuery("falabella:80726514", NOW) ?? "");
    expect(q.getAll("id")).toEqual(["in.(falabella:80726514,sodimac:80726514)", "neq.falabella:80726514"]);
    expect(q.get("order")).toBe("price.asc");
    expect(buildSiblingsQuery("hites:123", NOW)).toBeNull();
    expect(buildSiblingsQuery("falabella:bad id", NOW)).toBeNull();
  });
});

describe("isValidProductId", () => {
  it("acepta ids reales", () => {
    expect(isValidProductId("falabella:80726514")).toBe(true);
    expect(isValidProductId("hites:10052004071002")).toBe(true);
    expect(isValidProductId("falabella:prod48314876")).toBe(true);
    expect(isValidProductId("tusmascotas:253223")).toBe(true);
  });

  it("rechaza lo que no tiene la forma tienda:sku", () => {
    for (const bad of ["", "falabella", "falabella:", ":123", "Falabella:1", "fala bella:1", "falabella:1&limit=5", "falabella:1,2", "falabella:(1)", "a".repeat(200)]) {
      expect(isValidProductId(bad)).toBe(false);
    }
  });
});
