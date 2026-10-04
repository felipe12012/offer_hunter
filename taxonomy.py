"""Product taxonomy: category and subcategory of an offer, decided from its title.

The `category` the stores give us is the keyword the scanner searched for ("nike", "perro",
"muebles"), not what the product is: a Nike search returns hand cream, a furniture page returns
bowls. So the title decides; the scanner's keyword and the store are only hints for what the
title does not say.

`classify` returns (group, subcategory) as slugs. The web keeps the Spanish labels
(web/src/lib/taxonomy.ts) and must list the same slugs. Adding a rule here is all it takes: the
next scan re-classifies every product it sees.
"""

from __future__ import annotations

import re
import unicodedata

GROUPS: dict[str, str] = {
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
}

SUBCATEGORIES: dict[str, dict[str, str]] = {
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
    "automotriz": {"general": "Accesorios para el auto"},
    "otros": {"otros": "Otros"},
}


def normalize(text: str) -> str:
    """Lowercase and strip accents ("Colchón" -> "colchon"), like the web's search does."""
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").lower()


def _words(*alternatives: str) -> re.Pattern:
    """Match any of the alternatives as whole words (an alternative may hold regex pieces)."""
    return re.compile(r"\b(?:" + "|".join(alternatives) + r")\b")


# ---- who it is for -----------------------------------------------------------------------------

_BABY = _words("bebe", "bebes", "baby", "recien nacido", "lactante", "infant")
_KIDS = _words(
    "nino", "nina", "ninos", "ninas", "kids?", "junior", "infantil", "infantiles", "escolar",
    "juvenil", "boys?", "girls?",
)
_WOMEN = _words("mujer", "mujeres", "dama", "damas", "femenino", "femenina", "women", "womens", "woman", "lady", "ladies")
_MEN = _words("hombre", "hombres", "caballero", "caballeros", "masculino", "masculina", "men", "mens", "man")


def _audience(t: str) -> str:
    if _BABY.search(t):
        return "bebes"
    if _KIDS.search(t):
        return "ninos"
    if _WOMEN.search(t):
        return "mujer"
    if _MEN.search(t):
        return "hombre"
    return "unisex"


# ---- pets ----------------------------------------------------------------------------------------

_PET_STORES = {"tusmascotas", "laikamascotas"}
_PET = _words(
    "perro", "perros", "gato", "gatos", "canino", "caninos", "felino", "felinos", "mascota", "mascotas",
    "cachorro", "cachorros", "arena sanitaria", "arena para gatos?", "rascador", "rascadores", "antipulgas", "pets?",
)
_DOG = _words("perro", "perros", "canino", "caninos", "cachorro", "cachorros", "dogs?")
_CAT = _words("gato", "gatos", "felino", "felinos", "cats?", "kitten", "arena sanitaria", "arena", "rascador", "rascadores")

# ---- footwear ------------------------------------------------------------------------------------

_FOOT = _words(
    "zapatilla", "zapatillas", "zapato", "zapatos", "sandalia", "sandalias", "bota", "botas", "botin", "botines",
    "mocasin", "mocasines", "crocs", "pantufla", "pantuflas", "ojota", "ojotas", "zueco", "zuecos", "slip on",
    "sliders?", "sneakers?", "bototo", "bototos", "calzado", "baleta", "baletas", "alpargata", "alpargatas",
    "jibbitz", "chalas",
)
_FOOT_ACCESSORY = _words("jibbitz", "plantillas?", "cordones", "limpiador de zapatos", "betun")
_SHOE_BRAND_STORES = {"skechers", "crocs", "hushpuppies", "merrell", "vans", "salomon"}

# ---- home textile (before clothing: "manta polar" is bedding) -------------------------------------

_BED_TEXTILE = _words(
    "sabana", "sabanas", "plumon", "plumones", "edredon", "edredones", "cubrecama", "cobertor", "frazada",
    "frazadas", "manta", "mantas", "almohada", "almohadas", "duvet", "funda nordica", "sobrecama",
    "calientacamas", "ropa de cama", "cubrecolchon", "protector de colchon", "faldon", "toalla", "toallas",
    "cortina", "cortinas", "alfombra", "alfombras", "cojin", "cojines", "cubre cojin", "mantel", "manteles",
)

