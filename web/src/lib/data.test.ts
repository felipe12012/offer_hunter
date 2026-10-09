import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_FILTERS, parseFilters } from "./filters";

function setEnv(values: Partial<Record<"SUPABASE_URL" | "SUPABASE_SERVICE_KEY" | "NODE_ENV", string | undefined>>) {
  for (const [name, value] of Object.entries(values)) {
    if (value === undefined) vi.stubEnv(name, "");
    else vi.stubEnv(name, value);
  }
}

async function load() {
  vi.resetModules();
  return import("./data");
}

beforeEach(() => {
  vi.unstubAllEnvs();
});
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("sin credenciales fuera de producción (muestra local)", () => {
  beforeEach(() => setEnv({ SUPABASE_URL: "", SUPABASE_SERVICE_KEY: "", NODE_ENV: "development" }));

  it("devuelve productos de la muestra con su total", async () => {
    const { getFeed } = await load();
    const { rows, total } = await getFeed(DEFAULT_FILTERS);
    expect(total).toBeGreaterThan(10);
    expect(rows.length).toBeLessThanOrEqual(24);
  });

  it("ordena lo verificado primero", async () => {
    const { getFeed } = await load();
    const { rows } = await getFeed(DEFAULT_FILTERS);
    for (let i = 1; i < rows.length; i++) expect(rows[i - 1].verified_pct).toBeGreaterThanOrEqual(rows[i].verified_pct);
  });

  it("'solo verificadas' deja únicamente productos verificados", async () => {
    const { getFeed } = await load();
    const { rows } = await getFeed({ ...DEFAULT_FILTERS, ver: true });
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.every((row) => row.verified_pct >= 10)).toBe(true);
  });

  it("la búsqueda ignora tildes: 'colchon' encuentra 'COLCHON' y 'Cubrecama'", async () => {
    const { getFeed } = await load();
    const { rows } = await getFeed(parseFilters({ q: "colchon" }));
    expect(rows.some((row) => /colch/i.test(row.title))).toBe(true);
    const accented = await getFeed(parseFilters({ q: "Audífonos" }));
    expect(accented.rows.length).toBeGreaterThan(0);
  });

  it("filtra por categoría, tienda, rango de precio y descuento", async () => {
    const { getFeed } = await load();
    expect((await getFeed(parseFilters({ cat: "muebles" }))).rows.every((r) => r.category_group === "muebles")).toBe(true);
    expect((await getFeed(parseFilters({ store: "hites" }))).rows.every((r) => r.store === "hites")).toBe(true);
    expect((await getFeed(parseFilters({ pmin: "20000", pmax: "50000" }))).rows.every((r) => r.price >= 20000 && r.price <= 50000)).toBe(true);
    expect((await getFeed(parseFilters({ min: "60" }))).rows.every((r) => Math.max(r.verified_pct, r.web_discount_pct) >= 60)).toBe(true);
  });

  it("ordena por precio", async () => {
    const { getFeed } = await load();
    const { rows } = await getFeed(parseFilters({ sort: "price_asc" }));
    for (let i = 1; i < rows.length; i++) expect(rows[i - 1].price).toBeLessThanOrEqual(rows[i].price);
  });

  it("pagina", async () => {
    const { getFeed } = await load();
    const page9 = await getFeed(parseFilters({ page: "9" }));
    expect(page9.rows).toEqual([]);
  });

  it("estadísticas, súper ofertas, ficha, historial y relacionados", async () => {
    const data = await load();
    const stats = await data.getStats();
    expect(stats.total).toBeGreaterThan(0);
    expect(Object.keys(stats.stores).length).toBeGreaterThan(1);

    const supers = await data.getSuperDeals();
    expect(supers.every((row) => row.verified_pct >= 60)).toBe(true);

    const product = await data.getProduct("falabella:883785127");
    expect(product?.title).toContain("APOLOGY");
    expect(await data.getProduct("falabella:no-existe")).toBeNull();
    expect(await data.getProduct("id inválido; drop")).toBeNull();

    const history = await data.getHistory(product!);
    expect(history.length).toBeGreaterThanOrEqual(1);

    const related = await data.getRelated(product!);
    expect(related.every((row) => row.category_group === product!.category_group && row.id !== product!.id)).toBe(true);
  });
});

describe("sin credenciales en producción", () => {
  it("falla de forma visible: nunca muestra datos falsos", async () => {
    setEnv({ SUPABASE_URL: "", SUPABASE_SERVICE_KEY: "", NODE_ENV: "production" });
    const { getFeed } = await load();
    await expect(getFeed(DEFAULT_FILTERS)).rejects.toThrow(/SUPABASE_URL/);
  });
});

