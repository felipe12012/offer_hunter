// Servidor falso que imita lo mínimo de la Data API de Supabase (PostgREST), para probar la web
// en modo producción sin la clave real:
//
//   node web/scripts/mock-supabase.mjs &            # escucha en :3199
//   SUPABASE_URL=http://localhost:3199 SUPABASE_SERVICE_KEY=sb_secret_mock npm run start
//
// Exige la cabecera `apikey` y registra cada petición en <tmp>/mock-supabase.log.
import { appendFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";

const LOG = join(tmpdir(), "mock-supabase.log");

const KEY = "sb_secret_mock";
const now = Date.now();
const iso = (minutes) => new Date(now - minutes * 60_000).toISOString();

const rows = [
  { id: "falabella:1001", store: "falabella", title: "Notebook Gamer 15.6 RTX", url: "https://example.com/1", image_url: "https://example.com/1.jpg", category_group: "tecnologia", price: 599990, list_price: 1199990, web_discount_pct: 50, saving: 600000, verified_pct: 50, web_confirmed: true, history_drop_pct: 0, points: 3, prev_min: 599990, last_seen_at: iso(4) },
  { id: "sodimac:2002", store: "sodimac", title: "Colchón 1 Plaza Ortopédico", url: "https://example.com/2", image_url: "https://example.com/2.jpg", category_group: "muebles", price: 89990, list_price: 299990, web_discount_pct: 70, saving: 210000, verified_pct: 0, web_confirmed: false, history_drop_pct: 0, points: 1, prev_min: null, last_seen_at: iso(9) },
  { id: "hites:3003", store: "hites", title: "Tablet 10 pulgadas 128GB", url: "https://example.com/3", image_url: "https://example.com/3.jpg", category_group: "tecnologia", price: 139990, list_price: 139990, web_discount_pct: 0, saving: 0, verified_pct: 0, web_confirmed: false, history_drop_pct: 0, points: 2, prev_min: 139990, last_seen_at: iso(12) },
];

const stats = { total: 48971, verified: 2169, super: 12, last_seen: iso(4), stores: { falabella: 21000, sodimac: 9000, hites: 4000 }, groups: { tecnologia: 8000, muebles: 7000, ropa: 9000 } };

const server = createServer((req, res) => {
  const log = (status) => appendFileSync(LOG, `${status} ${req.method} ${req.url.slice(0, 1500)}\n`);
  if (req.headers.apikey !== KEY) {
    res.writeHead(401, { "Content-Type": "application/json" }).end(JSON.stringify({ message: "Invalid API key", code: "PGRST301" }));
    return log(401);
  }
  const url = new URL(req.url, "http://x");
  const json = (body, headers = {}) => res.writeHead(200, { "Content-Type": "application/json", ...headers }).end(JSON.stringify(body));
  log(200);
  if (url.pathname === "/rest/v1/rpc/offer_stats") return json(stats);
  if (url.pathname === "/rest/v1/offer_feed") {
    const id = url.searchParams.get("id");
    if (id?.startsWith("eq.")) return json(rows.filter((r) => r.id === id.slice(3)).map((r) => ({ ...r, category: r.category_group, distinct_prices: 2, hist_min: r.price, hist_max: r.list_price, prev_max: r.list_price, first_point_at: iso(600), first_seen_at: iso(600) })));
    if (id?.startsWith("neq.")) return json(rows.filter((r) => r.id !== id.slice(4)));
    return json(rows, { "Content-Range": `0-${rows.length - 1}/${stats.total}` });
  }
  if (url.pathname === "/rest/v1/offer_price_points") {
    return json([
      { observed_at: iso(600), price: 1199990, list_price: 1199990 },
      { observed_at: iso(30), price: 599990, list_price: 1199990 },
    ]);
  }
  res.writeHead(404, { "Content-Type": "application/json" }).end(JSON.stringify({ code: "PGRST205", message: "not found" }));
});

server.listen(3199, () => console.log("mock Supabase en http://localhost:3199, log en " + LOG));