# ---- clothing ------------------------------------------------------------------------------------

_CLOTHES = _words(
    "polera", "poleras", "poleron", "polerones", "camisa", "camisas", "blusa", "blusas", "pantalon",
    "pantalones", "jeans?", "shorts?", "bermudas?", "falda", "faldas", "vestido", "vestidos", "chaqueta",
    "chaquetas", "parkas?", "abrigo", "abrigos", "chaleco", "chalecos", "sweater", "sueter", "cardigan",
    "buzo", "buzos", "calzas?", "leggings?", "pijamas?", "ropa", "boxers?", "calzoncillos?", "sosten",
    "bikinis?", "jockey", "gorro", "gorros", "bufanda", "guantes", "cinturon", "cinturones", "calcetin",
    "calcetines", "calcetas?", "medias", "pantys?", "panties", "cortaviento", "impermeable", "tricota",
    "enterito", "jumper", "overol", "corbata", "traje", "camiseta", "camisetas", "bata", "casaca", "bluson",
    "chomba", "trusa", "brasier", "sujetador", "polar", "ponchos?", "short",
)

# ---- beauty and health ---------------------------------------------------------------------------

_BEAUTY_RULES: list[tuple[str, re.Pattern]] = [
    ("perfumes", _words("perfume", "perfumes", "eau de parfum", "eau de toilette", "colonia", "edp", "edt", "fragancia", "parfum", "body splash")),
    ("solar", _words("protector solar", "bloqueador", "fps[0-9]*", "spf[0-9]*", "after sun", "bronceador")),
    ("maquillaje", _words(
        "maquillaje", "labial", "labiales", "rimel", "delineador", "sombra de ojos", "sombras", "rubor", "corrector",
        "iluminador", "polvo compacto", "gloss", "esmalte", "esmaltes", "paleta de sombras", "brochas?", "pestanas",
        "mascara de pestanas", "base de maquillaje", "cejas",
    )),
    ("cuerpo", _words(
        "desodorante", "desodorantes", "antitranspirante", "jabon", "jabones", "crema corporal", "locion", "manos",
        "pies", "depilacion", "depilatoria", "afeitado", "afeitar", "rasuradora", "maquinilla", "pasta dental",
        "cepillo dental", "cepillo de dientes", "enjuague bucal", "higiene", "toallitas humedas", "aceite corporal",
        "gel de ducha", "body lotion", "corporal", "intimo", "toalla higienica", "protectores diarios", "tampones",
        "panal de adulto",
    )),
    ("capilar", _words(
        "shampoo", "champu", "acondicionador", "mascarilla capilar", "serum capilar", "tratamiento capilar",
        "kerastase", "cabello", "capilar", "keratina", "tintura", "tinte", "protector termico", "secador de pelo",
        "plancha de pelo", "alisador", "alisadora", "ampolla capilar", "spray fijador", "cera capilar", "cuero cabelludo",
        "anticaspa", "anti-?caspa", "caspa", "fitoshampoo", "fijador", "pomada", "gel fijador", "termoprotector",
        "frizz", "oleo", "bond",
    )),
    ("facial", _words(
        "facial", "rostro", "crema hidratante", "serum", "limpiador", "limpiadora", "micelar", "tonico", "retinol",
        "acido hialuronico", "niacinamida", "vitamina c", "contorno de ojos", "antiarrugas", "anti edad",
        "mascarilla", "exfoliante", "balsamo", "acne", "dermo", "cerave", "vichy", "la roche", "eucerin", "avene", "isdin",
        "crema", "colageno cosmetico", "hidratante", "cleanser", "gel limpiador",
    )),
    ("salud", _words(
        "vitamina", "vitaminas", "suplemento", "suplementos", "proteina", "colageno", "omega", "magnesio",
        "probiotico", "jarabe", "paracetamol", "ibuprofeno", "termometro", "tensiometro", "alcohol gel",
        "curitas?", "apositos", "multivitaminico", "creatina", "oximetro", "nebulizador", "comprimidos", "capsulas", "tabletas", "gotas", "ampollas",
        "[0-9]+ ?mg", "protesis",
    )),
]

