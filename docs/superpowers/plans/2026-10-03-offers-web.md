# Web de ofertas (Next.js + Supabase + Vercel) — plan de ejecución

Estado (3-oct-2026): **construido y verificado en local; falta desplegar en Vercel.**
Hecho: fases 1 a 6 (migraciones 0002, 0004, 0005 aplicadas; refresco en el pipeline; web en `web/` con
filtros, ficha, método, 84 pruebas, lint, build y comprobación de secretos). Pendiente: crear la clave
secreta propia de la web, cargarla en Vercel y desplegar (fase 7).
Desviaciones del plan: el gráfico es un SVG propio (sin Recharts); la búsqueda ignora tildes
(`title_norm`, migración 0005); `dup_rank` evita mostrar el mismo producto de Falabella y Sodimac dos veces.

Meta: una web pública, rápida y atractiva que lista las ofertas que ya recolecta el servicio
(`offer_hunter`), con filtros, orden y ficha de producto con el historial de precios, mostrando
**qué descuentos son reales y cuáles no están verificados**.

---

## 0. Cómo ejecutar este plan

1. Lee, en este orden: `README.md`, `docs/adding-a-store.md`, este archivo, (en especial la **sección 5B**, Supabase),
   `supabase/migrations/0001_offer_hunter.sql` y `0002_offer_feed.sql`.
2. Trabaja por fases (sección 7). Cada fase tiene una **definición de terminado**; no pases a la
   siguiente sin cumplirla.
3. Reglas del repositorio (importantes, el repo se comparte):
   - Hay **otras sesiones de agentes editando el mismo repo** (tiendas nuevas, notificador). Haz
     `git pull --rebase origin main` antes de cada commit y **haz `git add` solo de tus archivos**
     (nunca `git add -A`).
   - Un bot hace commit de `data/*.json` cada ~15 minutos en `main`. Es normal.
   - **No toques** `main_fast.py`, `notifier.py`, `deal_filter.py` ni `sources/` salvo lo que la
     fase 2 indica expresamente.
   - Nunca escribas claves en el repositorio, en commits, en logs ni en el chat.
4. Si algo de este plan contradice lo que ves en el código o en la base, **detente y pregunta**.

Prompt sugerido para opencode:

> Ejecuta el plan `docs/superpowers/plans/2026-10-03-offers-web.md` del repositorio, fase por fase.
> Respeta la sección 0 (reglas del repo) y la sección 6 (seguridad). Al terminar cada fase,
> muestra la evidencia de su definición de terminado y espera mi confirmación antes de la fase 7
> (despliegue).

---

## 1. Qué existe hoy (hechos verificados el 2026-10-03)

### El servicio
- Repo: `felipe12012/offer_hunter` (rama `main`). Python 3.12. Corre en GitHub Actions cada ~15 min.
- Escanea 14 tiendas (Falabella, Sodimac, Hites y marcas de zapatillas). ~32.000 productos vigentes.
- Envía ofertas a Telegram. Ver `README.md` para el detalle.
- **Qué es "verificado"** (`deal_filter.py`): el descuento anunciado por la web solo se cree si
  nuestro historial muestra que el producto se vendió antes a ≥95 % de su "precio normal"
  tachado (`web_confirmed`), o si el precio actual bajó ≥15 % bajo el mínimo anterior que vimos
  (`history_drop_pct`). El resto es "no verificado".

### La base de datos (Supabase)
- Proyecto `job-hunter-agent`, ref `qxwxftmlqimfausocwoi`, URL `https://qxwxftmlqimfausocwoi.supabase.co`.
  **Comparte proyecto con otra app**: no toques `public.listings` ni nada que no empiece con `offer_`.
- Tablas (RLS activado, sin políticas, sin permisos para `anon`/`authenticated`; solo `service_role`):

| Tabla | Columnas clave |
|---|---|
| `offer_products` | `id` (`"falabella:80726514"`), `store`, `title`, `url`, `image_url`, `category`, `price`, `list_price`, `discount_pct`, `first_seen_at`, `updated_at` |
| `offer_price_points` | `product_id`, `observed_at`, `price`, `list_price`, `source` (`scan`/`migrated`). Un punto por cada cambio de precio o de precio tachado |
| `offer_sent` | ofertas ya enviadas a Telegram: `product_id`, `price`, `sent_at`, `verified_pct`, `advertised_pct`, `reasons` |
| `offer_scan_runs` | una fila por escaneo: `started_at`, `scanned`, `qualifying`, `delivered`, `per_store`, `duration_seconds` |

- `category` mezcla grupos (`tecnologia`, `muebles`, `zapatillas`, `ropa`, `belleza`, `herramientas`,
  `mascotas`) con palabras de búsqueda (`notebook`, `nike`, `polera`…). La migración 0002 las
  agrupa en `category_group`.
- Hay ~12.000 productos **importados del historial JSON sin título ni imagen** (nunca vueltos a
  escanear). La web **no debe mostrarlos**; la migración 0002 los excluye.
- Cifras de referencia hoy: 32.387 productos vigentes, **245 verificados (≥10 %)**, ~12.000 que
  anuncian ≥30 %. Con el historial de un solo día **la mayoría aparecerá como "no verificada"**:
  es correcto, no es un fallo. La web debe explicarlo bien (sección 5.6).

### Lo que no existe (hay que construir)
- Columna de "visto por última vez" (sin ella, productos retirados de la tienda se mostrarían con
  precio viejo).
- La vista `offer_feed` con las señales de verificación precalculadas.
- La web.

---

## 2. Decisiones ya tomadas (cámbialas solo con confirmación del usuario)

