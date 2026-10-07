/** Enlace al bot para seguir el precio de un producto: t.me/<bot>?start=seguir_<tienda>_<sku>.
 *  El payload de Telegram admite solo letras, números, "_" y "-" (hasta 64): un sku con otros caracteres no se puede seguir. */
export function followLink(store: string, sku: string, bot: string | undefined): string | null {
  const username = (bot ?? "").replace(/^@/, "").trim();
  if (!/^[A-Za-z0-9_]{4,32}$/.test(username)) return null;
  if (!/^[a-z0-9]+$/.test(store) || !/^[A-Za-z0-9_-]{1,40}$/.test(sku)) return null;
  return `https://t.me/${username}?start=seguir_${store}_${sku}`;
}
