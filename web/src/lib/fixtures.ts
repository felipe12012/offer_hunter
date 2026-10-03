// Muestra REAL de la base (3-oct-2026) para desarrollar y probar sin la clave de Supabase.
// Solo se usa cuando NO hay credenciales y NODE_ENV !== "production" (ver data.ts).
// Las columnas derivadas se calculan con las mismas fórmulas que la vista offer_feed.
import type { FeedRow } from "./types";

type Seed = {
  id: string;
  title: string;
  price: number;
  list: number;
  prevMin: number | null;
  prevMax: number | null;
  group: string;
  img: string;
  url: string;
};

const SEEDS: Seed[] = [
  { id: "ahumada:96355", title: "Dove Desodorante Serum Roll-on Niacinamida + Vitamina C&E 45ml", price: 1500, list: 4999, prevMin: 4999, prevMax: 4999, group: "belleza", img: "https://www.farmaciasahumada.cl/dw/image/v2/BJVH_PRD/on/demandware.static/-/Sites-ahumada-master-catalog/default/dwcf986aaf/images/products/96355/96355.jpg?sw=247&sh=247&sm=fit", url: "https://www.farmaciasahumada.cl/dove-desodorante-serum-roll-on-niacinamida-vitamina-cande-45ml-96355.html" },
  { id: "falabella:151406771", title: "REBEL Secador Multifuncional 5 en 1 AirMax Rosa", price: 74990, list: 159990, prevMin: 159990, prevMax: 159990, group: "belleza", img: "https://media.falabella.com/falabellaCL/151406773_01/public", url: "https://www.falabella.com/falabella-cl/product/151406771/secador-5-en-1-airmax-pink" },
  { id: "sodimac:153607037", title: "MAKITA Taladro percutor 13mm 18v ltx basicbl 1 bateria + cargador DHP453WV", price: 98990, list: 169990, prevMin: 98990, prevMax: 169990, group: "herramientas", img: "https://media.sodimac.cl/falabellaCL/153607038_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/153607037/taladro-percutor-13mm-18v-ltx-basicbl-1-bateria-cargador-dhp453wv" },
  { id: "sodimac:147385918", title: "STANLEY Taladro percutor 13 mm 700W SDH700BA-B2C", price: 29990, list: 45570, prevMin: 29990, prevMax: 45570, group: "herramientas", img: "https://media.sodimac.cl/falabellaCL/147385921_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/147385918/taladro-percutor-13-mm-700w-sdh700ba-b2c-stanley" },
  { id: "falabella:156723000", title: "DEWALT Kit de Taladro Percutor 20V + Set de 32 Accesorios", price: 149990, list: 199990, prevMin: 149990, prevMax: 199990, group: "herramientas", img: "https://media.falabella.com/sodimacCL/7936257_01/public", url: "https://www.falabella.com/falabella-cl/product/156723000/taladro-13-mm-20-v-pilas-baterias" },
  { id: "sodimac:114424561", title: "KUANGYE Ropa Para Perros Suéter Labrador Golden Retriever Alaska", price: 12990, list: 27180, prevMin: 27180, prevMax: 27180, group: "mascotas", img: "https://media.sodimac.cl/falabellaCL/114424562_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/114424561/Ropa-Para-Perros-Sueter-Labrador-Golden-Retriever-Alaska" },
  { id: "sodimac:156400764", title: "TASTE OF THE WILD PACK 3 UNIDADES ALIMENTO SECO PARA PERRO PINE FOREST (VENADO) 5.6 K", price: 70900, list: 91000, prevMin: 70900, prevMax: 91000, group: "mascotas", img: "https://media.sodimac.cl/falabellaCL/156400765_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/156400764/pack-3-unidades-taste-of-the-wild-alimento-seco-para-perro-pine-forest-venado-5-6-k" },
  { id: "sodimac:145889537", title: "EVERSO Corral Jaulas Para Perros Plegable Mascota Casa 9158cm Gris", price: 9990, list: 32990, prevMin: 10990, prevMax: 10990, group: "mascotas", img: "https://media.sodimac.cl/falabellaCL/145889538_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/145889537/Corral-Jaulas-Para-Perros-Plegable-Mascota-Casa-9158cm-Gris" },
  { id: "sodimac:153128315", title: "EVERSO Cama Para Gatos Casa De Madera Cama Gatos Rascador Grande", price: 14990, list: 34990, prevMin: 15990, prevMax: 15990, group: "mascotas", img: "https://media.sodimac.cl/falabellaCL/153128317_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/153128315/cama-para-gatos-casa-de-madera-cama-gatos-rascador-grande" },
  { id: "sodimac:151030952", title: "CLEMS Escritorio Funcional Altura Ajustable 100x60x63-86cm Negro", price: 37490, list: 119990, prevMin: 49990, prevMax: 119990, group: "muebles", img: "https://media.sodimac.cl/falabellaCL/151030953_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/151030952/escritorio-funcional-altura-ajustable-100x60x63-86cm-negro" },
  { id: "sodimac:126306018", title: "MUNDO LIVING Seccional Intercambiable Provenza Blanco Invierno con Resortes", price: 339990, list: 999990, prevMin: 339990, prevMax: 999990, group: "muebles", img: "https://media.sodimac.cl/falabellaCL/126306019_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/126306018/Seccional-Intercambiable-Provenza-Blanco-Invierno-con-Resortes" },
  { id: "falabella:145084525", title: "CABSUR COLCHON CABURGA 1 PLAZA 90x190x20cm", price: 71990, list: 199990, prevMin: 71990, prevMax: 199990, group: "muebles", img: "https://media.falabella.com/falabellaCL/145084526_01/public", url: "https://www.falabella.com/falabella-cl/product/145084525/COLCHON-CABURGA-1-PLAZA-90x190x20cm" },
  { id: "sodimac:139864526", title: "CLEMS Cubrecama Quilt Reversible 1.5 Plazas 180x260cm Café", price: 12490, list: 35000, prevMin: 12990, prevMax: 35000, group: "muebles", img: "https://media.sodimac.cl/falabellaCL/139864528_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/139864526/cubrecama-quilt-reversible-1-5-plazas-180x260cm-cafe" },
  { id: "tusmascotas:253223", title: "Juguete Electronico Ardilla", price: 5620, list: 12490, prevMin: null, prevMax: null, group: "otros", img: "https://www.tusmascotas.cl/wp-content/uploads/2022/08/4781.jpg", url: "https://www.tusmascotas.cl/product/juguete-electronico-ardilla/" },
  { id: "falabella:129145494", title: "GENERICO PORTA BEBE RECIEN NACIDO CABESTRILLO RESPIRABLE VERDE", price: 9990, list: 29990, prevMin: 29990, prevMax: 29990, group: "ropa", img: "https://media.falabella.com/falabellaCL/129145496_01/public", url: "https://www.falabella.com/falabella-cl/product/129145494/PORTA-BEBE-RECIEN-NACIDO-CABESTRILLO-RESPIRABLE-VERDE" },
  { id: "falabella:883785127", title: "APOLOGY Pantalón Mujer", price: 11990, list: 24990, prevMin: 11990, prevMax: 24990, group: "ropa", img: "https://media.falabella.com/falabellaCL/883785133_1/public", url: "https://www.falabella.com/falabella-cl/product/883785127/pantalon-mujer-apology" },
  { id: "hites:10052004071002", title: "Polera Cooldry Quebec Manga Corta Rojo", price: 3190, list: 6490, prevMin: 6490, prevMax: 6490, group: "ropa", img: "https://www.hites.com/dw/image/v2/BDPN_PRD/on/demandware.static/-/Sites-mastercatalog_HITES/default/dwd5307bc1/images/original/mkp/10052004071/10052004071_ROJO_1.jpg?sw=306&sh=306", url: "https://www.hites.com/polera-cooldry-quebec-manga-corta-rojo-10052004071002.html" },
  { id: "falabella:146620564", title: "KENSINGTON Funda Blackbelt para Surface Go", price: 23990, list: 59900, prevMin: 23990, prevMax: 59900, group: "tecnologia", img: "https://media.falabella.com/falabellaCL/146620565_01/public", url: "https://www.falabella.com/falabella-cl/product/146620564/funda-blackbelt-para-surface-go" },
  { id: "hites:949044001", title: "Audífonos Bluetooth Huawei Freebuds 6i White", price: 52990, list: 109990, prevMin: 109990, prevMax: 109990, group: "tecnologia", img: "https://www.hites.com/dw/image/v2/BDPN_PRD/on/demandware.static/-/Sites-mastercatalog_HITES/default/dw75721321/images/original/pim/949044001/949044001_1.jpg?sw=306&sh=306", url: "https://www.hites.com/audifonos-bluetooth-huawei-freebuds-6i-white-949044001.html" },
  { id: "sodimac:145108689", title: "BASEUS Cargador inalámbrico Qi2 Mini4 Universal Explorer 15W Negro", price: 19980, list: 39990, prevMin: 19980, prevMax: 39990, group: "tecnologia", img: "https://media.sodimac.cl/falabellaCL/145108690_01/public", url: "https://www.sodimac.cl/sodimac-cl/articulo/145108689/Cargador-inalambrico-Qi2-Baseus-Mini4-Universal-Explorer-15W-Negro" },
  { id: "falabella:146762697", title: "MAUI AND SONS Zapatilla Amaral Beige Mujer", price: 16990, list: 39990, prevMin: 39990, prevMax: 39990, group: "zapatillas", img: "https://media.falabella.com/falabellaCL/146762725_01/public", url: "https://www.falabella.com/falabella-cl/product/146762697/zapatilla-amaral-beige-mujer-maui-and-sons" },
  { id: "vans:4310146", title: "Zapatilla Sk8-Hi Blanco Vans", price: 32990, list: 72990, prevMin: 72990, prevMax: 72990, group: "zapatillas", img: "https://cdn.shopify.com/s/files/1/0712/8439/2134/files/VN000D5I_W00_1.jpg?v=1772810718", url: "https://www.vans.cl/products/zapatillas-adulto-sk8-hi-blanco" },
  { id: "falabella:129946975", title: "GOTTA Botín Mujer", price: 26990, list: 54990, prevMin: 26990, prevMax: 54990, group: "zapatillas", img: "https://media.falabella.com/falabellaCL/129946977_01/public", url: "https://www.falabella.com/falabella-cl/product/129946975/Botin-Mujer-Cafe-35922" },
];

