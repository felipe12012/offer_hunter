// Responde 200 y la hora. No toca la base de datos ni expone datos.
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ ok: true, at: new Date().toISOString() }, { headers: { "Cache-Control": "no-store" } });
}
