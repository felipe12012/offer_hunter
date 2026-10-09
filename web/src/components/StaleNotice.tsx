import { getReference } from "@/lib/data";
import { agoFrom } from "@/lib/format";
import { STALE_NOTICE_MINUTES, staleMinutes } from "@/lib/live";

/** Aviso cuando el último escaneo que funcionó es viejo: se siguen mostrando los últimos productos conocidos, pero los
 *  precios pueden haber cambiado. Sin aviso mientras el escaneo está al día. */
export async function StaleNotice() {
  const reference = await getReference();
  if (staleMinutes(reference) < STALE_NOTICE_MINUTES) return null;
  return (
    <p role="status" className="border-b border-ink bg-claim-bg px-4 py-2 text-center text-sm font-semibold">
      Estamos reconectando con las tiendas: estos datos son de {agoFrom(new Date(reference).toISOString())}. Los precios
      pueden haber cambiado, confírmalos en la tienda.
    </p>
  );
}
