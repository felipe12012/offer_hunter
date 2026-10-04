import pytest

from models import Deal
from supabase_sync import _deal_row
from taxonomy import GROUPS, SUBCATEGORIES, classify, normalize

# (title, scanner keyword, store) -> (group, subcategory). Real titles that the keyword alone got wrong.
CASES = [
    ("Dove Desodorante Serum Roll-on Niacinamida", "nike", "ahumada", ("belleza", "cuerpo")),
    ("Crema Manos Aloe Vera Nivea 75mL", "nike", "ahumada", ("belleza", "cuerpo")),
    ("KERASTASE Shampoo Anti Caída Bain Prévention", "kerastase", "falabella", ("belleza", "capilar")),
    ("Serum Isdin Eryfotona Night 50 mL", "serum", "ahumada", ("belleza", "facial")),
    ("DKNY PERFUME BE DELICIOUS MUJER EDP 100 ML", "belleza", "falabella", ("belleza", "perfumes")),
    ("Compacto Color Arena Spf50 Pieles Intolerantes", "avene", "cruzverde", ("belleza", "solar")),
    ("TVILUM Cómoda 8 Cajones Pepe 140x82x40 cm Blanco", "ropa", "sodimac", ("muebles", "dormitorio")),
    ("Manta Infantil De Polar Con Capucha", "ropa", "sodimac", ("muebles", "textil")),
    ("DRIMKIP Colchón Bebé 70x140 cm", "muebles", "sodimac", ("muebles", "colchones")),
    ("CIC Colchón Excellence Plus 1 Plaza X 2.00Mt", "colchon 1 plaza", "falabella", ("muebles", "colchones")),
    ("CLEMS Escritorio Funcional Altura Ajustable", "muebles", "sodimac", ("muebles", "escritorio")),
    ("Mueble para TV Rack 160cm", "", "sodimac", ("muebles", "almacenamiento")),
    ("TCL Smart TV 65\" QLED 4K T6C Google TV", "tecnologia", "sodimac", ("tecnologia", "tv")),
    ("Galaxy Tab S11 Gris 128 Gb", "tablet", "hites", ("tecnologia", "tablets")),
    ("Tabletas Corega Limpiadoras de Prótesis Dentales", "tablet", "ahumada", ("belleza", "salud")),
    ("NINTENDO Fire Emblem: Fortune Weave Collection SW2", "tecnologia", "falabella", ("tecnologia", "gaming")),
    ("Playstation 5 Slim Digital", "consola", "falabella", ("tecnologia", "gaming")),
    ("Parlante Jbl Flip 7 Color Azul", "parlante", "hites", ("tecnologia", "audio")),
    ("Cargador Para iPhone 3 En 1 Inalámbrico", "tecnologia", "sodimac", ("tecnologia", "accesorios")),
    ("BOSCH Taladro Percutor GSB 18V-65 + 2 Baterías", "herramientas", "sodimac", ("herramientas", "electricas")),
    ("FILA Zapatilla Alpha Ray Mujer Blanco", "fila", "falabella", ("zapatillas", "mujer")),
    ("Zapatilla Adidas Breaknet 3.0 Hombre Junior Negro", "", "hites", ("zapatillas", "ninos")),
    ("Zapatillas Bebé Primeros Pasos", "", "falabella", ("zapatillas", "bebes")),
    ("Jibbitz Pelota Rugby Café Crocs", "", "crocs", ("zapatillas", "accesorios")),
    ("Pantalón Deportivo Unisex Puma", "puma", "lapolar", ("ropa", "unisex")),
    ("Polera Hombre Skuad", "jeans", "hites", ("ropa", "hombre")),
    ("LIPPI Chaqueta Niña Little Urban Steam-Pro", "ropa", "falabella", ("ropa", "ninos")),
    ("Leonardo - Alimento para Gato Adulto", "alimento gato", "laikamascotas", ("mascotas", "gatos")),
    ("KERU Comedero bebedero Para Perros", "muebles", "sodimac", ("mascotas", "perros")),
    ("Dentalife - Snack Dental Adultos Razas Medianas", "perro", "laikamascotas", ("mascotas", "perros")),
    ("JUGUETE STAY WILD PACK 2 PECES", "juguete", "tusmascotas", ("mascotas", "otras")),
    ("Fórmula Infantil Nan Prematuros 400 g", "alimento perro", "ahumada", ("bebes", "cuidado")),
    ("Silla Plegable De Playa Camping Pesca", "muebles", "sodimac", ("deportes", "camping")),
    ("Mochila Escolar 20 Litros", "", "falabella", ("accesorios", "bolsos")),
    ("Cartera Ecocuero Mujer Bratt Tote Negro Hush Puppies", "zapatillas", "hushpuppies", ("accesorios", "bolsos")),
    ("Slip On Cuero Hombre Jenson Café", "zapatillas", "hushpuppies", ("zapatillas", "hombre")),
]


@pytest.mark.parametrize("title,category,store,expected", CASES)
def test_classifies_by_the_title_not_by_the_scanner_keyword(title, category, store, expected):
    assert classify(title, category, store) == expected


def test_a_title_that_says_nothing_falls_back_to_the_scanner_keyword():
    assert classify("Producto sin descripción", "colchon 1 plaza", "hites") == ("muebles", "otros")
    assert classify("Producto sin descripción", "", "falabella") == ("otros", "otros")


def test_every_result_is_a_known_group_and_subcategory():
    for title, category, store, _ in CASES:
        group, sub = classify(title, category, store)
        assert group in GROUPS
        assert sub in SUBCATEGORIES[group]


def test_every_group_has_subcategories_and_a_label():
    assert set(GROUPS) == set(SUBCATEGORIES)
    assert all(SUBCATEGORIES[g] for g in GROUPS)


def test_normalize_strips_accents():
    assert normalize("Colchón Bebé") == "colchon bebe"


def test_deal_rows_carry_the_classification():
    deal = Deal(
        id="falabella:1", title="FILA Zapatilla Alpha Ray Mujer Blanco", url="https://x", store="falabella",
        category="fila", price=1, list_price=2, discount_pct=50.0, scraped_at="2026-10-04T00:00:00+00:00",
        image_url="",
    )
    row = _deal_row(deal)
    assert (row["grp"], row["subcat"]) == ("zapatillas", "mujer")