| Tema | Decisión | Por qué |
|---|---|---|
| Framework | **Next.js (App Router) + TypeScript** | Despliegue nativo en Vercel, render en servidor, caché por revalidación |
| Estilos | **Tailwind CSS**; componentes propios simples (sin librería pesada) | Rapidez y control del diseño |
| Gráfico | **Recharts** (solo en la ficha de producto, cargado en el cliente) | Historial de precios |
| Idioma | Español de Chile (`es-CL`), CLP con `Intl.NumberFormat('es-CL')` | Público objetivo |
| Datos | **Solo servidor** (Server Components / route handlers), clave secreta de Supabase en variable de entorno de Vercel **sin** prefijo `NEXT_PUBLIC_` | El navegador nunca habla con Supabase |
| Lectura | Vista materializada `offer_feed` + función `offer_stats()` + tabla `offer_price_points` | Respuesta en milisegundos |
| Caché | Revalidar cada 120 s (ISR / `unstable_cache` / `fetch` con `next.revalidate`) | Los datos cambian cada 15 min |
| Ubicación | Carpeta **`web/`** dentro del repo existente | Un solo repo; el despliegue usa `web/` como raíz |
| Imágenes | `<img>` normal con `loading="lazy"` y `referrerPolicy="no-referrer"`, **no** `next/image` | Cada tienda sirve imágenes desde un dominio distinto; el optimizador de Vercel tiene cupo en el plan gratis y algunas CDN bloquean si hay `Referer` |
| Acceso a datos | Un único módulo `web/src/lib/data.ts` | Un solo lugar que usa la clave secreta |

### Decisiones pendientes del usuario (propón el valor por defecto y avisa)
- **Nombre y dominio del sitio.** Por defecto: nombre provisional "CazaOfertas", sin dominio propio
  (URL `*.vercel.app`).
- **¿Indexable por Google?** Por defecto: **`noindex`** hasta que el usuario lo apruebe.
- **Enlaces a tiendas:** sin afiliados (enlace directo). No agregar parámetros de seguimiento.

---

## 3. Fase 1 — Base de datos (migraciones)

Quien aplique la migración necesita acceso de escritura a Supabase (el agente que escribió este
plan puede hacerlo con la integración MCP de Supabase; si no hay acceso, **pide al usuario que lo
aplique o que te dé acceso**, no pongas claves en el repo).

### 1.1 Aplicar `supabase/migrations/0002_offer_feed.sql`
Ya está escrita y **validada** en una transacción deshecha (resultado: 32.387 filas, 245
verificados, 231 en `otros`). Hace cuatro cosas:
1. Agrega `offer_products.last_seen_at` (los importados sin título quedan en `NULL`).
2. Reemplaza `offer_sync_scan` para que además actualice `last_seen_at` (como máximo una vez por
   hora por producto, para no generar escrituras de más). Devuelve una clave extra `touched`; el
   cliente Python ignora claves que no conoce.
3. Crea la vista materializada `offer_feed` con índices, **sin acceso para `anon`/`authenticated`**.
4. Crea `offer_refresh_feed()` (`SECURITY DEFINER` deliberado, ver comentario en el SQL).

Después de aplicar:
- Ejecuta `select public.offer_refresh_feed();` con la clave de servicio o desde el SQL editor, y
  `select count(*), count(*) filter (where verified_pct >= 10) from public.offer_feed;`.
- Revisa los avisos de seguridad de Supabase (`get_advisors`, tipo `security`). Esperado: avisos
  informativos de "RLS sin políticas" en las tablas `offer_*`, y un aviso sobre la vista
  materializada accesible por API **solo si** alguien le dio permisos a `anon`; no debe haberlos.

### 1.2 Crear `supabase/migrations/0004_offer_stats.sql`
Función de estadísticas para la portada. **El SQL de abajo NO está probado**: valídalo dentro de
`begin; … rollback;` antes de aplicarlo.

```sql
create or replace function public.offer_stats()
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  with live as (
    select * from public.offer_feed where last_seen_at > now() - interval '6 hours'
  )
  select jsonb_build_object(
    'total',     (select count(*) from live),
    'verified',  (select count(*) from live where verified_pct >= 10),
    'super',     (select count(*) from live where verified_pct >= 80),
    'last_seen', (select max(last_seen_at) from live),
    'stores',    coalesce((select jsonb_object_agg(store, n) from
                    (select store, count(*) n from live group by store) s), '{}'::jsonb),
    'groups',    coalesce((select jsonb_object_agg(category_group, n) from
                    (select category_group, count(*) n from live group by category_group) g), '{}'::jsonb)
  );
$$;
revoke execute on function public.offer_stats() from public, anon, authenticated;
grant  execute on function public.offer_stats() to service_role;
```

**Definición de terminado (fase 1):** las dos migraciones aplicadas; `offer_feed` con >30.000
filas; `offer_stats()` devuelve el JSON esperado; los avisos de seguridad no empeoraron respecto
a antes de empezar.

---

## 4. Fase 2 — Refrescar la vista en cada escaneo (Python)

Única fase que toca código del servicio. Cambios mínimos:

1. En `supabase_sync.py`, agregar a `SupabaseSync`:
   ```python
   def refresh_feed(self) -> None:
       self._post("rpc/offer_refresh_feed", {})
   ```
2. En `main_fast.mirror_to_supabase`, llamar `mirror.refresh_feed()` **después** de `record_run(...)`
   y dentro del mismo `try`. Si falla, solo se registra (ya está cubierto por el `except`): un
   fallo del refresco nunca debe tumbar el run ni detener las alertas.
3. Pruebas (`tests/test_supabase_sync.py`, `tests/test_workflow.py`): `refresh_feed` hace
   `POST /rest/v1/rpc/offer_refresh_feed` con cuerpo `{}`; `mirror_to_supabase` lo invoca una
   vez; si falla, el run termina en 0.
4. `python -m pytest -q` debe quedar en verde (hoy 240 pruebas).

