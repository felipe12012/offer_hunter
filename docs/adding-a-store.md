# Cómo agregar una tienda

Esta guía recoge lo aprendido integrando Sodimac, Falabella, Hites, Paris, Ripley y Tottus.
Léela completa antes de empezar: casi todos los problemas que tuvimos están en la sección 6.

Resumen del trabajo: **un módulo `sources/<tienda>.py` con una función `fetch_deals(watchlist)`**,
pruebas con una página real guardada, y tres líneas de registro en `main_fast.py`. Nada más se
toca: el filtro, el historial, la deduplicación y Telegram ya funcionan para cualquier tienda.

---

## 1. El contrato que debe cumplir una tienda

```python
def fetch_deals(watchlist: dict) -> list[Deal]:
    ...
```

- **Recibe** el contenido de `config/watchlist.json` (palabras clave, `scan`, etc.).
- **Devuelve** una lista de `Deal` (definido en `models.py`).
- **Lanza una excepción solo si la tienda está totalmente caída** (todas sus búsquedas fallaron).
  Un fallo parcial se registra en `stderr` y se sigue con el resto. El orquestador cuenta cada
  excepción como "tienda caída" y solo aborta el run si caen **todas** las tiendas.
- **No envía mensajes ni toca archivos.** Solo lee de la web.

### Campos de `Deal`

| Campo | Regla |
|---|---|
| `id` | `"<tienda>:<id estable del producto>"`. Debe ser el mismo en cada escaneo. Si la tienda comparte catálogo con otra (Falabella/Sodimac), usa el id numérico del producto tal cual: así el sistema detecta el duplicado entre tiendas |
| `title` | Marca + nombre, sin espacios sobrantes |
| `url` | Enlace **absoluto** al producto, sin parámetros de seguimiento (`?sponsoredClickData=…`) |
| `store` | Slug en minúsculas, igual al prefijo del `id` |
| `category` | La palabra de búsqueda o el **grupo** de `scan.category_patterns` (ej. `"tecnologia"`). Debe coincidir con `categories`/`keywords` de la watchlist o el producto se filtra |
| `price` | CLP, entero. **El precio que paga cualquier cliente** (ver sección 6) |
| `list_price` | CLP, el "precio normal" tachado. Si no hay, **igual a `price`** |
| `discount_pct` | `round((list_price - price) / list_price * 100, 1)` |
| `scraped_at` | `datetime.now(timezone.utc).isoformat()` |
| `image_url` | URL absoluta de la foto real del producto. `""` si no hay (el mensaje saldrá sin foto) |

---

## 2. Paso 1: investigar la tienda (antes de escribir código)

Haz esto en orden. Cada paso descarta el siguiente.

### 2.1. ¿Responde a una petición HTTP simple **desde GitHub**?

Desde tu PC casi todo funciona. Lo que importa es el runner de GitHub (IP de datacenter). Prueba
con un workflow temporal `probe.yml` (`workflow_dispatch`) que haga un `GET` con User-Agent de
navegador y muestre el código y el `<title>`:

| Resultado | Qué significa |
|---|---|
| `200` con productos | Perfecto: no necesitas navegador |
| `403`, `Blocked`, `Un momento…` | La tienda bloquea IP de datacenter. Hoy es el caso de Paris, Ripley y Tottus. Ver `docs/superpowers/plans/2026-10-02-hard-tier-unblock.md` antes de seguir |

Borra el workflow de prueba al terminar.

### 2.2. ¿Los productos vienen como JSON dentro de la página?

Busca `<script id="__NEXT_DATA__">` en el HTML (tiendas hechas con Next.js). Si existe:
`json.loads(...)["props"]["pageProps"]` suele traer `results`, `pagination` y los precios ya
separados. Es la opción más rápida y estable. **Es lo que usan Falabella y Sodimac.**

Revisa también:
- **`pagination`**: `count`, `perPage`, `currentPage`. ¿Qué parámetro cambia de página? (`&page=2`
  en Falabella). Compruébalo pidiendo la página 2 y viendo que los ids son distintos.
- **`currentUrl`**: algunas búsquedas se reescriben a una página de categoría, y solo esa URL
  acepta la paginación (pasa con Sodimac: `search?Ntt=taladro` → `/lista/cat…/Taladros`).
