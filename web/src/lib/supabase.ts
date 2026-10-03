// web/src/lib/supabase.ts — SOLO SERVIDOR.
// Único módulo que conoce la clave secreta. Las consultas son de solo lectura
// (GET y el POST a la función offer_stats); nunca se expone al cliente.
import "server-only";

import { buildHeaders } from "./headers";

export class SupabaseError extends Error {
  constructor(
    public status: number,
    public code: string | undefined,
    message: string,
  ) {
    super(message);
    this.name = "SupabaseError";
  }
}

/** No hay credenciales configuradas (la web puede entonces usar la muestra local en desarrollo). */
export class SupabaseConfigError extends Error {
  constructor() {
    super("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (server environment only)");
    this.name = "SupabaseConfigError";
  }
}

export function hasCredentials(): boolean {
  return Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_KEY);
}

const TIMEOUT_MS = 10_000;

async function once(url: string, init: RequestInit, revalidate: number): Promise<Response> {
  return fetch(url, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS), next: { revalidate } });
}

export async function rest<T>(
  path: string,
  opts: { revalidate?: number; count?: boolean; method?: "GET" | "POST"; body?: unknown } = {},
): Promise<{ rows: T; total: number | null }> {
  // Las credenciales se leen al usarse, no al importar: así `next build` no las necesita.
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) throw new SupabaseConfigError();

  const init: RequestInit = {
    method: opts.method ?? "GET",
    headers: buildHeaders(key, {
      ...(opts.count ? { Prefer: "count=exact" } : {}),
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    }),
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  };
  const target = `${url}/rest/v1/${path}`;
  const revalidate = opts.revalidate ?? 120;

  let res: Response;
  try {
    res = await once(target, init, revalidate);
    if (res.status >= 500) res = await once(target, init, revalidate); // un reintento ante errores 5xx
  } catch {
    try {
      res = await once(target, init, revalidate); // un reintento ante fallos de red o tiempo agotado
    } catch {
      throw new SupabaseError(0, undefined, "La base de datos no respondió");
    }
  }

  if (!res.ok) {
    let code: string | undefined;
    let message = res.statusText;
    try {
      const err = await res.json();
      code = err.code;
      message = err.message ?? message;
    } catch {
      /* el cuerpo no era JSON */
    }
    // Nunca incluir la clave ni la URL completa en el error visible.
    throw new SupabaseError(res.status, code, message);
  }

  const total = res.headers.get("content-range")?.split("/")[1];
  return {
    rows: (await res.json()) as T,
    total: total && total !== "*" ? Number(total) : null,
  };
}