**Definición de terminado (fase 2):** pruebas en verde; commit subido; tras el siguiente run de
Actions, el log muestra la línea `Supabase: …` y `offer_feed.last_seen_at` máximo avanza (verificar
con `select max(last_seen_at) from public.offer_feed;` antes y después).

---

## 5. Fase 3 a 6 — La web

### 5.1 Estructura de `web/`

```
web/
├─ package.json            (Node 20+; scripts: dev, build, start, lint, test)
├─ next.config.ts
├─ tsconfig.json
├─ tailwind config / postcss
├─ .env.example            (nombres de variables, sin valores)
├─ src/
│  ├─ app/
│  │  ├─ layout.tsx        (fuente, metadatos, <meta name="robots" content="noindex"> por defecto)
│  │  ├─ page.tsx          (portada: resumen + súper ofertas + listado con filtros)
│  │  ├─ oferta/[store]/[sku]/page.tsx   (ficha del producto)
│  │  ├─ como-verificamos/page.tsx       (explicación del método)
│  │  ├─ not-found.tsx · error.tsx · loading.tsx
│  │  └─ api/health/route.ts             (responde 200 y la hora; sin datos)
│  ├─ lib/
│  │  ├─ data.ts           (ÚNICO módulo que usa la clave secreta; solo SELECT)
│  │  ├─ filters.ts        (parseo y validación de parámetros de URL)
│  │  ├─ format.ts         (CLP, porcentajes, "hace X min")
│  │  └─ tiers.ts          (niveles de descuento y colores)
│  └─ components/
│     ├─ DealCard.tsx · DealGrid.tsx · FilterBar.tsx · FilterDrawer.tsx (móvil)
│     ├─ StatsStrip.tsx · SuperDeals.tsx · Pagination.tsx
│     ├─ PriceChart.tsx ("use client", Recharts) · VerifiedBadge.tsx · StoreBadge.tsx
│     └─ EmptyState.tsx · Footer.tsx
└─ tests/                  (Vitest para lib/*; humo con Playwright opcional)
```

### 5.2 Variables de entorno (solo servidor)

| Variable | Valor | Notas |
|---|---|---|
| `SUPABASE_URL` | `https://qxwxftmlqimfausocwoi.supabase.co` | |
| `SUPABASE_SERVICE_KEY` | clave secreta del proyecto (`sb_secret_…`) | **Sensible. Nunca `NEXT_PUBLIC_`.** Cabecera `apikey`; solo agregar `Authorization: Bearer` si la clave empieza con `eyJ` (clave JWT antigua) |

Hay que crear `.env.example` con esos nombres y **no** `.env.local` en el repo (comprobar `.gitignore`).

> La referencia completa de la conexión (cabeceras, objetos, peticiones, límites, errores y prueba de
> conexión) está en la **sección 5B**.

### 5.3 Capa de datos (`lib/data.ts`)

Usa `fetch` directo a PostgREST (permite `next: { revalidate: 120 }`) o `unstable_cache`. Todas las
consultas solo leen. Ejemplos (valores de parámetros siempre **validados y escapados**, nunca
concatenados sin filtrar):

```
Listado
GET {SUPABASE_URL}/rest/v1/offer_feed
    ?select=id,store,title,url,image_url,category_group,price,list_price,web_discount_pct,
            saving,verified_pct,web_confirmed,history_drop_pct,points,last_seen_at
    &last_seen_at=gte.<ahora-6h en ISO>
    &category_group=eq.tecnologia
    &store=in.(falabella,sodimac)
    &verified_pct=gte.30            (cuando se pide mínimo de descuento verificado)
    &web_discount_pct=gte.30        (cuando se pide mínimo anunciado)
    &price=gte.10000&price=lte.200000
    &title=ilike.*taladro*
    &order=verified_pct.desc,web_discount_pct.desc&limit=24&offset=0
  Cabecera: Prefer: count=exact   → el total llega en Content-Range ("0-23/1234")

Estadísticas de portada
POST {SUPABASE_URL}/rest/v1/rpc/offer_stats        (cuerpo {})

Ficha de producto
GET  …/offer_feed?id=eq.<id>&limit=1
GET  …/offer_price_points?product_id=eq.<id>&select=observed_at,price,list_price
                         &order=observed_at.asc

Relacionados (misma categoría, mejores descuentos)
GET  …/offer_feed?category_group=eq.<g>&id=neq.<id>&order=verified_pct.desc&limit=8
```

Reglas:
- `ilike` del buscador: escapar `*`, `%`, `(`, `)`, `,` del texto del usuario; largo máximo 60.
- Tope de `limit` 48; `offset` máximo razonable (por ejemplo 5.000).
- Orden permitido solo de una lista blanca (sección 5.4); cualquier otro valor cae al por defecto.
- Si Supabase responde error, la página muestra un estado de error amable (no la traza) y
  **no** se cachea el error.

### 5.4 Filtros y orden (todo en la URL, para poder compartir enlaces)

| Parámetro | Control | Detalle |
|---|---|---|
| `q` | Buscador de texto | Busca en el título |
| `cat` | Chips de categoría | `tecnologia`, `muebles`, `zapatillas`, `ropa`, `belleza`, `mascotas`, `herramientas`, `otros` (con contadores de `offer_stats().groups`) |
| `store` | Selección múltiple de tiendas | Con contadores de `offer_stats().stores` |
| `min` | Descuento mínimo | Chips 30 / 50 / 70 / 80 %; se aplica al **verificado** si `ver=1`, si no al máximo de verificado y anunciado |
| `pmin`, `pmax` | Rango de precio | Campos numéricos en CLP |
| `ver` | Interruptor "Solo verificadas" | Por defecto **desactivado** (si no, hoy se verían ~245 productos) |
| `sort` | Orden | `best` (por defecto: `verified_pct` desc, luego `web_discount_pct` desc), `web` (mayor descuento anunciado), `price_asc`, `price_desc`, `saving` (mayor ahorro en pesos), `new` (más recientes: `first_seen_at` desc) |
| `page` | Paginación | 24 por página, con total |

