// Construcción de cabeceras para la Data API de Supabase (PostgREST).
// Separado de supabase.ts para poder probarlo sin la clave ni "server-only".
//
// Reglas (ver docs/superpowers/plans/2026-10-03-offers-web.md, 5B.3):
//   - `apikey` siempre.
//   - `Authorization: Bearer` SOLO con claves JWT antiguas (empiezan por "eyJ");
//     las claves nuevas sb_secret_ no son JWT y romperían si se enviaran así.

export function buildHeaders(serviceKey: string, extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { apikey: serviceKey, Accept: "application/json", ...extra };
  if (serviceKey.startsWith("eyJ")) {
    headers.Authorization = `Bearer ${serviceKey}`;
  }
  return headers;
}
