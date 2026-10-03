import json
from pathlib import Path

import pytest

from priority import first_match, normalize, rules_from

CONFIG = json.loads((Path(__file__).parent.parent / "config" / "watchlist.json").read_text(encoding="utf-8"))
RULES = rules_from(CONFIG.get("priority"))


def label(title: str, category: str = "", hint: str = "", store: str = "") -> str | None:
    # `category` is accepted for readability of the cases below but is NOT part of the
    # match: for most stores it is just the search term that happened to return the product.
    return first_match(RULES, title, hint, store)


# ---- normalisation and token matching ----------------------------------------------

def test_normalize_drops_accents_case_and_punctuation():
    assert normalize("Zapatilla BEBÉ  N&D") == " zapatilla bebe n d "


def test_no_rules_means_nothing_is_priority():
    assert first_match(rules_from(None), "Zapatilla Mujer") is None
    assert first_match(rules_from({}), "Zapatilla Mujer") is None


def test_rules_from_is_cached_per_config():
    cfg = {"rules": [{"label": "x", "all": [["abc"]]}]}
    assert rules_from(cfg) is rules_from(json.loads(json.dumps(cfg)))


def test_short_tokens_match_whole_words_only():
    rules = rules_from({"rules": [{"label": "tops", "all": [["top"]]}]})
    assert first_match(rules, "Top deportivo") == "tops"
    assert first_match(rules, "Laptop gamer") is None


def test_equals_prefix_forces_a_whole_word_match_on_longer_tokens():
    rules = rules_from({"rules": [{"label": "r", "all": [["x"]], "none": ["=aros"]}]})
    assert first_match(rules, "x claros") == "r"          # 'aros' inside 'claros' is not the word
    assert first_match(rules, "x aros de plata") is None


def test_every_group_must_match_and_none_vetoes():
    rules = rules_from({"rules": [{"label": "r", "all": [["a"], ["b", "c"]], "none": ["z"]}]})
    assert first_match(rules, "a b") == "r"
    assert first_match(rules, "a c") == "r"
    assert first_match(rules, "a") is None
    assert first_match(rules, "a b z") is None


def test_the_search_term_and_the_category_hint_count_as_text():
    # Falabella titles often omit the department: "Vestido Floral Midi" found in Moda-Mujer.
    assert label("Vestido Floral Midi", category="ropa", hint="Moda Mujer") == "Ropa mujer"
    assert label("Vestido Floral Midi", category="ropa", hint="") is None


# ---- the shipped rules, with titles seen in the real stores ---------------------------

@pytest.mark.parametrize(
    "title, category, hint, expected",
    [
        ("Zapatilla Urbana Mujer Nike Air Max", "zapatillas", "", "Zapatillas mujer"),
        ("Zapatillas Dama Running Adidas", "zapatillas mujer", "", "Zapatillas mujer"),
        ("Zapatilla Running Hombre ASICS Gel", "zapatillas", "", "Zapatillas hombre"),
        ("Zapatillas Bebé Primeros Pasos", "zapatillas", "", "Zapatillas bebé"),
        ("Zapatilla Baby Converse Chuck Taylor", "converse", "", "Zapatillas bebé"),
        ("Zapatilla Nike Revolution", "zapatillas", "Zapatillas Mujer", "Zapatillas mujer"),
        ("KERASTASE Shampoo Matizador Cabello Rubio Bain Ultra-Violet Blond Absolu", "belleza", "", "Kerastase Blond"),
        ("KERASTASE Kérastase Blond Absolu Blond Guard Wonder Shield", "kerastase", "", "Kerastase Blond"),
        ("EMMA Colchón Original Basic 1 Plaza", "muebles", "", "Colchón 1 plaza"),
        ("EMMA Colchon Confort Premium 1 Plazas", "colchon", "", "Colchón 1 plaza"),
        ("Colchón Ortopédico Individual", "muebles", "", "Colchón 1 plaza"),
        ("Tablet Samsung Galaxy Tab A9 64GB", "tablet", "", "Tablet"),
        ("iPad 10ª generación 64GB", "tecnologia", "", "Tablet"),
        ("Polera Mujer Algodón Básica", "ropa", "", "Ropa mujer"),
        ("Polera Básica Algodón", "ropa", "Poleras Hombre", "Ropa hombre"),
        ("Jeans Hombre Slim Fit", "ropa", "", "Ropa hombre"),
        ("PlayStation 5 Slim Digital Edition", "tecnologia", "Consolas", "Consolas"),
        ("Consola Nintendo Switch OLED", "consola", "", "Consolas"),
        ("God of War Ragnarök PS5", "tecnologia", "Videojuegos", "Videojuegos"),
        ("N&D NyD Pumpkin Gato Adulto Salmón Calabaza y Naranja 1,5Kg", "mascotas", "", "Comida gato NYD"),
        ("Farmina N&D Prime Gato Pollo 5Kg", "comida gato nyd", "", "Comida gato NYD"),
    ],
)
def test_priority_titles_are_recognised(title, category, hint, expected):
    assert label(title, category, hint) == expected


