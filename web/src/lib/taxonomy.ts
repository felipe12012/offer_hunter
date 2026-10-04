// GENERADO por scripts/gen_web_taxonomy.py desde taxonomy.py. No editar a mano:
// para cambiar categorías se edita taxonomy.py y se vuelve a generar.

export const GROUPS = [
  "tecnologia",
  "zapatillas",
  "ropa",
  "belleza",
  "muebles",
  "herramientas",
  "mascotas",
  "bebes",
  "deportes",
  "accesorios",
  "automotriz",
  "otros",
] as const;
export type Group = (typeof GROUPS)[number];

export const GROUP_LABELS: Record<string, string> = {
  "tecnologia": "Tecnología",
  "zapatillas": "Zapatillas y calzado",
  "ropa": "Ropa",
  "belleza": "Belleza y salud",
  "muebles": "Hogar y muebles",
  "herramientas": "Herramientas y construcción",
  "mascotas": "Mascotas",
  "bebes": "Juguetes y bebés",
  "deportes": "Deportes y aire libre",
  "accesorios": "Accesorios y viaje",
  "automotriz": "Automotriz",
  "otros": "Otros",
};

/** Subcategorías de cada categoría, en el orden en que se muestran. */
export const SUBCATEGORIES: Record<string, Record<string, string>> = {
  "tecnologia": {
    "celulares": "Celulares",
    "computacion": "Computación e impresoras",
    "tablets": "Tablets y lectores",
    "tv": "Televisores",
    "audio": "Audio",
    "gaming": "Consolas y videojuegos",
    "camaras": "Cámaras y drones",
    "wearables": "Smartwatch y pulseras",
    "accesorios": "Cargadores y accesorios",
    "otros": "Otros de tecnología",
  },
  "zapatillas": {
    "mujer": "Mujer",
    "hombre": "Hombre",
    "ninos": "Niños",
    "bebes": "Bebés",
    "unisex": "Unisex",
    "accesorios": "Accesorios de calzado",
  },
  "ropa": {
    "mujer": "Mujer",
    "hombre": "Hombre",
    "ninos": "Niños",
    "bebes": "Bebés",
    "unisex": "Unisex",
  },
  "belleza": {
    "perfumes": "Perfumes",
    "capilar": "Cuidado capilar",
    "maquillaje": "Maquillaje",
    "facial": "Cuidado facial",
    "solar": "Protección solar",
    "cuerpo": "Cuerpo e higiene",
    "salud": "Salud y bienestar",
    "otros": "Otros de belleza",
  },
  "muebles": {
    "colchones": "Colchones y camas",
    "textil": "Ropa de cama y textil",
    "sofas": "Sofás y sillones",
    "escritorio": "Escritorio y oficina",
    "comedor": "Comedor y sillas",
    "dormitorio": "Dormitorio y clósets",
    "almacenamiento": "Repisas y organización",
    "decoracion": "Decoración e iluminación",
    "cocina": "Cocina y menaje",
    "electro": "Electrohogar",
    "otros": "Otros del hogar",
  },
  "herramientas": {
    "electricas": "Herramientas eléctricas",
    "manuales": "Herramientas manuales",
    "jardin": "Jardín y exterior",
    "construccion": "Construcción y ferretería",
    "otros": "Otras herramientas",
  },
  "mascotas": {
    "perros": "Perros",
    "gatos": "Gatos",
    "otras": "Otras mascotas y accesorios",
  },
  "bebes": {
    "juguetes": "Juguetes",
    "cuidado": "Pañales y cuidado",
    "coches": "Coches y cunas",
    "otros": "Otros de bebés",
  },
  "deportes": {
    "fitness": "Fitness",
    "ciclismo": "Ciclismo y ruedas",
    "camping": "Camping y aire libre",
    "equipos": "Pelotas y deportes de equipo",
  },
  "accesorios": {
    "bolsos": "Bolsos y mochilas",
    "maletas": "Maletas y viaje",
    "relojes": "Relojes y joyas",
    "lentes": "Lentes",
  },
  "automotriz": {
    "general": "Accesorios para el auto",
  },
  "otros": {
    "otros": "Otros",
  },
};
