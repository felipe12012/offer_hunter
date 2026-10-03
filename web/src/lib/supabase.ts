// web/src/lib/supabase.ts — SOLO SERVIDOR.
// Único módulo que conoce la clave secreta. Las consultas son de solo lectura
// (GET y el POST a la función offer_stats); nunca se expone al cliente.
import "server-only";

import { buildHeaders } from "./headers";

const URL = process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_KEY;

if (!URL || !KEY) {
  throw new Error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (server environment only)");
}

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

export async function rest<T>(
  path: string,
  opts: { revalidate?: number; count?: boolean; method?: "GET" | "POST"; body?: unknown } = {},
): Promise<{ rows: T; total: number | null }> {
  const res = await fetch(`${URL}/rest/v1/${path}`, {
    method: opts.method ?? "GET",
    headers: buildHeaders(KEY!, {
      ...(opts.count ? { Prefer: "count=exact" } : {}),
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    }),
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: AbortSignal.timeout(10_000),
    next: { revalidate: opts.revalidate ?? 120 },
  });

  if (!res.ok) {
    let code: string | undefined;
    let message = res.statusText;
    try {
      const err = await res.json();
      code = err.code;
      message = err.message ?? message;
    } catch {
      /* body was not JSON */
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
