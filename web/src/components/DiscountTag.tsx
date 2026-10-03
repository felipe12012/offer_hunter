import { dealView } from "@/lib/tiers";

/** La etiqueta de precio: el elemento visual principal del sitio. */
export function DiscountTag({
  row,
  size = "md",
}: {
  row: { verified_pct: number; web_discount_pct: number };
  size?: "md" | "lg";
}) {
  const view = dealView(row);
  if (view.pct <= 0) return null;

  const scale = size === "lg" ? { fontSize: "1.9rem" } : undefined;

  if (view.claimOnly) {
    return (
      <span className="tag tag--claim" style={scale} title="Descuento que anuncia la tienda; aún sin historial que lo respalde">
        <small>anuncia</small>
        <span aria-label={`descuento anunciado de ${view.pct} por ciento`}>-{view.pct}%</span>
      </span>
    );
  }

  const tone = view.tier ? `tag--${view.tier.key}` : "tag--ok";
  return (
    <span className={`tag ${tone}`} style={scale} title={view.tier?.label}>
      <span aria-label={`descuento verificado de ${view.pct} por ciento`}>-{view.pct}%</span>
    </span>
  );
}

export function VerifiedStamp({ verified }: { verified: boolean }) {
  return verified ? (
    <span className="stamp" title="El descuento está respaldado por el historial de precios que registramos">
      <span aria-hidden="true">✓</span> Verificada
    </span>
  ) : (
    <span className="stamp stamp--no" title="La tienda anuncia el descuento, pero aún no hay historial que lo respalde">
      Sin verificar
    </span>
  );
}