# ---- technology ----------------------------------------------------------------------------------

_EYEWEAR = re.compile(r"\b(?:lentes? (?:de sol|opticos?|de contacto|de lectura|fotocromaticos?)|gafas)\b")
_TECH_RULES: list[tuple[str, re.Pattern]] = [
    ("accesorios", re.compile(
        r"\b(?:cargador|cargadores|power ?bank|bateria externa|pendrive|microsd|mouse|teclado|webcam|mousepad|stylus|lapiz optico|"
        r"carcasas?|protector de pantalla|mica|tarjeta de memoria|control remoto)\b"
        r"|\bcable (?:usb|hdmi|lightning|tipo c|usb-c|de carga|displayport)\b"
        r"|\badaptador (?:usb|hdmi|tipo c|de corriente)\b"
        r"|\bfundas? (?:para|de) (?:celular|tablet|iphone|notebook|laptop|ipad|samsung|airpods)\b"
        r"|\bsoporte (?:para )?(?:celular|notebook|tablet|monitor|tv|laptop)\b"
    )),
    ("wearables", _words(
        "smartwatch", "smartwatches", "reloj inteligente", "smartband", "smart band", "banda inteligente", "apple watch",
        "galaxy watch", "amazfit", "garmin", "fitbit", "pulsera inteligente", "watch (?:gt|fit|se|ultra|series)",
    )),
    ("audio", _words(
        "audifono", "audifonos", "auricular", "auriculares", "parlante", "parlantes", "barra de sonido", "soundbar",
        "altavoz", "microfono", "microfonos", "earbuds", "airpods", "buds", "headset", "headphones", "home theater",
        "radio", "bocina", "bocinas", "karaoke", "equipo de musica", "tocadiscos", "tws", "minicomponente",
    )),
    ("tablets", _words("tablet", "tablets", "ipad", "galaxy tab", "kindle", "e-?reader", "lector de libros")),
    ("tv", re.compile(r"\b(?:tv|televisor|televisores|smart tv)\b")),
    ("celulares", re.compile(
        r"\b(?:celular|celulares|smartphone|smartphones|iphone|galaxy [asmzf][0-9]+|redmi|xiaomi|motorola|realme|"
        r"oppo|infinix|zte|honor [0-9x]+|poco [a-z][0-9]+|moto [gec][0-9]+)\b"
    )),
    ("computacion", _words(
        "notebook", "notebooks", "laptop", "laptops", "macbook", "chromebook", "computador", "computadores",
        "computadora", "pc", "pcs", "all in one", "monitor", "monitores", "impresora", "impresoras", "multifuncional",
        "tintas?", "toner", "escaner", "router", "modem", "disco duro", "ssd", "tarjeta de video", "gabinete",
        "placa madre", "procesador", "proyector", "servidor", "workstation",
    )),
    ("camaras", _words(
        "camara", "camaras", "gopro", "dron", "drones", "drone", "lente", "lentes", "tripode", "instax", "fotografica",
        "dslr", "mirrorless", "camcorder", "filmadora", "canon", "eos",
    )),
    ("gaming", _words(
        "playstation", "ps5", "ps4", "ps3", "ps2", "xbox", "nintendo", "consola", "consolas", "videojuego",
        "videojuegos", "joystick", "gamepad", "dualsense", "dualshock", "steam deck", "fifa", "zelda", "mario",
        "pokemon", "call of duty", "minecraft", "gta", "nba 2k", "fc 2[0-9]", "rog ally", "oculus", "meta quest",
        "realidad virtual", "gamer", "gaming",
    )),
]

# ---- tools ---------------------------------------------------------------------------------------

