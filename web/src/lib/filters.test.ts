import { describe, expect, it } from "vitest";

import {
  activeFilterCount,
  DEFAULT_FILTERS,
  filtersHref,
  filtersToQuery,
  MAX_PAGE,
  MAX_QUERY_LENGTH,
  normalizeQuery,
  parseFilters,
  queryWords,
} from "./filters";

describe("normalizeQuery", () => {
  it("quita tildes, pasa a minúsculas y colapsa espacios", () => {
    expect(normalizeQuery("  Colchón   1 PLAZA ")).toBe("colchon 1 plaza");
  });

  it("elimina todo lo que PostgREST podría interpretar", () => {
    expect(normalizeQuery("a,b(c)*d%e\\f\"g:h;i.j")).toBe("a b c d e f g h i j");
  });

  it("limita el largo", () => {
    expect(normalizeQuery("x".repeat(500)).length).toBeLessThanOrEqual(MAX_QUERY_LENGTH);
  });

  it("deja pasar guiones y números", () => {
    expect(normalizeQuery("Switch-2 256gb")).toBe("switch-2 256gb");
  });
});

describe("queryWords", () => {
  it("devuelve como máximo 5 palabras", () => {
    expect(queryWords("a b c d e f g")).toHaveLength(5);
  });
  it("no devuelve palabras vacías", () => {
    expect(queryWords("  ,, ")).toEqual([]);
  });
});

describe("parseFilters", () => {
  it("usa los valores por defecto sin parámetros", () => {
    expect(parseFilters({})).toEqual(DEFAULT_FILTERS);
  });

  it("acepta valores válidos", () => {
    expect(
      parseFilters({ q: "Taladro", cat: "tecnologia", store: "falabella,sodimac", min: "50", pmin: "1000", pmax: "90000", ver: "1", sort: "price_asc", page: "3" }),
    ).toEqual({ q: "taladro", cat: "tecnologia", stores: ["falabella", "sodimac"], min: 50, pmin: 1000, pmax: 90000, ver: true, sort: "price_asc", page: 3 });
  });

  it("descarta categorías y órdenes que no están en la lista blanca", () => {
    const f = parseFilters({ cat: "x; drop table", sort: "id.asc;select" });
    expect(f.cat).toBeNull();
    expect(f.sort).toBe("best");
  });

  it("descarta tiendas con caracteres raros y duplicadas, y limita la cantidad", () => {
    expect(parseFilters({ store: "falabella,falabella,a b,sodimac)" }).stores).toEqual(["falabella"]);
    const many = Array.from({ length: 40 }, (_, i) => `tienda${i}`).join(",");
    expect(parseFilters({ store: many }).stores).toHaveLength(12);
  });

  it("rechaza números inválidos, negativos o fuera de rango", () => {
    const f = parseFilters({ min: "-5", pmin: "abc", pmax: "1e9", page: "0" });
    expect(f.min).toBeNull();
    expect(f.pmin).toBeNull();
    expect(f.pmax).toBeNull();
    expect(f.page).toBe(1);
    expect(parseFilters({ page: String(MAX_PAGE + 1) }).page).toBe(1);
    expect(parseFilters({ min: "100" }).min).toBeNull();
  });

  it("descarta un precio máximo menor que el mínimo", () => {
    expect(parseFilters({ pmin: "5000", pmax: "100" }).pmax).toBeNull();
  });

  it("toma el primer valor si el parámetro viene repetido", () => {
    expect(parseFilters({ cat: ["ropa", "muebles"] }).cat).toBe("ropa");
  });

  it("'ver' solo se activa con 1", () => {
    expect(parseFilters({ ver: "true" }).ver).toBe(false);
    expect(parseFilters({ ver: "1" }).ver).toBe(true);
  });
});

describe("filtersToQuery / filtersHref", () => {
  it("omite lo que es valor por defecto", () => {
    expect(filtersToQuery(DEFAULT_FILTERS)).toBe("");
    expect(filtersHref(DEFAULT_FILTERS)).toBe("/");
  });

  it("ida y vuelta: parsear lo que se serializó da lo mismo", () => {
    const original = parseFilters({ q: "sofa", cat: "muebles", store: "sodimac", min: "70", ver: "1", sort: "saving", page: "2" });
    const params = Object.fromEntries(new URLSearchParams(filtersToQuery(original)));
    expect(parseFilters(params)).toEqual(original);
  });

  it("cambiar un filtro vuelve a la página 1", () => {
    const f = parseFilters({ page: "4", cat: "ropa" });
    expect(filtersHref(f, { cat: "muebles" })).toBe("/?cat=muebles");
  });

  it("puede pedir otra página explícitamente", () => {
    expect(filtersHref(DEFAULT_FILTERS, { page: 3 })).toBe("/?page=3");
  });
});

describe("activeFilterCount", () => {
  it("cuenta cada grupo de filtros una vez", () => {
    expect(activeFilterCount(DEFAULT_FILTERS)).toBe(0);
    expect(activeFilterCount({ ...DEFAULT_FILTERS, pmin: 1, pmax: 2, cat: "ropa" })).toBe(2);
  });
});
