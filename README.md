# cyberday-hunter

Escanea tiendas chilenas cada 15 minutos, **descarta los descuentos inflados** y envía a Telegram
**una oferta por mensaje, con foto**, solo cuando el descuento es real.

- Repositorio: <https://github.com/felipe12012/offer_hunter>
- Corre en GitHub Actions (`.github/workflows/fast.yml`). No hay servidores propios.
- Sin LLM ni APIs de pago: todo son reglas sobre datos estructurados.

> Para agregar una tienda nueva, ver [`docs/adding-a-store.md`](docs/adding-a-store.md).
> Para el disparador de 15 minutos, ver [`docs/trigger-setup.md`](docs/trigger-setup.md).

---

## 1. Qué hace

```
disparador (cron-job.org / cron de GitHub)
        │
        ▼
 GitHub Actions: fast.yml   (un escaneo a la vez)
        │
        ├─ 1. Escanea las tiendas en paralelo        sources/*.py
        ├─ 2. Evalúa cada producto                    deal_filter.py + price_history.py
        ├─ 3. Quita duplicados entre tiendas          main_fast.py
        ├─ 4. Envía cada oferta a Telegram            notifier.py
        └─ 5. Guarda el estado en el repo (commit)    data/*.json
```

Cada escaneo lee ~21.000 productos y tarda unos 4 minutos.

### Estado de las tiendas

| Tienda | Estado | Cómo se lee | Notas |
|---|---|---|---|
| **Falabella** | Activa | JSON incrustado (`__NEXT_DATA__`), HTTP simple | Búsquedas y ~60 categorías descubiertas desde el menú |
| **Sodimac** | Activa | Igual que Falabella (misma plataforma) | Su `/category/` redirige al home: usa `/lista/` |
| **Hites** | Activa | HTML paginado de `Search-UpdateGrid`, HTTP simple | Por consultas de texto, 4 en paralelo |
| **Ahumada** | Activa | Igual que Hites (Salesforce Commerce Cloud) | Farmacia: dermocosmética y belleza |
| **Vans, Crocs, Merrell, Salomon, Hush Puppies** | Activas | API de Shopify, HTTP simple | `sources/shopify.py` |
| **Asics, Reebok** | Activas | API de VTEX, HTTP simple | `sources/vtex.py` |
| **Converse, Puma, New Balance, Fila, Skechers, Salcobrand, Cruz Verde** | Activas | Navegador (Playwright) | Requieren `INSTALL_BROWSER=true`; una consulta = un Chromium |
| Paris, Ripley, Tottus | Pausadas | Navegador | Bloquean las IP de GitHub (HTTP 403) |
| Nike | Pausada | Navegador (patchright) | Cloudflare |

Las tiendas pausadas tienen código y pruebas, pero se omiten con `disabled_stores`.
Plan para reactivarlas: [`docs/superpowers/plans/2026-10-02-hard-tier-unblock.md`](docs/superpowers/plans/2026-10-02-hard-tier-unblock.md).

---

## 2. Qué cuenta como oferta real

La mayoría de las tiendas muestran descuentos de 40 a 70 % de forma permanente (precio tachado
inflado). Por eso un descuento anunciado **no basta**. Un producto se envía solo si cumple:

1. **Está en tu lista de intereses**: su categoría o título contiene alguno de los `categories` o
   `keywords` de `config/watchlist.json` (comparación sin distinguir mayúsculas).
2. **Y además cumple una de estas dos**:
   - **Descuento anunciado confirmado**: el descuento es ≥ `min_discount_pct` (30 %) **y** el
     historial muestra que ese producto se vendió realmente cerca del "precio normal" tachado
     (tolerancia 5 %). Si nunca lo vimos a ese precio, se descarta.
   - **Baja real contra el historial**: el precio actual está ≥ `min_real_discount_pct` (15 %)
     por debajo del mínimo histórico que vimos.

Consecuencias que conviene saber:

- El historial se construye con los propios escaneos, así que **un producto visto por primera vez
  ya rebajado no se puede confirmar**. Las ofertas aparecen cuando un producto cambia de precio.
- Modo configurable en `verify_advertised_discount`: `true` (solo verificados), `"label"` (también los
  sin historial, etiquetados *"no verificado"*, enviados en silencio y siempre después de los
  verificados) o `false` (confiar en el porcentaje de la web, con riesgo de precios inflados).
- **El porcentaje que se anuncia en Telegram (y con el que se ordenan y clasifican las alertas) es
  el verificado**: la baja contra nuestro historial, o el descuento de la web solo si el historial
  confirma su "precio normal". Si la web anuncia más (p. ej. -78 %) pero no se puede comprobar, el
  mensaje usa el porcentaje del historial y lo avisa: *"La web anuncia -78 %…, no verificado"*.
- Precio que se registra: el **más bajo entre el precio internet y el de evento**. El precio
  exclusivo de tarjeta (CMR) se ignora, porque no lo paga cualquiera.

---

## 3. Qué requiere el servicio para funcionar

### Secretos y variables en GitHub

Los secretos viven en el **environment `env`** del repositorio (Settings → Environments → `env`):

| Nombre | Tipo | Obligatorio | Para qué |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | secret | Sí | Token del bot (se crea con [@BotFather](https://t.me/BotFather) → `/newbot`) |
| `TELEGRAM_CHAT_ID` | secret | Sí | Chat que recibe las ofertas. Escríbele al bot y abre `https://api.telegram.org/bot<TOKEN>/getUpdates` para ver `"chat":{"id":...}` |
| `TELEGRAM_ALERT_CHAT_ID` | secret | No | Segundo chat/canal/grupo solo para las ofertas grandes (`alerts.alert_chat_min_pct`, 80 %). Si no está, todo va al chat principal. Es un número, negativo para grupos y canales (`-100…`) |
| `TELEGRAM_PUBLIC_CHAT_ID` | secret | No | Canal público que recibe una copia de cada oferta entregada, para que cualquiera la siga sin registrarse en el bot. `@nombre_del_canal` o el id `-100…`; el bot debe ser administrador con permiso de publicar. Un fallo aquí no pierde la oferta |
| `TELEGRAM_ALERT_THREAD_ID` | secret | No | Si el chat de alertas es un supergrupo con temas, el id del tema donde publicar |
| `SUPABASE_URL` | secret | No | `https://qxwxftmlqimfausocwoi.supabase.co`. Con las dos claves de Supabase definidas, cada escaneo también se guarda en la base de datos |
| `SUPABASE_SERVICE_KEY` | secret | No | Clave **secreta** del proyecto (Supabase → Project Settings → API Keys → *Secret key*, `sb_secret_…`). Solo para servidores: nunca en código ni en chats |
| `SCRAPER_PROXY` | secret | No | Proxy `http://user:pass@host:puerto` para las tiendas que usan navegador |
| `INSTALL_BROWSER` | variable | No | `true` instala Chromium (~4 min). Solo hace falta si se reactiva Paris, Ripley o Tottus |

### Disparador

El cron de GitHub (`7,22,37,52 * * * *`) es de mejor esfuerzo y deja pasar muchos ciclos. El
disparador fiable es un job de **cron-job.org** que llama a la API de GitHub cada 15 minutos
(token con permiso *Actions: Read and write* solo sobre este repo). Paso a paso en
[`docs/trigger-setup.md`](docs/trigger-setup.md). El token vence: cron-job.org avisa por correo
cuando falla.

### Lo que hace el workflow por sí solo

- **Un escaneo a la vez** (`concurrency`). Un disparo extra espera en cola.
- **Siempre parte de la punta de `main`**, no del commit del momento del disparo. Si no, un run en
  cola reenviaría ofertas ya entregadas y su `git push` fallaría.
- **Guarda el estado** haciendo commit de `data/*.json` tras cada run.
- **Avisa por Telegram si el pipeline falla** (último paso, `if: failure()`).
- **Prueba de envío**: ejecutar el workflow a mano con `selftest = true` manda 3 productos reales,
  marcados como "PRUEBA", sin tocar el estado.

---

## 4. Configuración (`config/watchlist.json`)

| Clave | Qué hace |
|---|---|
| `categories` | Temas de interés. Se buscan en `categoría + título` del producto |
| `keywords` | Palabras de interés. Se buscan igual **y** se usan como búsquedas en cada tienda |
| `min_discount_pct` | Descuento anunciado mínimo (por defecto 30) |
| `min_real_discount_pct` | Baja mínima contra el mínimo histórico (por defecto 15) |
| `verify_advertised_discount` | `true` (por defecto): solo pasan descuentos que el historial confirma. **`"label"`** (hoy): también pasan los que no tienen historial, pero se envían etiquetados *"no verificado"*, en silencio, después de los verificados y sin alertas fuertes ni canal. `false`: se confía en el % de la web |
| `disabled_stores` | Tiendas que se omiten, p. ej. `["paris","ripley","tottus"]` |
| `alerts.tiers` | Niveles de alerta: `[{"min_pct": 90, "label": "🚨🚨🚨 SUPER OFERTA"}, …]`. El mensaje abre con la etiqueta y el % (el mayor entre el descuento anunciado y el histórico) |
| `alerts.warn_from_pct` | Desde este % se agrega la advertencia "puede ser un error de precio" (80) |
| `alerts.silent_below_pct` | Las ofertas del chat principal con menos descuento que esto llegan **sin sonido** (hoy `80`). `null` = todas suenan. Los mensajes del chat de alertas siempre suenan |
| `alerts.alert_chat_min_pct` | Desde este % la oferta va al chat de alertas, si `TELEGRAM_ALERT_CHAT_ID` está definido (80) |
| `priority.rules` | Intereses prioritarios (zapatillas mujer/hombre/bebé, Kerastase Blond, colchón 1 plaza, tablets, ropa, consolas, videojuegos, comida de gato NYD). Cada regla: `label`, `all` (grupos; debe cumplirse al menos una palabra de **cada** grupo), `none` (palabras que la descartan) y `not_stores`. Se compara con el **título** y el nombre del departamento de la tienda, nunca con la palabra de búsqueda. Una palabra con `=` delante solo coincide como palabra completa |
| `priority.min_discount_pct` | Descuento anunciado mínimo para los prioritarios (20, en vez de 30) |
| `priority.max_per_run`, `priority.daily_cap` | Cupo propio de prioritarios **no verificados**: 30 por run y 800 por día (aparte del cupo genérico de 15 por run y 300 por día). Se reparten entre los intereses |
| `scan.deep_slugs`, `scan.deep_pages` | Categorías de tienda que se leen más a fondo (10 páginas en vez de 4) por ser de interés prioritario |
| `scan.max_search_pages` | Páginas por búsqueda en Falabella/Sodimac (3) |
| `scan.max_category_pages` | Páginas por categoría (4; son 48 productos por página) |
| `scan.max_categories` | Tope de categorías descubiertas por tienda (80) |
| `scan.category_patterns` | `{grupo: [fragmentos de nombre de categoría]}`. El grupo pasa a ser la categoría del producto |
| `scan.max_hites_pages` | Páginas por consulta en Hites (4) |
| `scan.hites_queries` | Consultas extra de Hites además de `keywords` |

`config/watchlist.example.json` es la plantilla.

---

### Intereses prioritarios

Prioridad no es exclusividad: **todas las ofertas siguen llegando**. Un producto que coincide con un
interés de `priority.rules`:

1. **Se busca a propósito** (búsquedas y categorías de tienda dedicadas, leídas más a fondo).
2. **Entra con menos descuento** (20 % anunciado en vez de 30 %).
3. **Sale marcado** con `⭐ Prioridad: Zapatillas mujer` (o el interés que sea).
4. **Se envía primero** dentro de cada run.
5. **Tiene cupo propio** si no está verificado (10 por run, 200 por día), así que no compite con el cupo de
   las no verificadas genéricas, y cada interés recibe su turno.
6. **Suena** si además está verificado; si no, llega en silencio como las demás no verificadas.

Para cambiar los intereses, edita `priority.rules` en `config/watchlist.json`. Para comprobar una regla
sin esperar un escaneo:

```
python -c "import json; from priority import *; r=rules_from(json.load(open('config/watchlist.json'))['priority']); print(first_match(r, 'Zapatilla Mujer Nike Air', '', 'falabella'))"
```

**Cupos de ofertas sin verificar.** Hay un límite diario (300 genéricas y 800 prioritarias) para no inundar el chat,
y se **libera poco a poco durante el día UTC** (con 2 h de ventaja al inicio), en vez de poder gastarse de golpe:
antes se agotaba en las primeras horas y el resto del día no llegaba nada. Las ofertas verificadas no tienen cupo.

## 5. Telegram

- **Un mensaje por oferta**: foto, título, tienda, precio actual, precio tachado, % y motivo, y un
  botón **🛒 Ir a la oferta** debajo del mensaje (si la URL no sirve para un botón, el enlace va en el texto).
- **Chat de alertas**: con `TELEGRAM_ALERT_CHAT_ID` configurado, las ofertas de 80 % o más van
  ahí (siempre con sonido) y el resto al chat principal (en silencio). Si el chat de alertas
  falla, la oferta se envía al principal: no se pierde.
- **Suscriptores del bot**: quien escribe `/start` al bot en un chat privado queda en la tabla
  `offer_subscribers` de Supabase (migración `0006`) y recibe lo mejor de cada run: ofertas
  verificadas, de intereses prioritarios o de 80 % o más (máx. 15 por persona y run, para no
  saturar). `/stop` o bloquear el bot los da de baja. No hay servidor: al inicio de cada run el
  pipeline lee los mensajes pendientes del bot (`getUpdates`) y responde, así que la bienvenida
  llega en un máximo de ~15 min. Requiere `SUPABASE_URL`/`SUPABASE_SERVICE_KEY`. Si el bot tuviera
  un webhook configurado, `getUpdates` no funciona: no lo configures.
- **Canal público** (`TELEGRAM_PUBLIC_CHAT_ID`): recibe una copia de cada oferta, para seguirlas sin bot.
- Si Telegram no puede bajar la foto desde la URL, el programa la descarga y la sube; si tampoco, el
  mensaje sale sin foto. **Nunca se pierde una oferta por una imagen.**
- Máximo **25 mensajes por run** (1,1 s entre mensajes y un reintento si Telegram responde 429).
  Lo que sobra queda pendiente y sale en el run siguiente, ordenado por mejor descuento.
- Un mismo producto de marketplace que aparece en dos tiendas (Falabella y Sodimac comparten
  catálogo) se envía **una sola vez**.
- Solo se marca como "visto" lo que Telegram **realmente recibió**; si el envío falla, se reintenta
  en el siguiente run. Si no se entrega ninguna oferta, el run termina con error y se avisa.

---

## 6. Estado guardado (`data/`)

| Archivo | Contenido |
|---|---|
| `price_history.json` | `{id: [{date, price}, …]}` con máximo 30 puntos por producto. Solo se agrega un punto cuando el precio cambia. ~1,3 MB |
| `seen_items.json` | Claves `id:precio` de las ofertas **ya entregadas**, para no repetirlas. Un cambio de precio genera una clave nueva y puede volver a avisar |

Los commits de estos archivos los hace el propio workflow (`chore: update seen items and price history`).

---

### Base de datos (Supabase)

Además de los JSON, cada escaneo se copia a Postgres en el proyecto `job-hunter-agent` de Supabase
(tablas con prefijo `offer_` en `public`; definidas en `supabase/migrations/0001_offer_hunter.sql`).
Los JSON siguen siendo la fuente de verdad para decidir qué se envía; si Supabase falla, el run
continúa y solo lo registra en el log (`Supabase sync failed…`).

| Tabla | Contenido |
|---|---|
| `offer_products` | Un registro por producto: tienda, título, URL, imagen, precio actual y precio tachado |
| `offer_price_points` | Historial de precios: un punto cada vez que cambia el precio o el tachado (con `list_price`) |
| `offer_sent` | Cada oferta entregada, con porcentajes anunciado/verificado, motivos y fecha. Único por `(producto, precio)` |
| `offer_scan_runs` | Una fila por escaneo: productos leídos, nuevos, calificados, entregados, por tienda y duración |

Seguridad: RLS activado, sin políticas y sin permisos para `anon` ni `authenticated`; solo la clave
secreta (rol `service_role`) puede leer o escribir.

**Activación (una vez):**
1. Crear los secretos `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` en el environment `env`.
2. Actions → *Fast Tier Deal Scan* → *Run workflow* → marcar **migrate** → ejecutar. Importa el
   historial y las ofertas ya enviadas de los JSON y verifica los conteos. Se puede repetir sin duplicar.
3. Los runs siguientes escriben solos. En el log aparece `Supabase: N products received, …`.

Consultas útiles (SQL editor de Supabase):

```sql
-- Ofertas enviadas hoy
select sent_at, store, title, verified_pct from offer_sent order by sent_at desc limit 50;
-- Evolución de precio de un producto
select observed_at, price, list_price from offer_price_points where product_id = 'falabella:126306018' order by observed_at;
-- Salud de los últimos escaneos
select started_at, scanned, qualifying, delivered, per_store, duration_seconds from offer_scan_runs order by started_at desc limit 20;
```

---

## 7. Mapa del código

| Archivo | Responsabilidad |
|---|---|
| `main_fast.py` | Orquestador: escaneo en paralelo → evaluación → deduplicación → envío → estado. También `--selftest` |
| `models.py` | `Deal` (producto) y `ScoredDeal` (oferta con motivos) |
| `deal_filter.py` | Reglas de la sección 2 |
| `price_history.py` | Lectura/escritura del historial de precios |
| `dedup.py` | Claves `id:precio` de ofertas ya entregadas |
| `supabase_sync.py` | Cliente de Supabase: copia productos, puntos de precio, ofertas enviadas y estadísticas de cada run |
| `migrate_to_supabase.py` | Importa una vez los JSON a Supabase (acción *migrate* del workflow) |
| `notifier.py` | Formato y envío a Telegram (foto, reintentos, respaldo) |
| `sources/nextdata.py` | Lector común del JSON incrustado (Falabella y Sodimac): paginación, descubrimiento de categorías |
| `sources/falabella.py`, `sodimac.py` | Configuración de cada tienda sobre `nextdata` |
| `sources/hites.py`, `ahumada.py` | Tiendas SFCC por HTML paginado; usan `sources/sfcc.py` (consultas en paralelo; una búsqueda sin resultados no es un error) |
| `sources/shopify.py`, `vtex.py` | Lectores comunes de tiendas Shopify y VTEX |
| `sources/health.py` | Los scrapers reportan aquí fallos y consultas vacías; alimenta el reporte por tienda |
| `reports.py` | Estado de cada tienda en cada run (tabla de log, resumen de GitHub, JSON para Supabase, caída/recuperación) |
| `watchdog.py` | Vigilancia externa (workflow `watchdog.yml`): avisa si no hay escaneos recientes o una tienda cae a 0 |
| `sources/paris.py`, `ripley.py`, `tottus.py` | Tiendas con navegador (pausadas) |
| `sources/images.py` | Elige la foto real del producto y hace scroll para cargar imágenes diferidas |

---

## 8. Uso local

```
pip install -r requirements.txt
python -m pytest -q          # ~330 pruebas, sin red
python main_fast.py          # escaneo real
python main_fast.py --selftest
```

**Ojo:** `python main_fast.py` **modifica `data/*.json`** y, si hay `TELEGRAM_BOT_TOKEN` y
`TELEGRAM_CHAT_ID` en el entorno o en un `.env`, **envía mensajes reales**. Para probar sin enviar,
no definas esas variables. No hagas commit de `.env` (está en `.gitignore`).

---

## 9. Diagnóstico: qué está pasando

Cada escaneo deja cuatro rastros, de más rápido a más detallado:

1. **Resumen del run en GitHub** (pestaña *Summary* del run en Actions): totales, cupo de alertas,
   estado de Supabase y una **tabla con el estado de cada tienda** y sus primeros errores.
2. **Log del run**, con una tabla por tienda y los totales:
   ```
   Store report:
     falabella    ok         14926 deals   41.2s
     hites        partial     3922 deals   63.0s  -> 1 consulta(s) con error
     ahumada      FAILED         0 deals    5.0s  -> All Farmacias Ahumada queries failed
   Scanned 34450 deals, 32631 new, 9222 qualifying (9222 unverified), 0 ...
   Telegram: nothing sent: 9222 unverified candidates are waiting but the daily unverified quota is spent (60/60) and there are no verified offers
   ```
3. **Supabase**, tabla `offer_scan_runs`: columnas `store_status` (estado, productos, segundos y errores
   por tienda), `errors` y `quota` de cada escaneo.
   ```sql
   select started_at, store_status->'hites' as hites, quota from offer_scan_runs order by started_at desc limit 10;
   ```
4. **Telegram**:
   - 🔴 *"tienda X: sin datos en 2 escaneos seguidos"* con el motivo, una sola vez; y 🟢 *"recuperada"*.
   - Si el pipeline falla, la alerta trae el **motivo** (`Motivo: …`), no solo el enlace.
   - El *watchdog* avisa si no hay escaneos en 40 min o si una tienda cae a 0.

**Estados de una tienda:** `ok` · `partial` (entregó productos pero algunas consultas fallaron) ·
`failed` (error, o 0 productos con errores) · `timeout` (superó 7 min) · `empty` (0 productos y ningún
error: sospechoso, suele ser un bloqueo o un cambio de la web) · `disabled`.

| Síntoma | Causa probable |
|---|---|
| Tienda en `empty` | Todas sus consultas devolvieron 0 productos: bloqueo de IP o cambio de estructura |
| Tienda en `failed` con el mismo mensaje en cada run | Bloqueada o cambió su HTML. Reproducir con `python -c "from sources import <tienda>; …"` desde tu PC |
| Muchas consultas "empty" en una tienda `ok` | Normal: una farmacia no vende "notebook". No se cuenta como error |
| `Telegram: nothing sent … quota` | El cupo diario de no verificadas se agotó (300/día, se reinicia a medianoche UTC) y no hay verificadas. No es un fallo |
| `delivered 0/N` y el run falla | Token o chat de Telegram incorrectos, o el bot nunca recibió un mensaje tuyo |
| `qualifying` siempre 0 | Normal los primeros días: el historial aún no confirma descuentos |
| No hay runs cada 15 minutos | El cron de GitHub se salta ciclos; revisar el job de cron-job.org (ver `docs/trigger-setup.md`) |
| Error en "Commit updated data files" | Conflicto de `git`. No debería ocurrir con el checkout de la punta de `main`; revisar si alguien empujó a `data/` a mano |
| El *watchdog* sale en rojo | No pudo leer `offer_scan_runs` de Supabase (clave o red); el mensaje está en su log |

---

## 10. Documentos de diseño

- Especificación original: [`docs/superpowers/specs/2026-10-01-cyberday-hunter-design.md`](docs/superpowers/specs/2026-10-01-cyberday-hunter-design.md)
- Plan del núcleo: [`docs/superpowers/plans/2026-10-01-cyberday-hunter-core.md`](docs/superpowers/plans/2026-10-01-cyberday-hunter-core.md)
- Plan pausado de tiendas bloqueadas: [`docs/superpowers/plans/2026-10-02-hard-tier-unblock.md`](docs/superpowers/plans/2026-10-02-hard-tier-unblock.md)