Comportamiento: los filtros se aplican en el servidor; en móvil viven en un cajón (`FilterDrawer`)
con botón "Filtros (n)"; hay botón "Limpiar filtros"; los controles son accesibles con teclado.

### 5.5 Qué muestra cada tarjeta (`DealCard`)

- Imagen cuadrada con fondo blanco (`object-contain`), marcador de posición si falla (`onError`).
- **Insignia de descuento** arriba a la izquierda. Usa el porcentaje **verificado** si existe
  (`verified_pct > 0`); si no, el anunciado, con un estilo apagado y la leyenda "anunciado".
- Niveles de color (`tiers.ts`), alineados con las alertas de Telegram:
  ≥90 % magenta/rojo intenso "SÚPER OFERTA"; ≥80 % rojo "OFERTAZA"; ≥60 % naranja "GRAN OFERTA";
  menos: neutro/verde.
- **Estado de verificación** (chip): "✓ Verificada" (con tooltip: "El precio normal se cobró
  realmente antes" o "Bajó X % respecto de su mínimo anterior") o "No verificada" (gris, con
  tooltip "La tienda anuncia X %, aún sin historial para comprobarlo").
- Tienda (pastilla con nombre legible), título a 2 líneas, **precio grande**, precio tachado,
  "Ahorras $X", y "Actualizado hace N min".
- Botón **"Ver en {Tienda}"** → `target="_blank"` con `rel="noopener noreferrer nofollow"`.
  Toda la tarjeta lleva a la ficha interna; el botón lleva a la tienda.
- Nunca mostrar como descuento un % que sea 0 o negativo.

### 5.6 Páginas

**Portada (`/`)**
1. Cabecera con marca, buscador y enlace a "Cómo verificamos".
2. `StatsStrip`: productos vigentes, ofertas verificadas, tiendas, **"Actualizado hace N min"**
   (`last_seen`).
3. `SuperDeals`: carrusel/fila horizontal con las ofertas **verificadas ≥ 60 %** (si no hay, se
   oculta la sección; no se rellena con no verificadas).
4. Barra de filtros + grilla + paginación.
5. Banner informativo mientras el historial sea corto (cuando `verified / total < 2 %`):
   "Estamos construyendo el historial de precios. Las ofertas marcadas ✓ están comprobadas; las
   demás son lo que anuncia la tienda."

**Ficha (`/oferta/[store]/[sku]`)**: reconstruir el id como `store:sku` (codificar/decodificar con
`encodeURIComponent`); 404 si no existe o si lleva más de 6 h sin verse (mostrar entonces
"Esta oferta ya no está disponible", con enlace a la categoría).
- Imagen, título, tienda, precio actual, precio tachado, ahorro.
- **Gráfico del historial** (`PriceChart`): línea del precio y línea del precio tachado; con un
  solo punto, mostrar el punto y el texto "Aún no hay variaciones registradas".
- Panel **"¿Es una oferta real?"**: explica en lenguaje simple por qué está verificada o no
  (usa `web_confirmed`, `history_drop_pct`, `hist_min`, `hist_max`, `points`, `first_point_at`).
- Relacionados, y botón principal "Ver en {Tienda}".

**`/como-verificamos`**: explica el método (historial propio, tolerancia de 5 %, qué significa
"no verificada", limitaciones: historial joven, no garantizamos stock ni precio final).

**Pie de página**: aviso "Los precios y la disponibilidad cambian; confirma siempre en la tienda.
No somos las tiendas ni vendemos productos."

### 5.7 Diseño

- Enfoque móvil primero (la mayoría del tráfico vendrá del celular): grilla de 2 columnas en
  móvil, 3 en tablet, 4 en escritorio; tipografía legible, objetivos táctiles ≥44 px.
- Tema claro y oscuro (`prefers-color-scheme`), contraste AA como mínimo.
- Paleta sobria con el color reservado para **los descuentos** (la insignia debe ser lo primero
  que se ve). Una fuente de sistema o una sola fuente web (Inter o similar), pesos limitados.
- Esqueletos de carga (`loading.tsx`) en la grilla; sin saltos de diseño (reservar la altura de
  imagen y de tarjeta).
- Estados vacíos claros ("No hay ofertas con esos filtros", con botón para limpiar).
- Evitar animaciones decorativas pesadas; respetar `prefers-reduced-motion`.

### 5.8 Pruebas y calidad (fase 6)

- **Vitest** sobre `lib/`: `filters.ts` (parseo, valores inválidos, límites, lista blanca de orden,
  escape del buscador), `format.ts` (CLP, "hace X"), `tiers.ts` (umbrales 60/80/90),
  construcción de la URL de PostgREST (nunca sin escapar).
- Pruebas de componentes: `DealCard` (insignia verificada vs. anunciada, ahorro, enlaces con
  `rel`), `PriceChart` con 1 punto.
- Humo con Playwright (opcional pero recomendado): portada carga, un filtro cambia la URL y la
  grilla, la ficha abre y muestra el gráfico.
- **Seguridad en build**: un test o script que falle si aparece `SUPABASE_SERVICE_KEY` o `sb_secret`
  en `web/.next/static` o en el HTML renderizado.
- Rendimiento: Lighthouse móvil ≥ 90 en rendimiento y ≥ 95 en accesibilidad y mejores prácticas
  en la portada.
- `npm run lint`, `npm run build` y `npm test` en verde.

---

## 5B. Conexión con Supabase (referencia completa)

Todo lo que la web necesita para hablar con la base de datos, en un solo lugar. Las cifras y
nombres de esta sección se **verificaron contra el proyecto real el 2026-10-03**; lo que no se
pudo verificar está marcado como *por verificar*.

### 5B.1 Cómo se conecta (y cómo no)

