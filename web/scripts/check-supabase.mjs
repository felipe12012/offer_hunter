// Prueba de conexión con Supabase (5B.8). Lee web/.env.local y comprueba, en
// orden, URL + clave + permisos + migraciones aplicadas. Nunca imprime la clave.
//
//   node web/scripts/check-supabase.mjs
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const envPath = resolve(here, "..", ".env.local");

function loadEnv(path) {
  const env = {};
  let text;
  try {
    text = readFileSync(path, "utf8");
  } catch {
    return env;
  }
  for (const line of text.split("\n")) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (match) env[match[1]] = match[2].replace(/^["']|["']$/g, "");
  }
  return env;
}

const env = { ...loadEnv(envPath), ...process.env };
const URL = env.SUPABASE_URL;
const KEY = env.SUPABASE_SERVICE_KEY;

if (!URL || !KEY) {
  console.error("FALLA: faltan SUPABASE_URL y/o SUPABASE_SERVICE_KEY en web/.env.local");
  process.exit(1);
}

function headers(extra = {}) {
  const h = { apikey: KEY, Accept: "application/json", ...extra };
  if (KEY.startsWith("eyJ")) h.Authorization = `Bearer ${KEY}`;
  return h;
}

async function check(name, fn) {
  try {
    const detail = await fn();
    console.log(`OK    ${name}${detail ? ` — ${detail}` : ""}`);
    return true;
  } catch (err) {
    console.error(`FALLA ${name} — ${err.message}`);
    return false;
  }
}

const get = async (path, extra) => {
  const res = await fetch(`${URL}/rest/v1/${path}`, { headers: headers(extra) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res;
};

const ok =
  (await check("offer_scan_runs (URL + clave + permisos)", async () => {
    const res = await get("offer_scan_runs?select=started_at&order=started_at.desc&limit=1");
    const rows = await res.json();
    if (!rows.length) throw new Error("sin filas");
    return `última exploración ${rows[0].started_at}`;
  })) &&
  (await check("offer_feed (migración 0002)", async () => {
    const res = await get("offer_feed?select=id&limit=1", { Prefer: "count=exact", Range: "0-0" });
    const total = Number(res.headers.get("content-range")?.split("/")[1] ?? 0);
    if (!total) throw new Error("total 0 (¿0002 aplicada?)");
    return `${total} productos`;
  })) &&
  (await check("offer_stats (migración 0004)", async () => {
    const res = await fetch(`${URL}/rest/v1/rpc/offer_stats`, {
      method: "POST",
      headers: headers({ "Content-Type": "application/json" }),
      body: "{}",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stats = await res.json();
    if (!("total" in stats && "groups" in stats)) throw new Error("respuesta inesperada");
    return `total=${stats.total} verified=${stats.verified}`;
  })) &&
  (await check("offer_price_points (historial)", async () => {
    const res = await get("offer_price_points?select=product_id&limit=1");
    const rows = await res.json();
    if (!rows.length) throw new Error("sin filas");
    return "1 fila";
  }));

process.exit(ok ? 0 : 1);