_TOOL_RULES: list[tuple[str, re.Pattern]] = [
    ("electricas", _words(
        "taladro", "taladros", "atornillador", "sierra", "sierras", "esmeril", "lijadora", "rotomartillo", "fresadora",
        "tupi", "tronzadora", "soldadora", "compresor", "termofusora", "pistola de calor", "pistola neumatica",
        "generador", "multiherramienta", "caladora", "amoladora", "sopladora", "clavadora", "engrapadora",
        "cepillo electrico", "bateria 1[28] ?v", "bateria 20 ?v", "inalambrico percutor",
    )),
    ("jardin", _words(
        "manguera", "mangueras", "riego", "cortacesped", "podadora", "desmalezadora", "motosierra", "parrilla",
        "parrillas", "asador", "asadores", "piscina", "piscinas", "rastrillo", "carretilla", "hidrolavadora",
        "fertilizante", "macetero", "macetas?", "pergola", "toldo", "quincho", "regadera",
    )),
    ("manuales", _words(
        "set de herramientas", "herramientas", "herramienta", "llave", "llaves", "alicate", "alicates", "martillo",
        "destornillador", "destornilladores", "serrucho", "nivel", "huincha", "caja de herramientas", "tenaza",
        "cinta metrica", "formon", "escuadra", "cincel", "mazo", "espatula", "plomada", "tronzador",
    )),
    ("construccion", _words(
        "pintura", "rodillo", "cemento", "adhesivo", "silicona", "piso", "pisos", "ceramica", "porcelanato",
        "cerradura", "candado", "bisagra", "tornillo", "tornillos", "clavo", "clavos", "perno", "pernos", "taco",
        "enchufe", "interruptor", "grifo", "griferia", "ducha", "lavamanos", "wc", "inodoro", "tuberia", "puerta",
        "ventana", "barniz", "sellador", "yeso", "tablero", "zinc", "cable electrico", "lavaplatos", "lavaplato",
    )),
]

# ---- sports --------------------------------------------------------------------------------------

_SPORT_RULES: list[tuple[str, re.Pattern]] = [
    ("camping", _words(
        "camping", "carpa", "carpas", "saco de dormir", "trekking", "pesca", "kayak", "reposera", "reposeras",
        "silla plegable", "cooler", "hielera", "picnic", "linterna", "mochila de trekking", "colchoneta inflable",
    )),
    ("ciclismo", _words(
        "bicicleta", "bicicletas", "bici", "casco de bicicleta", "patin", "patines", "skate", "skateboard",
        "scooter", "monopatin", "rollers", "longboard",
    )),
    ("fitness", _words(
        "mancuerna", "mancuernas", "pesa", "pesas", "kettlebell", "trotadora", "bicicleta estatica", "eliptica",
        "colchoneta", "yoga", "banda elastica", "multigimnasio", "rueda abdominal", "cuerda para saltar", "pilates",
        "foam roller", "gimnasio",
    )),
    ("equipos", _words(
        "futbol", "balon", "balones", "pelota", "pelotas", "raqueta", "raquetas", "basquetbol", "voleibol",
        "ping pong", "natacion", "goggles", "padel", "golf", "boxeo", "saco de boxeo", "dardos", "canilleras",
    )),
]

# ---- home ----------------------------------------------------------------------------------------