describe("con credenciales (Supabase)", () => {
  beforeEach(() => setEnv({ SUPABASE_URL: "https://p.supabase.co", SUPABASE_SERVICE_KEY: "sb_secret_abc", NODE_ENV: "production" }));

  function mockFetch(handler: (url: string, init: RequestInit) => Response) {
    const calls: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return handler(url, init);
    });
    return calls;
  }

  const row = { id: "falabella:1", title: "x", verified_pct: 50 };

  it("consulta offer_feed con la clave en la cabecera apikey y devuelve el total", async () => {
    const calls = mockFetch((url) =>
      url.includes("select=last_seen_at&")
        ? new Response("[]", { status: 200 })
        : new Response(JSON.stringify([row]), { status: 200, headers: { "content-range": "0-0/1234" } }),
    );
    const { getFeed } = await load();

    const result = await getFeed(DEFAULT_FILTERS);

    expect(result.total).toBe(1234);
    expect(result.rows).toEqual([row]);
    const list = calls.find((call) => !call.url.includes("select=last_seen_at&"))!;
    expect(list.url).toContain("https://p.supabase.co/rest/v1/offer_feed?");
    const headers = list.init.headers as Record<string, string>;
    expect(headers.apikey).toBe("sb_secret_abc");
    expect(headers.Authorization).toBeUndefined();
    expect(headers.Prefer).toBe("count=exact");
  });

  it("llama a la función offer_stats por POST", async () => {
    const calls = mockFetch(() => new Response(JSON.stringify({ total: 5, verified: 1, super: 0, last_seen: null, stores: {}, groups: {} }), { status: 200 }));
    const { getStats } = await load();
    expect((await getStats()).total).toBe(5);
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].url).toBe("https://p.supabase.co/rest/v1/rpc/offer_stats");
  });

  it("reintenta una vez ante un error 5xx", async () => {
    let attempt = 0;
    mockFetch((url) => {
      if (url.includes("select=last_seen_at&")) return new Response("[]", { status: 200 });
      return ++attempt === 1 ? new Response("busy", { status: 503 }) : new Response("[]", { status: 200 });
    });
    const { getFeed } = await load();
    await expect(getFeed(DEFAULT_FILTERS)).resolves.toEqual({ rows: [], total: 0 });
    expect(attempt).toBe(2);
  });

  it("si el escaneo se detuvo, la lista mide 'a la venta' desde el último escaneo y no desde ahora", async () => {
    const lastScan = new Date(Date.now() - 10 * 3_600_000).toISOString();
    const calls = mockFetch((url) =>
      url.includes("select=last_seen_at&")
        ? new Response(JSON.stringify([{ last_seen_at: lastScan }]), { status: 200 })
        : new Response("[]", { status: 200 }),
    );
    const { getFeed } = await load();
    await getFeed(DEFAULT_FILTERS);
    const list = calls.find((call) => !call.url.includes("select=last_seen_at&"))!;
    const since = Date.parse(new URL(list.url).searchParams.get("last_seen_at")!.replace("gte.", ""));
    // 6 h antes del último escaneo (con el redondeo de la consulta), no 6 h antes de ahora
    expect(Date.parse(lastScan) - since).toBeGreaterThan(5 * 3_600_000);
    expect(Date.parse(lastScan) - since).toBeLessThan(7 * 3_600_000);
  });

  it("un error de Supabase no filtra la clave ni la URL", async () => {
    mockFetch(() => new Response(JSON.stringify({ code: "42501", message: "permission denied for table offer_feed" }), { status: 403 }));
    const { getFeed } = await load();
    const error = await getFeed(DEFAULT_FILTERS).catch((e) => e);
    expect(error.status).toBe(403);
    expect(error.code).toBe("42501");
    expect(String(error.message) + String(error.stack)).not.toContain("sb_secret_abc");
    expect(String(error.message)).not.toContain("p.supabase.co");
  });

  it("si la base no responde, el error es genérico", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new Error("ECONNRESET https://p.supabase.co sb_secret_abc");
    });
    const { getFeed } = await load();
    const error = await getFeed(DEFAULT_FILTERS).catch((e) => e);
    expect(error.message).toBe("La base de datos no respondió");
  });

  it("no consulta ids con formato inválido", async () => {
    const calls = mockFetch(() => new Response("[]", { status: 200 }));
    const { getProduct } = await load();
    expect(await getProduct("x&select=*")).toBeNull();
    expect(calls).toHaveLength(0);
  });

  it("una clave JWT antigua también va en Authorization", async () => {
    setEnv({ SUPABASE_SERVICE_KEY: "eyJhbGciOi.payload.sig" });
    const calls = mockFetch(() => new Response("[]", { status: 200 }));
    const { getFeed } = await load();
    await getFeed(DEFAULT_FILTERS);
    expect((calls[0].init.headers as Record<string, string>).Authorization).toBe("Bearer eyJhbGciOi.payload.sig");
  });
});