```
Navegador ──(HTML ya renderizado)──▶ Vercel (Next.js, servidor) ──HTTPS, clave secreta──▶ Supabase Data API (PostgREST)
```

- **El navegador nunca habla con Supabase.** Solo el servidor de Next.js (Server Components y
  route handlers) lo hace. No hay claves ni URL de la base en el código del cliente.
- **Se usa la Data API REST** (`{SUPABASE_URL}/rest/v1/...`), no una conexión directa a Postgres.
  Motivos: es lo que ya usa el pipeline, no hace falta la contraseña de la base (se muestra una sola
  vez al crear el proyecto y no la tenemos), funciona igual de bien en funciones serverless de Vercel
  sin gestionar conexiones, y los permisos se controlan con la clave.
- **No se usa `supabase-js` obligatoriamente.** Un `fetch` directo basta y permite `next: { revalidate }`
  de Next.js. Si se prefiere `supabase-js`, ver 5B.7.
- **No se usan Auth, Storage, Realtime ni Edge Functions.** La web es de solo lectura y sin usuarios.

### 5B.2 Datos del proyecto

| Dato | Valor |
|---|---|
| Nombre del proyecto | `job-hunter-agent` (**compartido** con otra app: solo se tocan objetos `offer_*`) |
| Referencia (`ref`) | `qxwxftmlqimfausocwoi` |
| URL de la API | `https://qxwxftmlqimfausocwoi.supabase.co` |
| Base de la Data API | `https://qxwxftmlqimfausocwoi.supabase.co/rest/v1` |
| Región | `us-east-1` (usar la región de funciones de Vercel `iad1`, cercana) |
| Versión de Postgres | 17 |
| Estado | `ACTIVE_HEALTHY` |
| Esquema expuesto por la API | `public` (el único; no hay que enviar `Accept-Profile`) |

### 5B.3 Credenciales

| Variable (solo servidor) | Valor | Dónde se obtiene |
|---|---|---|
| `SUPABASE_URL` | `https://qxwxftmlqimfausocwoi.supabase.co` | Está arriba; no es secreto |
| `SUPABASE_SERVICE_KEY` | **Clave secreta** (`sb_secret_…`) | Dashboard de Supabase → *Project Settings* → *API Keys* → *Secret keys* |

Reglas:

1. **Crear una clave secreta propia para la web** (por ejemplo, llamarla `web-vercel`), en lugar de
   reutilizar la del pipeline. Así se puede **rotar o revocar una sin afectar a la otra**. Esto solo se
   puede hacer en el dashboard: pídeselo al usuario, nunca la pegues en el chat ni en el repositorio.
2. **Cabeceras de cada petición:**
   - `apikey: <SUPABASE_SERVICE_KEY>` (siempre).
   - `Authorization: Bearer <SUPABASE_SERVICE_KEY>` **solo si** la clave empieza con `eyJ` (clave JWT
     antigua `service_role`). Las claves nuevas `sb_secret_…` **no son JWT y no van en `Authorization`**.
   - `Accept: application/json`.
3. **No usar la clave `anon` ni la publicable** (`sb_publishable_…`). Existen en el proyecto, pero las
   tablas `offer_*` están cerradas para esos roles a propósito (RLS activado, sin políticas, permisos
   revocados). Con ellas la web recibiría `401`/`403` con `permission denied`. No abrir las tablas para
   hacerlas funcionar (ver 5B.10 si realmente se quiere acceso público).
4. El nombre de la variable **nunca** lleva el prefijo `NEXT_PUBLIC_` (Next.js lo enviaría al navegador).

**Dónde se configuran:**

| Entorno | Cómo |
|---|---|
| Local | `web/.env.local` (en `.gitignore`; nunca se sube). El repositorio solo tiene `web/.env.example` con los nombres |
| Vercel | *Project Settings* → *Environment Variables*: `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` en **Production, Preview y Development**; la clave marcada como **Sensitive** |
| GitHub Actions | No hace falta para la web. (El pipeline ya tiene sus propios secretos en el environment `env`.) |

### 5B.4 Objetos de la base de datos que usa la web

| Objeto | Tipo | Acceso | Para qué | Estado hoy |
|---|---|---|---|---|
| `offer_feed` | Vista materializada | `SELECT` | Listado, filtros, ficha, relacionados | ⏳ **No existe**: migración `0002` pendiente |
| `offer_price_points` | Tabla | `SELECT` | Gráfico del historial de precios | ✅ Existe (`id, product_id, observed_at, price, list_price, source`) |
| `offer_stats()` | Función (RPC) | `EXECUTE` | Contadores de la portada y de los filtros | ⏳ **No existe**: migración `0004` por crear |
| `offer_scan_runs` | Tabla | `SELECT` | (Opcional) "Última actualización" y estado de las tiendas | ✅ Existe (`started_at, scanned, per_store, store_status, errors, quota, …`) |
| `offer_refresh_feed()` | Función (RPC) | `EXECUTE` | **La llama el pipeline**, no la web | ⏳ Migración `0002` pendiente |
| `offer_products`, `offer_sent` | Tablas | — | **La web no las usa** (todo sale de `offer_feed`) | ✅ Existen |

Columnas de `offer_feed` (definidas en `supabase/migrations/0002_offer_feed.sql`; es la fuente de
verdad si algo cambia):