_HOME_RULES: list[tuple[str, re.Pattern]] = [
    ("electro", _words(
        "refrigerador", "refrigeradores", "frigobar", "congelador", "lavadora", "lavadoras", "secadora", "lavasecadora",
        "microondas", "horno", "hornos", "encimera", "campana", "aspiradora", "aspiradoras", "robot aspirador",
        "estufa", "estufas", "calefactor", "calefactores", "ventilador", "ventiladores", "aire acondicionado",
        "calefont", "purificador", "humidificador", "deshumidificador", "plancha a vapor", "plancha de ropa",
        "freidora", "freidoras", "cafetera", "cafeteras", "licuadora", "licuadoras", "hervidor", "hervidores",
        "batidora", "tostador", "sandwichera", "procesadora", "olla arrocera", "extractor", "dispensador de agua",
        "lavavajillas", "air fryer",
    )),
    ("colchones", _words(
        "colchon", "colchones", "cama", "camas", "box spring", "somier", "sommier", "topper", "base cama", "respaldo",
        "camarote", "cama nido", "divan", "europea", "super king", "king size", "plazas", "plaza y media",
    )),
    ("textil", _BED_TEXTILE),
    ("sofas", _words("sofa", "sofas", "sillon", "sillones", "puff", "poltrona", "poltronas", "chaise", "seccional", "juego de living", "living", "terraza")),
    ("escritorio", _words(
        "escritorio", "escritorios", "reposapies", "silla de oficina", "silla gamer", "silla ergonomica", "sillon gamer",
        "silla de escritorio", "librero", "libreros", "biblioteca", "archivador", "mesa de computador",
        "estacion de trabajo",
    )),
    ("dormitorio", _words(
        "comoda", "comodas", "velador", "veladores", "mesa de noche", "closet", "ropero", "zapatero", "cajonera",
        "sinfonier", "perchero", "tocador", "organizador de ropa",
    )),
    ("comedor", _words(
        "comedor", "comedores", "mesa", "mesas", "silla", "sillas", "taburete", "taburetes", "banca", "bancas",
        "banco", "bancos", "aparador", "vitrina", "trinchador", "juego de comedor",
    )),
    ("almacenamiento", _words(
        "repisa", "repisas", "estanteria", "estanterias", "estante", "estantes", "organizador", "organizadores",
        "rack", "cesto", "canasto", "caja organizadora", "ganchos?", "colgador", "mueble", "muebles", "modular",
        "bodega", "gabinete",
    )),
    ("decoracion", _words(
        "lampara", "lamparas", "ampolleta", "ampolletas", "luminaria", "aplique", "espejo", "espejos", "cuadro",
        "cuadros", "decoracion", "decorativo", "decorativa", "florero", "jarron", "vela", "velas", "reloj de pared",
        "guirnalda", "cinta led", "foco", "foco led",
    )),
    ("cocina", _words(
        "olla", "ollas", "sarten", "sartenes", "cuchillo", "cuchillos", "bowl", "bowls", "plato", "platos", "vaso",
        "vasos", "taza", "tazas", "cubiertos", "tabla de picar", "taper", "tapers", "botella", "termo", "jarro",
        "fuente", "molde", "bandeja", "menaje", "bateria de cocina", "vajilla", "copa", "copas", "colador",
        "rallador", "exprimidor", "tetera", "pocillo", "set de cocina", "panera", "stanley", "mate",
    )),
]
# ---- accessories ---------------------------------------------------------------------------------

_ACCESSORY_RULES: list[tuple[str, re.Pattern]] = [
    ("lentes", _EYEWEAR),
    ("maletas", _words("maleta", "maletas", "valija", "equipaje", "candado tsa", "cubre maleta", "organizador de viaje")),
    ("bolsos", _words(
        "mochila", "mochilas", "bolso", "bolsos", "cartera", "carteras", "billetera", "billeteras", "rinonera",
        "morral", "bandolera", "tote", "neceser", "lonchera",
    )),
    ("relojes", _words(
        "reloj", "relojes", "anillo", "anillos", "collar", "collares", "pulsera", "pulseras", "aros", "arete",
        "aretes", "joyas", "joyero", "cadena", "dije", "colgante",
    )),
]

# ---- automotive, babies and toys -----------------------------------------------------------------

_AUTO = _words(
    "neumatico", "neumaticos", "bateria de auto", "aceite de motor", "limpiaparabrisas", "cubreasiento",
    "cubre asiento", "alfombra para auto", "cargador de auto", "aspiradora para auto", "gato hidraulico",
    "compresor de aire", "portaequipaje", "dashcam", "casco de moto", "para auto", "de auto", "para vehiculo",
    "automotriz", "llantas?", "bencina", "bateria 12 ?v", "parlante para auto",
)
_BABY_RULES: list[tuple[str, re.Pattern]] = [
    ("cuidado", _words(
        "panal", "panales", "toallitas humedas", "formula infantil", "leche infantil", "mamadera", "mamaderas",
        "biberon", "biberones", "chupete", "chupetes", "sacaleche", "talco", "cambiador", "esterilizador",
    )),
    ("coches", _words(
        "coche", "coches", "silla de auto", "portabebe", "cuna", "cunas", "corral", "moises", "barandas", "trona",
        "silla alta", "andador", "monitor de bebe",
    )),
    ("juguetes", _words(
        "juguete", "juguetes", "lego", "muneca", "munecas", "peluche", "peluches", "puzzle", "rompecabeza",
        "rompecabezas", "didactico", "bloques", "juego de mesa", "hot wheels", "barbie", "funko", "disfraz", "slime",
        "plastilina", "pista de carreras", "playmobil", "nerf", "figura de accion",
    )),
]


