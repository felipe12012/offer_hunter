# ¿Sigue a la venta? Qué sabemos y qué falta

## Lo que NO funciona: deducirlo de que "dejó de aparecer"

Una primera versión (commit `d836664`, revertida en `0012`) daba una oferta por terminada si llevaba **1 hora sin
verse** (150 minutos para las de menos de 50 %). Se equivocó en **2 de cada 4** casos revisados a mano.

Motivo: no leemos el catálogo completo sino **las primeras páginas de cada listado**, y el orden cambia entre un
escaneo y otro. Un producto con stock sale del listado y vuelve a entrar. En Falabella, de los productos con 50 % o
más que se vieron en el último día, ~5.700 se veían en la última hora, ~800 entre 1 y 3 horas y ~2.200 entre 3 y
24 horas: mucho movimiento que no es "agotado". Por eso la web solo oculta un producto (y la ficha solo lo marca como
terminado, en blanco y negro) tras **6 horas** sin verlo (`web/src/lib/live.ts`).

## Lo que haría falta: comprobarlo en la tienda

Un verificador que abra cada oferta anunciada (o con 50 % o más que lleve un rato sin aparecer) y compruebe precio y
stock. Hallazgos al intentarlo (2026-10-05):

| Tienda | Ficha del producto | Búsqueda por código |
|---|---|---|
| Sodimac | responde 200, 1,2 MB; el stock está en `props.pageProps.productData` (campo exacto por confirmar) | no probada |
| Falabella | **403 de Cloudflare** con HTTP plano: solo se puede leer con navegador | no probada desde el servidor (mi IP quedó bloqueada tras ~1.000 peticiones seguidas) |

Ideas, de más a menos barata:

1. **Búsqueda por código en Falabella** (`search?Ntt=<productId>`): los listados no tienen Cloudflare. Si devuelve
   el producto está a la venta, con su precio. Probar desde el servidor de GitHub con pocas peticiones.
2. **Ficha de Sodimac** por HTTP.
3. Navegador (patchright) para las fichas de Falabella: lento (segundos por producto) y consume mucha CPU.

Con la comprobación, el resultado se usaría así: si está a la venta se refresca `last_seen_at` (y el precio, si cambió);
si no está, se retrocede `last_seen_at` unas horas para que la web lo marque como terminado de inmediato. Si vuelve a
aparecer en un escaneo, `offer_sync_scan` lo revive solo.
