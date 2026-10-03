// Falla si la clave secreta (o cualquier cosa con forma de clave) aparece en lo que llega al navegador.
//
//   npm run build && npm run check:secrets
//
// Revisa web/.next/static (JavaScript y CSS que se descargan) y, si hay un .env.local, busca
// además el valor exacto de SUPABASE_SERVICE_KEY en todo .next/ salvo en el código de servidor.
import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const staticDir = join(root, ".next", "static");

function walk(dir) {
  const files = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) files.push(...walk(full));
    else files.push(full);
  }
  return files;
}

if (!existsSync(staticDir)) {
  console.error("No existe .next/static: ejecuta `npm run build` primero.");
  process.exit(2);
}

const patterns = [
  { name: "clave secreta de Supabase (sb_secret_…)", re: /sb_secret_[A-Za-z0-9_-]{8,}/ },
  { name: "JWT (clave antigua anon/service_role)", re: /eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}/ },
  { name: "nombre de la variable secreta", re: /SUPABASE_SERVICE_KEY/ },
];

// Si hay un .env.local, también se busca el valor exacto de la clave.
const exact = [];
const envPath = join(root, ".env.local");
if (existsSync(envPath)) {
  const match = readFileSync(envPath, "utf8").match(/^SUPABASE_SERVICE_KEY\s*=\s*(.+)$/m);
  const value = match?.[1]?.trim().replace(/^["']|["']$/g, "");
  if (value && value.length > 8) exact.push(value);
}

let problems = 0;
for (const file of walk(staticDir)) {
  if (!/\.(js|css|html|json|map|txt)$/.test(file)) continue;
  const text = readFileSync(file, "utf8");
  for (const { name, re } of patterns) {
    if (re.test(text)) {
      console.error(`✗ ${name} en ${file.replace(root, "web")}`);
      problems += 1;
    }
  }
  for (const value of exact) {
    if (text.includes(value)) {
      console.error(`✗ el valor de SUPABASE_SERVICE_KEY aparece en ${file.replace(root, "web")}`);
      problems += 1;
    }
  }
}

if (problems > 0) {
  console.error(`\n${problems} problema(s). La clave no puede llegar al navegador: revisa que solo lib/supabase.ts la lea.`);
  process.exit(1);
}
console.log(`OK: ${walk(staticDir).length} archivos de .next/static sin claves.`);