- **Categorías**: ¿el HTML del home trae enlaces `/category/catNNN/Nombre`? Permite descubrir todo
  el catálogo de interés en lugar de depender de unas pocas palabras.

### 2.3. ¿Hay un endpoint de HTML paginado?

Tiendas Salesforce Commerce Cloud (Hites) paginan con `Search-UpdateGrid?q=…&start=0&sz=48`.
Prueba incrementando `start` y comprueba que los ids cambian.

### 2.4. Solo si nada de lo anterior funciona: navegador (Playwright)

Es lo más lento (~15 s por página), requiere instalar Chromium en el runner (~4 min por run) y es
lo más frágil. Úsalo solo si la tienda realmente renderiza todo con JavaScript. Mira
`sources/paris.py` como ejemplo.

---

## 3. Paso 2: escribir el módulo

### Camino A: tienda con el mismo JSON que Falabella/Sodimac

Es un archivo de ~15 líneas. Ejemplo (`sources/sodimac.py`):

```python
from models import Deal
from sources.nextdata import StoreConfig, fetch_store_deals

BASE_URL = "https://www.sodimac.cl"
CONFIG = StoreConfig(
    store="sodimac",
    base_url=BASE_URL,
    home_url=f"{BASE_URL}/sodimac-cl",
    search_url=f"{BASE_URL}/sodimac-cl/search?Ntt={{query}}",
    category_url=f"{BASE_URL}/sodimac-cl/lista/{{id}}/{{slug}}",
    category_href_re=r"/(?:category|lista)/(cat\d+)/([A-Za-z0-9%\-_.]+)",
)


def fetch_deals(watchlist: dict) -> list[Deal]:
    return fetch_store_deals(CONFIG, watchlist)
```

`fetch_store_deals` ya hace: descubrir categorías desde el home (filtradas por
`scan.category_patterns`), paginar búsquedas y categorías, repartir el trabajo en 4 hilos,
deduplicar, aislar fallos y lanzar error solo si todo falla. Si el JSON de la tienda tiene otros
nombres de campo, ajusta `_deal_from_result` en `sources/nextdata.py`.

### Camino B: tienda con HTML paginado (Hites)

Mira `sources/hites.py`. Estructura:

- `parse_html(html, category) -> list[Deal]`: función **pura** (sin red) que recibe el HTML y
  devuelve los `Deal`. Lanza `RuntimeError` si no encuentra ninguna tarjeta de producto, para que
  un cambio de estructura sea visible y no silencioso.
- `fetch_html(...)`: la petición, con 3 reintentos.
- `fetch_deals(watchlist)`: recorre consultas y páginas, se detiene cuando una página no trae
  productos nuevos, aísla cada consulta y lanza error si todas fallan.

La foto se obtiene con `pick_image(tarjeta, BASE_URL)` de `sources/images.py`: ignora los
marcadores de carga (`data:`), íconos de garantía, logos y tarjetas de pago.

### Camino C: tienda con navegador

Mira `sources/paris.py`: `fetch_html` abre Chromium con `SCRAPER_PROXY` opcional, espera el
selector de las tarjetas y llama a `scroll_to_load(page)` (necesario: las imágenes cargan al
hacer scroll). Requiere `INSTALL_BROWSER=true` en las variables del repo.

---

## 4. Paso 3: registrar la tienda en `main_fast.py`

Tres líneas:

```python
from sources.nueva import fetch_deals as fetch_nueva_deals          # 1. import

SOURCE_FETCHERS = [
    ...
    ("nueva", "fetch_nueva_deals"),                                   # 2. (slug, nombre del atributo)
]
```

- El slug debe ser el mismo que `Deal.store` y el prefijo del `id`.
- El nombre del atributo debe ser exactamente `fetch_<slug>_deals`: las pruebas lo usan para
  reemplazar el scraper por uno falso, y así **ninguna prueba hace llamadas reales**
  (`tests/test_workflow.py` recorre `main_fast.SOURCE_NAMES` automáticamente).

Para probarla sin activarla en producción, agrega su slug a `disabled_stores` en la watchlist.

---

## 5. Paso 4: pruebas

Las pruebas **nunca usan la red**. Trabajan con páginas reales guardadas.