function normalize(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function toRow(seed: Seed, index: number): FeedRow & { title_norm: string; first_seen_at: string } {
  const webDiscount = seed.list > seed.price ? Math.round(((seed.list - seed.price) / seed.list) * 1000) / 10 : 0;
  const confirmed = seed.list > seed.price && seed.prevMax !== null && seed.prevMax >= seed.list * 0.95;
  const drop =
    seed.prevMin !== null && seed.price < seed.prevMin
      ? Math.round(((seed.prevMin - seed.price) / seed.prevMin) * 1000) / 10
      : 0;
  const now = Date.now();
  return {
    id: seed.id,
    store: seed.id.split(":")[0],
    title: seed.title,
    title_norm: normalize(seed.title),
    url: seed.url,
    image_url: seed.img,
    category: seed.group,
    category_group: seed.group,
    price: seed.price,
    list_price: seed.list,
    web_discount_pct: webDiscount,
    saving: Math.max(seed.list - seed.price, 0),
    verified_pct: Math.max(drop, confirmed ? webDiscount : 0),
    web_confirmed: confirmed,
    history_drop_pct: drop,
    points: seed.prevMax === null ? 1 : 2,
    distinct_prices: seed.prevMax === null ? 1 : 2,
    hist_min: Math.min(seed.price, seed.prevMin ?? seed.price),
    hist_max: Math.max(seed.price, seed.prevMax ?? seed.price),
    prev_min: seed.prevMin,
    prev_max: seed.prevMax,
    first_point_at: new Date(now - 14 * 3_600_000).toISOString(),
    first_seen_at: new Date(now - (index + 1) * 40 * 60_000).toISOString(),
    last_seen_at: new Date(now - (4 + (index % 9)) * 60_000).toISOString(),
  };
}

export const FIXTURE_ROWS = SEEDS.map(toRow);