@pytest.mark.parametrize(
    "title, category, hint",
    [
        ("KERASTASE Shampoo Nutritive Bain Satin", "belleza", ""),                    # not Blond
        ("Cubrecolchón 1 Plaza Impermeable", "muebles", ""),                           # not a mattress
        ("Colchón 2 Plazas Ortopédico", "muebles", ""),                                # wrong size
        ("Colchón Cuna 1 Plaza", "muebles", ""),
        ("Funda para Tablet 10 pulgadas", "tablet", ""),                               # accessory
        ("Lápiz Óptico para Tablet", "tablet", ""),
        ("Consola Recibidor Madera Natural", "muebles", ""),                           # furniture
        ("Control Inalámbrico DualSense", "tecnologia", "Consolas"),                   # accessory
        ("Cartera Mujer Cuero", "ropa", "Moda Mujer"),                                 # accessory
        ("Perfume Mujer Floral 100ml", "belleza", ""),
        # real false positives seen when the search term was part of the text:
        ("Mocasin Mujer Inees Negro Hush Puppies", "zapatillas mujer", ""),
        ("Calcetin Algodón Hombre Cocktail Café Hush Puppies", "zapatillas hombre", ""),
        ("Alimento Para Gato Adulto Trigono 10kg", "comida gato nyd", ""),
        ("Churu Gato Sabor Atún 24 Unidades", "comida gato nyd", ""),
        ("Serum Blonde Life 150 ML Joico", "kerastase blond", ""),
        ("Sosten Copa Minimizer Blonda Flores", "kerastase blond", ""),
        ("Cama Europea 1 Plaza Luna 90x190 Cm Base Colchón Madera Rosa", "colchon 1 plaza", ""),
        ("Zueco Bebés Recién Nacidos Azul Crocs", "zapatillas bebe", ""),
        ("EXIT Clóset Verona 4 Puertas Ripado Correderas Metalicas 200x120x47", "tablet", ""),     # 'ipad' inside 'ripado'
        ("GAMESIR Control X5 Lite para iPhone 15 16, Android y iPad Mini. Sticks de Efecto", "tablet", ""),
        ("Consola Power Mixer Ct-4 Ch Mavi", "consola", ""),                                          # audio console
        ("Consola Podcast Multipista Portátil N-live Nai-33l Nux", "consola", ""),
        ("N&D Prime Perro Adulto Cordero 7Kg", "mascotas", ""),                        # dog food
        ("Taladro Percutor 650W", "herramientas", ""),
        ("Notebook HP 15 Ryzen 7", "tecnologia", ""),
    ],
)
def test_similar_but_unwanted_products_are_not_priority(title, category, hint):
    assert label(title, category, hint) is None


def test_baby_shoes_win_over_the_gender_rules():
    assert label("Zapatilla Bebé Niña Mujer Mini", "zapatillas", "") == "Zapatillas bebé"


def test_a_console_is_labelled_console_not_video_game():
    assert label("Consola PlayStation 5", "tecnologia", "") == "Consolas"


def test_a_mens_shoe_is_not_labelled_as_womens():
    assert label("Zapatilla Hombre Nike", "zapatillas", "") == "Zapatillas hombre"


def test_the_search_term_alone_never_makes_a_product_priority():
    # Stores return loosely related results for any query; only the product's own title
    # (and the store's real department name) may say what it is.
    assert label("Calcetin Mujer Algodón", category="zapatillas mujer") is None
    assert label("Alimento Para Gato Adulto Ekos 16kg", category="comida gato nyd") is None


def test_kerastase_blond_line_is_recognised_by_its_rubio_decolorado_wording():
    assert label("KERASTASE Acondicionador Reparación Profunda Cabello Rubio O Decolorado Cicaflash") == "Kerastase Blond"


def test_pharmacy_tablets_are_not_tablet_computers():
    assert label("Vitamina C 500 mg 60 tablets", store="ahumada") is None
    assert label("Tablet Samsung Galaxy Tab A9", store="hites") == "Tablet"