_TV_FURNITURE = _words("mueble", "muebles", "rack", "repisa", "panel", "centro de entretenimiento")

# Sub when only the scanner keyword tells the group.
_FALLBACK_SUB = {"zapatillas": "unisex", "ropa": "unisex", "mascotas": "otras"}


def _first(t: str, rules: list[tuple[str, re.Pattern]]) -> str | None:
    for sub, pattern in rules:
        if pattern.search(t):
            return sub
    return None


# Old scanner-keyword mapping, used only when the title says nothing (kept so nothing regresses).
_CATEGORY_HINTS: list[tuple[str, re.Pattern]] = [
    ("zapatillas", re.compile(r"zapat|adidas|nike|puma|skechers|converse|vans|reebok|new balance|fila|topper|asics|crocs|salomon|merrell|hush")),
    ("ropa", re.compile(r"ropa|polera|pantal|chaqueta|vestido|jeans|buzo|parka|abrigo|moda")),
    ("belleza", re.compile(r"kerastase|redken|belleza|crema|facial|dermo|hidratante|solar|serum|micelar|acido|vitamina|retinol|roche|cerave|vichy|eucerin|avene|isdin|perfume|maquillaje|blond|capilar")),
    ("mascotas", re.compile(r"mascota|perro|gato|nyd|n&d|alimento|arena|snack")),
    ("muebles", re.compile(r"colchon|mueble|sillon|sofa|cama|escritorio|comedor|living|closet")),
    ("tecnologia", re.compile(r"tecnolog|notebook|tablet|audifono|sony|parlante|televis|smart tv|celular|consola|monitor|videojuego|computador|smartphone")),
    ("herramientas", re.compile(r"herramienta|taladro")),
]


def classify(title: str, category: str = "", store: str = "") -> tuple[str, str]:
    """(group, subcategory) of a product. Always returns slugs listed in GROUPS / SUBCATEGORIES."""
    t = normalize(title)
    cat = normalize(category)

    # Pets: the title or a pet-only store.
    if store in _PET_STORES or _PET.search(t):
        if _DOG.search(t):
            return "mascotas", "perros"
        if _CAT.search(t):
            return "mascotas", "gatos"
        if _DOG.search(cat):
            return "mascotas", "perros"
        if _CAT.search(cat):
            return "mascotas", "gatos"
        return "mascotas", "otras"

    # Footwear.
    shoe_store_default = (
        store in _SHOE_BRAND_STORES and not _CLOTHES.search(t) and _first(t, _ACCESSORY_RULES) is None
    )
    if _FOOT.search(t) or shoe_store_default:
        if _FOOT_ACCESSORY.search(t):
            return "zapatillas", "accesorios"
        return "zapatillas", _audience(t)

    # Bedding and curtains before clothing ("manta polar", "cortina").
    if _BED_TEXTILE.search(t):
        return "muebles", "textil"

    if _CLOTHES.search(t):
        return "ropa", _audience(t)

    for sub, pattern in _BEAUTY_RULES:
        if pattern.search(t):
            return "belleza", sub

    if _EYEWEAR.search(t):
        return "accesorios", "lentes"

    sub = _first(t, _TECH_RULES)
    if sub == "tv" and _TV_FURNITURE.search(t):
        return "muebles", "almacenamiento"
    if sub:
        return "tecnologia", sub

    sub = _first(t, _TOOL_RULES)
    if sub:
        return "herramientas", sub

    sub = _first(t, _SPORT_RULES)
    if sub:
        return "deportes", sub

    sub = _first(t, _HOME_RULES)
    if sub:
        return "muebles", sub

    sub = _first(t, _ACCESSORY_RULES)
    if sub:
        return "accesorios", sub

    if _AUTO.search(t):
        return "automotriz", "general"

    sub = _first(t, _BABY_RULES)
    if sub:
        return "bebes", sub

    # The title says nothing: fall back to the scanner keyword.
    for group, pattern in _CATEGORY_HINTS:
        if pattern.search(cat):
            return group, _FALLBACK_SUB.get(group, "otros")
    return "otros", "otros"