| Columna | Tipo | Significado |
|---|---|---|
| `id` | text | `"falabella:80726514"`; único. En la URL de la ficha: `/oferta/falabella/80726514` |
| `store`, `title`, `url`, `image_url` | text | Tienda, título, enlace a la tienda, foto |
| `category`, `category_group` | text | Etiqueta original y grupo (`tecnologia`, `muebles`, `zapatillas`, `ropa`, `belleza`, `mascotas`, `herramientas`, `otros`) |
| `price`, `list_price`, `saving` | int | Precio actual, precio tachado, ahorro en pesos |
| `web_discount_pct` | numeric | Descuento que **anuncia la tienda** |
| `verified_pct` | numeric | Descuento **verificado** con nuestro historial (el que se debe destacar) |
| `web_confirmed` | boolean | El precio "normal" tachado se cobró de verdad antes |
| `history_drop_pct` | numeric | Baja contra el mínimo anterior que vimos |
| `points`, `distinct_prices`, `hist_min`, `hist_max`, `prev_min`, `prev_max`, `first_point_at` | | Datos del historial para el panel "¿Es una oferta real?" |
| `first_seen_at`, `last_seen_at`, `updated_at` | timestamptz | `last_seen_at` define si el producto sigue vigente (ver abajo) |

**Producto vigente:** `last_seen_at >= now() - interval '6 hours'`. Se aplica **en cada consulta**
de la web (el pipeline actualiza `last_seen_at` como máximo una vez por hora por producto).

### 5B.5 Peticiones exactas

En los ejemplos `$U` es `SUPABASE_URL` y `$K` es `SUPABASE_SERVICE_KEY`. Todas llevan
`-H "apikey: $K"` (más `Authorization` solo con claves `eyJ…`). Los valores de filtros siempre
codificados en URL.

```bash
# Listado con filtros, orden y paginación (+ total en la cabecera Content-Range)
curl -sD - "$U/rest/v1/offer_feed?select=id,store,title,url,image_url,category_group,price,list_price,web_discount_pct,saving,verified_pct,web_confirmed,history_drop_pct,points,last_seen_at\
&last_seen_at=gte.2026-10-03T06:00:00Z\
&category_group=eq.tecnologia\
&store=in.(falabella,sodimac)\
&verified_pct=gte.30\
&price=gte.10000&price=lte.200000\
&title=ilike.*taladro*\
&order=verified_pct.desc,web_discount_pct.desc&limit=24&offset=0" \
  -H "apikey: $K" -H "Prefer: count=exact"
#   → cuerpo: JSON con hasta 24 filas · cabecera: Content-Range: 0-23/1234

# Ficha de un producto
curl -s "$U/rest/v1/offer_feed?id=eq.falabella:80726514&limit=1" -H "apikey: $K"

# Historial de precios (para el gráfico)
curl -s "$U/rest/v1/offer_price_points?product_id=eq.falabella:80726514&select=observed_at,price,list_price&order=observed_at.asc" -H "apikey: $K"

# Relacionados: misma categoría, mejores descuentos verificados
curl -s "$U/rest/v1/offer_feed?category_group=eq.tecnologia&id=neq.falabella:80726514&order=verified_pct.desc&limit=8" -H "apikey: $K"

# Estadísticas de portada (RPC; cuerpo JSON vacío)
curl -s -X POST "$U/rest/v1/rpc/offer_stats" -H "apikey: $K" -H "Content-Type: application/json" -d '{}'

# (Opcional) estado del servicio: última exploración y por tienda
curl -s "$U/rest/v1/offer_scan_runs?select=started_at,scanned,store_status&order=started_at.desc&limit=1" -H "apikey: $K"
```

Operadores de filtro de PostgREST que usa la web: `eq`, `neq`, `gte`, `lte`, `in.(a,b)`, `ilike`
(comodín `*`, no `%`), `order=col.desc,col2.desc`, `limit`, `offset`, `select=col1,col2`. Un valor
con `,` `(` `)` `*` `%` se **escapa o se rechaza antes de enviarlo** (ver 5.3 del plan).

### 5B.6 Límites, tiempos y caché

| Tema | Valor | Qué hacer |
|---|---|---|
| Tiempo máximo de una consulta | **8 s** (`statement_timeout` del rol de la API; verificado) | Consultar solo `offer_feed` (con índices) y `select` con columnas concretas; nunca `select=*` en listados |
| Filas máximas por respuesta | 1.000 por defecto en PostgREST de Supabase (*por verificar* en este proyecto) | La web pagina de a 24 (máximo 48); no hace falta tocarlo |
| Tiempo de espera del cliente | 10 s por petición, 1 reintento solo en errores 5xx/red | Si falla, mostrar el estado de error y **no cachearlo** |
| Caché | `revalidate = 120` s para listado, ficha y estadísticas | El pipeline actualiza datos cada ~15 min |
| Volumen | ~32.000 productos vigentes; respuesta de un listado de 24: unas decenas de KB | Medir el *egress* en el dashboard tras el despliegue (el plan gratis de Supabase tiene cupo mensual; *por verificar*) |
| Pausa por inactividad | Los proyectos gratis se pausan tras días sin actividad (*por verificar* el plazo) | No aplica mientras el pipeline escriba cada 15 min, pero **si se detiene el pipeline, la web dejará de responder** |

### 5B.7 Código de referencia (`web/src/lib/supabase.ts`)

Único archivo que conoce la clave. Solo lecturas.

```ts
// web/src/lib/supabase.ts  — server only
import "server-only";

const URL = process.env.SUPABASE_URL;
const KEY = process.env.SUPABASE_SERVICE_KEY;

if (!URL || !KEY) {
  throw new Error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (server environment only)");
}

function headers(extra: Record<string, string> = {}): HeadersInit {
  const h: Record<string, string> = { apikey: KEY!, Accept: "application/json", ...extra };
  if (KEY!.startsWith("eyJ")) h.Authorization = `Bearer ${KEY}`; // legacy JWT keys only
  return h;
}

export class SupabaseError extends Error {
  constructor(public status: number, public code: string | undefined, message: string) {
    super(message);
  }
}

export async function rest<T>(
  path: string,                       // e.g. "offer_feed?select=id,title&limit=24"
  opts: { revalidate?: number; count?: boolean; method?: "GET" | "POST"; body?: unknown } = {},
): Promise<{ rows: T; total: number | null }> {
  const res = await fetch(`${URL}/rest/v1/${path}`, {
    method: opts.method ?? "GET",
    headers: headers({
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
    } catch { /* body was not JSON */ }
    // Never include the key or the full URL in the error shown to visitors.
    throw new SupabaseError(res.status, code, message);
  }
  const total = res.headers.get("content-range")?.split("/")[1];
  return { rows: (await res.json()) as T, total: total && total !== "*" ? Number(total) : null };
}
```

