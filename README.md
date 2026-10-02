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
| **Hites** | Activa | HTML paginado de `Search-UpdateGrid`, HTTP simple | Solo por consultas de texto |
| Paris | Pausada | Navegador (Playwright) | Bloquea las IP de GitHub (HTTP 403) |
| Ripley | Pausada | Navegador (Playwright) | Bloquea las IP de GitHub |
| Tottus | Pausada | Navegador (Playwright) | Cloudflare bloquea las IP de GitHub |

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
- Si solo quieres filtrar por porcentaje (con riesgo de precios inflados), pon
  `"verify_advertised_discount": false` en la watchlist.
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
| `verify_advertised_discount` | `false` desactiva la confirmación por historial (por defecto `true`) |
| `disabled_stores` | Tiendas que se omiten, p. ej. `["paris","ripley","tottus"]` |
| `alerts.tiers` | Niveles de alerta: `[{"min_pct": 90, "label": "🚨🚨🚨 SUPER OFERTA"}, …]`. El mensaje abre con la etiqueta y el % (el mayor entre el descuento anunciado y el histórico) |
| `alerts.warn_from_pct` | Desde este % se agrega la advertencia "puede ser un error de precio" (80) |
| `alerts.silent_below_pct` | Si se define (ej. `60`), las ofertas con menos descuento llegan **sin sonido** y solo las grandes suenan. `null` = todas suenan |
| `scan.max_search_pages` | Páginas por búsqueda en Falabella/Sodimac (3) |
| `scan.max_category_pages` | Páginas por categoría (4; son 48 productos por página) |
| `scan.max_categories` | Tope de categorías descubiertas por tienda (80) |
| `scan.category_patterns` | `{grupo: [fragmentos de nombre de categoría]}`. El grupo pasa a ser la categoría del producto |
| `scan.max_hites_pages` | Páginas por consulta en Hites (4) |
| `scan.hites_queries` | Consultas extra de Hites además de `keywords` |

`config/watchlist.example.json` es la plantilla.

---

## 5. Telegram

- **Un mensaje por oferta**: foto, título, tienda, precio actual, precio tachado, % y motivo, enlace.
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

## 7. Mapa del código

| Archivo | Responsabilidad |
|---|---|
| `main_fast.py` | Orquestador: escaneo en paralelo → evaluación → deduplicación → envío → estado. También `--selftest` |
| `models.py` | `Deal` (producto) y `ScoredDeal` (oferta con motivos) |
| `deal_filter.py` | Reglas de la sección 2 |
| `price_history.py` | Lectura/escritura del historial de precios |
| `dedup.py` | Claves `id:precio` de ofertas ya entregadas |
| `notifier.py` | Formato y envío a Telegram (foto, reintentos, respaldo) |
| `sources/nextdata.py` | Lector común del JSON incrustado (Falabella y Sodimac): paginación, descubrimiento de categorías |
| `sources/falabella.py`, `sodimac.py` | Configuración de cada tienda sobre `nextdata` |
| `sources/hites.py` | Hites por HTML paginado |
| `sources/paris.py`, `ripley.py`, `tottus.py` | Tiendas con navegador (pausadas) |
| `sources/images.py` | Elige la foto real del producto y hace scroll para cargar imágenes diferidas |

---

## 8. Uso local

```
pip install -r requirements.txt
python -m pytest -q          # 108 pruebas, sin red
python main_fast.py          # escaneo real
python main_fast.py --selftest
```

**Ojo:** `python main_fast.py` **modifica `data/*.json`** y, si hay `TELEGRAM_BOT_TOKEN` y
`TELEGRAM_CHAT_ID` en el entorno o en un `.env`, **envía mensajes reales**. Para probar sin enviar,
no definas esas variables. No hagas commit de `.env` (está en `.gitignore`).

---

## 9. Diagnóstico rápido

Cada run imprime en el log de Actions:

```
Deals per store: sodimac=8267, falabella=10575, hites=2166
Scanned 21008 deals, 20562 new, 38 qualifying, 8894 advertised discounts discarded as unverified
Telegram: delivered 25/38 individual messages (13 pending retry next run)
```

| Síntoma | Causa probable |
|---|---|
| Una tienda con `=0` en `Deals per store` | La tienda bloquea la IP o cambió su estructura. Ver `… scraper failed` / `… scan of … failed` |
| `qualifying` siempre 0 | Normal los primeros días: el historial aún no confirma descuentos. Se llena cuando los precios cambian |
| `delivered 0/N` y el run falla | Token o chat de Telegram incorrectos, o el bot nunca recibió un mensaje tuyo |
| No hay runs cada 15 minutos | El cron de GitHub se salta ciclos; revisar el job de cron-job.org (error 401/403/404/422, ver `docs/trigger-setup.md`) |
| Error en el paso "Commit updated data files" | Conflicto de `git` con otro commit. No debería ocurrir con el checkout de la punta de `main`; si pasa, revisar si alguien empujó cambios a `data/` a mano |

---

## 10. Documentos de diseño

- Especificación original: [`docs/superpowers/specs/2026-10-01-cyberday-hunter-design.md`](docs/superpowers/specs/2026-10-01-cyberday-hunter-design.md)
- Plan del núcleo: [`docs/superpowers/plans/2026-10-01-cyberday-hunter-core.md`](docs/superpowers/plans/2026-10-01-cyberday-hunter-core.md)
- Plan pausado de tiendas bloqueadas: [`docs/superpowers/plans/2026-10-02-hard-tier-unblock.md`](docs/superpowers/plans/2026-10-02-hard-tier-unblock.md)