1. **Guarda una página real** en `tests/fixtures/` (HTML o JSON de `pageProps`), recortada a 2–4
   productos que cubran los casos raros: con descuento, sin descuento, con varios precios, con
   precio de evento. Hazlo desde una página **ya cargada y desplazada**, para que incluya las
   imágenes reales y no los marcadores de carga.
2. **Pruebas del parser** (`tests/test_<tienda>.py`): título, precio, precio tachado, descuento,
   URL absoluta, `id` correcto, y que un HTML sin productos lance `RuntimeError`.
3. **Imágenes** (`tests/test_images.py`): agrega la tienda al diccionario `PARSERS` si es de
   HTML, con un fixture de dos tarjetas reales; verifica `image_url` real (no `data:` ni íconos).
4. **Aislamiento** (`tests/test_source_isolation.py`): agrega la tienda a `STORES` si es de HTML,
   para comprobar que una consulta que falla no tumba al resto y que, si fallan todas, se lanza
   error. Las tiendas de `nextdata` ya están cubiertas en `tests/test_nextdata.py`.
5. Ejecuta `python -m pytest -q`. Debe quedar todo en verde.

---

## 6. Trampas conocidas (cada una nos costó tiempo)

| Trampa | Qué pasa | Cómo se maneja |
|---|---|---|
| **IP de datacenter bloqueada** | Funciona en tu PC y da 403 en GitHub | Probar en un runner (sección 2.1) **antes** de escribir el parser |
| **Precio exclusivo de tarjeta (CMR)** | El precio más bajo del JSON no lo paga cualquiera | `price` = el menor entre precio internet y precio de evento; ignorar CMR |
| **Precio de evento** | En CyberDay aparece `eventPrice` aparte | Incluirlo al calcular `price`; es lo que dispara las ofertas reales |
| **Productos con varias variantes** | `price` trae una lista (una por variante) | Usar siempre el primer valor de cada lista, de forma consistente |
| **Imágenes diferidas** | Sin hacer scroll el HTML trae esqueletos de carga y `data:` | En navegador, `scroll_to_load(page)`. En JSON, usar `mediaUrls` |
| **Íconos que parecen producto** | Una tarjeta trae sellos de garantía y logos de tarjetas antes de la foto | `pick_image` los descarta por nombre; añade patrones a `_NOISE` si aparece uno nuevo |
| **Productos patrocinados repetidos** | El mismo producto sale dos veces en una página | Deduplicar por id dentro de la tienda |
| **Búsqueda reescrita a categoría** | `page=2` se ignora en la búsqueda | Paginar sobre `currentUrl` (ya lo hace `nextdata`) |
| **Mismo producto en dos tiendas** | Falabella y Sodimac comparten marketplace; la oferta llegaba duplicada | Misma numeración de `id`; `main_fast.dedupe_cross_store` envía una sola vez |
| **Descuentos permanentes** | 40–70 % "siempre": son precios tachados inflados | No es problema del scraper: `deal_filter` los descarta si el historial no los confirma |
| **Volumen** | Una categoría puede tener 49.000 productos | Respetar `scan.max_*_pages` y `max_categories`; hay pausa de 0,3 s entre páginas |
| **Palabra ambigua** | `notebook` también es un cuaderno de papel | Preferir categorías (`category_patterns`) a palabras sueltas cuando existan |

---

## 7. Lista de verificación antes de dar la tienda por terminada

- [ ] Responde con HTTP simple desde un **runner de GitHub** (o se decidió usar navegador).
- [ ] `fetch_deals` cumple el contrato (lista de `Deal`; error solo si todo falla).
- [ ] `id` estable, `url` absoluta, `image_url` real, `price`/`list_price` correctos.
- [ ] Fixtures reales y pruebas del parser, de imágenes y de aislamiento; `pytest` en verde.
- [ ] Registrada en `SOURCE_FETCHERS` con el nombre `fetch_<slug>_deals`.
- [ ] Escaneo real local: cuenta de productos razonable, casi todos con imagen
      (`Deal.image_url`), y precios coherentes con los de la web.
- [ ] Un run manual en Actions muestra la tienda con un número > 0 en `Deals per store`.
- [ ] Documentada en la tabla de tiendas del `README.md`.