Tipos mínimos (`web/src/lib/types.ts`): `FeedRow` con las columnas de 5B.4 que se usan, y
`PricePoint = { observed_at: string; price: number; list_price: number | null }`.

*Alternativa con `supabase-js`* (si el agente la prefiere): `createClient(URL, KEY, { auth: { persistSession:
false, autoRefreshToken: false } })` creado **solo en el servidor**; `.from("offer_feed").select(...)`,
`.rpc("offer_stats")`. Con `supabase-js` el control de caché de Next.js es menos directo.

### 5B.8 Prueba de conexión (antes de escribir la web)

Crear `web/scripts/check-supabase.mjs` que lea `.env.local` y haga, **en este orden**, mostrando
OK/FALLA por paso (sin imprimir la clave):

1. `GET offer_scan_runs?select=started_at&limit=1` → debe devolver 1 fila reciente (prueba URL + clave + permisos).
2. `GET offer_feed?select=id&limit=1` con `Prefer: count=exact` → total mayor que 30.000 (prueba que la migración `0002` está aplicada).
3. `POST rpc/offer_stats` → JSON con `total`, `verified`, `stores`, `groups` (prueba la migración `0004`).
4. `GET offer_price_points?select=product_id&limit=1` → 1 fila.

Si algún paso falla, **parar** y consultar la tabla de errores:

| Respuesta | Causa más probable | Solución |
|---|---|---|
| `401` `Invalid API key` | Clave mal copiada, revocada o con espacios; URL de otro proyecto | Revisar `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` |
| `401/403` `permission denied for table …` (`42501`) | Se está usando la clave `anon`/publicable | Usar la clave secreta; no abrir las tablas |
| `404` `PGRST205` / `relation … does not exist` | Migración no aplicada (`offer_feed`) o nombre mal escrito | Aplicar `0002`; revisar el nombre |
| `404` `PGRST202` / función no encontrada | `offer_stats` o `offer_refresh_feed` no creadas | Aplicar la migración que corresponda |
| `400` `column … does not exist` | La consulta pide una columna que no existe en `offer_feed` | Comparar con 5B.4 |
| `406` `PGRST106` esquema inválido | Se envió `Accept-Profile` con un esquema no expuesto | Quitar la cabecera; todo está en `public` |
| `500` `57014` `canceling statement due to statement timeout` | Consulta más lenta que 8 s (por ejemplo sin límite o sobre la tabla de historial completa) | Paginar, filtrar por índice, usar `offer_feed` |
| `429` | Demasiadas peticiones | Aumentar la caché; reintentar con espera |
| Respuestas vacías `[]` con la clave correcta | Filtro `last_seen_at` demasiado estricto, o el pipeline no está actualizando | Revisar `select max(last_seen_at) from offer_feed` |

### 5B.9 Orden de preparación (todo debe estar listo antes de la fase 3 del plan)

- [ ] Migración `0002_offer_feed.sql` aplicada (vista, `last_seen_at`, función de refresco).
- [ ] Migración `0004_offer_stats.sql` creada, validada en `begin; … rollback;` y aplicada.
- [ ] El pipeline refresca `offer_feed` tras cada escaneo (fase 2 del plan).
- [ ] Clave secreta propia de la web creada en el dashboard y cargada en Vercel y en `.env.local`.
- [ ] `node web/scripts/check-supabase.mjs` pasa los 4 pasos.

### 5B.10 Alternativas que NO se usan hoy (y cuándo considerarlas)

| Alternativa | Por qué no ahora | Cuándo reconsiderar |
|---|---|---|
| **Lectura pública con la clave publicable** (`GRANT SELECT` de `offer_feed` a `anon`) | Abre la API a cualquiera con la clave pública y Supabase marca la vista materializada expuesta como advertencia. Cualquiera podría consultar la API directamente y gastar el cupo | Si se necesita que el navegador consulte directo (por ejemplo, filtros en vivo sin pasar por el servidor) y se acepta ese riesgo |
| **Conexión directa a Postgres** (pooler `:6543`) | Requiere la contraseña de la base (no la tenemos) y gestionar conexiones | Si hacen falta consultas que PostgREST no permite |
| **Un rol de Postgres de solo lectura propio** | Cerraría la brecha de que la clave de la web puede escribir; no se puede crear la clave de ese rol desde la API REST | Mejora de seguridad futura: crear el rol, usarlo con conexión directa o con JWT propio |

Nota de seguridad: la clave secreta de la web **también puede escribir**. Por eso `lib/supabase.ts`
solo expone lecturas (`GET` y la llamada `POST` a `offer_stats`) y la web no ofrece ninguna ruta que
acepte datos del usuario hacia la base. Si la clave se filtra, **rotarla de inmediato** en Supabase
y actualizarla en Vercel.

---

## 6. Seguridad (lista obligatoria)

- La clave secreta de Supabase **solo en el servidor**: variable de entorno de Vercel marcada
  como sensible, sin prefijo `NEXT_PUBLIC_`; usada únicamente desde `lib/data.ts`; jamás en
  componentes de cliente (`"use client"`), ni en `console.log`, ni en mensajes de error.
- `lib/data.ts` **solo hace lecturas** (`GET` y `POST` a funciones `offer_stats`). No exponer
  ninguna ruta de API que acepte escritura.
- Validar y acotar todos los parámetros de URL (sección 5.3). Sin interpolación de texto del
  usuario en filtros de PostgREST sin escapar.
