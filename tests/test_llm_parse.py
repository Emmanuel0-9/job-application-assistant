"""Pruebas de src/llm_parse.py — la capa que convierte texto del modelo en datos.

Es la parte más frágil del proyecto: depende de que un modelo devuelva JSON, y
los modelos se salen del formato de formas conocidas. Cada caso de aquí es una
de esas formas, vista en la práctica.

Correr:  python -m pytest tests/ -v      (o simplemente: python tests/test_llm_parse.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pydantic import BaseModel

from src.llm_parse import (
    FaltaApiKey, RespuestaIAInvalida, _limpiar_cercos,
    crear_cliente, parsear_modelo, texto_de_respuesta,
)


class Analisis(BaseModel):
    """Modelo mínimo para las pruebas."""
    puntaje: int
    resumen: str


# ── _limpiar_cercos: las formas en que un modelo envuelve su respuesta ──────────

@pytest.mark.parametrize("crudo, esperado, caso", [
    ('{"a": 1}',                          '{"a": 1}', "json pelado"),
    ('```json\n{"a": 1}\n```',            '{"a": 1}', "cerco con etiqueta json"),
    ('```\n{"a": 1}\n```',                '{"a": 1}', "cerco sin etiqueta"),
    ('```json{"a": 1}```',                '{"a": 1}', "cerco sin saltos de línea"),
    ('  \n ```json\n{"a": 1}\n``` ',      '{"a": 1}', "espacios alrededor"),
    ('```JSON\n{"a": 1}\n```',            '{"a": 1}', "etiqueta en MAYÚSCULAS"),
    ('```Json\n{"a": 1}\n```',            '{"a": 1}', "etiqueta capitalizada"),
    ('Aquí tienes:\n```json\n{"a": 1}\n```', '{"a": 1}', "preámbulo antes del cerco"),
    ('```json\n{"a": 1}\n```\nEspero que sirva.', '{"a": 1}', "epílogo después del cerco"),
    ('```json\n{"a": 1}',                 '{"a": 1}', "cerco abierto sin cerrar"),
    ('Claro: {"a": 1}',                   '{"a": 1}', "preámbulo sin cerco"),
])
def test_limpiar_cercos(crudo, esperado, caso):
    assert _limpiar_cercos(crudo) == esperado, f"falló el caso: {caso}"


# ── parsear_modelo: camino feliz ───────────────────────────────────────────────

def test_parsea_json_valido():
    obj = parsear_modelo('{"puntaje": 85, "resumen": "buen encaje"}', Analisis)
    assert obj.puntaje == 85
    assert obj.resumen == "buen encaje"


def test_parsea_con_cercos_y_preambulo():
    crudo = 'Aquí está el análisis:\n```json\n{"puntaje": 70, "resumen": "regular"}\n```'
    obj = parsear_modelo(crudo, Analisis)
    assert obj.puntaje == 70


def test_puntaje_cero_es_valido():
    """Un puntaje de 0 es un dato real, no un 'sin resultado'."""
    obj = parsear_modelo('{"puntaje": 0, "resumen": "no aplica"}', Analisis)
    assert obj.puntaje == 0


# ── parsear_modelo: falla de forma clara, no revienta ──────────────────────────

def test_texto_que_no_es_json_lanza_error_claro():
    with pytest.raises(RespuestaIAInvalida) as exc:
        parsear_modelo("Lo siento, no puedo ayudarte con eso.", Analisis)
    assert "JSON" in str(exc.value)


def test_json_sin_los_campos_del_esquema():
    with pytest.raises(RespuestaIAInvalida) as exc:
        parsear_modelo('{"otra_cosa": 1}', Analisis)
    assert "esquema" in str(exc.value).lower()


def test_json_con_tipo_equivocado():
    with pytest.raises(RespuestaIAInvalida):
        parsear_modelo('{"puntaje": "ochenta", "resumen": "x"}', Analisis)


def test_respuesta_vacia():
    with pytest.raises(RespuestaIAInvalida):
        parsear_modelo("", Analisis)


def test_el_error_incluye_una_muestra_del_texto():
    """El mensaje debe mostrar qué devolvió el modelo, para poder depurarlo."""
    with pytest.raises(RespuestaIAInvalida) as exc:
        parsear_modelo("respuesta rarísima del modelo", Analisis)
    assert "rarísima" in str(exc.value)


# ── texto_de_respuesta: no asumir la forma de la respuesta de la API ──────────

class Bloque:
    def __init__(self, texto=None, tipo="text"):
        if texto is not None:
            self.text = texto
        self.type = tipo


class Respuesta:
    def __init__(self, bloques):
        self.content = bloques


def test_texto_de_respuesta_caso_normal():
    assert texto_de_respuesta(Respuesta([Bloque("hola")])) == "hola"


def test_texto_de_respuesta_junta_varios_bloques():
    r = Respuesta([Bloque("primero"), Bloque("segundo")])
    assert texto_de_respuesta(r) == "primero\nsegundo"


def test_texto_de_respuesta_ignora_bloques_que_no_son_texto():
    """Un modelo puede devolver un bloque de razonamiento antes del texto."""
    r = Respuesta([Bloque(None, tipo="thinking"), Bloque("la respuesta")])
    assert texto_de_respuesta(r) == "la respuesta"


@pytest.mark.parametrize("respuesta, caso", [
    (Respuesta([]),                       "sin bloques (antes: IndexError)"),
    (Respuesta(None),                     "content en None"),
    (Respuesta([Bloque(None, "tool_use")]), "solo un bloque sin texto"),
    (Respuesta([Bloque("")]),             "bloque de texto vacio"),
])
def test_texto_de_respuesta_falla_claro_en_vez_de_reventar(respuesta, caso):
    """Regresión: response.content[0].text daba IndexError o AttributeError."""
    with pytest.raises(RespuestaIAInvalida):
        texto_de_respuesta(respuesta)
    assert caso  # documenta el caso en el nombre del parámetro


# ── crear_cliente: avisar qué falta, no reventar con un error del SDK ─────────

def test_crear_cliente_sin_clave_explica_que_hacer(monkeypatch):
    import config
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
    with pytest.raises(FaltaApiKey) as exc:
        crear_cliente()
    mensaje = str(exc.value)
    assert "ANTHROPIC_API_KEY" in mensaje
    assert ".env" in mensaje, "el mensaje debe decir cómo arreglarlo"


def test_crear_cliente_con_clave_devuelve_un_cliente(monkeypatch):
    import config
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "sk-ant-clave-de-prueba")
    cliente = crear_cliente()
    assert hasattr(cliente, "messages"), "debe ser un cliente de Anthropic utilizable"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
