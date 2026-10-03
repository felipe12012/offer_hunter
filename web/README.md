# CazaOfertas (web)

Web pública de solo lectura que lista las ofertas que recolecta el servicio de la raíz del repositorio
(`offer_hunter`), con filtros, orden y una ficha por producto con su historial de precios. Marca como
**verificados** los descuentos que el historial propio respalda y deja claro cuáles solo son lo que anuncia la tienda.

Next.js (App Router) · TypeScript · Tailwind · Supabase (Data API, solo servidor) · Vercel.

## Páginas

| Ruta | Qué muestra |
|---|---|
| `/` | Portada: resumen, los descuentos verificados más grandes, filtros, orden y listado paginado |
| `/oferta/[tienda]/[sku]` | Ficha: precio, panel "¿Es una oferta real?", gráfico del historial y productos relacionados |
| `/como-verificamos` | Explica el método y sus límites |
| `/api/health` | Responde 200 y la hora (no toca la base de datos) |

Todos los filtros viven en la URL y se pueden compartir: `q`, `cat`, `store`, `min`, `pmin`, `pmax`, `ver`, `sort`, `page`
(validados en `src/lib/filters.ts`).

## Cómo funciona con los datos

```
Navegador ──HTML──▶ Next.js (servidor en Vercel) ──HTTPS + clave secreta──▶ Supabase Data API
```

- **El navegador nunca habla con Supabase.** Solo `src/lib/supabase.ts` conoce la clave, y solo hace lecturas.
- Lee la vista `offer_feed` (precalculada, 10 ms por consulta), la función `offer_stats()` y la tabla
  `offer_price_points`. Todo está definido en `../supabase/migrations/`.
- Los datos se cachean 120 s; el pipeline los actualiza cada ~15 min.
- Un producto solo se muestra si se vio en las últimas 6 horas, y Falabella/Sodimac no aparecen duplicados.
- La referencia completa de la conexión está en `../docs/superpowers/plans/2026-10-03-offers-web.md`, sección 5B.

## Desarrollo local

```bash
cd web
npm ci
cp .env.example .env.local     # y rellena SUPABASE_SERVICE_KEY (ver abajo)
npm run dev                    # http://localhost:3000
```

**Sin credenciales** (`SUPABASE_*` vacías) y fuera de producción, la web usa una **muestra real** de 23 productos
(`src/lib/fixtures.ts`), para poder desarrollar la interfaz sin la clave. **En producción nunca hay datos de
muestra**: sin credenciales falla de forma visible.

### Variables de entorno (solo servidor)

| Variable | Valor |
|---|---|
| `SUPABASE_URL` | `https://qxwxftmlqimfausocwoi.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Clave **secreta** (`sb_secret_…`). Crea una propia para la web en Supabase → Project Settings → API Keys → *Secret keys* (así se puede rotar sin tocar la del pipeline). **Nunca** con el prefijo `NEXT_PUBLIC_` |

La clave `anon` o la publicable **no sirven**: las tablas `offer_*` están cerradas a propósito para esos roles.

### Comandos

| Comando | Para qué |
|---|---|
| `npm test` | Pruebas unitarias (Vitest): filtros, consultas, formato, gráfico, capa de datos |
| `npm run lint` · `npx tsc --noEmit` | Calidad y tipos |
| `npm run build` | Compila (no necesita credenciales) |
| `npm run check:secrets` | Falla si la clave aparece en lo que se descarga en el navegador (ejecutar después de `build`) |
| `npm run check:supabase` | Comprueba la conexión real (URL, clave, vista, función) usando `.env.local` |
| `node scripts/mock-supabase.mjs` | Servidor falso de la API para probar el modo producción sin la clave |

## Despliegue en Vercel

1. **New Project** → importar `felipe12012/offer_hunter` con **Root Directory = `web`** (framework Next.js; `vercel.json` ya fija la región `iad1`).
2. **Environment Variables** (Production, Preview y Development): `SUPABASE_URL` y `SUPABASE_SERVICE_KEY`
   (esta última como **Sensitive**).
3. **No hace falta tocar el *Ignored Build Step***: `vercel.json` ya lo trae (`git diff HEAD^ HEAD --quiet -- .`).
   Sin él, los commits que el bot hace a `data/` cada 15 minutos dispararían unos 96 despliegues al día.
   Comprueba que un commit que solo cambia `data/` **no** despliega, y uno que cambia `web/` **sí**.
4. Primero se despliega en **Preview**; se revisa; y a Production solo con aprobación.

## Seguridad

- Cabeceras de seguridad y CSP en `next.config.ts`; `noindex` hasta que se decida lo contrario (`src/app/layout.tsx`).
- Lecturas únicamente; ninguna ruta acepta datos del usuario hacia la base.
- Todo valor de la URL se valida con listas blancas antes de armar una consulta (`filters.ts`, `query.ts`).
- Los títulos vienen de terceros y se tratan como texto (React los escapa); los enlaces externos llevan
  `rel="noopener noreferrer nofollow"`.
- Si la clave se filtra: rotarla en Supabase y actualizarla en Vercel (y en GitHub si el pipeline la compartía).