- Las tablas `offer_*` y `offer_feed` siguen **cerradas** a `anon` y `authenticated`. No agregar
  políticas RLS ni `grant` públicos para facilitar el desarrollo.
- Enlaces externos con `rel="noopener noreferrer nofollow"`. Sin `dangerouslySetInnerHTML` con
  datos de tiendas (los títulos vienen de terceros: tratarlos como texto no confiable).
- Cabeceras de seguridad básicas en `next.config` (`X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`/`frame-ancestors`).
- `noindex` hasta que el usuario decida lo contrario.
- Si la clave se filtra en cualquier lugar: rotarla en Supabase y actualizarla en GitHub (`env`) y
  en Vercel.

---

## 7. Plan de fases y definición de terminado

| Fase | Trabajo | Terminado cuando |
|---|---|---|
| **1** | Migraciones 0002 y 0004 (sección 3; la 0003, de diagnósticos por escaneo, **ya está aplicada**) | `offer_feed` con >30.000 filas, `offer_stats()` correcto, sin avisos de seguridad nuevos |
| **2** | Refresco en el pipeline (sección 4) | Pruebas en verde y `last_seen_at` avanza tras un run |
| **3** | Andamiaje de `web/`: Next.js, Tailwind, TypeScript, lint, `.env.example`, Vitest, `lib/supabase.ts` y `scripts/check-supabase.mjs` (sección 5B) | `npm run build` y `npm test` pasan, y `check-supabase.mjs` pasa los 4 pasos |
| **4** | Capa de datos y utilidades (`data.ts`, `filters.ts`, `format.ts`, `tiers.ts`) con pruebas | Pruebas de `lib/` en verde; una consulta real devuelve 24 productos |
| **5** | Páginas y componentes (portada, ficha, método, filtros, tarjetas) | La portada filtra y ordena por URL; la ficha muestra gráfico y panel; responsive revisado en 360, 768 y 1280 px |
| **6** | Calidad (sección 5.8) y seguridad (sección 6) | Lighthouse ≥ metas; el chequeo de secretos pasa; revisión de accesibilidad con teclado |
| **7** | Despliegue en Vercel | URL de producción responde; ver abajo |
| **8** | Verificación posterior | Lista de comprobación final |

### Fase 7 — Despliegue en Vercel

1. Importar el repo `felipe12012/offer_hunter` en Vercel con **Root Directory = `web`** y framework
   Next.js. (Con la integración MCP de Vercel o con `vercel` CLI; el agente que escribió este
   plan **no ve herramientas de Vercel en su sesión**, así que usa la tuya o pide al usuario que
   haga el paso en el panel.)
2. Variables de entorno de **Production y Preview**: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
   (esta última como *Sensitive*). Pídele al usuario que cargue la clave en el panel si no puedes
   hacerlo sin exponerla.
3. **Paso crítico, evita 96 despliegues al día:** el bot hace commit a `main` cada 15 min y Vercel
   despliega en cada push. Configura **Ignored Build Step** (Settings → Git) con:
   ```
   git diff HEAD^ HEAD --quiet -- .
   ```
   (con Root Directory = `web`, el `.` es `web/`; código de salida 0 = sin cambios = se omite el
   despliegue). Comprueba con un commit que solo cambie `data/` que **no** se despliega, y con
   otro que cambie `web/` que **sí** se despliega.
4. Región de funciones cercana a la base de datos (us-east / `iad1`).
5. Primer despliegue en **Preview**; revisar; luego promover a Production solo con la aprobación del
   usuario.
6. No configurar dominio propio sin que el usuario lo pida.

### Fase 8 — Lista de comprobación final

- [ ] La portada carga en menos de 3 s en móvil con datos reales.
- [ ] Cada filtro funciona solo y combinado; los enlaces con filtros se pueden compartir.
- [ ] "Solo verificadas" muestra únicamente productos con insignia ✓.
- [ ] Ningún producto sin imagen ni título aparece; ninguno con más de 6 h sin verse.
- [ ] La ficha de un producto con 1 punto de historial no se rompe.
- [ ] El HTML y los bundles **no** contienen la clave secreta (búsqueda de `sb_secret` y del valor).
- [ ] Un commit que solo toca `data/` no dispara despliegue.
- [ ] `robots` es `noindex`.
- [ ] El log del run de Actions sigue mostrando `Supabase: …` sin errores tras agregar el refresco.
- [ ] Los 240+ tests de Python siguen en verde.

---

## 8. Riesgos y cómo se manejan

| Riesgo | Mitigación |
|---|---|
| Hoy casi todo es "no verificada" (historial de 1 día) | Banner explicativo; orden por verificadas primero; el interruptor "Solo verificadas" arranca apagado; con los días mejora solo |
| Imágenes bloqueadas por la CDN de una tienda | `referrerPolicy="no-referrer"`, marcador de posición en `onError`; si una tienda falla sistemáticamente, ocultar su imagen y avisar |
| `offer_feed` desactualizada si el refresco falla | `last_seen_at` y "Actualizado hace N min" visibles; el refresco no es fatal para el pipeline |
| Consulta lenta con mucho historial | La vista materializada tiene índices; si `offer_price_points` supera ~1 M filas, considerar guardar el resumen por producto en lugar de recalcularlo |
| Costos / límites de Vercel o Supabase (planes gratis) | Revalidación de 120 s, sin `next/image`, consultas paginadas y acotadas |
| Producto retirado de la tienda | Filtro de 6 h sobre `last_seen_at` |
| Cambio en la estructura de las tiendas | Es un problema del scraper, no de la web: la web solo lee `offer_feed` |

---

## 9. Fuera de alcance (a propósito)

Cuentas de usuario, favoritos, alertas por correo, comparador entre tiendas, panel de
administración, afiliados, indexación en buscadores, y cualquier escritura desde la web.
Si el usuario los pide después, serían un plan aparte.
