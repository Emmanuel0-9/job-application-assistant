"""Pruebas de src/scraper.py — la parte que consume datos que no controlamos.

Los scrapers leen HTML y JSON de once portales ajenos. Ninguno garantiza su
formato: cambian el HTML, devuelven un error donde debería ir una lista, mandan
el salario como la palabra "negociable" o un campo en null. Cada prueba de aquí
es una de esas formas de romperse.

No se hace ninguna petición de red: se le pasa a las funciones lo que la red
habría devuelto.

Correr:  python -m pytest tests/test_scraper.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from bs4 import BeautifulSoup

from src.scraper import _clean, _entero_o_none, _first


# ── _first: el respaldo de selectores tiene que respaldar de verdad ────────────

def _soup(html):
    return BeautifulSoup(html, "lxml").div


def test_first_devuelve_el_texto_del_primer_selector():
    el = _soup('<div><h2 class="a">Backend Developer</h2></div>')
    assert _first(el, "h2.a", "h2.b") == "Backend Developer"


def test_first_pasa_al_siguiente_selector_si_el_primero_no_existe():
    el = _soup('<div><h2 class="b">Data Engineer</h2></div>')
    assert _first(el, "h2.a", "h2.b") == "Data Engineer"


def test_first_pasa_al_siguiente_si_el_primero_coincide_pero_esta_vacio():
    """Regresión: antes devolvía "" y ni probaba el respaldo. Se perdía el título."""
    el = _soup('<div><h2 class="a">   </h2><h2 class="b">Data Engineer</h2></div>')
    assert _first(el, "h2.a", "h2.b") == "Data Engineer"


def test_first_pasa_al_siguiente_si_al_primero_le_falta_el_atributo():
    """Regresión: el caso más caro, porque se perdía la URL de la oferta."""
    el = _soup('<div><a class="a">Ver</a><a class="b" href="/oferta/1">Ver</a></div>')
    assert _first(el, "a.a", "a.b", attr="href") == "/oferta/1"


def test_first_no_revienta_con_atributos_multivaluados():
    """BeautifulSoup devuelve una lista en class/rel; .strip() fallaba."""
    el = _soup('<div><a class="uno dos" href="/x">Ver</a></div>')
    assert _first(el, "a", attr="class") == "uno dos"


def test_first_devuelve_vacio_si_ningun_selector_sirve():
    el = _soup("<div><span>nada</span></div>")
    assert _first(el, "h2.a", "h2.b") == ""


def test_first_normaliza_espacios():
    el = _soup("<div><h2>Dev   \n  Python</h2></div>")
    assert _first(el, "h2") == "Dev Python"


# ── _entero_o_none: los portales mandan el salario en cualquier formato ────────

@pytest.mark.parametrize("entrada, esperado", [
    (80000,        80000),
    ("80000",      80000),
    ("80,000",     80000),
    ("$80,000",    80000),
    ("  80000  ",  80000),
    (80000.0,      80000),
    ("80000.50",   80000),
])
def test_entero_o_none_convierte_lo_convertible(entrada, esperado):
    assert _entero_o_none(entrada) == esperado


@pytest.mark.parametrize("basura", ["negociable", "", None, "a convenir", [], {}, "N/A"])
def test_entero_o_none_devuelve_none_en_vez_de_reventar(basura):
    """Regresión: un int() directo mataba la corrida entera por una oferta."""
    assert _entero_o_none(basura) is None


# ── _clean ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entrada, esperado", [
    ("  hola   mundo  ", "hola mundo"),
    ("linea1\n\nlinea2", "linea1 linea2"),
    (None,               ""),
    ("",                 ""),
    ("\t\n  ",           ""),
])
def test_clean(entrada, esperado):
    assert _clean(entrada) == esperado


# ── Respuestas malformadas de las APIs ────────────────────────────────────────

class RespuestaFalsa:
    """Imita lo mínimo de requests.Response que usan los scrapers."""
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class SesionFalsa:
    """Devuelve siempre el mismo payload, sin tocar la red."""
    def __init__(self, payload):
        self._payload = payload

    def get(self, *a, **kw):
        return RespuestaFalsa(self._payload)

    def post(self, *a, **kw):
        return RespuestaFalsa(self._payload)


@pytest.mark.parametrize("payload, caso", [
    ({"error": "rate limited"}, "dict de error donde se espera una lista"),
    ([],                         "lista vacia"),
    ([{"meta": 1}],             "solo metadatos, sin ofertas"),
    ("texto plano",             "texto en vez de JSON estructurado"),
    (None,                       "null"),
])
def test_remoteok_no_revienta_con_respuestas_malformadas(payload, caso):
    """Regresión: un dict de error hacía KeyError y tumbaba TODA la búsqueda."""
    from src.scraper import scrape_remoteok
    assert scrape_remoteok("python", session=SesionFalsa(payload)) == [], caso


@pytest.mark.parametrize("payload, caso", [
    ([1, 2, 3],                   "lista donde se espera un objeto"),
    ({},                           "objeto vacio"),
    ({"results": None},           "results en null"),
    ({"results": ["no-dict"]},    "elementos que no son objetos"),
])
def test_torre_no_revienta_con_respuestas_malformadas(payload, caso):
    from src.scraper import scrape_torre_co
    assert scrape_torre_co("python", session=SesionFalsa(payload)) == [], caso


@pytest.mark.parametrize("payload, caso", [
    ({"jobs": None},   "jobs en null"),
    ({},                "sin la clave jobs"),
    ({"jobs": "texto"}, "jobs no es una lista"),
])
def test_remotive_no_revienta_con_respuestas_malformadas(payload, caso):
    from src.scraper import scrape_remotive
    assert scrape_remotive("python", session=SesionFalsa(payload)) == [], caso


def test_remoteok_tolera_una_oferta_con_campos_en_null():
    """Un title en null chocaba contra el NOT NULL de la tabla."""
    from src.scraper import scrape_remoteok
    payload = [
        {"meta": True},
        {"position": None, "company": None, "salary_min": "negociable",
         "description": None, "url": None, "id": 7},
    ]
    ofertas = scrape_remoteok("python", session=SesionFalsa(payload))
    assert len(ofertas) == 1
    assert ofertas[0].title == "Sin título"
    assert ofertas[0].company == "Empresa no especificada"
    assert ofertas[0].salary is None
    assert ofertas[0].url.endswith("/7")


def test_remoteok_arma_bien_el_salario():
    from src.scraper import scrape_remoteok
    payload = [
        {"meta": True},
        {"position": "Dev", "company": "ACME", "salary_min": 80000,
         "salary_max": 120000, "description": "<p>hola</p>", "url": "http://x/1"},
    ]
    oferta = scrape_remoteok("python", session=SesionFalsa(payload))[0]
    assert oferta.salary == "USD 80,000–120,000/año"
    assert oferta.description == "hola"


def test_torre_tolera_details_en_null():
    """opp.get('details', {}).get(...) fallaba si details venía en null."""
    from src.scraper import scrape_torre_co
    payload = {"results": [{"opportunity": {
        "objective": "Dev", "organizations": None, "compensation": None,
        "details": None, "id": "abc",
    }}]}
    oferta = scrape_torre_co("python", session=SesionFalsa(payload))[0]
    assert oferta.title == "Dev"
    assert oferta.company == "Empresa no especificada"
    assert oferta.description == ""


# ── Scrapers de HTML: que el respaldo de selectores sirva de verdad ───────────

def _parchar_fetch(monkeypatch, html):
    """Hace que _fetch devuelva este HTML en vez de salir a la red."""
    import src.scraper as scraper
    monkeypatch.setattr(scraper, "_fetch", lambda url, session: BeautifulSoup(html, "lxml"))


def test_occ_extrae_una_oferta_normal(monkeypatch):
    from src.scraper import scrape_occ
    html = """
    <article data-id="1">
      <h2>Ingeniero de Datos</h2>
      <span class="company">ACME</span>
      <span class="salary">$40,000</span>
      <p>Buscamos alguien con Python.</p>
      <a href="/empleo/1">Ver</a>
    </article>"""
    _parchar_fetch(monkeypatch, html)
    ofertas = scrape_occ("datos")
    assert len(ofertas) == 1
    o = ofertas[0]
    assert o.title == "Ingeniero de Datos"
    assert o.company == "ACME"
    assert o.salary == "$40,000"
    assert o.url == "https://www.occ.com.mx/empleo/1"


def test_occ_usa_el_selector_de_respaldo_cuando_el_primero_viene_vacio(monkeypatch):
    """Regresión de _first: el portal deja un <h2> vacío y el título va en <h3>.

    Antes se devolvía "" y, como el scraper exige `if title and href`, la oferta
    se descartaba entera. Es justo el caso que los respaldos deberían cubrir.
    """
    from src.scraper import scrape_occ
    html = """
    <article data-id="1">
      <h2>   </h2>
      <h3>Ingeniero de Datos</h3>
      <a href="/empleo/1">Ver</a>
    </article>"""
    _parchar_fetch(monkeypatch, html)
    ofertas = scrape_occ("datos")
    assert len(ofertas) == 1, "la oferta se perdía por un h2 vacío"
    assert ofertas[0].title == "Ingeniero de Datos"


def test_occ_devuelve_vacio_si_el_portal_cambio_el_html(monkeypatch):
    """Sin tarjetas reconocibles no debe reventar: devuelve [] y avisa."""
    from src.scraper import scrape_occ
    _parchar_fetch(monkeypatch, "<div>El portal cambió por completo</div>")
    assert scrape_occ("datos") == []


def test_occ_descarta_tarjetas_sin_enlace(monkeypatch):
    """Una oferta sin URL no sirve: no se puede postular ni deduplicar."""
    from src.scraper import scrape_occ
    html = '<article data-id="1"><h2>Sin enlace</h2></article>'
    _parchar_fetch(monkeypatch, html)
    assert scrape_occ("datos") == []


def test_occ_no_revienta_si_la_peticion_falla(monkeypatch):
    import src.scraper as scraper
    monkeypatch.setattr(scraper, "_fetch", lambda url, session: None)
    assert scraper.scrape_occ("datos") == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
